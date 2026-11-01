from odoo import http
from odoo.exceptions import UserError
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestFreightQuoteSend(HttpCase):
    """Send by Email must reach a website visitor who has no account, and
    the link it carries must let them accept the price."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # As the website form leaves it: no partner until the team acts.
        cls.quote = cls.env['freight.quote'].create({
            'name': 'AVQ/TEST/0001',
            'source': 'website',
            'mode': 'ocean_fcl',
            'contact_name': 'Guest Shipper',
            'email': 'guest.shipper@example.com',
            'origin_address': 'Ahmedabad',
            'destination_address': 'Rotterdam',
            'state': 'quoted',
            'quoted_amount': 1850.0,
            'transit_days': 25,
        })

    def _send(self):
        action = self.quote.action_quote_send()
        composer = self.env['mail.compose.message'].with_context(action['context']).create({})
        # Queued rather than delivered, so the outgoing email can be read.
        composer.with_context(mail_notify_force_send=False)._action_send_mail()
        return self.env['mail.mail'].search([
            ('model', '=', 'freight.quote'), ('res_id', '=', self.quote.id),
        ])

    def test_send_emails_the_guest_a_tokenised_link(self):
        mail = self._send()
        partner = self.quote.partner_id
        self.assertEqual(partner.email, 'guest.shipper@example.com')
        self.assertEqual(mail.recipient_ids, partner)
        self.assertIn('AVQ/TEST/0001', mail.subject)
        self.assertIn('1,850.00', mail.body_html)
        self.assertIn(self.quote.access_token, mail.body_html)

    def test_send_needs_a_price(self):
        self.quote.state = 'in_progress'
        with self.assertRaises(UserError):
            self.quote.action_quote_send()

    def test_guest_accepts_from_the_link(self):
        self._send()
        self.authenticate(None, None)
        res = self.url_open(self.quote.get_portal_url())
        self.assertEqual(res.status_code, 200)
        self.assertIn('Accept and book', res.text)

        res = self.url_open('/my/freight/quotes/%s/accept' % self.quote.id, data={
            'csrf_token': http.Request.csrf_token(self),
            'access_token': self.quote.access_token,
        })
        shipment = self.quote.shipment_ids
        self.assertEqual(self.quote.state, 'won')
        self.assertEqual(shipment.partner_id, self.quote.partner_id)
        # Redirected to the shipment, opened with its own token.
        self.assertEqual(res.status_code, 200)
        self.assertIn(shipment.tracking_number, res.text)

    def test_wrong_token_opens_nothing(self):
        self.authenticate(None, None)
        res = self.url_open('/my/freight/quotes/%s?access_token=wrong' % self.quote.id)
        self.assertNotIn('Accept and book', res.text)
