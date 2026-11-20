import logging
import re

import requests

from odoo import api, models

_logger = logging.getLogger(__name__)

PARAM_API_KEY = 'aveenix_connect.nzbn_api_key'
API_URL = 'https://api.business.govt.nz/gateway/nzbn/v5'
# entityStatusCode of a business currently on the register.
STATUS_REGISTERED = '50'
# Addresses to show, best first: where the business works before where it
# receives post or legal documents.
_ADDRESS_TYPES = ('PHYSICAL', 'OFFICE', 'DELIVERY', 'SERVICE', 'REGISTERED', 'POSTAL')
_TIMEOUT = 20
NZBN_RE = re.compile(r'^\d{13}$')


def _current(items):
    """Entries of a register list still in effect (no end date)."""
    return [item for item in items or [] if isinstance(item, dict) and not item.get('endDate')]


def _tidy_name(name):
    """Register names are in capitals ("KIWI PLUMBING LIMITED"); show them in
    title case but keep acronyms without vowels (NZ, LTD) as they are."""
    if not name or not name.isupper():
        return name
    return ' '.join(
        word if not re.search(r'[AEIOUY]', word) else word.capitalize()
        for word in name.split()
    )


class ConnectNzbnClient(models.AbstractModel):
    """Server-side client for the NZBN API (New Zealand Business Number
    register, run by MBIE). Only public register data is read, with the
    subscription key from api.business.govt.nz."""

    _name = 'connect.nzbn.client'
    _description = 'Aveenix Connect NZBN Client'

    @api.model
    def _api_key(self):
        return (self.env['ir.config_parameter'].sudo().get_param(PARAM_API_KEY) or '').strip()

    @api.model
    def _is_configured(self):
        return bool(self._api_key())

    @api.model
    def _get(self, path, params=None):
        """GET a register resource: its JSON, {} when it does not exist, or
        None when there is no key or the call failed (logged)."""
        key = self._api_key()
        if not key:
            return None
        try:
            response = requests.get(
                API_URL + path, params=params, timeout=_TIMEOUT,
                headers={'Ocp-Apim-Subscription-Key': key, 'Accept': 'application/json'},
            )
        except requests.RequestException as e:
            _logger.warning('NZBN API call %s failed: %s', path, e)
            return None
        if response.status_code == 404:
            return {}
        if response.status_code != 200:
            _logger.warning('NZBN API call %s returned HTTP %s: %s',
                            path, response.status_code, response.text[:2000])
            return None
        try:
            return response.json()
        except ValueError:
            _logger.warning('NZBN API call %s returned a non-JSON body: %s', path, response.text[:2000])
            return None

    @api.model
    def search(self, term, page=0, page_size=50, industry_code=None):
        """One page of register entries matching `term`, as
        ({'items': [{'nzbn', 'name', 'status', 'registered'}], 'total': n}),
        or None when the register could not be searched."""
        term = (term or '').strip()
        if not term:
            return {'items': [], 'total': 0}
        params = {'search-term': term, 'page': page, 'page-size': page_size}
        if industry_code:
            params['industry-code'] = industry_code.strip()
        result = self._get('/entities', params)
        if result is None:
            return None
        items = [{
            'nzbn': item['nzbn'],
            'name': _tidy_name(item.get('entityName') or ''),
            'status': item.get('entityStatusDescription') or item.get('entityStatusCode') or '',
            'registered': self.is_registered(item),
        } for item in result.get('items') or [] if item.get('nzbn')]
        return {'items': items, 'total': result.get('totalItems') or len(items)}

    @api.model
    def get_entity(self, nzbn):
        """The full register entry of `nzbn`: a dict, {} when the number is
        not on the register, or None when the register could not be reached."""
        nzbn = (nzbn or '').strip()
        if not NZBN_RE.match(nzbn):
            return {}
        return self._get('/entities/%s' % nzbn)

    @api.model
    def is_registered(self, entity):
        return str(entity.get('entityStatusCode') or '') == STATUS_REGISTERED

    @api.model
    def listing_values(self, entity):
        """connect.business values from a register entry; only what the entry
        actually has, so nothing already on a listing is blanked."""
        trading = _current(entity.get('tradingNames'))
        values = {
            'nzbn': entity.get('nzbn'),
            'name': _tidy_name((trading[0].get('name') if trading else None) or entity.get('entityName')),
        }

        addresses = entity.get('addresses') or []
        if isinstance(addresses, dict):
            addresses = addresses.get('addressList') or []
        addresses = _current(addresses)
        addresses.sort(key=lambda a: _ADDRESS_TYPES.index(a['addressType'])
                       if a.get('addressType') in _ADDRESS_TYPES else len(_ADDRESS_TYPES))
        if addresses:
            address = addresses[0]
            lines = [address.get(key) for key in ('address2', 'address3', 'address4') if address.get(key)]
            country = self.env['res.country'].search(
                [('code', '=', address.get('countryCode') or 'NZ')], limit=1)
            values.update({
                'street': address.get('address1'),
                'street2': lines[0] if len(lines) > 1 else None,
                'city': lines[-1] if lines else None,
                'zip': address.get('postCode'),
                'country_id': country.id or None,
            })

        phones = _current(entity.get('phoneNumbers'))
        if phones:
            phone = phones[0]
            values['phone'] = ' '.join(filter(None, [
                '+%s' % phone['phoneCountryCode'] if phone.get('phoneCountryCode') else None,
                phone.get('phoneAreaCode'), phone.get('phoneNumber'),
            ]))
        emails = _current(entity.get('emailAddresses'))
        if emails:
            values['email'] = emails[0].get('emailAddress')
        websites = _current(entity.get('websites'))
        url = (websites[0].get('url') or '').strip() if websites else ''
        if url:
            values['business_url'] = url if url.startswith(('http://', 'https://')) else 'https://' + url
        industries = _current(entity.get('industryClassifications'))
        if industries:
            values['services'] = '\n'.join(
                i['classificationDescription'] for i in industries if i.get('classificationDescription'))
        return {field: value for field, value in values.items() if value}
