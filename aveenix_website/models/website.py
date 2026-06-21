from odoo import fields, models
from odoo.http import request

_LOCATION_SESSION_KEY = 'av_user_country_id'


class Website(models.Model):
    _inherit = 'website'

    def _get_geoip_country_code(self):
        """Prefer the browser-detected country stored in session over GeoIP.

        The header "Enable location" flow reverse-geocodes the visitor's
        browser location and saves the matching res.country id in the session
        (av_user_country_id). Using it here makes Odoo's pricelist selection
        follow the detected location, not just the IP-based GeoIP guess.
        """
        if request:
            country_id = request.session.get(_LOCATION_SESSION_KEY)
            if country_id:
                country = self.env['res.country'].sudo().browse(country_id)
                if country.exists() and country.code:
                    return country.code
        return super()._get_geoip_country_code()

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
