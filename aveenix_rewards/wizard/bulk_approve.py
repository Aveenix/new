from odoo import fields, models


class AveenixRewardBulkApprove(models.TransientModel):
    _name = 'aveenix.reward.bulk.approve'
    _description = 'Bulk Approve Rewards'

    reward_ids = fields.Many2many(
        comodel_name='aveenix.reward.record',
        string='Rewards to Approve',
        domain=[('state', '=', 'pending')],
    )

    def action_approve_all(self):
        for reward in self.reward_ids:
            try:
                reward.button_approve()
            except Exception as e:
                reward.message_post(body=f'Approval failed: {e}')
        return {'type': 'ir.actions.act_window_close'}
