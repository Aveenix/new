from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    available_country_ids = fields.Many2many(
        'res.country',
        'product_template_country_rel',
        'product_tmpl_id',
        'country_id',
        string='Available In Countries',
        help='Leave empty = available everywhere. Set countries to restrict visibility on website.',
    )

    is_sponsored = fields.Boolean(
        string='Sponsored Ad',
        default=False,
        help='Show this product in the sponsored advertisement slider on cart/checkout pages.',
    )
    sponsor_rank = fields.Integer(
        string='Sponsor Rank',
        default=0,
        help='Higher value = shown first in the sponsored ad slider. Paid placement lever.',
    )
