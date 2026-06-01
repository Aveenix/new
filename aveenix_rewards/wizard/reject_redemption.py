from odoo import fields, models
from odoo.exceptions import UserError


class AveenixRejectRedemption(models.TransientModel):
    _name = 'aveenix.reject.redemption'
    _description = 'Reject Redemption Request'

    redemption_id = fields.Many2one(
        comodel_name='aveenix.reward.redemption',
        string='Redemption Request',
        required=True,
    )
    reason = fields.Text(string='Rejection Reason', required=True)

    def action_confirm_reject(self):
        self.ensure_one()
        rec = self.redemption_id
        if rec.state not in ('submitted', 'approved'):
            raise UserError('Cannot reject a request in this state.')
        card = rec.loyalty_card_id
        if card:
            card.points += rec.points_to_redeem
            self.env['loyalty.history'].sudo().create({
                'card_id': card.id,
                'description': f'Refund: redemption request rejected ({rec.name})',
                'issued': rec.points_to_redeem,
                'used': 0.0,
            })
        rec.write({
            'state': 'rejected',
            'rejection_reason': self.reason,
        })
        return {'type': 'ir.actions.act_window_close'}
