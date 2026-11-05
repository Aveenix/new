from urllib.parse import urlencode

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

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
    'image_1920',
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

    def action_approve_claim(self):
        for business in self.filtered('claim_user_id'):
            user = business.claim_user_id
            business.write({'owner_id': user.id, 'claim_user_id': False})
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
