"""The approved affiliate offer database — one table for both networks."""

import logging
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .affiliate_network import (
    NETWORK_CJ,
    NETWORK_CLICKBANK,
    NETWORKS,
    apply_params,
    network_hosts,
    sanitize_token,
    verify_target_url,
)

_logger = logging.getLogger(__name__)

PARAM_CLICKBANK_NICKNAME = 'aveenix_affiliate.clickbank_nickname'
PARAM_ENABLED = 'aveenix_affiliate.enabled'
PARAM_CJ_DISCOVERY = 'aveenix_affiliate.cj_discovery_enabled'
PARAM_MIN_RELEVANCE = 'aveenix_affiliate.min_relevance'
PARAM_MAX_OFFERS = 'aveenix_affiliate.max_offers_per_article'
PARAM_DISCLOSURE = 'aveenix_affiliate.disclosure'

DEFAULT_MIN_RELEVANCE = 35
DEFAULT_MAX_OFFERS = 2
DEFAULT_DISCLOSURE = (
    'Disclosure: this article contains affiliate links. Aveenix may earn a '
    'commission if you buy through them, at no extra cost to you.'
)

HOPLINK_BASE = 'https://hop.clickbank.net/'

# Relevance weights. A section match alone scores 40, just over the default
# floor of 35, because an offer curated for Fitness is already a defensible
# recommendation on a Fitness article even with no keyword in common. Keyword
# hits are what lift one such offer above its section-mates, and the cap stops
# a keyword-stuffed offer from winning on volume alone. Raising the floor above
# 40 is therefore the setting that demands a keyword match, not just a section.
SECTION_WEIGHT = 40
KEYWORD_WEIGHT = 12
KEYWORD_CAP = 48
BRAND_WEIGHT = 12
MAX_SCORE = 100

# Words too common to say anything about what an offer is for.
_NOISE_TERMS = frozenset({
    'the', 'and', 'for', 'with', 'from', 'your', 'you', 'new', 'best', 'top',
    'buy', 'shop', 'get', 'now', 'off', 'free', 'sale', 'deal', 'deals',
    'official', 'online', 'store', 'inc', 'ltd', 'com',
})


class AffiliateOffer(models.Model):
    """A verified affiliate offer that may be recommended inside an article.

    One model for CJ products, CJ text links and ClickBank HopLinks, because
    everything downstream — matching, placement, click logging, revenue — treats
    them identically. The only per-network behaviour is how `target_url` is
    verified and which tracking parameters ride on it, both of which are a few
    lines at the edges rather than a reason to split the table.

    Offers are NOT `product.template` records on purpose: CJ feeds return
    thousands of items Aveenix does not sell, and admitting them to the product
    catalogue would put them in /shop, in pricelists and in stock valuation.
    An offer is an editorial recommendation, not a thing Aveenix sells.
    """

    _name = 'affiliate.offer'
    # mail.thread for the approval trail: who approved which offer, and when,
    # is the question an advertising complaint actually turns on.
    _inherit = ['mail.thread']
    _description = 'Affiliate Offer'
    _order = 'state, name'

    name = fields.Char(string='Offer', required=True)
    network = fields.Selection(NETWORKS, string='Network', required=True, index=True)
    advertiser_id = fields.Many2one(
        comodel_name='affiliate.advertiser',
        string='Advertiser / Vendor',
        index=True,
        ondelete='cascade',
    )
    description = fields.Text(string='Description')
    image_url = fields.Char(string='Image URL')
    target_url = fields.Char(
        string='Affiliate Link',
        help='The verified network link. CJ discovery fills this in; for '
             'ClickBank it is the HopLink. It must point at one of the '
             "network's own click domains — nothing else is ever served.",
    )
    keywords = fields.Char(
        string='Keywords',
        help='Comma-separated terms that describe what this offer is for. '
             'These are what an article is matched against.',
    )
    section_ids = fields.Many2many(
        comodel_name='affiliate.section',
        relation='affiliate_offer_section_rel',
        column1='offer_id',
        column2='section_id',
        string='Sections',
        help='News sections this offer suits. An offer with no section can '
             'still match on keywords alone, but scores lower.',
    )
    price = fields.Monetary(string='Price', currency_field='currency_id')
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
        ondelete='restrict',
    )
    commission_note = fields.Char(string='Commission')
    external_id = fields.Char(string='Network Offer ID', index=True)
    source = fields.Selection(
        [
            ('cj_product', 'CJ Product Feed'),
            ('cj_link', 'CJ Link Search'),
            ('manual', 'Manually Added'),
        ],
        string='Source',
        default='manual',
        required=True,
    )
    state = fields.Selection(
        [
            ('draft', 'Pending Approval'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
        ],
        string='Status',
        default='draft',
        required=True,
        index=True,
        tracking=True,
        help='Only approved offers can be matched to articles or clicked.',
    )
    active = fields.Boolean(string='Active', default=True)

    placement_ids = fields.One2many(
        'affiliate.offer.placement', 'offer_id', string='Placements',
    )
    placement_count = fields.Integer(string='Placement Count', compute='_compute_placement_count')
    click_count = fields.Integer(string='Clicks', compute='_compute_click_count')
    commission_ids = fields.One2many(
        'affiliate.commission', 'offer_id', string='Commissions',
    )
    revenue_total = fields.Monetary(
        string='Revenue', currency_field='currency_id', compute='_compute_revenue_total',
    )

    # NULL external_id (manual offers) stays exempt, which is what Postgres
    # does with NULLs in a unique index and what we want: hand-added offers are
    # not identified by a network id.
    _network_external_id_uniq = models.Constraint(
        'UNIQUE(network, external_id)',
        'This offer already exists for that network.',
    )

    # ── Engine settings ──────────────────────────────────────────────────

    @api.model
    def _av_settings(self):
        """Engine settings, resolved with bounds.

        Read in one place because the matcher, the article renderer and the
        redirect route all need the same answers, and a half-applied setting
        (placement on, disclosure missing) is the kind of inconsistency that
        matters to an advertising regulator rather than just to a reader.

        Values are clamped rather than trusted: a hand-edited system parameter
        of 0 would otherwise place an offer on every article regardless of
        relevance, which is the one outcome the brief rules out.
        """
        params = self.env['ir.config_parameter'].sudo()

        def as_int(key, default):
            try:
                return int(float(params.get_param(key) or default))
            except (TypeError, ValueError):
                return default

        return {
            'enabled': (params.get_param(PARAM_ENABLED) or 'True') == 'True',
            'cj_discovery': (params.get_param(PARAM_CJ_DISCOVERY) or 'True') == 'True',
            'min_relevance': min(max(as_int(PARAM_MIN_RELEVANCE, DEFAULT_MIN_RELEVANCE), 1), MAX_SCORE),
            'max_offers': min(max(as_int(PARAM_MAX_OFFERS, DEFAULT_MAX_OFFERS), 1), 4),
            'disclosure': (params.get_param(PARAM_DISCLOSURE) or DEFAULT_DISCLOSURE).strip(),
        }

    # ── Computes ─────────────────────────────────────────────────────────

    @api.depends('placement_ids')
    def _compute_placement_count(self):
        for offer in self:
            offer.placement_count = len(offer.placement_ids)

    def _compute_click_count(self):
        grouped = self.env['affiliate.click.log']._read_group(
            [('offer_id', 'in', self.ids)],
            groupby=['offer_id'],
            aggregates=['__count'],
        )
        counts = {offer.id: count for offer, count in grouped}
        for offer in self:
            offer.click_count = counts.get(offer.id, 0)

    @api.depends('commission_ids.commission_amount')
    def _compute_revenue_total(self):
        for offer in self:
            offer.revenue_total = sum(offer.commission_ids.mapped('commission_amount'))

    # ── The link trust boundary ──────────────────────────────────────────

    @api.constrains('target_url', 'network')
    def _check_target_url(self):
        """Refuse any link that is not an https URL on the network's own domains.

        This is the write-time half of the "only verified affiliate links" rule;
        the redirect route re-checks at click time, so a link that was somehow
        written around this constraint still cannot be served.
        """
        for offer in self:
            if not offer.target_url:
                continue
            if not verify_target_url(offer.network, offer.target_url):
                raise ValidationError(_(
                    'The affiliate link for "%(offer)s" is not a valid %(network)s '
                    'link.\n\nIt must start with https:// and its domain must be '
                    'one of: %(hosts)s\n\nGot: %(url)s',
                    offer=offer.name or '',
                    network=dict(NETWORKS).get(offer.network, offer.network),
                    hosts=', '.join(sorted(network_hosts(offer.network))),
                    url=offer.target_url,
                ))

    # ── Lifecycle ────────────────────────────────────────────────────────

    def action_approve(self):
        """Approve offers so the matcher may use them.

        ClickBank offers arrive here by hand, which is the manual-approval gate
        the brief requires. The link check is repeated rather than trusted from
        create time, because an offer can be edited while in draft.
        """
        for offer in self:
            if not offer.target_url:
                raise UserError(_(
                    'Offer "%s" has no affiliate link, so it cannot be approved.',
                    offer.name,
                ))
            if not verify_target_url(offer.network, offer.target_url):
                raise UserError(_(
                    'Offer "%s" has a link that is not on a %s click domain, '
                    'so it cannot be approved.',
                    offer.name, dict(NETWORKS).get(offer.network, offer.network),
                ))
        return self.write({'state': 'approved'})

    def action_reject(self):
        return self.write({'state': 'rejected'})

    def action_reset_to_draft(self):
        return self.write({'state': 'draft'})

    def action_build_hoplink(self):
        """Fill `target_url` with the HopLink for this vendor.

        Assembling HopLinks by hand is the likeliest way to end up with a link
        that tracks to nobody — a typo in the affiliate nickname still returns a
        working page, so the mistake is invisible until the commission never
        arrives. Building it from the configured nickname removes that class of
        error.
        """
        nickname = (self.env['ir.config_parameter'].sudo()
                    .get_param(PARAM_CLICKBANK_NICKNAME) or '').strip()
        if not nickname:
            raise UserError(_(
                'Set the ClickBank affiliate nickname in Website Settings first.'
            ))
        for offer in self:
            if offer.network != NETWORK_CLICKBANK:
                raise UserError(_('HopLinks only apply to ClickBank offers.'))
            vendor = (offer.advertiser_id.external_id or '').strip()
            if not vendor:
                raise UserError(_(
                    'Offer "%s" needs a vendor with its ClickBank nickname set in '
                    'the Network ID field.', offer.name,
                ))
            offer.target_url = apply_params(
                HOPLINK_BASE, {'affiliate': nickname, 'vendor': vendor},
            )
        return True

    def _av_is_placeable(self):
        """True when every offer in `self` may be shown and clicked right now.

        Checked at match time, at render time and again at click time, because
        an offer can be archived or rejected between a placement being made and
        a visitor clicking it — and the click is the half that costs money.
        """
        return bool(self) and all(
            offer.active
            and offer.state == 'approved'
            and offer.target_url
            and (not offer.advertiser_id or offer.advertiser_id.active)
            for offer in self
        )

    # ── Matching ─────────────────────────────────────────────────────────

    def _av_match_text(self):
        """The text an article's keywords are scored against.

        Name and curated keywords only — not the description. A long marketing
        description mentions everything in passing, which is precisely how the
        news classifier used to file a cast retrospective under Gadgets for
        saying "battery" once (see aveenix_news._SECTION_KEYWORDS).
        """
        self.ensure_one()
        return ' '.join(filter(None, [self.name or '', self.keywords or ''])).lower()

    def _av_relevance(self, article, keywords):
        """Score this offer against `article`, returning (score, matched_terms).

        Deliberately a transparent sum rather than an embedding similarity: the
        score is stored on the placement, so an editor who wonders why a given
        product showed up under a given article can read the answer off the
        record instead of taking it on faith.
        """
        self.ensure_one()
        text = self._av_match_text()
        matched = [
            term for term in keywords
            if term and re.search(r'\b%s\b' % re.escape(term), text)
        ]
        score = min(len(matched) * KEYWORD_WEIGHT, KEYWORD_CAP)
        if article.category and article.category in self.section_ids.mapped('code'):
            score += SECTION_WEIGHT
        brand = (self.advertiser_id.name or '').strip().lower()
        if brand and len(brand) > 2 and brand not in _NOISE_TERMS:
            if re.search(r'\b%s\b' % re.escape(brand), (article.title or '').lower()):
                score += BRAND_WEIGHT
        return min(score, MAX_SCORE), matched

    # ── Outbound link ────────────────────────────────────────────────────

    def _av_outbound_url(self, click, placement):
        """The tracked network URL for one click on one placement.

        Built from `target_url` and nothing else — no part of this link comes
        from an AI response, a request parameter or a template. Attribution
        rides along as network tracking parameters so the network's own reports
        break down by article and placement, and `tid`/`sid` carry the click id
        that joins their reporting back to our click log.
        """
        self.ensure_one()
        tracking_id = sanitize_token(click.tracking_id, 100)
        if self.network == NETWORK_CLICKBANK:
            # ClickBank gives each attribution dimension its own parameter, so
            # nothing has to be packed into tid beyond the click id itself.
            return apply_params(self.target_url, {
                'tid': tracking_id,
                'traffic_source': 'aveenix_news',
                'campaign': sanitize_token(placement.news_id.category or '', 100),
                'offer': sanitize_token(
                    self.advertiser_id.external_id or self.external_id or '', 100,
                ),
                'creative': sanitize_token(placement.position, 150),
                'aff_sub1': sanitize_token(placement.news_id.id, 100),
                'aff_sub2': sanitize_token(placement.id, 100),
            })
        if self.network == NETWORK_CJ:
            # CJ carries publisher sub-tracking in a single `sid`; the rest of
            # the attribution stays in our click log, joined on this value.
            return apply_params(self.target_url, {'sid': tracking_id})
        return self.target_url

    # ── Discovery ────────────────────────────────────────────────────────

    @api.model
    def _av_store_discovered(self, rows):
        """Upsert discovered offers, returning the recordset of usable ones.

        CJ links come from advertisers Aveenix has already joined, so they are
        approved on arrival — the human gate the brief asks for applies to
        ClickBank, where we choose the offers ourselves.

        An offer whose link is not on a known CJ click domain is stored as draft
        with a warning rather than dropped or auto-approved. CJ rotates its
        redirector domains, so an unknown host most likely means our allowlist
        is behind — which should surface as a queue of offers to review, never
        as a redirect we cannot vouch for.
        """
        Advertiser = self.env['affiliate.advertiser']
        stored = self.browse()
        for row in rows:
            target_url = (row.get('target_url') or '').strip()
            if not target_url or not row.get('name'):
                continue
            network = row['network']
            advertiser = Advertiser._av_get_or_create(
                network,
                row.get('advertiser_external_id'),
                row.get('advertiser_name'),
                commission_note=row.get('commission_note') or '',
            )
            verified = verify_target_url(network, target_url)
            if not verified:
                _logger.warning(
                    'CJ returned a link on an unrecognised host, storing offer '
                    '%r as draft for review: %s', row.get('name'), target_url,
                )
            vals = {
                'name': row['name'],
                'network': network,
                'source': row.get('source') or 'manual',
                'external_id': row.get('external_id') or False,
                'description': row.get('description') or '',
                'image_url': row.get('image_url') or '',
                'keywords': row.get('keywords') or '',
                'commission_note': row.get('commission_note') or '',
                'advertiser_id': advertiser.id or False,
                'price': row.get('price') or 0.0,
                'currency_id': self._av_currency(row.get('currency_code')).id,
            }
            existing = self.with_context(active_test=False).search([
                ('network', '=', network),
                ('external_id', '=', row.get('external_id') or False),
            ], limit=1) if row.get('external_id') else self.browse()

            if existing:
                # An offer a human rejected stays rejected: re-discovering it
                # must not quietly undo that decision.
                if existing.state != 'rejected':
                    vals['state'] = 'approved' if verified else 'draft'
                # Only the link itself is re-verified; keep the stored one when
                # the new one would fail the check.
                if verified or not existing.target_url:
                    vals['target_url'] = target_url
                existing.write(vals)
                stored |= existing
            else:
                vals['target_url'] = target_url
                vals['state'] = 'approved' if verified else 'draft'
                stored |= self.create(vals)
        return stored

    @api.model
    def _av_currency(self, code):
        """Resolve a network currency code, falling back to the company's."""
        if code:
            currency = self.env['res.currency'].with_context(active_test=False).search(
                [('name', '=', code.upper())], limit=1,
            )
            if currency:
                return currency
        return self.env.company.currency_id

    @api.model
    def _av_discover_for_keywords(self, keywords):
        """Ask CJ for offers matching `keywords` and store what comes back.

        Called only when the local database has nothing good enough for an
        article, which turns the offer table into a cache that fills from real
        demand instead of from a maintained list of seed terms. Product Feed
        first; Link Search is the fallback for advertisers that publish no feed.
        """
        if not keywords:
            return self.browse()
        client = self.env['affiliate.cj.client']
        if not client._av_is_configured():
            return self.browse()
        rows = client._av_search_products(keywords)
        if not rows:
            rows = client._av_search_links(keywords)
        if not rows:
            return self.browse()
        return self._av_store_discovered(rows)
