"""Advertisers (CJ) and vendors (ClickBank) whose offers Aveenix may place."""

from odoo import api, fields, models

from .affiliate_network import NETWORKS


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
        """Refresh the joined-program list from CJ Advertiser Lookup."""
        rows = self.env['affiliate.cj.client']._av_list_advertisers()
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
