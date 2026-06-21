import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

SYNC_ACTIONS = [
    ("pull_metadata", "Refresh Metadata (Shipping & Payment Methods)"),
    ("pull_categories", "Pull Product Categories"),
    ("pull_tags", "Pull Product Tags"),
    ("pull_attributes", "Pull Product Attributes"),
    ("pull_taxes", "Pull Tax Rates"),
    ("pull_customers", "Pull Customers"),
    ("pull_single_product", "Fetch Single Product (by ID)"),
    ("pull_all_products", "Pull All Products"),
    ("pull_products", "Pull Simple Products"),
    ("pull_affiliate_products", "Pull Affiliate Products"),
    ("pull_variable_products", "Pull Variable Products"),
    ("pull_orders", "Pull Orders"),
    ("push_stock", "Push Stock Quantities to WooCommerce"),
    ("push_paid_orders", "Push Paid Orders to WooCommerce"),
    ("push_order_statuses", "Push Order Fulfillment Statuses"),
]

class WooSyncWizard(models.TransientModel):

    _name = "wc.sync.wizard"
    _description = "WooCommerce Sync Wizard"

    backend_id = fields.Many2one(
        comodel_name="wc.store",
        string="WooCommerce Store",
        required=True,
        domain=[("active", "=", True)],
        default=lambda self: self._default_backend(),
    )
    sync_action = fields.Selection(
        selection=SYNC_ACTIONS,
        string="What to Sync",
        required=True,
        default="pull_orders",
    )
    force_resync = fields.Boolean(
        string="Force Re-sync",
        default=True,
        help="Re-process records even if they appear up to date. "
             "On by default for manual syncs; untick for a fast incremental "
             "pull of only records changed since the last sync.",
    )
    max_records = fields.Integer(
        string="Max Records to Fetch", default=0,
        help="Stop this sync after fetching this many records (0 = no limit). "
             "Use to pull large catalogs in smaller chunks and avoid "
             "overloading the server.",
    )
    single_product_id = fields.Char(
        string="WooCommerce Product ID",
        help="The numeric WooCommerce product ID to fetch "
             "(used with 'Fetch Single Product').",
    )
    start_page = fields.Integer(
        string="Start Page", default=1,
        help="API page to start fetching from (100 records per page). "
             "Use with 'Max Records' to pull a big catalog over several runs: "
             "run 1 = page 1, run 2 = next page after where run 1 stopped, etc.",
    )
    result_summary = fields.Text(
        string="Result", readonly=True,
    )
    state = fields.Selection(
        [("draft", "Configure"), ("done", "Complete")],
        default="draft",
    )

    @api.model
    def _default_backend(self):
        return self.env["wc.store"].search(
            [("active", "=", True)], limit=1
        )

    def action_run_sync(self):
        self.ensure_one()
        # no_commit: never cr.commit() mid-request. Committing inside the web
        # worker breaks the request transaction and recycles the worker
        # ("Connection lost. Trying to reconnect..."). The whole manual run is
        # one transaction instead.
        backend = self.backend_id.with_context(
            return_raw_results=True,
            wc_max_records=self.max_records or 0,
            wc_start_page=self.start_page or 1,
            # Stop well under the request watchdog (limit_time_real, default
            # 120s) so a large manual pull ends gracefully instead of killing
            # the web worker. Re-run to continue from the last sync point.
            wc_time_budget=90,
            no_commit=True,
        )
        action = self.sync_action
        force = self.force_resync

        action_map = {
            "pull_metadata": backend.action_pull_metadata,
            "pull_categories": lambda: backend._do_pull_categories(force),
            "pull_tags": lambda: backend._do_pull_tags(force),
            "pull_attributes": lambda: backend._do_pull_attributes(force),
            "pull_taxes": lambda: backend._do_pull_taxes(force),
            "pull_customers": lambda: backend._do_pull_customers(force),
            "pull_single_product": lambda: backend._do_pull_single_product(self.single_product_id, force),
            "pull_all_products": lambda: backend._do_pull_all_products(force),
            "pull_products": lambda: backend._do_pull_products(force),
            "pull_affiliate_products": lambda: backend._do_pull_affiliate_products(force),
            "pull_variable_products": lambda: backend._do_pull_variable_products(force),
            "pull_orders": lambda: backend._do_pull_orders(force),
            "push_stock": backend.action_push_stock,
            "push_paid_orders": backend.action_push_paid_orders,
            "push_order_statuses": backend.action_push_order_statuses,
        }

        fn = action_map.get(action)
        if not fn:
            raise UserError(_("Unknown sync action: %s") % action)

        try:
            res = fn()
            if isinstance(res, dict) and any(k in res for k in ("created", "updated", "skipped", "failed")):
                created = res.get("created", 0)
                updated = res.get("updated", 0)
                skipped = res.get("skipped", 0)
                failed = res.get("failed", 0)
                errors = res.get("errors", [])
                
                label = dict(SYNC_ACTIONS).get(action, action)
                summary_lines = [
                    _("Sync Action: %s") % label,
                    _("Status: Completed"),
                    _("- Created: %d") % created,
                    _("- Updated: %d") % updated,
                    _("- Skipped: %d") % skipped,
                    _("- Failed: %d") % failed,
                ]
                if errors:
                    summary_lines.append(_("\nErrors / Warnings:"))
                    for err in errors[:50]:
                        summary_lines.append("  • %s" % err)
                    if len(errors) > 50:
                        summary_lines.append("  • ... and %d more errors" % (len(errors) - 50))
                summary = "\n".join(summary_lines)
            else:
                label = dict(SYNC_ACTIONS).get(action, action)
                summary = _("✓ '%s' completed successfully for store: %s") % (label, backend.name)
        except Exception as exc:
            _logger.exception("Manual sync failed: %s", exc)
            summary = _("✗ Sync failed: %s") % str(exc)

        self.write({"result_summary": summary, "state": "done"})
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_close(self):
        return {"type": "ir.actions.act_window_close"}
