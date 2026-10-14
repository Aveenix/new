from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    aveenix_product_type = fields.Selection(
        selection=[
            ('dropship', 'Dropship'),
            ('standard', 'Standard'),
            ('affiliate', 'Affiliate'),
        ],
        string='Aveenix Product Type',
        help='Controls how rewards are calculated. Dropship/Standard: margin-based. Affiliate: commission-received-based.',
    )
    reward_pool_perc = fields.Float(
        string='Reward Pool %',
        default=0.0,
        help='Percentage of margin (or affiliate commission) allocated as reward pool for this product. Set by admin per product.',
    )
