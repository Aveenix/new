from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    reward_config_id = fields.Many2one(
        comodel_name='aveenix.reward.config',
        string='Reward Agreement',
        help='Specific reward agreement for this customer. Leave empty to use the default agreement set in Settings.',
    )
    affiliated = fields.Boolean(
        string='Affiliated',
        help='Mark this partner as an affiliate for reward distribution purposes.',
    )
