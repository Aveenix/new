from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    aveenix_welcome_offer_optin = fields.Boolean(
        string='Welcome Offer Opt-in',
        help='Set when this contact submitted their email through the website '
             '"$20 off your first order" footer promo.',
    )
