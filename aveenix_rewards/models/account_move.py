from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _reverse_moves(self, default_values_list=None, cancel=False):
        """Auto-reverse approved rewards when a credit note is created."""
        res = super()._reverse_moves(
            default_values_list=default_values_list, cancel=cancel
        )
        for move in self:
            if move.move_type not in ('out_invoice', 'out_refund'):
                continue
            sale_orders = move.line_ids.sale_line_ids.order_id
            if not sale_orders:
                # Also check via invoice_origin name
                sale_orders = self.env['sale.order'].search([
                    ('name', '=', move.invoice_origin)
                ])
            for order in sale_orders:
                approved_rewards = order.reward_record_ids.filtered(
                    lambda r: r.state == 'approved'
                )
                for reward in approved_rewards:
                    try:
                        reward.button_reverse()
                    except Exception as e:
                        reward.message_post(body=f'Auto-reversal failed: {e}')
        return res
