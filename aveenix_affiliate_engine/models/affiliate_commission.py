"""Revenue pulled back from the network and joined to the click that earned it."""

import logging
from datetime import timedelta

from odoo import api, fields, models

from .affiliate_network import NETWORKS, NETWORK_CJ

_logger = logging.getLogger(__name__)

# CJ truncates long reporting windows, and commissions can post days after the
# click, so the cron re-reads a trailing window every night and relies on
# commission_id being unique to avoid double-counting.
_LOOKBACK_DAYS = 7


class AffiliateCommission(models.Model):
    """One commission as the network reports it.

    The row CJ sends carries a shopper id, which is the `sid` the redirect put
    on the click URL. Resolving it back to our click log is what turns network
    revenue into per-article and per-placement revenue — without it, reporting
    stops at "this advertiser earned us money" and can never answer which
    article did the work.
    """

    _name = 'affiliate.commission'
    _description = 'Affiliate Commission'
    _order = 'event_date desc, id desc'
    _rec_name = 'external_id'

    network = fields.Selection(NETWORKS, string='Network', required=True, index=True)
    external_id = fields.Char(string='Commission ID', required=True, index=True)
    order_id_external = fields.Char(string='Order Reference')
    advertiser_id = fields.Many2one('affiliate.advertiser', string='Advertiser', index=True)
    click_id = fields.Many2one(
        comodel_name='affiliate.click.log',
        string='Click',
        index=True,
        ondelete='set null',
        help='The logged click this commission was traced back to, via the '
             'tracking id carried on the outbound link.',
    )
    offer_id = fields.Many2one('affiliate.offer', string='Offer', index=True, ondelete='set null')
    news_id = fields.Many2one('aveenix.news', string='Article', index=True, ondelete='set null')
    placement_id = fields.Many2one(
        'affiliate.offer.placement', string='Placement', ondelete='set null',
    )
    sale_amount = fields.Monetary(string='Sale Amount', currency_field='currency_id')
    commission_amount = fields.Monetary(string='Commission', currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        default=lambda self: self.env.company.currency_id, ondelete='restrict',
    )
    status = fields.Char(string='Status')
    action_type = fields.Char(string='Action Type')
    event_date = fields.Datetime(string='Event Date', index=True)
    tracking_id = fields.Char(
        string='Tracking ID', index=True,
        help='The sid/tid value the network echoed back.',
    )

    # The nightly cron deliberately re-reads a trailing window, so this index
    # is what makes re-reading idempotent instead of double-counting revenue.
    _network_external_id_uniq = models.Constraint(
        'UNIQUE(network, external_id)',
        'This commission has already been imported.',
    )

    # ── Import ───────────────────────────────────────────────────────────

    @api.model
    def _av_cron_import_cj_commissions(self, lookback_days=_LOOKBACK_DAYS):
        """Pull recent CJ commissions and attribute them to clicks."""
        client = self.env['affiliate.cj.client']
        if not client._av_is_configured():
            return 0
        before = fields.Datetime.now()
        since = before - timedelta(days=lookback_days)
        records = client._av_fetch_commissions(
            since.strftime('%Y-%m-%dT%H:%M:%SZ'),
            before.strftime('%Y-%m-%dT%H:%M:%SZ'),
        )
        imported = 0
        for row in records:
            if self._av_store_cj_record(row):
                imported += 1
        if imported:
            _logger.info('Imported %s new CJ commission record(s).', imported)
        return imported

    @api.model
    def _av_store_cj_record(self, row):
        """Create or refresh one CJ commission row. True when newly created."""
        external_id = str(row.get('commissionId') or '').strip()
        if not external_id:
            return False
        tracking_id = (row.get('shopperId') or '').strip()
        click = self.env['affiliate.click.log'].search(
            [('tracking_id', '=', tracking_id)], limit=1,
        ) if tracking_id else self.env['affiliate.click.log']

        vals = {
            'network': NETWORK_CJ,
            'external_id': external_id,
            'order_id_external': str(row.get('orderId') or ''),
            'status': row.get('actionStatus') or '',
            'action_type': row.get('actionType') or '',
            'sale_amount': self._av_float(row.get('saleAmountUsd')),
            'commission_amount': self._av_float(row.get('pubCommissionAmountUsd')),
            'currency_id': self.env['affiliate.offer']._av_currency('USD').id,
            'event_date': self._av_datetime(row.get('eventDate') or row.get('postingDate')),
            'tracking_id': tracking_id,
            'advertiser_id': self.env['affiliate.advertiser']._av_get_or_create(
                NETWORK_CJ, row.get('advertiserId'), row.get('advertiserName'),
            ).id or False,
            # Attribution comes from the click, which already knows the article
            # and placement. Copied onto the commission so revenue reporting
            # keeps working if a click row is ever pruned.
            'click_id': click.id or False,
            'offer_id': click.offer_id.id or False,
            'news_id': click.news_id.id or False,
            'placement_id': click.placement_id.id or False,
        }
        existing = self.search([
            ('network', '=', NETWORK_CJ), ('external_id', '=', external_id),
        ], limit=1)
        if existing:
            # CJ corrects and reverses commissions after the fact, so an
            # already-imported row is updated rather than skipped.
            existing.write(vals)
            return False
        self.create(vals)
        return True

    @api.model
    def _av_float(self, value):
        try:
            return float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0

    @api.model
    def _av_datetime(self, value):
        if not value:
            return False
        try:
            return fields.Datetime.to_datetime(str(value).replace('Z', '').replace('T', ' ')[:19])
        except Exception:
            return False
