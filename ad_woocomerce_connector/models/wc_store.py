import logging
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

from ..components.api_client import WooRESTClient, WooStoreLocation, WooConnectionError

_logger = logging.getLogger(__name__)

SYNC_DELTA = 30

def merge_sync_results(target, source):
    if not source:
        return target
    for key in ['created', 'updated', 'skipped', 'failed']:
        target[key] = target.get(key, 0) + source.get(key, 0)
    target['errors'] = target.get('errors', []) + source.get('errors', [])
    return target

class WooBackend(models.Model):

    _name = "wc.store"
    _description = "WooCommerce Store"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name"

    name = fields.Char(
        string="Store Name", required=True, tracking=True,
        help="Friendly label for this WooCommerce store connection.",
    )
    active = fields.Boolean(default=True)
    color = fields.Integer()

    api_version = fields.Selection(
        selection=[("wc/v3", "REST API v3")],
        string="API Version", default="wc/v3", required=True,
    )
    store_url = fields.Char(
        string="Store URL",
        help="Base URL of the WooCommerce store, e.g. https://myshop.com",
    )
    consumer_key = fields.Char(string="Consumer Key")
    consumer_secret = fields.Char(string="Consumer Secret")

    use_sandbox = fields.Boolean(
        string="Sandbox / Staging Mode", default=True, tracking=True,
    )
    sandbox_url = fields.Char(string="Sandbox URL")
    sandbox_key = fields.Char(string="Sandbox Consumer Key")
    sandbox_secret = fields.Char(string="Sandbox Consumer Secret")

    company_id = fields.Many2one(
        comodel_name="res.company", string="Company", required=True,
        default=lambda self: self.env.company,
    )
    warehouse_id = fields.Many2one(
        comodel_name="stock.warehouse", string="Default Warehouse",
        check_company=True,
    )
    stock_warehouse_ids = fields.Many2many(
        comodel_name="stock.warehouse",
        string="Stock Warehouses",
        help="Warehouses used to compute quantities pushed to WooCommerce.",
    )
    sales_team_id = fields.Many2one(
        comodel_name="crm.team", string="Sales Team",
    )
    records_per_page = fields.Integer(
        string="Records per Page", default=100,
        help="Number of records fetched per API page (max 100 for WooCommerce).",
    )

    order_name_prefix = fields.Char(
        string="Order Name Prefix", default="WC-",
        help="Prefix prepended to WooCommerce order numbers when creating Odoo orders.",
    )
    allowed_order_status_ids = fields.Many2many(
        comodel_name="wc.order.stage",
        string="Fetch Orders with Status",
        help="Only orders with these statuses will be pulled. Leave empty for all.",
    )
    push_fulfillment_status = fields.Boolean(
        string="Push Fulfillment Status",
        help="Update order status in WooCommerce when delivery is completed.",
    )
    push_tracking_info = fields.Boolean(
        string="Include Tracking Number",
        help="Send carrier tracking reference along with fulfillment status.",
    )
    default_shipping_product_id = fields.Many2one(
        comodel_name="product.product",
        string="Default Shipping Product",
        domain=[("type", "=", "service")],
    )
    default_fee_product_id = fields.Many2one(
        comodel_name="product.product",
        string="Default Fee Product",
        domain=[("type", "=", "service")],
    )

    allow_customers_without_email = fields.Boolean(
        string="Allow Customers Without Email",
    )

    default_product_type = fields.Selection(
        selection=[
            ("consu", "Consumable"),
            ("service", "Service"),
            ("product", "Storable Product"),
        ],
        string="Default Product Type", default="consu", required=True,
    )
    default_category_id = fields.Many2one(
        comodel_name="product.category",
        string="Default Product Category",
    )
    allow_products_without_sku = fields.Boolean(
        string="Allow Products Without SKU",
    )
    match_product_by_sku = fields.Boolean(
        string="Match Existing Products by SKU",
        help="If an Odoo product with the same SKU exists, link it instead of creating a new one.",
    )
    push_stock_to_store = fields.Boolean(
        string="Sync Stock to WooCommerce",
        help="Automatically push Odoo on-hand quantities to WooCommerce.",
    )

    orders_last_sync = fields.Datetime(string="Orders Last Synced")
    products_last_sync = fields.Datetime(string="Products Last Synced")
    customers_last_sync = fields.Datetime(string="Customers Last Synced")

    # Self-resuming bulk sync progress: JSON {task: next_page}. A task absent
    # means "not started / done". Used by cron_bulk_sync to chunk huge pulls.
    bulk_sync_progress = fields.Text(
        string="Bulk Sync Progress", default="{}", copy=False,
        help="Internal: tracks the next page to fetch per task for the "
             "self-resuming bulk sync cron.",
    )
    bulk_sync_running = fields.Boolean(
        string="Bulk Sync Running", default=False, copy=False,
    )

    webhook_token = fields.Char(
        string="Webhook Token", readonly=True, copy=False,
        help="Secret token used to validate incoming WooCommerce webhook calls.",
    )
    webhook_instructions = fields.Html(
        string="Webhook Setup Guide",
        compute="_compute_webhook_instructions", readonly=True,
    )

    order_count = fields.Integer(
        string="Orders Synced", compute="_compute_counts",
    )
    product_count = fields.Integer(
        string="Products Synced", compute="_compute_counts",
    )
    customer_count = fields.Integer(
        string="Customers Synced", compute="_compute_counts",
    )

    def _compute_counts(self):
        for rec in self:
            rec.order_count = self.env["wc.order"].search_count(
                [("backend_id", "=", rec.id)]
            )
            rec.product_count = self.env["wc.product.link"].search_count(
                [("backend_id", "=", rec.id)]
            )
            rec.customer_count = self.env["wc.customer.link"].search_count(
                [("backend_id", "=", rec.id)]
            )

    @api.depends("use_sandbox", "webhook_token", "store_url", "sandbox_url")
    def _compute_webhook_instructions(self):
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        for rec in self:
            token = rec.webhook_token or "(generate token first)"
            store = rec.sandbox_url if rec.use_sandbox else rec.store_url
            rec.webhook_instructions = """
            <div class="alert alert-info">
                <h4>How to register WooCommerce Webhooks</h4>
                <p>Go to <strong>WooCommerce → Settings → Advanced → Webhooks</strong>
                   and add the following webhooks:</p>
                <table class="table table-sm table-bordered">
                  <thead><tr><th>Event</th><th>Delivery URL</th></tr></thead>
                  <tbody>
                    <tr><td>Order Created</td>
                        <td>{base}/woocommerce/webhook/order_created/{token}</td></tr>
                    <tr><td>Order Updated</td>
                        <td>{base}/woocommerce/webhook/order_updated/{token}</td></tr>
                    <tr><td>Product Created</td>
                        <td>{base}/woocommerce/webhook/product_created/{token}</td></tr>
                    <tr><td>Product Updated</td>
                        <td>{base}/woocommerce/webhook/product_updated/{token}</td></tr>
                    <tr><td>Customer Created</td>
                        <td>{base}/woocommerce/webhook/customer_created/{token}</td></tr>
                    <tr><td>Customer Updated</td>
                        <td>{base}/woocommerce/webhook/customer_updated/{token}</td></tr>
                  </tbody>
                </table>
                <p><strong>API Version:</strong> WP REST API Integration v3</p>
            </div>
            """.format(base=base_url, token=token)

    def get_api_client(self) -> WooRESTClient:
        self.ensure_one()
        if self.use_sandbox:
            url, key, secret = self.sandbox_url, self.sandbox_key, self.sandbox_secret
        else:
            url, key, secret = self.store_url, self.consumer_key, self.consumer_secret
        if not url or not key or not secret:
            raise UserError(
                "WooCommerce credentials are incomplete for store '%s'. "
                "Please fill in URL, Consumer Key and Consumer Secret." % self.name
            )
        location = WooStoreLocation(url, key, secret, self.api_version)
        client = WooRESTClient(location)
        # Propagate the wizard's chunk controls so every paginated pull
        # (tags, categories, customers, products, ...) honors Start Page /
        # Max Records, not just the product pulls.
        client.sync_start_page = self.env.context.get("wc_start_page") or 1
        client.sync_max_records = self.env.context.get("wc_max_records") or 0
        client.sync_time_budget = self.env.context.get("wc_time_budget") or 0
        # Shared deadline (set by a multi-type pull) wins over per-call budget.
        client._deadline = self.env.context.get("wc_deadline") or None
        return client

    def action_verify_connection(self):
        self.ensure_one()
        try:
            client = self.get_api_client()
            ok = client.test_connection()
        except (WooConnectionError, UserError) as exc:
            raise UserError("Connection failed: %s" % exc) from exc
        if ok:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "Connection Successful",
                    "message": "Successfully connected to %s." % self.name,
                    "type": "success",
                    "sticky": False,
                },
            }
        raise UserError(
            "Could not verify connection to '%s'. Check your credentials." % self.name
        )

    def action_generate_webhook_token(self):
        for rec in self:
            rec.webhook_token = str(uuid.uuid4()).replace("-", "")

    def action_pull_metadata(self):
        results = {"created": 0, "updated": 0, "skipped": 0, "failed": 0, "errors": []}
        for backend in self:
            ship_res = backend._pull_shipping_methods()
            pay_res = backend._pull_payment_methods()
            merge_sync_results(results, ship_res)
            merge_sync_results(results, pay_res)
        if self.env.context.get("return_raw_results"):
            return results
        msg = f"Store metadata refreshed successfully. Created: {results['created']}, Updated: {results['updated']}, Skipped: {results['skipped']}, Failed: {results['failed']}"
        return self._notify(msg)

    def action_pull_categories(self):
        results = {"created": 0, "updated": 0, "skipped": 0, "failed": 0, "errors": []}
        for backend in self:
            res = backend._do_pull_categories(force=False)
            merge_sync_results(results, res)
        if self.env.context.get("return_raw_results"):
            return results
        return self._notify(f"Product categories synced. Created: {results['created']}, Updated: {results['updated']}, Skipped: {results['skipped']}, Failed: {results['failed']}.")

    def action_pull_tags(self):
        results = {"created": 0, "updated": 0, "skipped": 0, "failed": 0, "errors": []}
        for backend in self:
            res = backend._do_pull_tags(force=False)
            merge_sync_results(results, res)
        if self.env.context.get("return_raw_results"):
            return results
        return self._notify(f"Product tags synced. Created: {results['created']}, Updated: {results['updated']}, Skipped: {results['skipped']}, Failed: {results['failed']}.")

    def action_pull_attributes(self):
        results = {"created": 0, "updated": 0, "skipped": 0, "failed": 0, "errors": []}
        for backend in self:
            res = backend._do_pull_attributes(force=False)
            merge_sync_results(results, res)
        if self.env.context.get("return_raw_results"):
            return results
        return self._notify(f"Product attributes synced. Created: {results['created']}, Updated: {results['updated']}, Skipped: {results['skipped']}, Failed: {results['failed']}.")

    def action_pull_taxes(self):
        results = {"created": 0, "updated": 0, "skipped": 0, "failed": 0, "errors": []}
        for backend in self:
            res = backend._do_pull_taxes(force=False)
            merge_sync_results(results, res)
        if self.env.context.get("return_raw_results"):
            return results
        return self._notify(f"Tax rates synced. Created: {results['created']}, Updated: {results['updated']}, Skipped: {results['skipped']}, Failed: {results['failed']}.")

    def action_pull_customers(self):
        results = {"created": 0, "updated": 0, "skipped": 0, "failed": 0, "errors": []}
        for backend in self:
            res = backend._do_pull_customers(force=False)
            backend.customers_last_sync = datetime.now() - timedelta(seconds=SYNC_DELTA)
            merge_sync_results(results, res)
        if self.env.context.get("return_raw_results"):
            return results
        return self._notify(f"Customers synced. Created: {results['created']}, Updated: {results['updated']}, Skipped: {results['skipped']}, Failed: {results['failed']}.")

    def action_pull_products(self):
        results = {"created": 0, "updated": 0, "skipped": 0, "failed": 0, "errors": []}
        for backend in self:
            res = backend._do_pull_products(force=False)
            backend.products_last_sync = datetime.now() - timedelta(seconds=SYNC_DELTA)
            merge_sync_results(results, res)
        if self.env.context.get("return_raw_results"):
            return results
        return self._notify(f"Products synced. Created: {results['created']}, Updated: {results['updated']}, Skipped: {results['skipped']}, Failed: {results['failed']}.")

    def action_pull_variable_products(self):
        results = {"created": 0, "updated": 0, "skipped": 0, "failed": 0, "errors": []}
        for backend in self:
            res = backend._do_pull_variable_products(force=False)
            merge_sync_results(results, res)
        if self.env.context.get("return_raw_results"):
            return results
        return self._notify(f"Variable products synced. Created: {results['created']}, Updated: {results['updated']}, Skipped: {results['skipped']}, Failed: {results['failed']}.")

    def action_pull_orders(self):
        results = {"created": 0, "updated": 0, "skipped": 0, "failed": 0, "errors": []}
        for backend in self:
            res = backend._do_pull_orders(force=False)
            backend.orders_last_sync = datetime.now() - timedelta(seconds=SYNC_DELTA)
            merge_sync_results(results, res)
        if self.env.context.get("return_raw_results"):
            return results
        return self._notify(f"Orders synced. Created: {results['created']}, Updated: {results['updated']}, Skipped: {results['skipped']}, Failed: {results['failed']}.")

    def action_push_stock(self):
        results = {"created": 0, "updated": 0, "skipped": 0, "failed": 0, "errors": []}
        for backend in self:
            bindings = self.env["wc.product.link"].search([
                ("backend_id", "=", backend.id),
                ("external_id", "!=", False),
                ("wc_manage_stock", "=", True),
            ])
            res = bindings.with_context(return_raw_results=True).push_stock_to_store()
            if isinstance(res, dict) and "success" in res:
                merge_sync_results(results, {
                    "created": 0,
                    "updated": res["success"],
                    "skipped": 0,
                    "failed": res["failed"],
                    "errors": res["errors"],
                })
        if self.env.context.get("return_raw_results"):
            return results
        return self._notify(f"Stock quantities pushed. Updated: {results['updated']}, Failed: {results['failed']}.")

    def action_push_order_statuses(self):
        results = {"created": 0, "updated": 0, "skipped": 0, "failed": 0, "errors": []}
        for backend in self:
            res = backend._do_push_order_statuses()
            merge_sync_results(results, res)
        if self.env.context.get("return_raw_results"):
            return results
        return self._notify(f"Order statuses pushed. Updated: {results['updated']}, Failed: {results['failed']}.")

    def action_push_paid_orders(self):
        results = {"created": 0, "updated": 0, "skipped": 0, "failed": 0, "errors": []}
        for backend in self:
            res = backend._do_push_paid_orders()
            merge_sync_results(results, res)
        if self.env.context.get("return_raw_results"):
            return results
        return self._notify(f"Paid orders pushed to WooCommerce. Created: {results['created']}, Failed: {results['failed']}.")

    def action_view_orders(self):
        return {
            "name": "WooCommerce Orders",
            "type": "ir.actions.act_window",
            "res_model": "wc.order",
            "view_mode": "list,form",
            "domain": [("backend_id", "=", self.id)],
            "context": {"default_backend_id": self.id},
        }

    def action_view_products(self):
        return {
            "name": "WooCommerce Products",
            "type": "ir.actions.act_window",
            "res_model": "wc.product.link",
            "view_mode": "list,form",
            "domain": [("backend_id", "=", self.id)],
            "context": {"default_backend_id": self.id},
        }

    def action_view_customers(self):
        return {
            "name": "WooCommerce Customers",
            "type": "ir.actions.act_window",
            "res_model": "wc.customer.link",
            "view_mode": "list,form",
            "domain": [("backend_id", "=", self.id)],
            "context": {"default_backend_id": self.id},
        }

    def _build_date_filter(self, last_sync_field: str, force: bool = False) -> dict:
        if force:
            return {}
            
        last = self[last_sync_field]
        if last:
            return {
                "modified_after": last.isoformat(),
                "dates_are_gmt": True,
            }
        return {}

    def _do_pull_categories(self, force=False):
        client = self.get_api_client()
        records = []
        for page in client.get_all_pages("products/categories", {"per_page": 100}):
            records.extend(page)
        return self.env["wc.category.link"].syncing_from_wc(self, records, force)

    def _do_pull_tags(self, force=False):
        client = self.get_api_client()
        records = []
        for page in client.get_all_pages("products/tags", {"per_page": 100}):
            records.extend(page)
        return self.env["wc.tag"].syncing_from_wc(self, records, force)

    def _do_pull_attributes(self, force=False):
        client = self.get_api_client()
        result = client.get("products/attributes")
        attributes = result.get("data", [])
        wc_attr_model = self.env["wc.attribute.link"]
        res = wc_attr_model.syncing_from_wc(self, attributes, force)
        for attr in attributes:
            wc_attr = wc_attr_model.search([
                ("backend_id", "=", self.id),
                ("external_id", "=", str(attr["id"])),
            ], limit=1)
            if not wc_attr:
                continue
            terms_result = client.get("products/attributes/%s/terms" % attr["id"])
            terms = terms_result.get("data", [])
            term_res = self.env["wc.attribute.term"].sync_terms_from_wc(
                self, wc_attr, terms, force
            )
            merge_sync_results(res, term_res)
        return res

    def _do_pull_taxes(self, force=False):
        client = self.get_api_client()
        records = []
        for page in client.get_all_pages("taxes", {"per_page": 100}):
            records.extend(page)
        results = {"created": 0, "updated": 0, "skipped": 0, "failed": 0, "errors": []}
        for record in records:
            try:
                status = self._sync_one_tax(record, force)
                results[status] += 1
            except Exception as exc:
                _logger.exception("Failed syncing tax %s: %s", record.get("id"), exc)
                results["failed"] += 1
                results["errors"].append("Tax %s: %s" % (record.get("id"), exc))
        return results

    def _sync_one_tax(self, record: dict, force=False):
        ext_id = str(record.get("id", ""))
        existing = self.env["wc.tax.link"].search([
            ("backend_id", "=", self.id),
            ("external_id", "=", ext_id),
        ], limit=1)
        rate = float(record.get("rate") or 0)
        vals = {
            "wc_rate": rate,
            "wc_tax_class": record.get("class", "standard"),
            "wc_compound": record.get("compound", False),
            "wc_shipping": record.get("shipping", True),
            "backend_id": self.id,
            "external_id": ext_id,
            "sync_date": datetime.now(),
        }
        if existing:
            if force:
                existing.with_context(syncing_from_wc=True).write(vals)
                return "updated"
            return "skipped"
        odoo_tax = self.env["account.tax"].search([
            ("amount", "=", rate),
            ("type_tax_use", "=", "sale"),
            ("company_id", "=", self.company_id.id),
        ], limit=1)
        name = record.get("name") or ("Tax %s%%" % rate)
        if not odoo_tax:
            odoo_tax = self.env["account.tax"].create({
                "name": name,
                "amount": rate,
                "amount_type": "percent",
                "type_tax_use": "sale",
                "company_id": self.company_id.id,
            })
        vals["tax_id"] = odoo_tax.id
        vals["name"] = name
        self.env["wc.tax.link"].with_context(syncing_from_wc=True).create(vals)
        return "created"

    def _do_pull_customers(self, force=False):
        client = self.get_api_client()
        params = self._build_date_filter("customers_last_sync", force=force)
        params["role"] = "customer"
        results = {"created": 0, "updated": 0, "skipped": 0, "failed": 0, "errors": []}
        for page in client.get_all_pages("customers", params):
            res = self.env["wc.customer.link"].syncing_from_wc(self, page, force)
            merge_sync_results(results, res)
        return results

    def _pull_products_by_type(self, wc_type, target_model, force=False):
        """Paginated product pull for one WC type.

        Uses the backend's records_per_page and commits after every page so
        large catalogs (20k+) don't build one huge transaction that exhausts
        memory and restarts the server.
        """
        client = self.get_api_client()
        per_page = min(self.records_per_page or 100, 100)
        params = dict(self._build_date_filter("products_last_sync", force=force))
        params["type"] = wc_type
        params["status"] = "any"
        results = {"created": 0, "updated": 0, "skipped": 0, "failed": 0, "errors": []}
        # Start Page / Max Records are applied by get_all_pages from the client
        # (set from the wizard context in get_api_client).
        for page in client.get_all_pages("products", params, per_page=per_page):
            res = self.env[target_model].syncing_from_wc(self, page, force)
            merge_sync_results(results, res)
            # Flush this page to DB and free memory before fetching the next.
            if not self.env.context.get("no_commit"):
                self.env.cr.commit()
            self.env.invalidate_all()
        return results

    def _do_pull_single_product(self, product_id, force=True):
        """Fetch one WooCommerce product by its ID and sync it."""
        if not product_id:
            raise UserError("Please enter a WooCommerce Product ID.")
        client = self.get_api_client()
        result = client.get("products/%s" % str(product_id).strip())
        record = result.get("data") or {}
        if not record or not record.get("id"):
            raise UserError(
                "No WooCommerce product found with ID %s." % product_id
            )
        import json
        _logger.info(
            "WC PRODUCT JSON %s:\n%s",
            product_id, json.dumps(record, indent=2, default=str),
        )
        wc_type = (record.get("type") or "simple").strip()
        if wc_type == "variable":
            target_model = "wc.template.link"
        else:
            target_model = "wc.product.link"
        return self.env[target_model].syncing_from_wc(self, [record], force=force)

    def _do_pull_products(self, force=False):
        return self._pull_products_by_type("simple", "wc.product.link", force)

    def _do_pull_affiliate_products(self, force=False):
        return self._pull_products_by_type("external", "wc.product.link", force)

    def _do_pull_variable_products(self, force=False):
        return self._pull_products_by_type("variable", "wc.template.link", force)

    def _do_pull_all_products(self, force=False):
        """Pull every product type: simple, external/affiliate and variable.

        Shares one wall-clock deadline across the three pulls so the total run
        respects the time budget (not 3x)."""
        backend = self
        budget = self.env.context.get("wc_time_budget") or 0
        if budget:
            import time
            backend = self.with_context(wc_deadline=time.time() + budget)
        results = {"created": 0, "updated": 0, "skipped": 0, "failed": 0, "errors": []}
        merge_sync_results(results, backend._do_pull_products(force))
        merge_sync_results(results, backend._do_pull_affiliate_products(force))
        merge_sync_results(results, backend._do_pull_variable_products(force))
        return results

    def _do_pull_orders(self, force=False):
        client = self.get_api_client()
        params = self._build_date_filter("orders_last_sync", force=force)
        if self.allowed_order_status_ids:
            params["status"] = ",".join(
                self.allowed_order_status_ids.mapped("code")
            )
        results = {"created": 0, "updated": 0, "skipped": 0, "failed": 0, "errors": []}
        for page in client.get_all_pages("orders", params):
            res = self.env["wc.order"].syncing_from_wc(self, page, force)
            merge_sync_results(results, res)
        return results

    def _pull_shipping_methods(self):
        client = self.get_api_client()
        result = client.get("shipping/zones")
        zones = result.get("data", [])
        results = {"created": 0, "updated": 0, "skipped": 0, "failed": 0, "errors": []}
        for zone in zones:
            zone_id = zone.get("id")
            try:
                methods_result = client.get("shipping/zones/%s/methods" % zone_id)
                for method in methods_result.get("data", []):
                    try:
                        status = self._sync_one_shipping_method(method)
                        results[status] += 1
                    except Exception as exc:
                        _logger.exception("Failed syncing shipping method: %s", exc)
                        results["failed"] += 1
                        results["errors"].append("Shipping Method: %s" % exc)
            except Exception as exc:
                _logger.exception("Failed pulling methods for zone %s: %s", zone_id, exc)
                results["failed"] += 1
                results["errors"].append("Shipping Zone %s: %s" % (zone_id, exc))
        return results

    def _sync_one_shipping_method(self, record: dict):
        method_id = record.get("method_id", "")
        instance_id = str(record.get("instance_id", ""))
        ext_id = "%s_%s" % (method_id, instance_id)
        existing = self.env["wc.shipping.carrier"].search([
            ("backend_id", "=", self.id),
            ("external_id", "=", ext_id),
        ], limit=1)
        if existing:
            return "skipped"
        title = record.get("method_title") or record.get("title") or method_id
        carrier = self.env["delivery.carrier"].search(
            [("name", "=", title)], limit=1
        )
        if not carrier:
            product = self.env["product.product"].search(
                [("name", "=", title), ("type", "=", "service")], limit=1
            )
            if not product:
                product = self.env["product.product"].create({
                    "name": title, "type": "service",
                })
            carrier = self.env["delivery.carrier"].create({
                "name": title, "product_id": product.id,
            })
        self.env["wc.shipping.carrier"].with_context(syncing_from_wc=True).create({
            "carrier_id": carrier.id,
            "wc_method_id": method_id,
            "wc_instance_id": instance_id,
            "backend_id": self.id,
            "external_id": ext_id,
            "sync_date": datetime.now(),
        })
        return "created"

    def _pull_payment_methods(self):
        client = self.get_api_client()
        result = client.get("payment_gateways")
        gateways = result.get("data", [])
        results = {"created": 0, "updated": 0, "skipped": 0, "failed": 0, "errors": []}
        for gw in gateways:
            ext_id = gw.get("id", "")
            if not ext_id:
                continue
            try:
                existing = self.env["wc.payment.mode"].search([
                    ("backend_id", "=", self.id),
                    ("external_id", "=", ext_id),
                ], limit=1)
                if existing:
                    name = gw.get("title") or ext_id
                    is_enabled = gw.get("enabled", True)
                    desc = gw.get("description", "")
                    if (existing.name != name or 
                        existing.is_enabled != is_enabled or 
                        existing.description != desc):
                        existing.with_context(syncing_from_wc=True).write({
                            "name": name,
                            "is_enabled": is_enabled,
                            "description": desc,
                        })
                        results["updated"] += 1
                    else:
                        results["skipped"] += 1
                else:
                    self.env["wc.payment.mode"].with_context(syncing_from_wc=True).create({
                        "name": gw.get("title") or ext_id,
                        "external_id": ext_id,
                        "backend_id": self.id,
                        "is_enabled": gw.get("enabled", True),
                        "description": gw.get("description", ""),
                    })
                    results["created"] += 1
            except Exception as exc:
                _logger.exception("Failed syncing payment gateway %s: %s", ext_id, exc)
                results["failed"] += 1
                results["errors"].append("Payment Gateway %s: %s" % (ext_id, exc))
        return results

    def _do_push_paid_orders(self):
        """Push paid Odoo sale orders (fully-paid invoice) that are not yet in
        WooCommerce. Creates a wc.order binding for each, then exports it."""
        results = {"created": 0, "updated": 0, "skipped": 0, "failed": 0, "errors": []}

        # Sale orders whose invoices are fully paid and that have no WC binding
        # on this backend yet.
        orders = self.env["sale.order"].search([
            ("state", "in", ("sale", "done")),
            ("invoice_ids.payment_state", "in", ("paid", "in_payment")),
        ])
        orders = orders.filtered(
            lambda o: o._wc_is_paid() and not o.wc_bind_ids.filtered(
                lambda b: b.backend_id == self and b.external_id
            )
        )

        bindings = self.env["wc.order"]
        for order in orders:
            binding = order.wc_bind_ids.filtered(lambda b: b.backend_id == self)[:1]
            if not binding:
                binding = self.env["wc.order"].with_context(
                    syncing_from_wc=True
                ).create({"order_id": order.id, "backend_id": self.id})
            bindings |= binding

        if not bindings:
            return results

        res = bindings.with_context(return_raw_results=True).push_order_to_store()
        if isinstance(res, dict) and "success" in res:
            results["created"] += res["success"]
            results["failed"] += res["failed"]
            results["errors"].extend(res["errors"])
        return results

    def _do_push_order_statuses(self):
        if not self.push_fulfillment_status:
            return {"created": 0, "updated": 0, "skipped": 0, "failed": 0, "errors": []}
        domain = [
            ("backend_id", "=", self.id),
            ("external_id", "!=", False),
            ("order_id.all_deliveries_done", "=", True),
        ]
        bindings = self.env["wc.order"].search(domain)
        results = {"created": 0, "updated": 0, "skipped": 0, "failed": 0, "errors": []}
        for binding in bindings:
            if binding.wc_status_id and binding.wc_status_id.is_terminal:
                results["skipped"] += 1
                continue
            binding.wc_fulfillment_status = "completed"
            res = binding.with_context(return_raw_results=True).push_status_to_store()
            if isinstance(res, dict) and "success" in res:
                results["updated"] += res["success"]
                results["failed"] += res["failed"]
                results["errors"].extend(res["errors"])
        return results

    # ------------------------------------------------------------------
    # Self-resuming bulk sync
    # ------------------------------------------------------------------
    # Each task: (endpoint, target model, extra params). Pages are fetched
    # sequentially and progress is saved so a huge catalog is imported across
    # many short background runs instead of one long one.
    _BULK_TASKS = [
        ("categories", "products/categories", "wc.category.link", {}),
        ("tags", "products/tags", "wc.tag", {}),
        ("taxes", "taxes", "wc.tax.link", {}),
        ("customers", "customers", "wc.customer.link", {}),
        ("products_simple", "products", "wc.product.link", {"type": "simple"}),
        ("products_external", "products", "wc.product.link", {"type": "external"}),
        ("products_variable", "products", "wc.template.link", {"type": "variable"}),
    ]

    def start_bulk_sync(self):
        """Kick off the self-resuming bulk sync.

        Resumes from saved progress if a previous run was stopped part-way;
        otherwise starts fresh. Use action_restart_bulk_sync to force a
        full re-pull from page 1.
        """
        import json
        self.ensure_one()
        progress = json.loads(self.bulk_sync_progress or "{}")
        # If every task is already "done" (a completed run), start fresh.
        done_tasks = {t for t, v in progress.items() if v == "done"}
        all_done = done_tasks and len(done_tasks) == len(self._BULK_TASKS)
        if all_done or not progress:
            self.bulk_sync_progress = "{}"
            msg = "Bulk sync started in the background."
        else:
            msg = "Bulk sync resumed from where it left off."
        self.bulk_sync_running = True
        self.env.ref("ad_woocomerce_connector.cron_wc_bulk_sync").sudo()._trigger()
        return self._notify(msg + " Pulling data across several runs — you can keep working.")

    def action_restart_bulk_sync(self):
        """Force a full bulk sync from scratch (ignore saved progress)."""
        self.ensure_one()
        self.write({"bulk_sync_progress": "{}", "bulk_sync_running": True})
        self.env.ref("ad_woocomerce_connector.cron_wc_bulk_sync").sudo()._trigger()
        return self._notify("Bulk sync restarted from scratch in the background.")

    def stop_bulk_sync(self):
        """Stop the self-resuming bulk sync. The current chunk finishes, then
        no further runs are triggered. Progress is kept so it can resume."""
        self.ensure_one()
        self.write({"bulk_sync_running": False})
        return self._notify("Bulk sync stopped. Progress is saved — click "
                            "Start Full Bulk Sync to resume from where it left off.")

    def _bulk_run_chunk(self, time_budget=90.0, per_page=100):
        """Process one time-bounded chunk of the bulk sync.
        Returns True if everything is done, False if more work remains."""
        import json
        import time
        self.ensure_one()
        progress = json.loads(self.bulk_sync_progress or "{}")
        client = self.get_api_client()
        deadline = time.time() + time_budget
        _logger.info(
            "[BulkSync] %s: chunk start (budget %.0fs). Progress so far: %s",
            self.name, time_budget, progress,
        )

        for task_key, endpoint, model_name, extra in self._BULK_TASKS:
            if progress.get(task_key) == "done":
                continue
            page = progress.get(task_key) or 1
            _logger.info("[BulkSync] %s: task '%s' starting at page %s",
                         self.name, task_key, page)
            params = dict(extra)
            params["status"] = "any" if endpoint == "products" else None
            params = {k: v for k, v in params.items() if v is not None}

            while True:
                if time.time() > deadline:
                    progress[task_key] = page
                    self.write({"bulk_sync_progress": json.dumps(progress)})
                    self.env.cr.commit()
                    _logger.info(
                        "[BulkSync] %s: time budget reached on task '%s' page %s; "
                        "stopping chunk, will resume next run.",
                        self.name, task_key, page,
                    )
                    return False  # more work remains

                params["page"] = page
                params["per_page"] = per_page
                _t = time.time()
                result = client.get(endpoint, params)
                records = result.get("data", []) or []
                _logger.info(
                    "[BulkSync] %s: task '%s' page %s -> %d records in %.2fs",
                    self.name, task_key, page, len(records), time.time() - _t,
                )
                if not records:
                    progress[task_key] = "done"
                    _logger.info("[BulkSync] %s: task '%s' DONE (no more records)",
                                 self.name, task_key)
                    break

                self.env[model_name].syncing_from_wc(self, records, force=True)
                self.env.cr.commit()
                self.env.invalidate_all()

                if len(records) < per_page:
                    progress[task_key] = "done"
                    _logger.info("[BulkSync] %s: task '%s' DONE (last page %s)",
                                 self.name, task_key, page)
                    break
                page += 1
                progress[task_key] = page

            self.write({"bulk_sync_progress": json.dumps(progress)})
            self.env.cr.commit()

        # All tasks done.
        self.write({"bulk_sync_running": False})
        self.env.cr.commit()
        _logger.info("[BulkSync] %s: ALL TASKS COMPLETE.", self.name)
        return True

    @api.model
    def cron_bulk_sync(self):
        """Run a chunk of bulk sync for each backend; re-trigger if unfinished."""
        backends = self.search([("active", "=", True), ("bulk_sync_running", "=", True)])
        if not backends:
            _logger.info("[BulkSync] cron fired but no store is running a bulk sync.")
            return
        _logger.info("[BulkSync] cron run for %d store(s): %s",
                     len(backends), backends.mapped("name"))
        all_done = True
        for backend in backends:
            try:
                done = backend._bulk_run_chunk()
                all_done = all_done and done
            except Exception as exc:
                _logger.exception("[BulkSync] chunk failed for %s: %s", backend.name, exc)
        if not all_done:
            # More work remains → run again immediately (next background slot).
            _logger.info("[BulkSync] work remains -> re-triggering cron.")
            self.env.ref("ad_woocomerce_connector.cron_wc_bulk_sync").sudo()._trigger()
        else:
            _logger.info("[BulkSync] all stores finished; no re-trigger.")

    @api.model
    def cron_pull_customers(self, domain=None):
        for backend in self.search(domain or [("active", "=", True)]):
            try:
                backend._do_pull_customers()
                backend.customers_last_sync = datetime.now() - timedelta(seconds=SYNC_DELTA)
            except Exception as exc:
                _logger.exception("Cron: customer pull failed for %s: %s", backend.name, exc)

    @api.model
    def cron_pull_products(self, domain=None):
        for backend in self.search(domain or [("active", "=", True)]):
            try:
                # Pull ALL product types (simple, affiliate/external, variable).
                backend._do_pull_all_products()
                backend.products_last_sync = datetime.now() - timedelta(seconds=SYNC_DELTA)
            except Exception as exc:
                _logger.exception("Cron: product pull failed for %s: %s", backend.name, exc)

    @api.model
    def cron_pull_variable_products(self, domain=None):
        for backend in self.search(domain or [("active", "=", True)]):
            try:
                backend._do_pull_variable_products()
            except Exception as exc:
                _logger.exception("Cron: variable product pull failed for %s: %s", backend.name, exc)

    @api.model
    def cron_pull_orders(self, domain=None):
        for backend in self.search(domain or [("active", "=", True)]):
            try:
                backend._do_pull_orders()
                backend.orders_last_sync = datetime.now() - timedelta(seconds=SYNC_DELTA)
            except Exception as exc:
                _logger.exception("Cron: order pull failed for %s: %s", backend.name, exc)

    @api.model
    def cron_pull_categories(self, domain=None):
        for backend in self.search(domain or [("active", "=", True)]):
            try:
                backend._do_pull_categories()
            except Exception as exc:
                _logger.exception("Cron: category pull failed for %s: %s", backend.name, exc)

    @api.model
    def cron_pull_taxes(self, domain=None):
        for backend in self.search(domain or [("active", "=", True)]):
            try:
                backend._do_pull_taxes()
            except Exception as exc:
                _logger.exception("Cron: tax pull failed for %s: %s", backend.name, exc)

    @api.model
    def cron_pull_metadata(self, domain=None):
        for backend in self.search(domain or [("active", "=", True)]):
            try:
                backend._pull_shipping_methods()
                backend._pull_payment_methods()
            except Exception as exc:
                _logger.exception("Cron: metadata pull failed for %s: %s", backend.name, exc)

    @api.model
    def cron_push_stock(self, domain=None):
        for backend in self.search(domain or [("active", "=", True), ("push_stock_to_store", "=", True)]):
            try:
                bindings = self.env["wc.product.link"].search([
                    ("backend_id", "=", backend.id),
                    ("external_id", "!=", False),
                    ("wc_manage_stock", "=", True),
                ])
                bindings.push_stock_to_store()
            except Exception as exc:
                _logger.exception("Cron: stock push failed for %s: %s", backend.name, exc)

    @api.model
    def cron_push_order_statuses(self, domain=None):
        for backend in self.search(domain or [("active", "=", True)]):
            try:
                backend._do_push_order_statuses()
            except Exception as exc:
                _logger.exception("Cron: order status push failed for %s: %s", backend.name, exc)

    @api.model
    def cron_push_paid_orders(self, domain=None):
        for backend in self.search(domain or [("active", "=", True)]):
            try:
                backend._do_push_paid_orders()
            except Exception as exc:
                _logger.exception("Cron: paid order push failed for %s: %s", backend.name, exc)

    @staticmethod
    def _notify(message: str) -> dict:
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "WooCommerce Sync",
                "message": message,
                "type": "success",
                "sticky": False,
            },
        }
