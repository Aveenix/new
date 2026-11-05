from odoo import fields, models

from .connect_google_client import PARAM_API_KEY


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    connect_google_places_api_key = fields.Char(
        string='Google Places API Key (server)',
        config_parameter=PARAM_API_KEY,
    )
    # The browser key lives on the core website field, so the Maps Embed
    # iframe and the Maps JavaScript API share it with the rest of Odoo.
    connect_google_maps_api_key = fields.Char(
        string='Google Maps API Key (browser)',
        related='website_id.google_maps_api_key',
        readonly=False,
    )
