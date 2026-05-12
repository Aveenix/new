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
