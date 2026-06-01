from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    default_reward_config_id = fields.Many2one(
        comodel_name='aveenix.reward.config',
        string='Default Reward Agreement',
        help='Fallback reward agreement used when a customer has no specific agreement assigned.',
    )
    payment_gateway_config_ids = fields.One2many(
        comodel_name='aveenix.payment.gateway.config',
        inverse_name='company_id',
        string='Payment Gateway Configurations',
    )
    reward_point_value = fields.Float(
        string='Point Value for Payout',
        default=1.0,
        digits=(16, 4),
        help='Monetary value of 1 reward point when paying out to customer. '
             'e.g. 1.0 means 1 point = 1 unit of payout currency. '
             '0.5 means 1 point = 0.50 currency units.',
    )
