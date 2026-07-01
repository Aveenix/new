import html
import logging
import re

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


def wc_unescape(value):
    """Decode HTML entities WooCommerce returns in names (&amp; &#038; ...)."""
    if not value:
        return value
    return html.unescape(value)


def clean_wc_description(html: str) -> str:
    """Strip junk from a scraped WooCommerce/Amazon product description:
    <script>/<style> blocks, leaked Amazon tracking JS, and noise lines like
    'Best Sellers Rank', 'ASIN', 'Product summary shift+alt+...'.
    Returns tidy HTML safe to show on the website.
    """
    if not html:
        return ""
    text = html

    # 0) Amazon A+ ships each image twice: a real <img> plus a lazy placeholder
    #    (<img src="...grey-pixel.gif" data-src="..." class="a-lazy-loaded">).
    #    The real img already shows, so drop the placeholder to avoid duplicates
    #    / empty grey boxes.
    text = re.sub(
        r'(?is)<img\b(?=[^>]*\b(?:data-src|grey-pixel|a-lazy-loaded)\b)[^>]*?/?>',
        "", text,
    )

    # 1) Remove script/style/noscript blocks entirely.
    text = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", "", text)

    # 2) Remove leaked inline JS blobs (Amazon click-tracking) that arrive as
    #    plain text, e.g. "var dpAcrHasRegistered... });".
    text = re.sub(r"(?is)\bvar\s+dpAcr[^<]*?\}\)\s*;?", "", text)
    text = re.sub(r"(?is)(P\.when|ue\.count|execute\(function)[^<]*?\}\)\s*;?", "", text)

    # 3) Drop known Amazon noise lines/labels.
    noise_patterns = [
        r"(?im)^\s*Best Sellers Rank.*$",
        r"(?im)^\s*Customer Reviews?:.*$",
        r"(?im)^\s*ASIN\s*[:：].*$",
        r"(?im)^\s*Date First Available.*$",
        r"(?im)^\s*Department\s*[:：].*$",
        r"(?im)^\s*Product Warranty.*$",
        r"(?im)^\s*Product summary.*$",
        r"(?im)^\s*shift\s*\+\s*alt\s*\+\s*\w+\s*$",
        r"(?im)click here",
    ]
    for pat in noise_patterns:
        text = re.sub(pat, "", text)

    # 4) Collapse excess blank lines / spaces.
    text = re.sub(r"(?:\s*<br\s*/?>\s*){3,}", "<br/><br/>", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

PRODUCT_STATUS = [
    ("draft", "Draft"),
    ("pending", "Pending Review"),
    ("private", "Private"),
    ("publish", "Published"),
]

STOCK_STATUS = [
    ("instock", "In Stock"),
    ("outofstock", "Out of Stock"),
    ("onbackorder", "On Backorder"),
]

class WooProduct(models.Model):

    _name = "wc.product.link"
    _description = "WooCommerce Product"
    _inherit = "wc.binding"
    _inherits = {"product.product": "product_id"}
    _rec_name = "name"

    product_id = fields.Many2one(
        comodel_name="product.product",
        string="Odoo Product Variant",
        required=True,
        ondelete="cascade",
    )
    wc_product_name = fields.Char(string="Name on Store")
    wc_status = fields.Selection(PRODUCT_STATUS, string="Store Status", default="publish")
    wc_stock_status = fields.Selection(STOCK_STATUS, string="Stock Status", default="instock")
    wc_manage_stock = fields.Boolean(string="Store Manages Stock")
    wc_stock_qty = fields.Float(
        string="Synced Qty",
        help="Last stock quantity pushed to WooCommerce.",
    )
    wc_regular_price = fields.Char(string="Regular Price")
    wc_sale_price = fields.Char(string="Sale Price")
    wc_sku = fields.Char(string="SKU on Store")
    wc_weight = fields.Char(string="Weight")
    wc_category_ids = fields.Many2many(
        comodel_name="wc.category.link",
        string="WooCommerce Categories",
    )
    wc_tag_ids = fields.Many2many(
        comodel_name="wc.tag",
        string="WooCommerce Tags",
    )
    wc_image_urls = fields.Text(
        string="Image URLs",
        help="Comma-separated image URLs from WooCommerce.",
    )
    is_variation = fields.Boolean(
        string="Is Variation",
        help="Set when this product is a variation of a variable product.",
    )
    wc_product_type = fields.Char(
        string="WooCommerce Type",
        help="Raw product type from WooCommerce (simple, external, variable, ...).",
    )
    wc_affiliate_url = fields.Char(
        string="Affiliate Link",
        help="External/affiliate product link pulled from WooCommerce meta_data.",
    )
    wc_template_id = fields.Many2one(
        comodel_name="wc.template.link",
        string="Parent Template",
        ondelete="set null",
    )

    _sql_constraints = [
        (
            "wc_product_link_unique",
            "unique(backend_id, external_id)",
            "A WooCommerce product with this ID already exists for this store.",
        )
    ]

    def push_to_store(self):
        from ..components.exporter import WooProductExporter
        exporter = WooProductExporter()

        def _op(binding):
            if binding.wc_manage_stock:
                qty = binding._get_computed_stock()
                binding.with_context(syncing_from_wc=True).write({"wc_stock_qty": qty})
            exporter.run(binding.backend_id, binding)
            binding.mark_synced("Product pushed to WooCommerce.")

        return self._run_with_notification(_op, title="Push Complete")

    def push_stock_to_store(self):
        from ..components.exporter import WooStockExporter
        exporter = WooStockExporter()

        def _op(binding):
            qty = binding._get_computed_stock()
            binding.with_context(syncing_from_wc=True).write({"wc_stock_qty": qty})
            exporter.run(binding.backend_id, binding)
            binding.mark_synced("Stock pushed to WooCommerce.")

        return self.filtered("external_id")._run_with_notification(_op, title="Push Stock Complete")

    def _get_computed_stock(self):
        backend = self.backend_id
        warehouses = backend.stock_warehouse_ids
        if not warehouses:
            return self.product_id.qty_available
        total = 0.0
        for wh in warehouses:
            total += self.product_id.with_context(warehouse=wh.id).qty_available
        return total

    @api.model
    def syncing_from_wc(self, backend, records: list, force: bool = False):
        results = {"created": 0, "updated": 0, "skipped": 0, "failed": 0, "errors": []}
        for record in records:
            ext_id = str(record.get("id", ""))
            if not ext_id:
                continue
            try:
                binding, status = self._sync_one(backend, record, force)
                results[status] += 1
            except Exception as exc:
                _logger.exception("Failed syncing WooCommerce product %s: %s", ext_id, exc)
                results["failed"] += 1
                results["errors"].append("Product %s: %s" % (ext_id, exc))
        return results

    @staticmethod
    def _get_meta(record: dict, key: str, default=""):
        for meta in record.get("meta_data", []):
            if meta.get("key") == key:
                val = meta.get("value")
                return val if val not in (None, False) else default
        return default

    @staticmethod
    def _collect_image_urls(record: dict, dropship: bool = False) -> list:
        """Return the product image URL(s).

        Affiliate/simple products store the URL in the 'fifu_image_url' meta key
        (may itself be a comma/newline separated list). Dropship products (CJ)
        don't use FIFU — their images live in the WC native 'images' array, so
        for those we read 'images[*].src'.
        """
        urls = []
        value = WooProduct._get_meta(record, "fifu_image_url")
        if value:
            for part in str(value).replace("\n", ",").split(","):
                u = part.strip()
                if u.startswith("http") and u not in urls:
                    urls.append(u)
        # Dropship (or any product) with no FIFU URL -> fall back to native images.
        if dropship or not urls:
            for img in record.get("images") or []:
                src = (img.get("src") or "").strip() if isinstance(img, dict) else ""
                if src.startswith("http") and src not in urls:
                    urls.append(src)
        return urls

    def _sync_one(self, backend, record: dict, force: bool = False):
        from datetime import datetime
        ext_id = str(record["id"])
        wc_type_raw = (record.get("type") or "simple").strip()

        # WC API sometimes returns variations even when ?type=simple|external is
        # requested. If already inside a _sync_variations call (context flag set),
        # process normally. Otherwise fetch the parent and delegate — which will
        # call _sync_variations and create all variants including this one.
        if wc_type_raw == "variation" or record.get("parent_id"):
            if self.env.context.get('wc_syncing_variations'):
                # Called from _sync_variations — process normally, no redirect.
                pass
            else:
                parent_id = record.get("parent_id")
                if parent_id:
                    _logger.info(
                        "[WC Product] id=%s is a variation of parent %s — "
                        "delegating to variable product sync.",
                        ext_id, parent_id,
                    )
                    try:
                        client = backend.get_api_client()
                        parent_result = client.get("products/%s" % parent_id)
                        parent_data = parent_result.get("data", {})
                        if parent_data:
                            self.env["wc.template.link"].syncing_from_wc(
                                backend, [parent_data], force=force
                            )
                    except Exception as exc:
                        _logger.warning(
                            "[WC Product] Failed fetching parent %s for variation %s: %s",
                            parent_id, ext_id, exc,
                        )
                else:
                    _logger.info(
                        "[WC Product] Skipping variation id=%s — no parent_id in record.",
                        ext_id,
                    )
                return None, "skipped"

        _logger.info(
            "[WC Product] Syncing id=%s name=%r type=%r",
            ext_id,
            (record.get("name") or "").strip(),
            wc_type_raw,
        )

        existing = self.search([
            ("backend_id", "=", backend.id),
            ("external_id", "=", ext_id),
        ], limit=1)

        sku = (record.get("sku") or "").strip()

        if not sku and not backend.allow_products_without_sku and not force:
            _logger.debug(
                "Skipping WooCommerce product %s — no SKU and 'allow_products_without_sku' is off.",
                ext_id,
            )
            return None, "skipped"

        name = wc_unescape((record.get("name") or "").strip()) or "WooCommerce Product %s" % ext_id
        product_type = backend.default_product_type or "consu"

        regular_price_raw = record.get("regular_price") or record.get("price") or ""
        try:
            list_price = float(regular_price_raw) if regular_price_raw else 0.0
        except (ValueError, TypeError):
            list_price = 0.0

        weight_raw = record.get("weight") or ""
        try:
            weight = float(weight_raw) if weight_raw else 0.0
        except (ValueError, TypeError):
            weight = 0.0

        stock_qty_raw = record.get("stock_quantity")
        try:
            stock_qty = float(stock_qty_raw) if stock_qty_raw is not None else 0.0
        except (ValueError, TypeError):
            stock_qty = 0.0

        wc_type = (record.get("type") or "simple").strip()
        is_affiliate = wc_type in ("external", "affiliate")
        affiliate_url = ""
        if is_affiliate:
            affiliate_url = (
                self._get_meta(record, "original_link")
                or (record.get("external_url") or "")
            )

        # Dropshipping: SKU starting with "CJ" (e.g. CJ supplier products).
        is_dropship = bool(sku) and sku.upper().startswith("CJ")

        wc_cat_records = record.get("categories", [])
        wc_tag_records = record.get("tags", [])
        cat_ids = self._resolve_categories(backend, wc_cat_records)
        tag_ids = self._resolve_tags(backend, wc_tag_records)
        public_categ_ids = self._resolve_public_categories(backend, wc_cat_records)
        internal_categ = self._resolve_internal_category(backend, wc_cat_records)
        product_tag_ids = self._resolve_product_tags(backend, wc_tag_records)

        image_list = self._collect_image_urls(record, dropship=is_dropship)
        images = ",".join(image_list)

        vals = {
            "wc_product_name": name,
            "wc_status": record.get("status", "publish"),
            "wc_stock_status": record.get("stock_status", "instock"),
            "wc_manage_stock": bool(record.get("manage_stock", False)),
            "wc_stock_qty": stock_qty,
            "wc_regular_price": regular_price_raw,
            "wc_sale_price": record.get("sale_price", ""),
            "wc_sku": sku,
            "wc_weight": weight_raw,
            "wc_image_urls": images,
            "wc_category_ids": [(6, 0, cat_ids)],
            "wc_tag_ids": [(6, 0, tag_ids)],
            "wc_product_type": wc_type,
            "wc_affiliate_url": affiliate_url,
            "backend_id": backend.id,
            "external_id": ext_id,
            "sync_date": datetime.now(),
        }

        tmpl_vals = {
            "name": name,
            "list_price": list_price,
            "weight": weight,
        }
        Tmpl = self.env["product.template"]
        # Link both the internal product category and the eCommerce category.
        if internal_categ:
            tmpl_vals["categ_id"] = internal_categ.id
        if public_categ_ids and "public_categ_ids" in Tmpl._fields:
            tmpl_vals["public_categ_ids"] = [(6, 0, public_categ_ids)]
        if product_tag_ids and "product_tag_ids" in Tmpl._fields:
            tmpl_vals["product_tag_ids"] = [(6, 0, product_tag_ids)]
        if "external_image_urls" in Tmpl._fields:
            tmpl_vals["external_image_urls"] = images
        # WC native description -> website product description (cleaned).
        wc_description = clean_wc_description(record.get("description") or "")
        if "description_ecommerce" in Tmpl._fields:
            tmpl_vals["description_ecommerce"] = wc_description
        has_affiliate_url_field = "affiliate_url" in Tmpl._fields
        if is_affiliate:
            tmpl_vals["aveenix_product_type"] = "affiliate"
            if has_affiliate_url_field:
                tmpl_vals["affiliate_url"] = affiliate_url
        elif is_dropship:
            tmpl_vals["aveenix_product_type"] = "dropship"

        if existing:
            if not force and self._is_up_to_date(existing, record):
                return existing, "skipped"
            existing.product_id.with_context(syncing_from_wc=True).write(dict(
                tmpl_vals,
                default_code=sku or existing.product_id.default_code,
            ))
            existing.with_context(syncing_from_wc=True).write(vals)
            return existing, "updated"

        odoo_product = None
        if sku and backend.match_product_by_sku:
            odoo_product = self.env["product.product"].search(
                [("default_code", "=", sku)], limit=1
            )
            if odoo_product:
                _logger.info(
                    "Matched WooCommerce product %s to existing Odoo product %s by SKU '%s'",
                    ext_id, odoo_product.id, sku,
                )

        is_var = record.get("parent_id") or record.get("is_variation") or False
        if not odoo_product and not is_var:
            odoo_product = self.env["product.product"].search(
                [("name", "=", name)], limit=1
            )
            if odoo_product:
                _logger.info(
                    "Matched WooCommerce product %s to existing Odoo product %s by Name '%s'",
                    ext_id, odoo_product.id, name,
                )

        if not odoo_product:
            categ_id = (
                internal_categ.id if internal_categ
                else backend.default_category_id.id
                if backend.default_category_id
                else self.env.ref("product.product_category_goods").id
            )
            matched_variant_id = self.env.context.get('wc_matched_variant_id')
            parent_tmpl_id = self.env.context.get('wc_parent_tmpl_id')
            if matched_variant_id:
                # _sync_variations pre-matched this WC variation to the correct
                # Odoo variant via attribute values — use it directly.
                odoo_product = self.env["product.product"].browse(matched_variant_id)
                _logger.info(
                    "[WC Variation] Using attribute-matched variant %s for WC variation id=%s",
                    odoo_product.id, ext_id,
                )
                write_vals = {}
                if sku:
                    write_vals["default_code"] = sku
                if list_price:
                    write_vals["lst_price"] = list_price
                if weight:
                    write_vals["weight"] = weight
                if write_vals:
                    odoo_product.with_context(syncing_from_wc=True).write(write_vals)
            elif parent_tmpl_id:
                # Fallback: attribute matching failed (no structured attributes).
                # Reuse an unbound variant from the parent template.
                parent_tmpl = self.env["product.template"].browse(parent_tmpl_id)
                bound_product_ids = self.env["wc.product.link"].search(
                    [("product_id.product_tmpl_id", "=", parent_tmpl_id)]
                ).mapped("product_id.id")
                unbound = parent_tmpl.product_variant_ids.filtered(
                    lambda v: v.id not in bound_product_ids
                )
                odoo_product = unbound[:1] or parent_tmpl.product_variant_ids[:1]
                if odoo_product:
                    _logger.info(
                        "[WC Variation] Reusing variant %s (tmpl=%s) for WC variation id=%s",
                        odoo_product.id, parent_tmpl_id, ext_id,
                    )
                    write_vals = {}
                    if sku:
                        write_vals["default_code"] = sku
                    if list_price:
                        write_vals["lst_price"] = list_price
                    if weight:
                        write_vals["weight"] = weight
                    if write_vals:
                        odoo_product.with_context(syncing_from_wc=True).write(write_vals)
                else:
                    _logger.warning(
                        "[WC Variation] Parent template %s has no variants — skipping variation id=%s",
                        parent_tmpl_id, ext_id,
                    )
                    return None, "skipped"
            else:
                product_vals = {
                    "name": name,
                    "default_code": sku,
                    "type": product_type,
                    "categ_id": categ_id,
                    "list_price": list_price,
                    "weight": weight,
                    "sale_ok": True,
                    "purchase_ok": True,
                }
                odoo_product = self.env["product.product"].with_context(
                    syncing_from_wc=True
                ).create(product_vals)

        tmpl_extra = {}
        if is_affiliate:
            tmpl_extra["aveenix_product_type"] = "affiliate"
            if has_affiliate_url_field:
                tmpl_extra["affiliate_url"] = affiliate_url
        elif is_dropship:
            tmpl_extra["aveenix_product_type"] = "dropship"
        if "external_image_urls" in Tmpl._fields:
            tmpl_extra["external_image_urls"] = images
        if "description_ecommerce" in Tmpl._fields:
            tmpl_extra["description_ecommerce"] = wc_description
        if internal_categ:
            tmpl_extra["categ_id"] = internal_categ.id
        if public_categ_ids and "public_categ_ids" in Tmpl._fields:
            tmpl_extra["public_categ_ids"] = [(6, 0, public_categ_ids)]
        if product_tag_ids and "product_tag_ids" in Tmpl._fields:
            tmpl_extra["product_tag_ids"] = [(6, 0, product_tag_ids)]
        if tmpl_extra:
            odoo_product.product_tmpl_id.with_context(
                syncing_from_wc=True).write(tmpl_extra)

        vals["product_id"] = odoo_product.id
        binding = self.with_context(syncing_from_wc=True).create(vals)
        _logger.info(
            "Created wc.product.link %s for WooCommerce product %s (%s)",
            binding.id, ext_id, name,
        )
        return binding, "created"

    def _resolve_categories(self, backend, cat_list: list) -> list:
        ids = []
        for cat in cat_list:
            wc_cat = self.env["wc.category.link"].search([
                ("backend_id", "=", backend.id),
                ("external_id", "=", str(cat.get("id", ""))),
            ], limit=1)
            if wc_cat:
                ids.append(wc_cat.id)
        return ids

    def _resolve_public_categories(self, backend, cat_list: list) -> list:
        """Return product.public.category ids for a product's WC categories."""
        ids = []
        for cat in cat_list:
            wc_cat = self.env["wc.category.link"].search([
                ("backend_id", "=", backend.id),
                ("external_id", "=", str(cat.get("id", ""))),
            ], limit=1)
            if wc_cat and wc_cat.public_categ_id:
                ids.append(wc_cat.public_categ_id.id)
        return ids

    def _resolve_internal_category(self, backend, cat_list: list):
        """Return the first matching internal product.category (for categ_id)."""
        for cat in cat_list:
            wc_cat = self.env["wc.category.link"].search([
                ("backend_id", "=", backend.id),
                ("external_id", "=", str(cat.get("id", ""))),
            ], limit=1)
            if wc_cat and wc_cat.category_id:
                return wc_cat.category_id
        return False

    def _resolve_tags(self, backend, tag_list: list) -> list:
        ids = []
        for tag in tag_list:
            wc_tag = self.env["wc.tag"].search([
                ("backend_id", "=", backend.id),
                ("external_id", "=", str(tag.get("id", ""))),
            ], limit=1)
            if wc_tag:
                ids.append(wc_tag.id)
        return ids

    def _resolve_product_tags(self, backend, tag_list: list) -> list:
        """Return native product.tag ids for a product's WC tags."""
        ids = []
        for tag in tag_list:
            wc_tag = self.env["wc.tag"].search([
                ("backend_id", "=", backend.id),
                ("external_id", "=", str(tag.get("id", ""))),
            ], limit=1)
            if wc_tag and wc_tag.product_tag_id:
                ids.append(wc_tag.product_tag_id.id)
        return ids

    def _is_up_to_date(self, binding, remote_record: dict) -> bool:
        if not binding.sync_date:
            return False
        modified_str = (
            remote_record.get("date_modified_gmt")
            or remote_record.get("date_modified")
        )
        if not modified_str:
            return False
        from datetime import datetime
        try:
            remote_dt = datetime.strptime(modified_str, "%Y-%m-%dT%H:%M:%S")
            return binding.sync_date >= remote_dt
        except ValueError:
            return False

    def pull_from_store(self):
        def _op(binding):
            client = binding.backend_id.get_api_client()
            if binding.is_variation and binding.wc_template_id and binding.wc_template_id.external_id:
                result = client.get(
                    "products/%s/variations/%s" % (
                        binding.wc_template_id.external_id,
                        binding.external_id,
                    )
                )
            else:
                result = client.get("products/%s" % binding.external_id)
            data = result.get("data", {})
            if data:
                self.syncing_from_wc(binding.backend_id, [data], force=True)
                binding.mark_synced("Product pulled from WooCommerce.")

        return self.filtered("external_id")._run_with_notification(_op, title="Pull Complete")

    @api.model
    def get_or_create_for_order_line(self, backend, item: dict):
        var_id = item.get("variation_id", 0)
        prod_id = item.get("product_id", 0)
        ext_id = str(var_id) if var_id else str(prod_id) if prod_id else ""

        if ext_id and ext_id != "0":
            binding = self.search([
                ("backend_id", "=", backend.id),
                ("external_id", "=", ext_id),
            ], limit=1)
            if binding and binding.product_id:
                return binding.product_id

            client = backend.get_api_client()
            try:
                if var_id and prod_id:
                    parent_result = client.get("products/%s" % prod_id)
                    parent_data = parent_result.get("data", {})
                    if parent_data:
                        self.env["wc.template.link"].syncing_from_wc(
                            backend, [parent_data], force=True
                        )
                    binding = self.search([
                        ("backend_id", "=", backend.id),
                        ("external_id", "=", ext_id),
                    ], limit=1)
                    if binding and binding.product_id:
                        return binding.product_id

                    var_result = client.get("products/%s/variations/%s" % (prod_id, var_id))
                    var_data = var_result.get("data", {})
                    if var_data:
                        if not var_data.get("name") and parent_data.get("name"):
                            attr_parts = [
                                a.get("option", "")
                                for a in var_data.get("attributes", [])
                                if a.get("option")
                            ]
                            var_data["name"] = parent_data["name"]
                            if attr_parts:
                                var_data["name"] += " - " + ", ".join(attr_parts)
                        binding = self._sync_one(backend, var_data, force=True)
                        if binding and binding.product_id:
                            binding.with_context(syncing_from_wc=True).write({"is_variation": True})
                            return binding.product_id

                elif prod_id:
                    result = client.get("products/%s" % prod_id)
                    data = result.get("data", {})
                    if data:
                        binding = self._sync_one(backend, data, force=True)
                        if binding and binding.product_id:
                            return binding.product_id

            except Exception as exc:
                _logger.warning(
                    "Could not fetch WooCommerce product (prod_id=%s, var_id=%s): %s",
                    prod_id, var_id, exc,
                )

        sku = (item.get("sku") or "").strip()
        if sku:
            product = self.env["product.product"].search(
                [("default_code", "=", sku)], limit=1
            )
            if product:
                return product

        item_name = wc_unescape((item.get("name") or "").strip()) or "WooCommerce Product"
        _logger.warning(
            "Creating fallback Odoo product for WooCommerce item '%s' (ext_id=%s, sku=%s)",
            item_name, ext_id, sku,
        )
        categ_id = (
            backend.default_category_id.id
            if backend.default_category_id
            else self.env.ref("product.product_category_goods").id
        )
        new_product = self.env["product.product"].with_context(
            syncing_from_wc=True
        ).create({
            "name": item_name,
            "default_code": sku or False,
            "type": backend.default_product_type or "consu",
            "categ_id": categ_id,
            "list_price": self._safe_float(
                item.get("price") or item.get("subtotal_tax") or 0
            ),
            "sale_ok": True,
            "purchase_ok": True,
        })

        if ext_id and ext_id != "0":
            try:
                self.with_context(syncing_from_wc=True).create({
                    "product_id": new_product.id,
                    "backend_id": backend.id,
                    "external_id": ext_id,
                    "wc_product_name": item_name,
                    "wc_sku": sku,
                })
            except Exception:
                pass

        return new_product

    @staticmethod
    def _safe_float(val, default=0.0):
        try:
            return float(val) if val not in (None, "", False) else default
        except (ValueError, TypeError):
            return default

class ProductProductWoo(models.Model):
    _inherit = "product.product"

    wc_bind_ids = fields.One2many(
        comodel_name="wc.product.link",
        inverse_name="product_id",
        string="WooCommerce Bindings",
        copy=False,
    )

    def action_push_stock_to_store(self):
        self.mapped("wc_bind_ids").push_stock_to_store()

    def action_push_product_to_store(self):
        backends = self.env["wc.store"].search([("active", "=", True)])
        if not backends:
            raise UserError("No active WooCommerce stores found.")

        for product in self:
            for backend in backends:
                binding = self.env["wc.product.link"].search([
                    ("product_id", "=", product.id),
                    ("backend_id", "=", backend.id),
                ], limit=1)

                if not binding:
                    binding = self.env["wc.product.link"].with_context(
                        syncing_from_wc=True
                    ).create({
                        "product_id": product.id,
                        "backend_id": backend.id,
                        "wc_product_name": product.name,
                        "wc_sku": product.default_code or "",
                        "wc_regular_price": str(product.list_price),
                        "wc_manage_stock": True,
                    })

                binding.push_to_store()

class WooProductTemplate(models.Model):

    _name = "wc.template.link"
    _description = "WooCommerce Variable Product"
    _inherit = "wc.binding"
    _inherits = {"product.template": "template_id"}
    _rec_name = "name"

    template_id = fields.Many2one(
        comodel_name="product.template",
        string="Odoo Product Template",
        required=True,
        ondelete="cascade",
    )
    wc_product_name = fields.Char(string="Name on Store")
    wc_status = fields.Selection(PRODUCT_STATUS, string="Store Status", default="publish")
    wc_sku = fields.Char(string="Template SKU")
    wc_regular_price = fields.Char(string="Regular Price")
    wc_variation_ids = fields.One2many(
        comodel_name="wc.product.link",
        inverse_name="wc_template_id",
        string="Variations",
        copy=False,
    )
    wc_category_ids = fields.Many2many(
        comodel_name="wc.category.link",
        string="WooCommerce Categories",
    )
    wc_tag_ids = fields.Many2many(
        comodel_name="wc.tag",
        string="WooCommerce Tags",
    )
    wc_image_urls = fields.Text(string="Image URLs")

    _sql_constraints = [
        (
            "wc_template_link_unique",
            "unique(backend_id, external_id)",
            "A WooCommerce variable product with this ID already exists for this store.",
        )
    ]

    @api.model
    def syncing_from_wc(self, backend, records: list, force: bool = False):
        results = {"created": 0, "updated": 0, "skipped": 0, "failed": 0, "errors": []}
        for record in records:
            ext_id = str(record.get("id", ""))
            if not ext_id:
                continue
            try:
                binding, status = self._sync_one(backend, record, force, results)
                results[status] += 1
            except Exception as exc:
                _logger.exception("Failed syncing variable product %s: %s", ext_id, exc)
                results["failed"] += 1
                results["errors"].append("Variable Product %s: %s" % (ext_id, exc))
        return results

    def _sync_one(self, backend, record: dict, force: bool = False, results=None):
        from datetime import datetime
        ext_id = str(record["id"])
        existing = self.search([
            ("backend_id", "=", backend.id),
            ("external_id", "=", ext_id),
        ], limit=1)

        name = wc_unescape((record.get("name") or "").strip()) or "WooCommerce Variable Product %s" % ext_id
        WcProduct = self.env["wc.product.link"]
        wc_cat_records = record.get("categories", [])
        wc_tag_records = record.get("tags", [])
        cat_ids = WcProduct._resolve_categories(backend, wc_cat_records)
        tag_ids = WcProduct._resolve_tags(backend, wc_tag_records)
        public_categ_ids = WcProduct._resolve_public_categories(backend, wc_cat_records)
        internal_categ = WcProduct._resolve_internal_category(backend, wc_cat_records)
        product_tag_ids = WcProduct._resolve_product_tags(backend, wc_tag_records)

        regular_price_raw = record.get("regular_price") or record.get("price") or ""
        try:
            list_price = float(regular_price_raw) if regular_price_raw else 0.0
        except (ValueError, TypeError):
            list_price = 0.0

        sku = (record.get("sku") or "").strip()
        is_dropship = bool(sku) and sku.upper().startswith("CJ")
        images = ",".join(WcProduct._collect_image_urls(record, dropship=is_dropship))
        wc_description = clean_wc_description(record.get("description") or "")
        has_desc_field = "description_ecommerce" in self.env["product.template"]._fields

        vals = {
            "wc_product_name": name,
            "wc_status": record.get("status", "publish"),
            "wc_sku": record.get("sku", ""),
            "wc_regular_price": regular_price_raw,
            "wc_image_urls": images,
            "wc_category_ids": [(6, 0, cat_ids)],
            "wc_tag_ids": [(6, 0, tag_ids)],
            "backend_id": backend.id,
            "external_id": ext_id,
            "sync_date": datetime.now(),
        }

        if existing:
            if not force:
                self._sync_variations(backend, existing, record, force, results)
                return existing, "skipped"
            tmpl_write = {"name": name, "list_price": list_price}
            if is_dropship:
                tmpl_write["aveenix_product_type"] = "dropship"
            if "external_image_urls" in self.env["product.template"]._fields:
                tmpl_write["external_image_urls"] = images
            if has_desc_field:
                tmpl_write["description_ecommerce"] = wc_description
            if internal_categ:
                tmpl_write["categ_id"] = internal_categ.id
            if public_categ_ids and "public_categ_ids" in self.env["product.template"]._fields:
                tmpl_write["public_categ_ids"] = [(6, 0, public_categ_ids)]
            if product_tag_ids and "product_tag_ids" in self.env["product.template"]._fields:
                tmpl_write["product_tag_ids"] = [(6, 0, product_tag_ids)]
            existing.template_id.with_context(syncing_from_wc=True).write(tmpl_write)
            existing.with_context(syncing_from_wc=True).write(vals)
            self._sync_variations(backend, existing, record, force, results)
            return existing, "updated"

        odoo_tmpl = None
        tmpl_sku = (record.get("sku") or "").strip()
        if tmpl_sku and backend.match_product_by_sku:
            odoo_tmpl = self.env["product.template"].search(
                [("default_code", "=", tmpl_sku)], limit=1
            )
            if odoo_tmpl:
                _logger.info(
                    "Matched WooCommerce variable template %s to existing Odoo template %s by SKU '%s'",
                    ext_id, odoo_tmpl.id, tmpl_sku,
                )
        if not odoo_tmpl:
            odoo_tmpl = self.env["product.template"].search(
                [("name", "=", name)], limit=1
            )
            if odoo_tmpl:
                _logger.info(
                    "Matched WooCommerce variable template %s to existing Odoo template %s by Name '%s'",
                    ext_id, odoo_tmpl.id, name,
                )

        if odoo_tmpl:
            odoo_tmpl.with_context(syncing_from_wc=True).write({
                "name": name,
                "list_price": list_price,
                "default_code": tmpl_sku or odoo_tmpl.default_code,
            })
        else:
            categ_id = (
                internal_categ.id if internal_categ
                else backend.default_category_id.id
                if backend.default_category_id
                else self.env.ref("product.product_category_goods").id
            )
            odoo_tmpl = self.env["product.template"].with_context(
                syncing_from_wc=True
            ).create({
                "name": name,
                "type": backend.default_product_type or "consu",
                "categ_id": categ_id,
                "list_price": list_price,
                "sale_ok": True,
                "default_code": tmpl_sku or False,
            })

        tmpl_extra = {}
        if is_dropship:
            tmpl_extra["aveenix_product_type"] = "dropship"
        if "external_image_urls" in self.env["product.template"]._fields:
            tmpl_extra["external_image_urls"] = images
        if has_desc_field:
            tmpl_extra["description_ecommerce"] = wc_description
        if internal_categ:
            tmpl_extra["categ_id"] = internal_categ.id
        if public_categ_ids and "public_categ_ids" in self.env["product.template"]._fields:
            tmpl_extra["public_categ_ids"] = [(6, 0, public_categ_ids)]
        if product_tag_ids and "product_tag_ids" in self.env["product.template"]._fields:
            tmpl_extra["product_tag_ids"] = [(6, 0, product_tag_ids)]
        if tmpl_extra:
            odoo_tmpl.with_context(syncing_from_wc=True).write(tmpl_extra)

        vals["template_id"] = odoo_tmpl.id
        vals["name"] = name
        tmpl_binding = self.with_context(syncing_from_wc=True).create(vals)
        _logger.info(
            "Created wc.template.link %s for variable product %s (%s)",
            tmpl_binding.id, ext_id, name,
        )
        self._sync_variations(backend, tmpl_binding, record, force, results)
        return tmpl_binding, "created"

    def _ensure_attribute_lines(self, odoo_tmpl, var_records):
        """Create/update product.template.attribute.line from WC variation attributes.

        Collects all (attr_name → set of values) across every variation, then
        writes attribute_line_ids so Odoo generates the right variant combination
        matrix.  Returns a mapping:
            { frozenset({(attr_name, value), ...}) : product.product }
        so _sync_variations can match each WC variation to its Odoo variant.
        """
        AttrModel = self.env["product.attribute"]
        ValModel  = self.env["product.attribute.value"]

        # --- 1. Collect unique attr names and values from all variations -------
        attr_values_map = {}   # attr_name -> ordered list of unique values (insertion order)
        for var in var_records:
            for a in var.get("attributes") or []:
                attr_name = (a.get("name") or "").strip()
                opt       = (a.get("option") or "").strip()
                if not attr_name or not opt:
                    continue
                if attr_name not in attr_values_map:
                    attr_values_map[attr_name] = []
                if opt not in attr_values_map[attr_name]:
                    attr_values_map[attr_name].append(opt)

        if not attr_values_map:
            # No structured attributes — cannot build combination matrix.
            return {}

        # --- 2. Find-or-create product.attribute and product.attribute.value ---
        attr_id_map = {}   # attr_name -> product.attribute record
        val_id_map  = {}   # (attr_name, value) -> product.attribute.value record

        for attr_name, values in attr_values_map.items():
            attr = AttrModel.search([("name", "=", attr_name)], limit=1)
            if not attr:
                attr = AttrModel.create({"name": attr_name})
            attr_id_map[attr_name] = attr
            for v in values:
                val = ValModel.search(
                    [("attribute_id", "=", attr.id), ("name", "=", v)], limit=1
                )
                if not val:
                    val = ValModel.create({"attribute_id": attr.id, "name": v})
                val_id_map[(attr_name, v)] = val

        # --- 3. Write attribute_line_ids on the template ----------------------
        existing_lines = {
            line.attribute_id.id: line
            for line in odoo_tmpl.attribute_line_ids
        }
        line_commands = []
        for attr_name, values in attr_values_map.items():
            attr = attr_id_map[attr_name]
            val_ids = [val_id_map[(attr_name, v)].id for v in values]
            if attr.id in existing_lines:
                line = existing_lines[attr.id]
                current_val_ids = line.value_ids.ids
                missing = [v for v in val_ids if v not in current_val_ids]
                if missing:
                    line_commands.append((1, line.id, {"value_ids": [(4, v) for v in missing]}))
            else:
                line_commands.append((0, 0, {
                    "attribute_id": attr.id,
                    "value_ids": [(4, v) for v in val_ids],
                }))
        if line_commands:
            odoo_tmpl.with_context(syncing_from_wc=True).write(
                {"attribute_line_ids": line_commands}
            )

        # --- 4. Build variation-key → product.product mapping ----------------
        # After writing attribute lines Odoo auto-generates product.product
        # records. Map each by its ptav combination.
        variant_map = {}
        for variant in odoo_tmpl.product_variant_ids:
            key = frozenset(
                (ptav.attribute_id.name, ptav.name)
                for ptav in variant.product_template_attribute_value_ids
            )
            variant_map[key] = variant
        return variant_map

    def _sync_variations(self, backend, tmpl_binding, record: dict, force: bool, results=None):
        variation_ids = record.get("variations", [])
        if not variation_ids:
            return

        client = backend.get_api_client()
        var_endpoint = "products/%s/variations" % record["id"]
        try:
            var_records = []
            for page in client.get_all_pages(var_endpoint, {"per_page": 100}):
                var_records.extend(page)
        except Exception as exc:
            _logger.warning("Could not fetch variations for product %s: %s", record["id"], exc)
            if results is not None:
                results["failed"] += 1
                results["errors"].append("Variations fetch %s: %s" % (record["id"], exc))
            return

        odoo_tmpl = tmpl_binding.template_id
        parent_name = wc_unescape(record.get("name") or "")

        # Build attribute lines on the template and get a variant lookup map.
        variant_map = self._ensure_attribute_lines(odoo_tmpl, var_records)
        _logger.info(
            "[WC Variations] Template %s — attribute matrix built, %d Odoo variants available",
            odoo_tmpl.id, len(odoo_tmpl.product_variant_ids),
        )

        wc_product_model = self.env["wc.product.link"]

        for var in var_records:
            var_ext_id = str(var.get("id", ""))
            if not var_ext_id:
                continue

            if not var.get("name"):
                attr_parts = [
                    a.get("option", "")
                    for a in var.get("attributes", [])
                    if a.get("option")
                ]
                var["name"] = parent_name
                if attr_parts:
                    var["name"] += " - " + ", ".join(attr_parts)

            if not var.get("categories"):
                var["categories"] = record.get("categories", [])
            if not var.get("tags"):
                var["tags"] = record.get("tags", [])

            # Find the matching Odoo variant by attribute values.
            var_key = frozenset(
                (a.get("name", "").strip(), a.get("option", "").strip())
                for a in (var.get("attributes") or [])
                if a.get("name") and a.get("option")
            )
            matched_variant = variant_map.get(var_key)

            try:
                # wc_syncing_variations prevents _sync_one from re-delegating
                # to the parent and creating an infinite fetch loop.
                # wc_matched_variant_id passes the pre-matched product.product
                # so _sync_one does not create a new template.
                var_binding, status = wc_product_model.with_context(
                    wc_syncing_variations=True,
                    wc_parent_tmpl_id=tmpl_binding.template_id.id,
                    wc_matched_variant_id=matched_variant.id if matched_variant else False,
                )._sync_one(backend, var, force)
                if results is not None:
                    results[status] += 1
                if var_binding:
                    var_binding.with_context(syncing_from_wc=True).write({
                        "is_variation": True,
                        "wc_template_id": tmpl_binding.id,
                    })
            except Exception as exc:
                _logger.exception("Failed syncing variation %s: %s", var_ext_id, exc)
                if results is not None:
                    results["failed"] += 1
                    results["errors"].append("Variation %s: %s" % (var_ext_id, exc))

    def pull_from_store(self):
        def _op(binding):
            client = binding.backend_id.get_api_client()
            result = client.get("products/%s" % binding.external_id)
            data = result.get("data", {})
            if data:
                self.syncing_from_wc(binding.backend_id, [data], force=True)
                binding.mark_synced("Template pulled from WooCommerce.")

        return self.filtered("external_id")._run_with_notification(_op, title="Pull Complete")

    def push_to_store(self):
        from ..components.exporter import WooVariableProductExporter
        exporter = WooVariableProductExporter()

        def _op(binding):
            exporter.run(binding.backend_id, binding)
            binding.mark_synced("Variable product pushed to WooCommerce.")

        return self._run_with_notification(_op, title="Push Complete")

class ProductTemplateWoo(models.Model):
    _inherit = "product.template"

    wc_bind_ids = fields.One2many(
        comodel_name="wc.template.link",
        inverse_name="template_id",
        string="WooCommerce Bindings",
        copy=False,
    )

    def action_push_product_to_store(self):
        backends = self.env["wc.store"].search([("active", "=", True)])
        if not backends:
            raise UserError("No active WooCommerce stores found.")

        for template in self:
            if template.wc_bind_ids:
                template.wc_bind_ids.push_to_store()
            else:
                for product in template.product_variant_ids:
                    product.action_push_product_to_store()
