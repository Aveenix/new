"""Client for the CJ Affiliate (Commission Junction) publisher APIs.

    CJ here is CJ Affiliate / Commission Junction, cj.com — the affiliate
    network. It is NOT CJdropshipping.com, the product supplier wired up by the
    separate `aveenix_cj_dropshipping` module. The two share nothing but a name.

CJ exposes its publisher surface over two transports, and this client uses each
where CJ actually offers it rather than forcing one style:

  * GraphQL (``Authorization: Bearer <PAT>``, POST a document)
      - ``shoppingProducts``        product discovery, on ads.api.cj.com
      - ``promotionalProperties``   the property id Link Search needs
      - ``publisherCommissions``    revenue, on commissions.api.cj.com
  * REST v2, XML responses — the long-stable publisher endpoints
      - ``/v2/advertiser-lookup``   which programs we have joined
      - ``/v2/link-search``         text/banner links for an advertiser

Every call needs the Personal Access Token from developers.cj.com; most also
need the publisher company id (CID). Both are read from system parameters at
call time and never leave the server.

A failed or schema-mismatched call returns None or [] and logs the response
body verbatim. That is deliberate: CJ's GraphQL reference is a JavaScript app
that cannot be read without an account, so these documents are written to the
documented argument names and the first live run is what confirms them. When a
field name is wrong CJ answers with an ``errors`` array naming it, which the log
surfaces directly instead of failing silently.
"""

import logging

import requests
from lxml import etree

from odoo import _, api, models
from odoo.exceptions import UserError

from .affiliate_network import NETWORK_CJ

_logger = logging.getLogger(__name__)

PARAM_TOKEN = 'aveenix_affiliate.cj_token'
PARAM_COMPANY_ID = 'aveenix_affiliate.cj_company_id'
PARAM_WEBSITE_ID = 'aveenix_affiliate.cj_website_id'
PARAM_ADS_ENDPOINT = 'aveenix_affiliate.cj_ads_endpoint'
PARAM_COMMISSION_ENDPOINT = 'aveenix_affiliate.cj_commission_endpoint'

DEFAULT_ADS_ENDPOINT = 'https://ads.api.cj.com/query'
DEFAULT_COMMISSION_ENDPOINT = 'https://commissions.api.cj.com/query'
ADVERTISER_LOOKUP_URL = 'https://advertiser-lookup.api.cj.com/v2/advertiser-lookup'
LINK_SEARCH_URL = 'https://link-search.api.cj.com/v2/link-search'

_TIMEOUT = 30

# Entities and network lookups are off: the payload is parsed, not trusted.
_XML_PARSER = etree.XMLParser(resolve_entities=False, no_network=True)

_PRODUCTS_QUERY = """
query AveenixShoppingProducts($companyId: ID!, $keywords: [String!], $partnerIds: [ID!], $limit: Int, $offset: Int) {
  shoppingProducts(companyId: $companyId, keywords: $keywords, partnerIds: $partnerIds, limit: $limit, offset: $offset) {
    totalCount
    count
    resultList {
      id
      advertiserId
      advertiserName
      brand
      title
      description
      link
      imageLink
      availability
      price { amount currency }
      salePrice { amount currency }
    }
  }
}
"""

# `companyId` is the argument shoppingProducts documents; if CJ names it
# `publisherId` here instead, the errors array says so on the first run.
_PROPERTIES_QUERY = """
query AveenixPromotionalProperties($companyId: ID!) {
  promotionalProperties(companyId: $companyId) {
    resultList {
      id
      name
      type
      status
      url
    }
  }
}
"""

_COMMISSIONS_QUERY = """
query AveenixPublisherCommissions($publisherIds: [String!]!, $since: Timestamp!, $before: Timestamp!) {
  publisherCommissions(forPublishers: $publisherIds, sincePostingDate: $since, beforePostingDate: $before) {
    count
    payloadComplete
    records {
      commissionId
      advertiserId
      advertiserName
      orderId
      actionStatus
      actionType
      saleAmountUsd
      pubCommissionAmountUsd
      postingDate
      eventDate
      shopperId
    }
  }
}
"""


def _money(value):
    """Return (amount, currency) from CJ money, dict-shaped or scalar."""
    if isinstance(value, dict):
        try:
            amount = float(value.get('amount') or 0.0)
        except (TypeError, ValueError):
            amount = 0.0
        return amount, (value.get('currency') or '').upper()
    try:
        return float(value or 0.0), ''
    except (TypeError, ValueError):
        return 0.0, ''


def _text(node, tag):
    """Text of `tag` under `node`, '' when missing — CJ omits empty elements."""
    found = node.find(tag)
    if found is None or found.text is None:
        return ''
    return found.text.strip()


class AffiliateCjClient(models.AbstractModel):
    _name = 'affiliate.cj.client'
    _description = 'CJ Affiliate (Commission Junction) Publisher API Client'

    # ── Credentials ──────────────────────────────────────────────────────

    @api.model
    def _av_credentials(self):
        """Token, publisher CID and promotional property id, straight from config.

        Read with sudo() because discovery runs in cron and in a public-request
        context, neither of which may read system parameters directly. The values
        are used to sign requests here and are never returned to a caller that
        could put them in a template or a response.
        """
        params = self.env['ir.config_parameter'].sudo()
        return {
            'token': (params.get_param(PARAM_TOKEN) or '').strip(),
            'company_id': (params.get_param(PARAM_COMPANY_ID) or '').strip(),
            'website_id': (params.get_param(PARAM_WEBSITE_ID) or '').strip(),
        }

    @api.model
    def _av_is_configured(self):
        creds = self._av_credentials()
        return bool(creds['token'] and creds['company_id'])

    # ── Transports ───────────────────────────────────────────────────────

    @api.model
    def _av_graphql(self, endpoint, document, variables, label):
        """POST a GraphQL document. Returns the `data` dict, or None on failure."""
        creds = self._av_credentials()
        if not creds['token']:
            _logger.info('CJ %s skipped: no Personal Access Token configured.', label)
            return None
        try:
            response = requests.post(
                endpoint,
                headers={
                    'Authorization': 'Bearer %s' % creds['token'],
                    'Content-Type': 'application/json',
                },
                json={'query': document, 'variables': variables},
                timeout=_TIMEOUT,
            )
        except requests.RequestException as error:
            _logger.warning('CJ %s request failed: %s', label, error)
            return None
        if response.status_code != 200:
            # Body verbatim: CJ explains auth and quota problems in it.
            _logger.warning(
                'CJ %s returned HTTP %s: %s', label, response.status_code, response.text[:2000],
            )
            return None
        try:
            payload = response.json()
        except ValueError:
            _logger.warning('CJ %s returned non-JSON: %s', label, response.text[:2000])
            return None
        if payload.get('errors'):
            # The one message that tells us a document needs correcting.
            _logger.warning('CJ %s GraphQL errors: %s', label, payload['errors'])
            return None
        return payload.get('data') or None

    @api.model
    def _av_rest_xml(self, url, params, label):
        """GET a CJ REST v2 endpoint. Returns the parsed root, or None on failure."""
        creds = self._av_credentials()
        if not creds['token']:
            _logger.info('CJ %s skipped: no Personal Access Token configured.', label)
            return None
        try:
            response = requests.get(
                url,
                headers={'Authorization': 'Bearer %s' % creds['token']},
                params=params,
                timeout=_TIMEOUT,
            )
        except requests.RequestException as error:
            _logger.warning('CJ %s request failed: %s', label, error)
            return None
        if response.status_code != 200:
            _logger.warning(
                'CJ %s returned HTTP %s: %s', label, response.status_code, response.text[:2000],
            )
            return None
        try:
            return etree.fromstring(response.content, parser=_XML_PARSER)
        except etree.XMLSyntaxError as error:
            _logger.warning('CJ %s returned unparseable XML (%s): %s',
                            label, error, response.text[:2000])
            return None

    @api.model
    def _av_endpoint(self, param, default):
        value = self.env['ir.config_parameter'].sudo().get_param(param)
        return (value or default).strip()

    # ── Product Feed (GraphQL) ───────────────────────────────────────────

    @api.model
    def _av_search_products(self, keywords, advertiser_ids=None, limit=20):
        """Shopping products matching `keywords`, as normalised offer dicts."""
        creds = self._av_credentials()
        if not creds['company_id'] or not keywords:
            return []
        variables = {
            'companyId': creds['company_id'],
            'keywords': list(keywords)[:10],
            'limit': limit,
            'offset': 0,
        }
        # Omitted entirely when empty: CJ reads "no partnerIds" as "every feed
        # I am joined to", which is what article-driven discovery wants.
        if advertiser_ids:
            variables['partnerIds'] = [str(aid) for aid in advertiser_ids]
        data = self._av_graphql(
            self._av_endpoint(PARAM_ADS_ENDPOINT, DEFAULT_ADS_ENDPOINT),
            _PRODUCTS_QUERY, variables, 'shoppingProducts',
        )
        if not data:
            return []
        result = (data.get('shoppingProducts') or {}).get('resultList') or []
        offers = []
        for row in result:
            link = (row.get('link') or '').strip()
            if not link:
                continue
            amount, currency = _money(row.get('salePrice') or row.get('price'))
            offers.append({
                'network': NETWORK_CJ,
                'source': 'cj_product',
                'external_id': str(row.get('id') or '')[:128],
                'name': (row.get('title') or '').strip()[:255],
                'description': (row.get('description') or '').strip(),
                'image_url': (row.get('imageLink') or '').strip(),
                'target_url': link,
                'price': amount,
                'currency_code': currency,
                'advertiser_external_id': str(row.get('advertiserId') or '').strip(),
                'advertiser_name': (row.get('advertiserName') or '').strip(),
                'keywords': ', '.join(
                    term for term in [row.get('brand'), row.get('title')] if term
                )[:512],
            })
        return offers

    # ── Link Search (REST v2) ────────────────────────────────────────────

    @api.model
    def _av_search_links(self, keywords, limit=20):
        """Text/banner links matching `keywords`.

        The fallback for advertisers that run no product feed, which is why a
        topical article can still be monetised when Product Feed comes back
        empty. Needs the promotional property id (`website-id`) CJ issues for
        aveenix.com — hence Promotional Properties being worth a call at all.
        """
        creds = self._av_credentials()
        if not creds['website_id'] or not keywords:
            return []
        root = self._av_rest_xml(LINK_SEARCH_URL, {
            'website-id': creds['website_id'],
            'advertiser-ids': 'joined',
            'keywords': ' '.join(list(keywords)[:5]),
            'records-per-page': min(limit, 100),
            'page-number': 1,
        }, 'link-search')
        if root is None:
            return []
        offers = []
        for node in root.iter('link'):
            click_url = _text(node, 'clickUrl') or _text(node, 'click-url')
            if not click_url:
                continue
            offers.append({
                'network': NETWORK_CJ,
                'source': 'cj_link',
                'external_id': _text(node, 'link-id')[:128],
                'name': _text(node, 'link-name')[:255],
                'description': _text(node, 'description'),
                'image_url': '',
                'target_url': click_url,
                'price': 0.0,
                'currency_code': '',
                'advertiser_external_id': _text(node, 'advertiser-id'),
                'advertiser_name': _text(node, 'advertiser-name'),
                'commission_note': _text(node, 'sale-commission') or _text(node, 'lead-commission'),
                'keywords': _text(node, 'keywords')[:512] or _text(node, 'link-name')[:512],
            })
        return offers

    # ── Advertiser Lookup (REST v2) ──────────────────────────────────────

    @api.model
    def _av_list_advertisers(self, limit=100):
        """Advertisers whose programs Aveenix has joined."""
        creds = self._av_credentials()
        if not creds['company_id']:
            return []
        root = self._av_rest_xml(ADVERTISER_LOOKUP_URL, {
            'requestor-cid': creds['company_id'],
            'advertiser-ids': 'joined',
            'records-per-page': min(limit, 100),
            'page-number': 1,
        }, 'advertiser-lookup')
        if root is None:
            return []
        advertisers = []
        for node in root.iter('advertiser'):
            external_id = _text(node, 'advertiser-id')
            if not external_id:
                continue
            actions = node.find('actions')
            commission = ''
            if actions is not None:
                first = actions.find('action')
                if first is not None:
                    commission = _text(first, 'commission') or _text(first, 'name')
            advertisers.append({
                'network': NETWORK_CJ,
                'external_id': external_id,
                'name': _text(node, 'advertiser-name') or external_id,
                'commission_note': commission,
                'program_url': _text(node, 'program-url'),
                'account_status': _text(node, 'account-status'),
            })
        return advertisers

    # ── Promotional Properties (GraphQL) ─────────────────────────────────

    @api.model
    def _av_list_promotional_properties(self):
        """Aveenix's registered promotional properties, for picking a website id."""
        creds = self._av_credentials()
        if not creds['company_id']:
            raise UserError(_(
                'Set the CJ Personal Access Token and Publisher Company ID (CID) '
                'in Website Settings before loading promotional properties.'
            ))
        data = self._av_graphql(
            self._av_endpoint(PARAM_ADS_ENDPOINT, DEFAULT_ADS_ENDPOINT),
            _PROPERTIES_QUERY, {'companyId': creds['company_id']},
            'promotionalProperties',
        )
        if not data:
            return []
        return (data.get('promotionalProperties') or {}).get('resultList') or []

    # ── Commission Detail (GraphQL) ──────────────────────────────────────

    @api.model
    def _av_fetch_commissions(self, since, before):
        """Commission records posted in [since, before). Timestamps are ISO-8601 Z."""
        creds = self._av_credentials()
        if not creds['company_id']:
            return []
        data = self._av_graphql(
            self._av_endpoint(PARAM_COMMISSION_ENDPOINT, DEFAULT_COMMISSION_ENDPOINT),
            _COMMISSIONS_QUERY,
            {
                'publisherIds': [creds['company_id']],
                'since': since,
                'before': before,
            },
            'publisherCommissions',
        )
        if not data:
            return []
        block = data.get('publisherCommissions') or {}
        if block.get('payloadComplete') is False:
            # CJ truncates long windows; a narrower cron window is the fix.
            _logger.warning(
                'CJ publisherCommissions truncated the window %s..%s; '
                'some commissions were not returned.', since, before,
            )
        return block.get('records') or []
