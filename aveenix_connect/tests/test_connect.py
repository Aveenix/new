import base64
import io
import json
import re
from datetime import timedelta
from unittest.mock import Mock, patch

import requests
from PIL import Image

from odoo import fields, http
from odoo.exceptions import AccessError
from odoo.tests import HttpCase, new_test_user, tagged

from odoo.addons.aveenix_connect.models.connect_google_client import PARAM_API_KEY
from odoo.addons.aveenix_connect.models.connect_nzbn_client import PARAM_API_KEY as PARAM_NZBN_API_KEY

CLIENT_REQUESTS = 'odoo.addons.aveenix_connect.models.connect_google_client.requests.post'
NZBN_REQUESTS = 'odoo.addons.aveenix_connect.models.connect_nzbn_client.requests.get'
CLAIM_CODE = 'odoo.addons.aveenix_connect.models.connect_business.secrets.randbelow'

# A register entry as the NZBN API returns it (only the fields we read).
NZBN_ENTITY = {
    'nzbn': '9429000000017',
    'entityName': 'HARBOUR ROOFING NZ LIMITED',
    'entityStatusCode': '50',
    'entityStatusDescription': 'Registered',
    'tradingNames': [{'name': 'Harbour Roofing', 'startDate': '2020-01-01'}],
    'addresses': {'addressList': [
        {'addressType': 'REGISTERED', 'address1': 'Level 9, 1 Law St', 'address3': 'Wellington',
         'postCode': '6011', 'countryCode': 'NZ'},
        {'addressType': 'PHYSICAL', 'address1': '12 Beach Rd', 'address2': 'Devonport',
         'address3': 'Auckland', 'postCode': '0624', 'countryCode': 'NZ'},
        {'addressType': 'PHYSICAL', 'address1': 'Old Rd', 'address3': 'Hamilton',
         'endDate': '2021-01-01', 'countryCode': 'NZ'},
    ]},
    'phoneNumbers': [{'phoneCountryCode': '64', 'phoneAreaCode': '9', 'phoneNumber': '5550199'}],
    'emailAddresses': [{'emailAddress': 'office@harbour-roofing.example.com'}],
    'websites': [{'url': 'www.harbour-roofing.example.com'}],
    'industryClassifications': [{'classificationCode': 'E323110', 'classificationDescription': 'Roofing service'}],
}


def _response(body, status=200):
    return Mock(status_code=status, json=Mock(return_value=body), text=json.dumps(body))


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
        # Footer: Connect after Home in "Explore Aveenix", Jobs in "Our Services".
        footer = res.text[res.text.index('av-footer-main'):]
        self.assertLess(footer.index('>Home<'), footer.index('>Aveenix Connect<'))
        self.assertLess(footer.index('>Aveenix Connect<'), footer.index('>Aveenix Digital<'))
        self.assertIn('<a href="/connect/jobs">Aveenix Jobs</a>', footer)
        self.assertLess(footer.index('>Aveenix Jobs<'), footer.index('Aveenix Marketplace'))
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
        # Footer "Our Services", alphabetical: Automotive, Freight, Jobs, Marketplace.
        footer = res.text[res.text.index('av-footer-main'):]
        self.assertLess(footer.index('Aveenix Automotive'), footer.index('>Aveenix Freight<'))
        self.assertLess(footer.index('>Aveenix Freight<'), footer.index('>Aveenix Jobs<'))
        self.assertLess(footer.index('>Aveenix Jobs<'), footer.index('Aveenix Marketplace'))

    def test_review(self):
        url = '/connect/business/%s/review' % self.plumber.id
        self.authenticate('connect_visitor', 'connect_visitor')
        # Only customers who contacted the business through Aveenix review it.
        self._post(url, {'rating': '4', 'comment': 'Never used them.'})
        self.assertEqual(self.plumber.rating_count, 0)
        self.assertIn('you can review a business once you have sent it', self.url_open(self.plumber.website_url).text)

        self._post('/connect/business/%s/enquiry' % self.plumber.id, {
            'name': 'Victor Visitor', 'email': self.visitor.email, 'message': 'Can you fix a leak?'})
        self._post(url, {'rating': '4', 'comment': 'Fixed our leak the same day.'})
        self.assertEqual(self.plumber.rating_count, 1)
        self.assertEqual(self.plumber.rating_avg, 4)
        # One review per visitor.
        self._post(url, {'rating': '1', 'comment': 'Again'})
        self.assertEqual(self.plumber.rating_count, 1)

        # Owners don't rate their own business.
        self.authenticate('connect_owner', 'connect_owner')
        self._post(url, {'rating': '5', 'comment': 'Best!'})
        self.assertEqual(self.plumber.rating_count, 1)

    def test_enquiry_and_quote(self):
        self.authenticate(None, None)
        # An enquiry is recorded and reaches the owner.
        self._post('/connect/business/%s/enquiry' % self.plumber.id, {
            'name': 'Pat Public', 'email': 'pat@example.com', 'message': 'Do you do gas fitting?'})
        lead = self.env['connect.lead'].search([('email', '=', 'pat@example.com')])
        self.assertEqual((lead.kind, lead.business_ids), ('enquiry', self.plumber))
        self.assertIn(self.owner.partner_id, self.plumber.message_ids[0].partner_ids)

        # A quote request goes to the claimed listings of the category that
        # are in, or serve, the place asked for.
        self.unclaimed.owner_id = self.visitor
        self.unclaimed.write({'city': 'Hamilton', 'service_areas': 'Waikato, Cambridge'})
        trades = self.category
        self._post('/connect/quote', {
            'category_id': str(trades.id), 'where': 'cambridge', 'message': 'Rewire a garage',
            'name': 'Quinn', 'email': 'quinn@example.com'})
        quote = self.env['connect.lead'].search([('email', '=', 'quinn@example.com')])
        self.assertEqual((quote.kind, quote.business_ids), ('quote', self.unclaimed))
        self.assertIn('Rewire a garage', self.unclaimed.message_ids[0].body)
        self.assertIn(self.visitor.partner_id, self.unclaimed.message_ids[0].partner_ids)

        # Nothing matches: the request is kept for the team.
        self._post('/connect/quote', {
            'category_id': str(trades.id), 'where': 'Dunedin', 'message': 'Fix a roof',
            'name': 'Dana', 'email': 'dana@example.com'})
        unmatched = self.env['connect.lead'].search([('email', '=', 'dana@example.com')])
        self.assertTrue(unmatched)
        self.assertFalse(unmatched.business_ids)

        # A missing field shows the form again instead of sending anything.
        res = self._post('/connect/quote', {'category_id': str(trades.id), 'where': '', 'message': 'x',
                                            'name': 'Eve', 'email': 'eve@example.com'})
        self.assertIn('Enter your city, suburb or postcode.', res.text)
        self.assertFalse(self.env['connect.lead'].search([('email', '=', 'eve@example.com')]))

    def test_report(self):
        self.authenticate(None, None)
        self._post('/connect/business/%s/report' % self.unclaimed.id, {
            'reason': 'closed', 'details': 'Shut down last year', 'email': 'neighbour@example.com'})
        report = self.env['connect.report'].search([('business_id', '=', self.unclaimed.id)])
        self.assertEqual((report.reason, report.state), ('closed', 'new'))
        # Unknown reasons are refused.
        self._post('/connect/business/%s/report' % self.unclaimed.id, {'reason': 'nonsense'})
        self.assertEqual(len(self.env['connect.report'].search([('business_id', '=', self.unclaimed.id)])), 1)

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
        # No email on the listing: the team checks the claim.
        self.authenticate('connect_visitor', 'connect_visitor')
        self._post('/connect/business/%s/claim' % self.unclaimed.id, {})
        self.assertEqual(self.unclaimed.claim_user_id, self.visitor)
        self.unclaimed.action_approve_claim()
        self.assertEqual(self.unclaimed.owner_id, self.visitor)
        self.assertTrue(self.unclaimed.is_verified)
        self.assertFalse(self.unclaimed.claim_user_id)

    def test_claim_by_code(self):
        listing = self.env['connect.business'].create({
            'name': 'Coastal Cafe', 'city': 'Napier', 'email': 'hello@coastal.example.com',
            'category_ids': [(6, 0, self.category.ids)], 'is_published': True,
        })
        new_test_user(self.env, login='connect_thief', groups='base.group_portal')
        self.authenticate('connect_visitor', 'connect_visitor')
        self.assertIn('h•••@coastal.example.com', self.url_open(listing.website_url).text)
        with patch(CLAIM_CODE, return_value=123456):
            res = self._post('/connect/business/%s/claim' % listing.id, {})
        self.assertIn('/claim/verify', res.url)
        mail = self.env['mail.mail'].search([('email_to', '=', 'hello@coastal.example.com')])
        self.assertIn('123456', mail.body_html)
        self.assertNotIn('123456', ''.join(listing.message_ids.mapped('body')))

        verify = '/connect/business/%s/claim/verify' % listing.id
        self._post(verify, {'code': '000000'})
        self.assertFalse(listing.owner_id)
        # The code only works for the visitor it was sent for.
        self.authenticate('connect_thief', 'connect_thief')
        self._post(verify, {'code': '123456'})
        self.assertFalse(listing.owner_id)
        self.authenticate('connect_visitor', 'connect_visitor')
        res = self._post(verify, {'code': '123456'})
        self.assertEqual(listing.owner_id, self.visitor)
        self.assertTrue(listing.is_verified)
        self.assertIn('/my/connect/%s' % listing.id, res.url)

    def test_claim_code_limits(self):
        listing = self.env['connect.business'].create({
            'name': 'Hill Dental', 'city': 'Nelson', 'email': 'desk@hill.example.com',
            'category_ids': [(6, 0, self.category.ids)], 'is_published': True,
        })
        with patch(CLAIM_CODE, return_value=111111):
            self.assertTrue(listing._send_claim_code(self.visitor))
            # No new code (and email) within a minute.
            self.assertFalse(listing._send_claim_code(self.visitor))
        # Expired codes no longer work.
        listing.sudo().claim_code_expires = fields.Datetime.now() - timedelta(minutes=1)
        self.assertFalse(listing._check_claim_code(self.visitor, '111111'))
        # After too many wrong codes, only the team can approve a claim.
        listing.sudo().claim_code_expires = fields.Datetime.now() + timedelta(minutes=10)
        for _attempt in range(10):
            self.assertFalse(listing._check_claim_code(self.visitor, '999999'))
        self.assertFalse(listing._check_claim_code(self.visitor, '111111'))
        self.assertTrue(listing._claim_code_locked())
        self.authenticate('connect_visitor', 'connect_visitor')
        self._post('/connect/business/%s/claim' % listing.id, {})
        self.assertEqual(listing.claim_user_id, self.visitor)

    def test_badges_and_structured_data(self):
        builder = self.env.ref('aveenix_connect.licence_type_lbp')
        licence = self.env['connect.licence'].create(
            {'business_id': self.plumber.id, 'type_id': builder.id, 'number': 'BP123456'})
        page = self.url_open(self.plumber.website_url).text
        self.assertNotIn('Licensed Builder', page)
        self.assertNotIn('Verified Business', page)
        licence.action_verify()
        self.plumber.is_verified = True
        page = self.url_open(self.plumber.website_url).text
        self.assertIn('Licensed Builder', page)
        self.assertIn('Verified Business', page)

        scripts = re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)
        data = next(d for d in map(json.loads, scripts) if isinstance(d, dict) and d.get('@type') == 'LocalBusiness')
        self.assertEqual(data['name'], 'Kiwi Plumbing Co')
        self.assertEqual(data['address']['addressLocality'], 'Auckland')

    def test_header_actions(self):
        self.authenticate(None, None)
        page = self.url_open('/connect/search?what=plumb').text
        self.assertIn('href="/connect/favourites"', page)
        self.assertIn('href="/connect/compare"', page)
        # Login comes back to the page the visitor was on.
        self.assertIn('href="/web/login?redirect=%2Fconnect%2Fsearch%3Fwhat%3Dplumb"', page)
        # The shop keeps its own links.
        shop = self.url_open('/').text
        self.assertNotIn('href="/connect/favourites"', shop)
        self.assertIn('href="/web/login"', shop)

    def test_favourites(self):
        toggle = '/connect/list/toggle'
        self.authenticate(None, None)
        # Guests' favourites live in their session.
        res = self.make_jsonrpc_request(toggle, {'kind': 'fav', 'business_id': self.plumber.id})
        self.assertEqual(res, {'active': True, 'count': 1})
        page = self.url_open('/connect/favourites').text
        self.assertIn('Kiwi Plumbing Co', page)
        self.assertNotIn('Harbour Electricians', page)
        # Unpublished listings cannot be added.
        with self.assertRaises(Exception):
            self.make_jsonrpc_request(toggle, {'kind': 'fav', 'business_id': self.hidden.id})

        # Logging in moves them to the account, which keeps them from then on.
        # (The login keeps the session's data; authenticate() starts a new
        # session, so put the guest's list back in it.)
        self.authenticate('connect_visitor', 'connect_visitor')
        self.session['connect_fav_ids'] = [self.plumber.id]
        http.root.session_store.save(self.session)
        self.url_open('/connect')
        self.assertEqual(self.visitor.connect_favourite_ids, self.plumber)
        self.make_jsonrpc_request(toggle, {'kind': 'fav', 'business_id': self.unclaimed.id})
        self.assertEqual(self.visitor.connect_favourite_ids, self.plumber | self.unclaimed)
        res = self.make_jsonrpc_request(toggle, {'kind': 'fav', 'business_id': self.plumber.id})
        self.assertEqual(res, {'active': False, 'count': 1})
        self.assertEqual(self.visitor.connect_favourite_ids, self.unclaimed)
        # An unpublished favourite drops out of the list.
        self.unclaimed.is_published = False
        self.assertIn('No favourites yet', self.url_open('/connect/favourites').text)

    def test_compare(self):
        toggle = '/connect/list/toggle'
        Business = self.env['connect.business']
        extra = Business.create([{
            'name': 'Extra %s' % i, 'city': 'Auckland', 'is_published': True,
            'category_ids': [(6, 0, self.category.ids)],
        } for i in range(3)])
        self.plumber.write({'services': 'Leaks\nHot water', 'service_areas': 'North Shore'})
        self.authenticate(None, None)
        for business in self.plumber | self.unclaimed | extra[:2]:
            self.assertTrue(self.make_jsonrpc_request(toggle, {'kind': 'compare', 'business_id': business.id})['active'])
        # Four at most.
        res = self.make_jsonrpc_request(toggle, {'kind': 'compare', 'business_id': extra[2].id})
        self.assertEqual(res, {'active': False, 'full': True, 'count': 4})
        page = self.url_open('/connect/compare').text
        for name in ('Kiwi Plumbing Co', 'Harbour Electricians', 'Extra 0', 'Extra 1', 'Hot water', 'North Shore'):
            self.assertIn(name, page)
        self.assertNotIn('Extra 2', page)
        self.make_jsonrpc_request(toggle, {'kind': 'compare', 'business_id': self.unclaimed.id})
        self.assertNotIn('Harbour Electricians', self.url_open('/connect/compare').text)

    def test_home_reviews_and_hero(self):
        def review(business, text):
            business.message_post(body=text, author_id=self.visitor.partner_id.id, rating_value=5,
                                  message_type='comment', subtype_xmlid='mail.mt_comment')
        self.env['connect.category'].search([]).image_1920 = False
        review(self.plumber, 'Fixed our leak in an hour.')
        review(self.hidden, 'Secret review.')
        page = self.url_open('/connect').text
        self.assertIn('Latest reviews', page)
        self.assertIn('Fixed our leak in an hour.', page)
        self.assertIn('%s#avc-reviews' % self.plumber.website_url, page)
        self.assertNotIn('Secret review.', page)  # its listing is not published
        self.assertNotIn('avc-hero-photos', page)  # no category photo yet

        image = io.BytesIO()
        Image.new('RGB', (40, 20), '#3a7').save(image, 'PNG')
        self.category.image_1920 = base64.b64encode(image.getvalue())
        page = self.url_open('/connect').text
        self.assertIn('avc-hero-photos', page)
        self.assertIn('/web/image/connect.category/%s/image_1920' % self.category.id, page)

    def test_faq(self):
        res = self.url_open('/connect')
        self.assertIn('How do I claim my business?', res.text)
        self.assertIn('href="/connect/quote"', res.text)
        self.assertIn('href="/connect/jobs"', res.text)

    # ── Jobs ─────────────────────────────────────────────────────────────

    def test_jobs(self):
        self.authenticate('connect_owner', 'connect_owner')
        self._post('/my/connect/jobs/new', {
            'business_id': str(self.plumber.id), 'name': 'Apprentice Plumber', 'employment_type': 'full_time',
            'description': 'Learn the trade with us.', 'pay': '$25 per hour'})
        job = self.env['connect.job'].search([('business_id', '=', self.plumber.id)])
        self.assertEqual(job.name, 'Apprentice Plumber')
        self.assertEqual(job.city, 'Auckland')  # defaults to the business's city
        # Owners cannot post for a listing that is not theirs.
        self._post('/my/connect/jobs/new', {
            'business_id': str(self.unclaimed.id), 'name': 'Sparky', 'employment_type': 'full_time',
            'description': 'x'})
        self.assertFalse(self.env['connect.job'].search([('business_id', '=', self.unclaimed.id)]))

        self.authenticate(None, None)
        self.assertIn('Apprentice Plumber', self.url_open('/connect/jobs?where=auckland').text)
        page = self.url_open(job._website_url()).text
        self.assertIn('"@type": "JobPosting"', page)
        self._post('/connect/jobs/%s/apply' % job.id, {
            'name': 'Ana Applicant', 'email': 'ana@example.com', 'message': 'Keen to learn.'})
        application = job.message_ids[0]
        self.assertIn('Ana Applicant', application.body)
        self.assertIn(self.owner.partner_id, application.partner_ids)

        # Closed ads, and ads past their closing date, are not public.
        job.date_closing = fields.Date.today() - timedelta(days=1)
        self.assertNotIn('Apprentice Plumber', self.url_open('/connect/jobs').text)
        self.assertNotEqual(self.url_open(job._website_url()).status_code, 200)
        self.env['connect.job']._cron_close_expired()
        self.assertFalse(job.active)
        job.write({'date_closing': False, 'active': True})
        self.authenticate('connect_owner', 'connect_owner')
        self._post('/my/connect/jobs/%s/toggle' % job.id, {})
        self.assertFalse(job.active)
        self.assertNotIn('Apprentice Plumber', self.url_open('/connect/jobs').text)

    # ── NZBN ─────────────────────────────────────────────────────────────

    def test_nzbn_values(self):
        values = self.env['connect.nzbn.client'].listing_values(NZBN_ENTITY)
        self.assertEqual(values['name'], 'Harbour Roofing')
        self.assertEqual(values['street'], '12 Beach Rd')  # physical address before registered
        self.assertEqual(values['street2'], 'Devonport')
        self.assertEqual(values['city'], 'Auckland')
        self.assertEqual(values['zip'], '0624')
        self.assertEqual(values['phone'], '+64 9 5550199')
        self.assertEqual(values['business_url'], 'https://www.harbour-roofing.example.com')
        self.assertEqual(values['services'], 'Roofing service')
        legal = dict(NZBN_ENTITY, tradingNames=[])
        self.assertEqual(self.env['connect.nzbn.client'].listing_values(legal)['name'],
                         'Harbour Roofing NZ Limited')

    def test_nzbn_import(self):
        client = self.env['connect.nzbn.client']
        with patch(NZBN_REQUESTS) as get:
            self.assertIsNone(client.search('roofing'))  # no key, no call
            get.assert_not_called()
        self.env['ir.config_parameter'].set_param(PARAM_NZBN_API_KEY, 'nzbn-key')

        closed = dict(NZBN_ENTITY, nzbn='9429000000024', entityName='GONE LTD', entityStatusCode='80')
        search = {'totalItems': 2, 'page': 0, 'pageSize': 50, 'items': [NZBN_ENTITY, closed]}

        def fake_get(url, params=None, headers=None, timeout=None):
            self.assertEqual(headers['Ocp-Apim-Subscription-Key'], 'nzbn-key')
            if url.endswith('/entities'):
                self.assertEqual(params['search-term'], 'roofing')
                return _response(search)
            return _response(NZBN_ENTITY) if url.endswith(NZBN_ENTITY['nzbn']) else _response({}, 404)

        job = self.env['connect.nzbn.import'].create({'name': 'roofing', 'category_id': self.category.id})
        with patch(NZBN_REQUESTS, side_effect=fake_get):
            job.action_run()
        listing = self.env['connect.business'].search([('nzbn', '=', NZBN_ENTITY['nzbn'])])
        self.assertEqual(listing.name, 'Harbour Roofing')
        self.assertTrue(listing.is_published)
        self.assertEqual(listing.category_ids, self.category)
        self.assertFalse(self.env['connect.business'].search([('nzbn', '=', closed['nzbn'])]))
        self.assertEqual((job.state, job.imported_count), ('done', 1))

        # A run again creates no duplicate.
        job.action_restart()
        with patch(NZBN_REQUESTS, side_effect=fake_get):
            job.action_run()
        self.assertEqual(self.env['connect.business'].search_count([('nzbn', '=', NZBN_ENTITY['nzbn'])]), 1)

        # Refreshing keeps an owner's details and unpublishes closed businesses.
        listing.write({'owner_id': self.owner.id, 'phone': '021 000 000'})
        listing._apply_nzbn(dict(NZBN_ENTITY, entityStatusCode='80'))
        self.assertEqual(listing.phone, '021 000 000')
        self.assertFalse(listing.is_published)

        # API down: the import keeps its page for the next run.
        job.action_restart()
        with patch(NZBN_REQUESTS, side_effect=requests.ConnectionError('offline')):
            job.action_run()
        self.assertEqual((job.state, job.next_page), ('running', 0))
        self.assertTrue(job.last_error)

    def test_add_from_nzbn(self):
        self.env['ir.config_parameter'].set_param(PARAM_NZBN_API_KEY, 'nzbn-key')
        self.authenticate('connect_visitor', 'connect_visitor')
        with patch(NZBN_REQUESTS, return_value=_response(NZBN_ENTITY)):
            page = self.url_open('/connect/add?nzbn=%s' % NZBN_ENTITY['nzbn']).text
        self.assertIn('value="Harbour Roofing"', page)
        self.assertIn('value="12 Beach Rd"', page)
        # Already listed: the visitor is sent to the listing to claim it.
        self.unclaimed.nzbn = NZBN_ENTITY['nzbn']
        res = self.url_open('/connect/add?nzbn=%s' % NZBN_ENTITY['nzbn'])
        self.assertIn(self.unclaimed.website_url, res.url)

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
        builder = self.env.ref('aveenix_connect.licence_type_lbp')
        self.authenticate('connect_owner', 'connect_owner')
        res = self._post('/my/connect/%s' % self.plumber.id, {
            'city': 'Wellington',
            'phone': '+64 4 555 0123',
            'from_0': '09:00', 'to_0': '17:30',
            'closed_6': 'on',
            'services': 'Leaks\nHot water',
            'service_areas': 'Wellington, Hutt Valley',
            'licence_type_id': str(builder.id),
            'licence_number': 'BP42',
            'is_published': '',  # not an owner field: ignored
            'is_verified': '1',  # idem
        })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.plumber.city, 'Wellington')
        self.assertTrue(self.plumber.is_published)
        self.assertFalse(self.plumber.is_verified)
        self.assertEqual(self.plumber.hours_ids.mapped('dayofweek'), ['0'])
        self.assertEqual(self.plumber.hours_ids.hour_to, 17.5)
        self.assertEqual(self.plumber._service_list(), ['Leaks', 'Hot water'])
        self.assertEqual(self.plumber.service_areas, 'Wellington, Hutt Valley')
        # The licence waits for the team's check.
        self.assertEqual(self.plumber.licence_ids.mapped('state'), ['pending'])
        with self.assertRaises(AccessError):
            self.plumber.licence_ids.with_user(self.owner).write({'state': 'verified'})

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
