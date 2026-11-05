"""Affiliate shop products backed by a network offer."""

from odoo import fields, models


class ProductTemplate(models.Model):
    """Link an affiliate-type product to the offer it was published from.

    Set only on products created by `affiliate.offer.action_publish_to_shop`.
    Its presence is what tells the Buy on Partner Site redirect to send the
    visitor through the network's tracked link (CJ `sid`, ClickBank `tid`)
    instead of the plain retailer URL used for hand-made affiliate products.
    """

    _inherit = 'product.template'

    affiliate_offer_id = fields.Many2one(
        comodel_name='affiliate.offer',
        string='Affiliate Offer',
        index=True,
        copy=False,
        ondelete='set null',
        help='The CJ / ClickBank offer this product was published from. The '
             'offer sync keeps its link, price and availability up to date.',
    )
    affiliate_network = fields.Selection(
        related='affiliate_offer_id.network', string='Affiliate Network',
    )

    # NULLs are exempt in a Postgres unique index, so ordinary products are
    # untouched; an offer can never be published as two products.
    _affiliate_offer_uniq = models.Constraint(
        'UNIQUE(affiliate_offer_id)',
        'This affiliate offer is already published as a shop product.',
    )
