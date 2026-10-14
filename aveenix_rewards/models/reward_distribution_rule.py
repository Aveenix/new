from odoo import api, fields, models
from odoo.exceptions import ValidationError


class AveenixRewardDistributionRule(models.Model):
    _name = 'aveenix.reward.distribution.rule'
    _description = 'Reward Distribution Rule'
    _order = 'sequence'

    config_id = fields.Many2one(
        comodel_name='aveenix.reward.config',
        required=True,
        ondelete='cascade',
    )
    sequence = fields.Integer(default=10)

    participant_type = fields.Selection(
        selection=[
            ('customer', 'Customer'),
            ('affiliate', 'Affiliate Partner'),
            ('smb', 'SMB Partner'),
            ('platform', 'Platform (Internal)'),
        ],
        required=True,
        string='Participant Type',
    )
    # Optional: pin to a specific partner; if empty, partner is derived at reward time
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Fixed Partner (optional)',
        help='Leave empty to derive partner from the sale order (customer, affiliate partner, SMB partner).',
    )
    percentage = fields.Float(string='%', required=True)

    @api.constrains('percentage')
    def _check_percentage(self):
        for rec in self:
            if not (0 < rec.percentage <= 100):
                raise ValidationError('Percentage must be between 0 and 100.')
