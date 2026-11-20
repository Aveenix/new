import secrets
from datetime import timedelta
from urllib.parse import urlencode

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import email_normalize
from odoo.tools.json import scriptsafe as json_scriptsafe
from odoo.tools.misc import consteq, hmac as hmac_digest

# Claiming by code: the code goes to the listing's own email address, so
# whoever reads that inbox can claim. A code lives 30 minutes, a new one can
# be asked for every minute, and after _CLAIM_CODE_MAX_WRONG wrong codes in
# total the listing only takes claims checked by the team.
_CLAIM_CODE_TTL = timedelta(minutes=30)
_CLAIM_CODE_RESEND = timedelta(minutes=1)
_CLAIM_CODE_MAX_WRONG = 10

WEEKDAYS = [
    ('0', 'Monday'),
    ('1', 'Tuesday'),
    ('2', 'Wednesday'),
    ('3', 'Thursday'),
    ('4', 'Friday'),
    ('5', 'Saturday'),
    ('6', 'Sunday'),
]

# What a listing's owner may change from My Account. Publishing, featuring,
# ownership, the Google link, the name and the categories stay with the
# Connect team, whichever route a write comes from (portal form, JSON-RPC).
OWNER_FIELDS = frozenset({
    'description', 'phone', 'email', 'business_url',
    'street', 'street2', 'city', 'zip', 'state_id', 'country_id',
    'image_1920', 'services', 'service_areas',
})


class ConnectBusiness(models.Model):
    """A business listed in the Aveenix Connect directory.

    Everything stored here is our own data, entered by the Connect team or
    the business owner. Google content (rating, hours, photos) is never
    stored: Google Maps Platform terms only allow keeping the place ID, so the
    website loads the rest live in the visitor's browser."""

    _name = 'connect.business'
    _description = 'Connect Business Listing'
    _inherit = [
        'rating.mixin',  # brings mail.thread
        'mail.activity.mixin',
        'website.published.mixin',
        'website.seo.metadata',
        'image.mixin',
    ]
    _order = 'is_featured desc, name'

    name = fields.Char(string='Business Name', required=True, tracking=True)
    description = fields.Html(string='About', translate=True)
    category_ids = fields.Many2many('connect.category', string='Categories')
    is_featured = fields.Boolean(
        string='Featured', tracking=True,
        help='Featured listings come first in search results and show on the Connect home page.',
    )
    owner_id = fields.Many2one(
        'res.users', string='Owner', index=True, tracking=True,
        help='Manages this listing from My Account.',
    )
    claim_user_id = fields.Many2one(
        'res.users', string='Claim Requested By', readonly=True, copy=False, tracking=True,
        help='Asked from the website to become the owner; approve or reject the claim.',
    )
    is_verified = fields.Boolean(
        string='Verified Business', copy=False, tracking=True,
        help='Shows the "Verified Business" badge. Set when the owner confirms a claim with the '
             'code emailed to the listing, or when the team approves a claim.',
    )
    # Claim-by-code state, only ever read and written with sudo.
    claim_code_hash = fields.Char(copy=False, groups='base.group_system')
    claim_code_user_id = fields.Many2one('res.users', copy=False, groups='base.group_system')
    claim_code_expires = fields.Datetime(copy=False, groups='base.group_system')
    claim_code_wrong = fields.Integer(copy=False, groups='base.group_system')

    nzbn = fields.Char(
        string='NZBN', copy=False, index='btree_not_null', tracking=True,
        help='New Zealand Business Number: links the listing to its entry on the NZBN register.',
    )
    nzbn_synced_on = fields.Datetime(string='NZBN Synced On', copy=False, readonly=True)

    services = fields.Text(help='One service per line; shown on the listing and searched.')
    service_areas = fields.Char(
        string='Service Areas',
        help='Cities, suburbs or regions served, separated by commas. Quote requests '
             'for these places reach this business.',
    )
    licence_ids = fields.One2many('connect.licence', 'business_id', string='Licences')
    job_ids = fields.One2many('connect.job', 'business_id', string='Job Ads')

    street = fields.Char()
    street2 = fields.Char()
    city = fields.Char(index=True)
    zip = fields.Char()
    state_id = fields.Many2one('res.country.state', string='State', domain="[('country_id', '=?', country_id)]")
    country_id = fields.Many2one('res.country', string='Country')
    phone = fields.Char()
    email = fields.Char()
    business_url = fields.Char(string='Website')

    hours_ids = fields.One2many('connect.business.hours', 'business_id', string='Opening Hours', copy=True)
    image_ids = fields.One2many('connect.business.image', 'business_id', string='Photos', copy=True)

    google_place_id = fields.Char(
        string='Google Place ID', copy=False, index='btree_not_null', tracking=True,
        help='Links the listing to its Google Maps place. The website then shows '
             'Google\'s rating, hours and photos live; nothing else from Google is stored.',
    )

    _google_place_id_uniq = models.Constraint(
        'UNIQUE(google_place_id)',
        'This Google place is already linked to another listing.',
    )
    _nzbn_uniq = models.Constraint(
        'UNIQUE(nzbn)',
        'This NZBN is already listed.',
    )

    def _compute_website_url(self):
        super()._compute_website_url()
        for business in self:
            if business.id:
                business.website_url = '/connect/business/%s' % self.env['ir.http']._slug(business)

    def write(self, vals):
        if not self.env.su and self.env.user.share and not OWNER_FIELDS.issuperset(vals):
            raise AccessError(_(
                'You can update your listing\'s details; the Connect team handles the rest.'))
        return super().write(vals)

    # ── Address / maps ───────────────────────────────────────────────────

    def _address_line(self):
        self.ensure_one()
        city = ' '.join(filter(None, [self.city, self.zip]))
        return ', '.join(filter(None, [
            self.street, self.street2, city, self.state_id.name, self.country_id.name,
        ]))

    def _maps_query(self):
        self.ensure_one()
        return ', '.join(filter(None, [self.name, self._address_line()]))

    def _google_maps_url(self):
        """Link to the listing on Google Maps (Maps URLs: no key, no cost)."""
        self.ensure_one()
        params = {'api': 1, 'query': self._maps_query()}
        if self.google_place_id:
            params['query_place_id'] = self.google_place_id
        return 'https://www.google.com/maps/search/?' + urlencode(params)

    def _google_embed_url(self, api_key):
        """Maps Embed API iframe URL (free to use), or None when there is no
        key or nothing to place on the map."""
        self.ensure_one()
        if not api_key or not (self.google_place_id or self._address_line()):
            return None
        query = 'place_id:%s' % self.google_place_id if self.google_place_id else self._maps_query()
        return 'https://www.google.com/maps/embed/v1/place?' + urlencode({'key': api_key, 'q': query})

    # ── Ownership claims ─────────────────────────────────────────────────

    def _request_claim(self, user):
        """A website visitor asks to become this listing's owner."""
        self.ensure_one()
        if self.owner_id or self.claim_user_id:
            raise UserError(_('This listing already has an owner or a pending claim.'))
        self.claim_user_id = user
        self.message_post(
            body=_('%s asked to claim this listing.', user.name),
            author_id=user.partner_id.id,
            subtype_xmlid='mail.mt_note',
        )

    def _masked_email(self):
        """The listing's email with most of the name hidden (j•••@example.co.nz),
        to show where a claim code goes without publishing the address further."""
        self.ensure_one()
        local, _sep, domain = (email_normalize(self.email) or '').partition('@')
        return '%s•••@%s' % (local[:1], domain) if domain else ''

    def _claim_code_hash(self, user, code):
        return hmac_digest(self.env(su=True), 'aveenix_connect.claim_code', '%s:%s:%s' % (self.id, user.id, code))

    def _claim_code_locked(self):
        self.ensure_one()
        return self.sudo().claim_code_wrong >= _CLAIM_CODE_MAX_WRONG

    def _send_claim_code(self, user):
        """Email `user` a one-time code, sent to the listing's own email address,
        that makes them the owner. Returns False when a code was sent to them
        less than a minute ago (the earlier code still works)."""
        self.ensure_one()
        business = self.sudo()
        if business.owner_id or not email_normalize(business.email) or self._claim_code_locked():
            raise UserError(_('This listing cannot be claimed with a code.'))
        now = fields.Datetime.now()
        if business.claim_code_user_id == user and business.claim_code_expires \
                and business.claim_code_expires - _CLAIM_CODE_TTL + _CLAIM_CODE_RESEND > now:
            return False
        code = '%06d' % secrets.randbelow(1000000)
        business.write({
            'claim_code_hash': self._claim_code_hash(user, code),
            'claim_code_user_id': user.id,
            'claim_code_expires': now + _CLAIM_CODE_TTL,
        })
        # Not linked to the listing (model / res_id unset), so the code never
        # shows in its chatter, and deleted with its message once sent.
        self.env.ref('aveenix_connect.mail_template_claim_code').sudo().with_context(
            claim_code=code, claim_user_name=user.name,
        ).send_mail(business.id, email_values={
            'model': False, 'res_id': False, 'auto_delete': True,
            'recipient_ids': [], 'partner_ids': [],
        }, email_layout_xmlid='mail.mail_notification_light')
        business.message_post(
            body=_('%s asked for a claim code, emailed to the listing\'s address.', user.name),
            subtype_xmlid='mail.mt_note',
        )
        return True

    def _check_claim_code(self, user, code):
        """Make `user` the verified owner if `code` is the one emailed to them.
        Wrong codes count towards the limit that turns claiming by code off."""
        self.ensure_one()
        business = self.sudo()
        code = (code or '').strip()
        if business.owner_id or business.claim_code_user_id != user or not business.claim_code_hash \
                or self._claim_code_locked() or business.claim_code_expires < fields.Datetime.now():
            return False
        if not consteq(business.claim_code_hash, self._claim_code_hash(user, code)):
            business.claim_code_wrong += 1
            return False
        business.write({
            'owner_id': user.id,
            'is_verified': True,
            'claim_user_id': False,
            'claim_code_hash': False,
            'claim_code_user_id': False,
            'claim_code_expires': False,
            'claim_code_wrong': 0,
        })
        business.message_post(
            body=_('%s confirmed the code emailed to the listing and is now its owner.', user.name),
            subtype_xmlid='mail.mt_note',
        )
        return True

    def action_approve_claim(self):
        for business in self.filtered('claim_user_id'):
            user = business.claim_user_id
            business.write({'owner_id': user.id, 'claim_user_id': False, 'is_verified': True})
            business.message_post(
                body=_(
                    'Your claim was approved: you can now update this listing from My Account > Connect Listings.'),
                partner_ids=user.partner_id.ids,
                subtype_xmlid='mail.mt_comment',
            )

    def action_reject_claim(self):
        for business in self.filtered('claim_user_id'):
            user = business.claim_user_id
            business.claim_user_id = False
            business.message_post(
                body=_('Your claim for this listing was not approved.'),
                partner_ids=user.partner_id.ids,
                subtype_xmlid='mail.mt_comment',
            )

    # ── Reviews, badges, search engines ──────────────────────────────────

    def _can_review(self, user):
        """Reviews come only from customers who contacted the business through
        Aveenix (an enquiry or a quote request), never from its owner."""
        self.ensure_one()
        if user._is_public() or self.owner_id == user:
            return False
        partner = user.partner_id
        return bool(self.env['connect.lead'].sudo().search_count([
            ('business_ids', 'in', self.id),
            '|', ('partner_id', '=', partner.id), ('email', '=', partner.email_normalized or '-'),
        ], limit=1))

    def _badges(self):
        """(icon, label) of the trust badges the listing has earned."""
        self.ensure_one()
        badges = [('fa-check-circle', _('Verified Business'))] if self.is_verified else []
        return badges + [
            (licence.type_id.icon or 'fa-certificate', licence.type_id.name)
            for licence in self.licence_ids if licence.state == 'verified'
        ]

    def _service_list(self):
        self.ensure_one()
        return [line.strip() for line in (self.services or '').splitlines() if line.strip()]

    def _service_area_list(self):
        self.ensure_one()
        return [area.strip() for area in (self.service_areas or '').split(',') if area.strip()]

    def _structured_data(self):
        """schema.org LocalBusiness JSON-LD for the business page, so search
        engines and AI assistants read the listing without guessing."""
        self.ensure_one()
        base_url = self.get_base_url()
        data = {
            '@context': 'https://schema.org',
            '@type': 'LocalBusiness',
            'name': self.name,
            'url': base_url + self.website_url,
            'address': {
                '@type': 'PostalAddress',
                'streetAddress': ', '.join(filter(None, [self.street, self.street2])) or None,
                'addressLocality': self.city or None,
                'postalCode': self.zip or None,
                'addressRegion': self.state_id.name or None,
                'addressCountry': self.country_id.code or None,
            },
            'telephone': self.phone or None,
            'email': self.email or None,
            'sameAs': [self.business_url] if self.business_url else None,
            'image': base_url + '/web/image/connect.business/%s/image_512' % self.id if self.image_128 else None,
            'areaServed': self._service_area_list() or None,
            'identifier': {'@type': 'PropertyValue', 'propertyID': 'NZBN', 'value': self.nzbn} if self.nzbn else None,
            'openingHoursSpecification': [{
                '@type': 'OpeningHoursSpecification',
                'dayOfWeek': 'https://schema.org/' + dict(WEEKDAYS)[hours.dayofweek],
                'opens': hours._format_hour(hours.hour_from),
                'closes': hours._format_hour(hours.hour_to),
            } for hours in self.hours_ids] or None,
        }
        if self.rating_count:
            data['aggregateRating'] = {
                '@type': 'AggregateRating',
                'ratingValue': round(self.rating_avg, 1),
                'reviewCount': self.rating_count,
            }
        data['address'] = {k: v for k, v in data['address'].items() if v}
        return Markup(json_scriptsafe.dumps({k: v for k, v in data.items() if v}, ensure_ascii=False))

    # ── NZBN register ────────────────────────────────────────────────────

    def _apply_nzbn(self, entity):
        """Update the listing from its NZBN register entry. Once a listing has
        an owner, their details win: the register only fills empty fields.
        A business no longer registered is taken off the website."""
        self.ensure_one()
        client = self.env['connect.nzbn.client']
        values = client.listing_values(entity)
        values.pop('nzbn', None)
        if self.owner_id:
            values = {field: value for field, value in values.items() if not self[field]}
        values['nzbn_synced_on'] = fields.Datetime.now()
        if not client.is_registered(entity) and self.is_published:
            values['is_published'] = False
            self.message_post(
                body=_('Unpublished: the NZBN register no longer lists this business as registered.'),
                subtype_xmlid='mail.mt_note',
            )
        self.sudo().write(values)

    def action_nzbn_refresh(self):
        client = self.env['connect.nzbn.client']
        for business in self:
            if not business.nzbn:
                raise UserError(_('Enter the NZBN of "%s" first.', business.name))
            entity = client.get_entity(business.nzbn)
            if entity is None:
                raise UserError(_('The NZBN register could not be reached; check the API key '
                                  'in the settings and the server log.'))
            if not entity:
                raise UserError(_('NZBN %s is not on the register.', business.nzbn))
            business._apply_nzbn(entity)

    @api.model
    def _cron_nzbn_refresh(self, limit):
        """Refresh the listings synced longest ago (at most every 30 days)."""
        client = self.env['connect.nzbn.client']
        if not client._is_configured():
            return
        stale = fields.Datetime.now() - timedelta(days=30)
        businesses = self.sudo().with_context(active_test=False).search([
            ('nzbn', '!=', False),
            '|', ('nzbn_synced_on', '=', False), ('nzbn_synced_on', '<', stale),
        ], order='nzbn_synced_on asc nulls first, id', limit=limit)
        for business in businesses:
            entity = client.get_entity(business.nzbn)
            if entity is None:  # API down or key refused: try again next run
                break
            if entity:
                business._apply_nzbn(entity)
            else:  # not on the register: look again next month, not every run
                business.nzbn_synced_on = fields.Datetime.now()

    def action_open_google_link(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Link to Google'),
            'res_model': 'connect.google.link',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_business_id': self.id,
                'default_query': ', '.join(filter(None, [self.name, self.city])),
            },
        }


class ConnectBusinessHours(models.Model):
    """Opening hours entered for a listing, one range per day."""

    _name = 'connect.business.hours'
    _description = 'Connect Opening Hours'
    _order = 'dayofweek'

    business_id = fields.Many2one('connect.business', required=True, index=True, ondelete='cascade')
    dayofweek = fields.Selection(WEEKDAYS, string='Day', required=True)
    hour_from = fields.Float(string='Opens', required=True)
    hour_to = fields.Float(string='Closes', required=True)

    _day_uniq = models.Constraint(
        'UNIQUE(business_id, dayofweek)',
        'Each day can only have one opening range.',
    )
    _hours_check = models.Constraint(
        'CHECK(hour_from >= 0 AND hour_from < hour_to AND hour_to <= 24)',
        'Opening hours must fall within the day, with opening before closing.',
    )

    @api.model
    def _format_hour(self, value):
        hours, minutes = divmod(round(value * 60), 60)
        return '%02d:%02d' % (hours, minutes)

    def _display_range(self):
        self.ensure_one()
        return '%s – %s' % (self._format_hour(self.hour_from), self._format_hour(self.hour_to))


class ConnectBusinessImage(models.Model):
    """A photo in a listing's gallery."""

    _name = 'connect.business.image'
    _description = 'Connect Business Photo'
    _inherit = ['image.mixin']
    _order = 'sequence, id'

    name = fields.Char(string='Caption')
    sequence = fields.Integer(default=10)
    business_id = fields.Many2one('connect.business', required=True, index=True, ondelete='cascade')
    image_1920 = fields.Image(required=True)
