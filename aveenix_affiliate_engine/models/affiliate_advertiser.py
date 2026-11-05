"""Advertisers (CJ) and vendors (ClickBank) whose offers Aveenix may place."""

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .affiliate_network import NETWORK_CJ, NETWORKS

_logger = logging.getLogger(__name__)

# Per advertiser per run. Bounds CJ calls and cron time; a larger catalogue is
# better narrowed with shop keywords than paged through wholesale.
SHOP_IMPORT_LIMIT = 100


class AffiliateAdvertiser(models.Model):
    """One affiliate program Aveenix is working with.

    Both networks collapse onto this: a CJ *advertiser* and a ClickBank *vendor*
    are the same thing for our purposes — the party whose offers we may promote
    and who decides the commission. Keeping them in one model is what lets the
    matcher apply a single "is this program enabled?" test regardless of network.

    Archiving an advertiser disables every one of its offers at once, which is
    the per-advertiser switch the brief asks for and the fastest way to react to
    a program being paused or a partnership ending.
    """

    _name = 'affiliate.advertiser'
    _description = 'Affiliate Advertiser'
    _order = 'name'

    name = fields.Char(string='Name', required=True)
    network = fields.Selection(NETWORKS, string='Network', required=True, index=True)
    external_id = fields.Char(
        string='Network ID',
        required=True,
        index=True,
        help='CJ advertiser (company) id, or the ClickBank vendor nickname.',
    )
    active = fields.Boolean(
        string='Active',
        default=True,
        help='Uncheck to stop placing any offer from this advertiser.',
    )
    commission_note = fields.Char(
        string='Commission',
        help='Commission terms as the network reports them, for reference only — '
             'actual earnings come from the network reporting APIs.',
    )
    program_url = fields.Char(string='Program URL')
    shop_import = fields.Boolean(
        string='Import Products to Shop',
        help='Pull this advertiser\'s CJ product feed on schedule and list the '
             'products on Aveenix as affiliate products with a Buy on Partner '
             'Site button. Only enable for programs you have been approved for.',
    )
    shop_keywords = fields.Char(
        string='Shop Keywords',
        help='Optional, comma-separated. Narrows the feed to matching products; '
             'empty imports the first products of the whole feed.',
    )
    shop_last_sync = fields.Datetime(string='Last Shop Sync', readonly=True)
    shop_sync_message = fields.Char(string='Shop Sync Result', readonly=True)
    shop_product_count = fields.Integer(
        string='Shop Products', compute='_compute_shop_product_count',
    )
    offer_ids = fields.One2many('affiliate.offer', 'advertiser_id', string='Offers')
    offer_count = fields.Integer(string='Offer Count', compute='_compute_offer_stats')
    approved_offer_count = fields.Integer(
        string='Approved Offers', compute='_compute_offer_stats',
    )

    # Upserted by discovery on every sync, so uniqueness has to be enforced
    # by the database rather than by the search that precedes the write.
    _network_external_id_uniq = models.Constraint(
        'UNIQUE(network, external_id)',
        'This advertiser is already registered for that network.',
    )

    @api.depends('offer_ids', 'offer_ids.state')
    def _compute_offer_stats(self):
        for advertiser in self:
            offers = advertiser.offer_ids
            advertiser.offer_count = len(offers)
            advertiser.approved_offer_count = len(
                offers.filtered(lambda offer: offer.state == 'approved')
            )

    def _compute_shop_product_count(self):
        grouped = self.env['product.template']._read_group(
            [('affiliate_offer_id.advertiser_id', 'in', self.ids)],
            groupby=['affiliate_offer_id'],
            aggregates=['__count'],
        )
        counts = {}
        for offer, count in grouped:
            counts[offer.advertiser_id.id] = counts.get(offer.advertiser_id.id, 0) + count
        for advertiser in self:
            advertiser.shop_product_count = counts.get(advertiser.id, 0)

    @api.model
    def _av_get_or_create(self, network, external_id, name, **extra):
        """Find or create the advertiser a discovered offer belongs to.

        Discovery creates advertisers as a side effect of finding offers, so the
        enable/disable list fills itself from real results and an admin never has
        to pre-register a program before its products can be found.
        """
        if not external_id:
            return self.browse()
        advertiser = self.with_context(active_test=False).search([
            ('network', '=', network),
            ('external_id', '=', str(external_id)),
        ], limit=1)
        if advertiser:
            # Names and commission terms change on the network side; the
            # active flag is ours and is never overwritten by a sync.
            updates = {
                key: value for key, value in extra.items()
                if value and advertiser[key] != value
            }
            if name and advertiser.name != name:
                updates['name'] = name
            if updates:
                advertiser.write(updates)
            return advertiser
        return self.create(dict(
            extra,
            network=network,
            external_id=str(external_id),
            name=name or str(external_id),
        ))

    def action_view_offers(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': 'affiliate.offer',
            'view_mode': 'list,form',
            'domain': [('advertiser_id', '=', self.id)],
            'context': {'default_advertiser_id': self.id, 'default_network': self.network},
        }

    @api.model
    def _av_cron_sync_cj_advertisers(self):
        """Refresh the joined-program list from CJ Advertiser Lookup.

        Returns the number of joined programs, or None when CJ could not be read.
        """
        rows = self.env['affiliate.cj.client']._av_list_advertisers()
        if rows is None:
            return None
        for row in rows:
            self._av_get_or_create(
                row['network'], row['external_id'], row['name'],
                commission_note=row.get('commission_note') or '',
                program_url=row.get('program_url') or '',
            )
        return len(rows)

    def action_sync_cj_advertisers(self):
        self._av_cron_sync_cj_advertisers()
        return True

    # ── Shop import ──────────────────────────────────────────────────────

    def _av_import_shop_products(self):
        """Pull each advertiser's CJ feed into offers and shop products.

        Goes through `affiliate.offer._av_store_discovered`, the same upsert the
        article matcher uses, so duplicate prevention, link verification and
        "a rejected offer stays rejected" hold here too. The outcome is written
        on the advertiser, which is the admin's view of whether the sync works;
        the exact CJ reply for a failure is in the server log.
        """
        client = self.env['affiliate.cj.client']
        Offer = self.env['affiliate.offer']
        imported = 0
        for advertiser in self:
            if advertiser.network != NETWORK_CJ or not advertiser.active:
                continue
            keywords = [
                term.strip() for term in (advertiser.shop_keywords or '').split(',')
                if term.strip()
            ]
            message = ''
            try:
                with self.env.cr.savepoint():
                    rows = client._av_search_products(
                        keywords, advertiser_ids=[advertiser.external_id],
                        limit=SHOP_IMPORT_LIMIT,
                    )
                    offers = Offer._av_store_discovered(rows)
                    publishable = offers.filtered(
                        lambda offer: offer._av_is_placeable() and offer._av_is_in_stock()
                    )
                    publishable.action_publish_to_shop()
                    # Re-check every product of this advertiser, not just the ones
                    # CJ returned, so a rejected or archived offer leaves the shop.
                    Offer.with_context(active_test=False).search([
                        ('advertiser_id', '=', advertiser.id),
                        ('product_tmpl_ids', '!=', False),
                    ])._av_sync_shop_products()
                    imported += len(publishable)
                    message = _(
                        '%(found)s products from CJ, %(listed)s listed in the shop.',
                        found=len(rows), listed=len(publishable),
                    ) if rows else _('CJ returned no products — check the server log.')
            except Exception as error:  # noqa: BLE001 — one advertiser must not stop the rest
                _logger.exception('CJ shop import failed for advertiser %s', advertiser.id)
                message = _('Failed: %s', error)
            advertiser.write({
                'shop_last_sync': fields.Datetime.now(),
                'shop_sync_message': message[:255],
            })
        return imported

    @api.model
    def _av_cron_import_shop_products(self):
        imported = 0
        if self.env['affiliate.cj.client']._av_is_configured():
            imported = self.search([
                ('network', '=', NETWORK_CJ), ('shop_import', '=', True),
            ])._av_import_shop_products()
        else:
            _logger.info('CJ shop import skipped: CJ credentials not configured.')
        # Every shop product, whatever its advertiser: one whose advertiser was
        # archived or whose import was switched off is skipped above, and must
        # still come off the shop once its offer is no longer clickable.
        self.env['affiliate.offer'].with_context(active_test=False).search([
            ('product_tmpl_ids', '!=', False),
        ])._av_sync_shop_products()
        return imported

    def action_import_shop_products(self):
        if not self.env['affiliate.cj.client']._av_is_configured():
            raise UserError(_(
                'Set the CJ Personal Access Token and Publisher ID (CID) in '
                'Website Settings first.'
            ))
        self._av_import_shop_products()
        return True

    def action_view_shop_products(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Shop Products'),
            'res_model': 'product.template',
            'view_mode': 'list,form',
            'domain': [('affiliate_offer_id.advertiser_id', '=', self.id)],
            'context': {'active_test': False},
        }
