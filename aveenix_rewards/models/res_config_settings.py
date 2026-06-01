from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    reward_config_id = fields.Many2one(
        related='company_id.default_reward_config_id',
        string='Default Reward Agreement',
        readonly=False,
        help='Applied to all customers who have no specific agreement assigned on their partner record.',
    )
    reward_point_value = fields.Float(
        related='company_id.reward_point_value',
        string='Point Value for Payout',
        readonly=False,
        digits=(16, 4),
    )
