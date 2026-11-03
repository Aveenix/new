from odoo import http
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestFreightSite(HttpCase):
    """Header and quote form layout the client asked for."""

    def assertInOrder(self, text, *parts):
        positions = [text.index(part) for part in parts]
        self.assertEqual(positions, sorted(positions), parts)

    def test_header(self):
        html = self.url_open('/freight').text
        # Login stays beside the freight actions; Get a Quote comes before Track.
        self.assertIn('av-account-action', html)
        self.assertInOrder(html, 'av-freight-quote-btn">Get a Quote', '<span>Track</span>')
        # Nav: Air before Ocean, Get a Quote before Track Shipment.
        nav = html[html.index('av-freight-nav'):]
        self.assertInOrder(nav, '<span>Air</span>', '<span>Ocean</span>',
                           '<span>Get a Quote</span>', '<span>Track Shipment</span>')

    def test_quote_modes(self):
        html = self.url_open('/freight/quote').text
        self.assertInOrder(html, '>Air Freight<', '>Ocean Freight – FCL<', '>Rail Freight<', '>Road Freight<')
        # Air, listed first, is the one preselected.
        self.assertRegex(html, r'value="air" checked=')
        # Empty textareas still render (QWeb drops a tag whose t-out is None).
        self.assertIn('<textarea id="avf_notes"', html)
        self.assertIn('<textarea id="avf_site"', html)

    # ── Road services ────────────────────────────────────────────────────

    def _post_quote(self, **values):
        self.env['ir.config_parameter'].set_param('aveenix_website.recaptcha_v2_enabled', 'False')
        if not self.session:
            self.authenticate(None, None)  # a visitor session, for the CSRF token
        data = {
            'csrf_token': http.Request.csrf_token(self),
            'contact_name': 'Road Shipper',
            'email': 'road.shipper@example.com',
            'origin_address': 'Auckland',
            'destination_address': 'Hamilton',
            'commodity': values.pop('commodity'),
            **values,
        }
        self.url_open('/freight/quote', data=data)
        return self.env['freight.quote'].search([('commodity', '=', data['commodity'])])

    def test_road_services(self):
        hiab = self.env.ref('aveenix_freight.road_service_hiab')
        fcl = self.env.ref('aveenix_freight.road_service_fcl')
        linehaul = self.env.ref('aveenix_freight.road_service_linehaul')
        linehaul.active = False

        # The Road page lists active services, each opening the quote form with it chosen.
        html = self.url_open('/freight/services/road-rail').text
        self.assertIn('/freight/quote?mode=road&amp;road_service_id=%s' % hiab.id, html)
        self.assertNotIn('Linehaul Service', html)
        self.assertNotIn('Hiab Trucks', self.url_open('/freight/services/air-freight').text)
        html = self.url_open('/freight/quote?mode=road&road_service_id=%s' % hiab.id).text
        self.assertRegex(html, r'value="%s"[^>]*selected=' % hiab.id)

        # Hiab keeps the heavy-lift details, not container ones.
        quote = self._post_quote(
            commodity='Hiab load', mode='road', road_service_id=str(hiab.id),
            container_type='40hc', max_item_weight_kg='2500', site_access='Gravel drive, power lines',
        )
        self.assertEqual(quote.road_service_id, hiab)
        self.assertEqual(quote.max_item_weight_kg, 2500)
        self.assertEqual(quote.site_access, 'Gravel drive, power lines')
        self.assertFalse(quote.container_type)

        # FCL trucks take containers, like ocean FCL.
        quote = self._post_quote(
            commodity='FCL truck load', mode='road', road_service_id=str(fcl.id),
            container_type='40hc', container_qty='2', max_item_weight_kg='900',
        )
        self.assertEqual(quote.container_type, '40hc')
        self.assertEqual(quote.container_qty, 2)
        self.assertFalse(quote.max_item_weight_kg)

        # A road service only sticks to road freight, and only an active one.
        self.assertFalse(self._post_quote(
            commodity='Air load', mode='air', road_service_id=str(hiab.id)).road_service_id)
        self.assertFalse(self._post_quote(
            commodity='Archived load', mode='road', road_service_id=str(linehaul.id)).road_service_id)

        # The service travels to the shipment and names the invoice line.
        quote = self.env['freight.quote'].search([('commodity', '=', 'Hiab load')])
        quote.write({'state': 'quoted', 'quoted_amount': 640})
        quote.action_create_shipment()
        shipment = quote.shipment_ids
        self.assertEqual(shipment.road_service_id, hiab)
        self.assertEqual(shipment.max_item_weight_kg, 2500)
        shipment.action_create_invoice()
        self.assertIn('Road Freight – Hiab Trucks', shipment.invoice_ids.invoice_line_ids.name)
