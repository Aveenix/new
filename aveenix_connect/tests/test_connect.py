from unittest.mock import Mock, patch

import requests

from odoo import http
from odoo.exceptions import AccessError
from odoo.tests import HttpCase, new_test_user, tagged

from odoo.addons.aveenix_connect.models.connect_google_client import PARAM_API_KEY

CLIENT_REQUESTS = 'odoo.addons.aveenix_connect.models.connect_google_client.requests.post'


@tagged('post_install', '-at_install')
class TestConnect(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.category = cls.env.ref('aveenix_connect.category_trades')
        cls.owner = new_test_user(cls.env, login='connect_owner', groups='base.group_portal', name='Olivia Owner')
        cls.visitor = new_test_user(cls.env, login='connect_visitor', groups='base.group_portal', name='Victor Visitor')
        Business = cls.env['connect.business']
        cls.plumber = Business.create({
            'name': 'Kiwi Plumbing Co',
            'city': 'Auckland',
            'phone': '+64 9 555 0101',
            'category_ids': [(6, 0, cls.category.ids)],
            'owner_id': cls.owner.id,
            'is_published': True,
        })
        cls.unclaimed = Business.create({
            'name': 'Harbour Electricians',
            'city': 'Auckland',
            'category_ids': [(6, 0, cls.category.ids)],
            'is_published': True,
        })
        cls.hidden = Business.create({
            'name': 'Secret Sparkies',
            'city': 'Auckland',
            'category_ids': [(6, 0, cls.category.ids)],
        })

    def _post(self, url, data):
        return self.url_open(url, data=dict(data, csrf_token=http.Request.csrf_token(self)))

    # ── Website ──────────────────────────────────────────────────────────

    def test_connect_pages(self):
        res = self.url_open('/connect')
        self.assertEqual(res.status_code, 200)
        self.assertIn('av-logo-connect', res.text)
        self.assertIn('av-connect-nav', res.text)
        self.assertIn('<a href="/connect">Aveenix Connect</a>', res.text)
        footer = res.text[res.text.index('av-footer-main'):]
        self.assertLess(footer.index('>Aveenix News<'), footer.index('>Aveenix Connect<'))
        self.assertNotIn('av-shop-nav', res.text)

        res = self.url_open('/connect/search?what=plumb&where=auck')
        self.assertEqual(res.status_code, 200)
        self.assertIn('Kiwi Plumbing Co', res.text)
        self.assertNotIn('Harbour Electricians', res.text)
        self.assertNotIn('Secret Sparkies', res.text)

        res = self.url_open('/connect/category/%s' % self.env['ir.http']._slug(self.category))
        self.assertEqual(res.status_code, 200)
        self.assertIn('Harbour Electricians', res.text)
        self.assertNotIn('Secret Sparkies', res.text)

        res = self.url_open(self.plumber.website_url)
        self.assertEqual(res.status_code, 200)
        self.assertIn('Kiwi Plumbing Co', res.text)
        self.assertIn('Send an enquiry', res.text)

    def test_unpublished_listing_is_hidden(self):
        res = self.url_open('/connect/business/%s' % self.hidden.id)
        self.assertNotEqual(res.status_code, 200)
        self.assertNotIn('Secret Sparkies', res.text)
        # Its owner sees it while it waits for approval.
        self.hidden.owner_id = self.visitor
        self.authenticate('connect_visitor', 'connect_visitor')
        res = self.url_open('/connect/business/%s' % self.hidden.id)
        self.assertEqual(res.status_code, 200)
        self.assertIn('Waiting for approval', res.text)

    def test_shop_header_unchanged(self):
        res = self.url_open('/')
        self.assertEqual(res.status_code, 200)
        self.assertIn('av-shop-nav', res.text)
        self.assertIn('av-shop-search', res.text)
        self.assertNotIn('av-logo-connect', res.text)

    def test_freight_header_unchanged(self):
        if self.env['ir.module.module']._get('aveenix_freight').state != 'installed':
            self.skipTest('aveenix_freight is not installed')
        res = self.url_open('/freight')
        self.assertEqual(res.status_code, 200)
        self.assertIn('av-logo-freight', res.text)
        self.assertIn('av-freight-nav', res.text)
        self.assertNotIn('av-logo-connect', res.text)
        self.assertNotIn('av-shop-nav', res.text)
        # Footer "Explore Aveenix" order: News, Freight, then Connect.
        footer = res.text[res.text.index('av-footer-main'):]
        self.assertLess(footer.index('>Aveenix News<'), footer.index('>Aveenix Freight<'))
        self.assertLess(footer.index('>Aveenix Freight<'), footer.index('>Aveenix Connect<'))

    def test_review(self):
        url = '/connect/business/%s/review' % self.unclaimed.id
        self.authenticate('connect_visitor', 'connect_visitor')
        self._post(url, {'rating': '4', 'comment': 'Fixed our wiring the same day.'})
        self.assertEqual(self.unclaimed.rating_count, 1)
        self.assertEqual(self.unclaimed.rating_avg, 4)
        # One review per visitor.
        self._post(url, {'rating': '1', 'comment': 'Again'})
        self.assertEqual(self.unclaimed.rating_count, 1)

        # Owners don't rate their own business.
        self.authenticate('connect_owner', 'connect_owner')
        self._post('/connect/business/%s/review' % self.plumber.id, {'rating': '5', 'comment': 'Best!'})
        self.assertEqual(self.plumber.rating_count, 0)

    def test_list_your_business(self):
        self.authenticate('connect_visitor', 'connect_visitor')
        self.assertRegex(self.url_open('/connect/add').text, r'<textarea[^>]*name="description"')
        res = self._post('/connect/add', {
            'name': 'Victor Bakery',
            'category_ids': [str(self.category.id)],
            'city': 'Hamilton',
            'email': 'hello@victor-bakery.example.com',
            'description': 'Fresh bread\nevery morning',
        })
        self.assertEqual(res.status_code, 200)
        business = self.env['connect.business'].search([('name', '=', 'Victor Bakery')])
        self.assertTrue(business)
        self.assertFalse(business.is_published)
        self.assertEqual(business.owner_id, self.visitor)
        self.assertEqual(business.category_ids, self.category)
        self.assertNotIn('Victor Bakery', self.url_open('/connect/search?what=bakery').text)

    def test_claim(self):
        self.authenticate('connect_visitor', 'connect_visitor')
        self._post('/connect/business/%s/claim' % self.unclaimed.id, {})
        self.assertEqual(self.unclaimed.claim_user_id, self.visitor)
        self.unclaimed.action_approve_claim()
        self.assertEqual(self.unclaimed.owner_id, self.visitor)
        self.assertFalse(self.unclaimed.claim_user_id)

    # ── Owners ───────────────────────────────────────────────────────────

    def test_owner_rights(self):
        self.plumber.with_user(self.owner).write({'phone': '+64 9 555 0199'})
        self.assertEqual(self.plumber.phone, '+64 9 555 0199')
        for vals in ({'is_published': False}, {'is_featured': True}, {'owner_id': self.visitor.id}):
            with self.assertRaises(AccessError):
                self.plumber.with_user(self.owner).write(vals)
        with self.assertRaises(AccessError):
            self.plumber.with_user(self.visitor).write({'phone': '0'})
        with self.assertRaises(AccessError):
            self.hidden.with_user(self.owner).read(['name'])

    def test_publish_button(self):
        """The team approves a listing with the backend Publish button; an
        owner cannot publish their own listing through it."""
        team = new_test_user(self.env, login='connect_team', groups='aveenix_connect.group_connect_user')
        self.hidden.with_user(team).website_publish_button()
        self.assertTrue(self.hidden.is_published)
        self.hidden.with_user(team).website_publish_button()
        self.assertFalse(self.hidden.is_published)

        self.plumber.is_published = False
        with self.assertRaises(AccessError):
            self.plumber.with_user(self.owner).website_publish_button()
        self.assertFalse(self.plumber.is_published)

    def test_owner_portal_edit(self):
        self.authenticate('connect_owner', 'connect_owner')
        res = self._post('/my/connect/%s' % self.plumber.id, {
            'city': 'Wellington',
            'phone': '+64 4 555 0123',
            'from_0': '09:00', 'to_0': '17:30',
            'closed_6': 'on',
            'is_published': '',  # not an owner field: ignored
        })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.plumber.city, 'Wellington')
        self.assertTrue(self.plumber.is_published)
        self.assertEqual(self.plumber.hours_ids.mapped('dayofweek'), ['0'])
        self.assertEqual(self.plumber.hours_ids.hour_to, 17.5)

        # Someone else's listing is out of reach.
        self.authenticate('connect_visitor', 'connect_visitor')
        self._post('/my/connect/%s' % self.plumber.id, {'city': 'Nowhere'})
        self.assertEqual(self.plumber.city, 'Wellington')

    # ── Google ───────────────────────────────────────────────────────────

    def test_google_search(self):
        client = self.env['connect.google.client']
        with patch(CLIENT_REQUESTS) as post:
            self.assertEqual(client.search_text('Kiwi Plumbing'), [])
            post.assert_not_called()

        self.env['ir.config_parameter'].set_param(PARAM_API_KEY, ' test-key ')
        body = {'places': [{'id': 'ChIJ123', 'displayName': {'text': 'Kiwi Plumbing Co'},
                            'formattedAddress': '1 Queen St, Auckland'}]}
        with patch(CLIENT_REQUESTS, return_value=Mock(status_code=200, json=Mock(return_value=body))) as post:
            self.assertEqual(client.search_text('Kiwi Plumbing'), [
                {'place_id': 'ChIJ123', 'name': 'Kiwi Plumbing Co', 'address': '1 Queen St, Auckland'},
            ])
            self.assertEqual(post.call_args.kwargs['headers']['X-Goog-Api-Key'], 'test-key')
        with patch(CLIENT_REQUESTS, side_effect=requests.ConnectionError('offline')):
            self.assertEqual(client.search_text('Kiwi Plumbing'), [])

        wizard = self.env['connect.google.link'].create({'business_id': self.plumber.id, 'query': 'Kiwi'})
        with patch(CLIENT_REQUESTS, return_value=Mock(status_code=200, json=Mock(return_value=body))):
            wizard.action_search()
        wizard.line_ids.action_link()
        self.assertEqual(self.plumber.google_place_id, 'ChIJ123')
        self.assertIn('query_place_id=ChIJ123', self.plumber._google_maps_url())
