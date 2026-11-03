import logging

import requests

from odoo import api, models

_logger = logging.getLogger(__name__)

PARAM_API_KEY = 'aveenix_connect.google_places_api_key'
SEARCH_TEXT_URL = 'https://places.googleapis.com/v1/places:searchText'
# Just enough for the team to pick the right place. Places API (New) bills by
# the fields asked for, and none of this is stored: only the chosen place ID.
SEARCH_FIELD_MASK = 'places.id,places.displayName,places.formattedAddress'
_TIMEOUT = 15


class ConnectGoogleClient(models.AbstractModel):
    """Server-side Google Places API (New) client, used by the backend to
    find the Google place a listing should link to. Visitors never reach it:
    the website loads Google details in the browser with the Maps key."""

    _name = 'connect.google.client'
    _description = 'Aveenix Connect Google Places Client'

    @api.model
    def _api_key(self):
        return (self.env['ir.config_parameter'].sudo().get_param(PARAM_API_KEY) or '').strip()

    @api.model
    def _is_configured(self):
        return bool(self._api_key())

    @api.model
    def search_text(self, query, limit=10):
        """Places matching a free-text query ("Joe's Pizza, Auckland") as a
        list of {'place_id', 'name', 'address'}. Returns [] when no key is
        set or on any network / API error, which is logged."""
        key = self._api_key()
        query = (query or '').strip()
        if not key or not query:
            return []
        try:
            response = requests.post(
                SEARCH_TEXT_URL,
                json={'textQuery': query, 'pageSize': limit},
                headers={'X-Goog-Api-Key': key, 'X-Goog-FieldMask': SEARCH_FIELD_MASK},
                timeout=_TIMEOUT,
            )
        except requests.RequestException as e:
            _logger.warning('Google Places search failed: %s', e)
            return []
        if response.status_code != 200:
            _logger.warning('Google Places search returned HTTP %s: %s',
                            response.status_code, response.text[:2000])
            return []
        try:
            places = response.json().get('places') or []
        except ValueError:
            _logger.warning('Google Places search returned a non-JSON body: %s', response.text[:2000])
            return []
        return [{
            'place_id': place['id'],
            'name': (place.get('displayName') or {}).get('text') or '',
            'address': place.get('formattedAddress') or '',
        } for place in places if place.get('id')]
