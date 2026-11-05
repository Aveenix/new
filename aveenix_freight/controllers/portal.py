from odoo import http
from odoo.exceptions import AccessError, MissingError, UserError
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager

from ..models.freight_shipment import SHIPMENT_STATES

_PPG = 20


class FreightPortal(CustomerPortal):
    """My Account > Freight: the customer's quote requests and shipments.

    Reads go through the portal record rules (security/freight_security.xml),
    so a customer only ever reaches their own company's records; the two
    writes (accept / decline) run as sudo after that same access check.
    """

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'freight_quote_count' in counters:
            values['freight_quote_count'] = request.env['freight.quote'].search_count([]) \
                if request.env['freight.quote'].has_access('read') else 0
        if 'freight_shipment_count' in counters:
            values['freight_shipment_count'] = request.env['freight.shipment'].search_count([]) \
                if request.env['freight.shipment'].has_access('read') else 0
        return values

    def _freight_list(self, model, url, page, template, key, page_name):
        Model = request.env[model]
        total = Model.search_count([])
        pager = portal_pager(url=url, total=total, page=page, step=_PPG)
        records = Model.search([], limit=_PPG, offset=pager['offset'])
        values = self._prepare_portal_layout_values()
        values.update({key: records, 'pager': pager, 'page_name': page_name,
                       'state_labels': dict(SHIPMENT_STATES)})
        return request.render(template, values)

    @http.route(['/my/freight/quotes', '/my/freight/quotes/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_freight_quotes(self, page=1, **kw):
        return self._freight_list('freight.quote', '/my/freight/quotes', page,
                                  'aveenix_freight.portal_freight_quotes', 'quotes', 'freight_quotes')

    @http.route(['/my/freight/shipments', '/my/freight/shipments/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_freight_shipments(self, page=1, **kw):
        return self._freight_list('freight.shipment', '/my/freight/shipments', page,
                                  'aveenix_freight.portal_freight_shipments', 'shipments', 'freight_shipments')

    @http.route('/my/freight/quotes/<int:quote_id>', type='http', auth='public', website=True)
    def portal_freight_quote(self, quote_id, access_token=None, message=None, **kw):
        try:
            quote = self._document_check_access('freight.quote', quote_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')
        values = self._get_page_view_values(
            quote, access_token, {'quote': quote, 'page_name': 'freight_quote', 'message': message},
            'my_freight_quotes_history', False)
        return request.render('aveenix_freight.portal_freight_quote', values)

    @http.route('/my/freight/quotes/<int:quote_id>/<string:answer>', type='http', auth='public',
                website=True, methods=['POST'])
    def portal_freight_quote_answer(self, quote_id, answer, access_token=None, reason=None, **kw):
        try:
            quote = self._document_check_access('freight.quote', quote_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')
        try:
            if answer == 'accept':
                shipment = quote.action_portal_accept()
                return request.redirect(shipment.get_portal_url())
            if answer == 'decline':
                quote.action_portal_decline((reason or '').strip()[:255] or None)
                return request.redirect(quote.get_portal_url(query_string='&message=declined'))
        except UserError:
            # Answered twice (another tab, or the team moved it on meanwhile).
            return request.redirect(quote.get_portal_url(query_string='&message=closed'))
        return request.redirect(quote.get_portal_url())

    @http.route('/my/freight/shipments/<int:shipment_id>', type='http', auth='public', website=True)
    def portal_freight_shipment(self, shipment_id, access_token=None, **kw):
        try:
            shipment = self._document_check_access('freight.shipment', shipment_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')
        values = self._get_page_view_values(
            shipment, access_token, {
                'shipment': shipment,
                'events': shipment._public_events(),
                'invoices': shipment.invoice_ids.filtered(lambda m: m.state == 'posted'),
                'state_labels': dict(SHIPMENT_STATES),
                'page_name': 'freight_shipment',
            },
            'my_freight_shipments_history', False)
        return request.render('aveenix_freight.portal_freight_shipment', values)
