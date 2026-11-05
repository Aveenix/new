"""The record of what the matcher decided for one article."""

from odoo import api, fields, models


class AffiliateOfferPlacement(models.Model):
    """One offer placed in one article, at one position.

    This exists as a stored record rather than being worked out at page render
    for three reasons: matching involves an AI call and a possible network
    round-trip, which has no business happening while a visitor waits; the same
    article must show the same recommendation to everyone; and a click needs
    something stable to attribute itself to. The score and matched keywords are
    kept so an editor can see *why* an offer was chosen.
    """

    _name = 'affiliate.offer.placement'
    _description = 'Affiliate Offer Placement'
    _order = 'score desc, id'
    _rec_name = 'offer_id'

    news_id = fields.Many2one(
        comodel_name='aveenix.news',
        string='Article',
        required=True,
        index=True,
        ondelete='cascade',
    )
    offer_id = fields.Many2one(
        comodel_name='affiliate.offer',
        string='Offer',
        required=True,
        index=True,
        ondelete='cascade',
    )
    position = fields.Selection(
        [
            ('in_content', 'Inside Article'),
            ('sidebar', 'Sidebar'),
        ],
        string='Position',
        default='in_content',
        required=True,
    )
    score = fields.Integer(
        string='Relevance',
        help='0-100. Offers below the configured minimum are never placed.',
    )
    matched_keywords = fields.Char(
        string='Matched On',
        help='The article keywords this offer matched, for review.',
    )
    active = fields.Boolean(string='Active', default=True)
    network = fields.Selection(related='offer_id.network', store=True, string='Network')
    category = fields.Selection(
        related='news_id.category', store=True, string='Article Category',
    )
    click_count = fields.Integer(string='Clicks', compute='_compute_click_count')

    _news_offer_uniq = models.Constraint(
        'UNIQUE(news_id, offer_id)',
        'This offer is already placed in that article.',
    )

    def _compute_click_count(self):
        grouped = self.env['affiliate.click.log']._read_group(
            [('placement_id', 'in', self.ids)],
            groupby=['placement_id'],
            aggregates=['__count'],
        )
        counts = {placement.id: count for placement, count in grouped}
        for placement in self:
            placement.click_count = counts.get(placement.id, 0)

    def _av_is_live(self):
        """True when this placement may be rendered or clicked.

        Re-tests the whole chain each time — master switch, placement, offer,
        advertiser, section — because any link in it can be switched off after
        the placement was created, and a switch is only worth having if it takes
        effect without a re-match.

        The master switch belongs here rather than only in the controller that
        renders the page: the click route is a second entry point, and checking
        it in one shared predicate is what stops "engine off" from meaning
        "no new cards, but old links still earn".
        """
        self.ensure_one()
        return bool(
            self.env['affiliate.offer']._av_settings()['enabled']
            and self.active
            and self.offer_id._av_is_placeable()
            and self.env['affiliate.section']._av_allows(self.news_id.category)
        )

    @api.model
    def _av_live_for_article(self, article):
        """Live placements for `article`, best first."""
        return article.av_placement_ids.filtered(
            lambda placement: placement._av_is_live()
        ).sorted(key=lambda placement: -placement.score)

    def action_open_offer(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'affiliate.offer',
            'res_id': self.offer_id.id,
            'view_mode': 'form',
        }
