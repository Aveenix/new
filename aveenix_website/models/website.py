from odoo import fields, models


class Website(models.Model):
    _inherit = 'website'

    aveenix_primary_color = fields.Char(
        string='Primary Color',
        default='#CC0000',
        help='Main brand color (header buttons, badges, search button). Hex value e.g. #CC0000',
    )
    aveenix_accent_color = fields.Char(
        string='Accent Color',
        default='#FFB300',
        help='Accent / highlight color (CTA buttons, stars, promo). Hex value e.g. #FFB300',
    )
