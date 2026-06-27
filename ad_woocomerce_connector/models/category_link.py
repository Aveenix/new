import html
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


def wc_unescape(value):
    """Decode HTML entities (&amp; &#038; &quot; ...) that WooCommerce returns
    in names so they don't show literally in Odoo."""
    if not value:
        return value
    return html.unescape(value)

class WooProductCategory(models.Model):

    _name = "wc.category.link"
    _description = "WooCommerce Product Category"
    _inherit = "wc.binding"
    _inherits = {"product.category": "category_id"}
    _rec_name = "name"

    category_id = fields.Many2one(
        comodel_name="product.category",
        string="Odoo Category",
        required=True,
        ondelete="cascade",
    )
    wc_slug = fields.Char(string="Slug")
    wc_description = fields.Text(string="WooCommerce Description")
    wc_count = fields.Integer(
        string="Product Count",
        help="Number of products in this category on WooCommerce.",
    )
    wc_parent_id = fields.Many2one(
        comodel_name="wc.category.link",
        string="Parent WooCommerce Category",
        ondelete="set null",
    )
    public_categ_id = fields.Many2one(
        comodel_name="product.public.category",
        string="eCommerce Category",
        ondelete="set null",
        help="Linked website/eCommerce category created from this WooCommerce category.",
    )

    _sql_constraints = [
        (
            "wc_category_link_unique",
            "unique(backend_id, external_id)",
            "A WooCommerce category with this ID already exists for this store.",
        )
    ]

    @api.model
    def syncing_from_wc(self, backend, records: list, force: bool = False):
        results = {"created": 0, "updated": 0, "skipped": 0, "failed": 0, "errors": []}
        by_ext = {str(r["id"]): r for r in records if r.get("id")}

        def sort_key(r):
            parent = r.get("parent", 0)
            return 0 if not parent or str(parent) not in by_ext else 1

        sorted_records = sorted(records, key=sort_key)

        for record in sorted_records:
            ext_id = str(record.get("id", ""))
            if not ext_id:
                continue
            try:
                binding, status = self._sync_one(backend, record, force)
                results[status] += 1
            except Exception as exc:
                _logger.exception("Failed syncing WooCommerce category %s: %s", ext_id, exc)
                results["failed"] += 1
                results["errors"].append("Category %s: %s" % (ext_id, exc))

        _logger.info(
            "[WC Category] Pull complete — created=%d updated=%d skipped=%d failed=%d",
            results["created"], results["updated"], results["skipped"], results["failed"],
        )
        return results

    def _sync_one(self, backend, record: dict, force: bool = False):
        ext_id = str(record["id"])
        name = wc_unescape(record.get("name")) or "Unnamed Category"
        _logger.info("[WC Category] Syncing WC category id=%s name=%r (force=%s)\nResponse JSON: %s", ext_id, name, force, record)

        existing = self.search([
            ("backend_id", "=", backend.id),
            ("external_id", "=", ext_id),
        ], limit=1)

        parent_woo = None
        parent_ext = str(record.get("parent") or "")
        if parent_ext and parent_ext != "0":
            parent_woo = self.search([
                ("backend_id", "=", backend.id),
                ("external_id", "=", parent_ext),
            ], limit=1)
            if parent_woo:
                _logger.info("[WC Category] Parent resolved: WC id=%s → %r", parent_ext, parent_woo.name)
            else:
                _logger.warning("[WC Category] Parent WC id=%s not found in Odoo for category %s", parent_ext, ext_id)

        vals = {
            "name": name,
            "wc_slug": record.get("slug", ""),
            "wc_description": record.get("description", ""),
            "wc_count": record.get("count", 0),
            "backend_id": backend.id,
            "external_id": ext_id,
            "sync_date": fields.Datetime.now(),
        }
        if parent_woo:
            vals["parent_id"] = parent_woo.category_id.id
            vals["wc_parent_id"] = parent_woo.id

        # Mirror into an eCommerce (website) category too.
        public_categ = self._sync_public_category(record, vals["name"], parent_woo)
        if public_categ:
            vals["public_categ_id"] = public_categ.id
            _logger.info("[WC Category] eCommerce category: id=%s name=%r", public_categ.id, public_categ.name)

        if existing:
            if not force:
                _logger.info("[WC Category] Skipped (already synced, force=False): WC id=%s name=%r", ext_id, name)
                return existing, "skipped"
            existing.with_context(syncing_from_wc=True).write(vals)
            _logger.info("[WC Category] Updated: WC id=%s name=%r → Odoo category id=%s", ext_id, name, existing.category_id.id)
            return existing, "updated"
        else:
            cat_vals = {"name": vals["name"]}
            if parent_woo:
                cat_vals["parent_id"] = parent_woo.category_id.id
            category = self.env["product.category"].create(cat_vals)
            vals["category_id"] = category.id
            binding = self.with_context(syncing_from_wc=True).create(vals)
            _logger.info("[WC Category] Created: WC id=%s name=%r → Odoo category id=%s binding id=%s", ext_id, name, category.id, binding.id)
            return binding, "created"

    def _sync_public_category(self, record, name, parent_woo):
        """Create/find the matching product.public.category (eCommerce),
        mirroring the WooCommerce parent hierarchy."""
        PublicCateg = self.env["product.public.category"]
        parent_public = parent_woo.public_categ_id if parent_woo else False

        domain = [
            ("name", "=", name),
            ("parent_id", "=", parent_public.id if parent_public else False),
        ]
        public_categ = PublicCateg.search(domain, limit=1)
        if not public_categ:
            public_categ = PublicCateg.create({
                "name": name,
                "parent_id": parent_public.id if parent_public else False,
            })
        elif parent_public and public_categ.parent_id != parent_public:
            public_categ.write({"parent_id": parent_public.id})
        return public_categ

    def push_to_store(self):
        from ..components.exporter import WooCategoryExporter
        exporter = WooCategoryExporter()

        def _op(binding):
            exporter.run(binding.backend_id, binding)
            binding.mark_synced("Category pushed to WooCommerce.")

        return self._run_with_notification(_op, title="Push Complete")

    def pull_from_store(self):
        def _op(binding):
            client = binding.backend_id.get_api_client()
            result = client.get("products/categories/%s" % binding.external_id)
            data = result.get("data", {})
            if data:
                self.syncing_from_wc(binding.backend_id, [data], force=True)
                binding.mark_synced("Category pulled from WooCommerce.")

        return self.filtered("external_id")._run_with_notification(_op, title="Pull Complete")

class ProductCategoryWoo(models.Model):

    _inherit = "product.category"

    wc_bind_ids = fields.One2many(
        comodel_name="wc.category.link",
        inverse_name="category_id",
        string="WooCommerce Bindings",
        copy=False,
    )
