from odoo import api, fields, models
from odoo.exceptions import UserError


class WooOrderPushWizard(models.TransientModel):
    _name = "wc.order.push.wizard"
    _description = "Push Sale Orders to a WooCommerce Store"

    backend_id = fields.Many2one(
        comodel_name="wc.store",
        string="WooCommerce Store",
        required=True,
        domain=[("active", "=", True)],
        default=lambda self: self.env["wc.store"].search(
            [("active", "=", True)], limit=1
        ),
    )
    order_ids = fields.Many2many(
        comodel_name="sale.order",
        string="Orders",
    )

    def action_push(self):
        self.ensure_one()
        if not self.order_ids:
            raise UserError("No orders selected to push.")
        return self.order_ids._push_to_backend(self.backend_id)
