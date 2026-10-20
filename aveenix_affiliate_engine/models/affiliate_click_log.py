"""Article/offer attribution added to the site's existing click log."""

from odoo import fields, models

from .affiliate_network import NETWORKS


class AffiliateClickLog(models.Model):
    """One click table for the whole site, extended rather than duplicated.

    `aveenix_website` already logs clicks on outbound product links. An offer
    click is the same event about a different subject, so it belongs here: a
    second table would mean every "how much did outbound traffic earn?" question
    had to be asked twice and reconciled.

    `product_id` becomes optional in `aveenix_website` for this reason — a click
    can now be about an offer instead of a product. Exactly one of the two is
    set, and `display_name` is overridden below because the inherited
    `_rec_name` points at `product_id`, which offer clicks leave empty.
    """

    _inherit = 'affiliate.click.log'

    offer_id = fields.Many2one(
        comodel_name='affiliate.offer',
        string='Offer',
        index=True,
        ondelete='set null',
    )
    placement_id = fields.Many2one(
        comodel_name='affiliate.offer.placement',
        string='Placement',
        index=True,
        ondelete='set null',
        help='Which placement in which article produced this click.',
    )
    news_id = fields.Many2one(
        comodel_name='aveenix.news',
        string='Article',
        index=True,
        ondelete='set null',
        help='Stored directly as well as through the placement, so click '
             'history survives an article being re-matched or a placement '
             'being removed.',
    )
    network = fields.Selection(NETWORKS, string='Network', index=True)
    tracking_id = fields.Char(
        string='Tracking ID',
        index=True,
        help='The value sent to the network as tid/sid. Network commission '
             'reports echo it back, which is how revenue is matched to this click.',
    )
    position = fields.Selection(
        related='placement_id.position', store=True, string='Placement Position',
    )
    commission_ids = fields.One2many(
        'affiliate.commission', 'click_id', string='Commissions',
    )

    def _compute_display_name(self):
        for click in self:
            subject = click.offer_id.name or click.product_id.name or 'Outbound click'
            when = fields.Datetime.to_string(click.timestamp) if click.timestamp else ''
            click.display_name = '%s — %s' % (subject, when) if when else subject
