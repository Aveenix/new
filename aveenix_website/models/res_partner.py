from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    aveenix_welcome_offer_optin = fields.Boolean(
        string='Welcome Offer Opt-in',
        help='Set when this contact submitted their email through the website '
             '"$20 off your first order" footer promo.',
    )

    av_welcome_discount_eligible = fields.Boolean(
        string='Welcome Discount Eligible',
        compute='_compute_av_welcome_discount',
        help='True when the new-user welcome discount is enabled and this '
             'customer has no confirmed order yet, so the first-order perk '
             'still applies to them.',
    )
    av_welcome_discount_label = fields.Char(
        string='Welcome Discount',
        compute='_compute_av_welcome_discount',
        help='Display text for the welcome discount (e.g. "$20 OFF").',
    )

    @api.depends('aveenix_welcome_offer_optin')
    def _compute_av_welcome_discount(self):
        # Depends is nominal (recompute cheaply on form load); eligibility is
        # driven by order history + settings, evaluated per partner below.
        info = self.env.company._av_welcome_discount_info()
        for partner in self:
            eligible = info['enabled'] and partner._av_welcome_discount_eligible()
            partner.av_welcome_discount_eligible = eligible
            partner.av_welcome_discount_label = info['label'] if eligible else False

    def _av_welcome_discount_eligible(self):
        """True if this partner still qualifies for the new-user welcome
        discount, i.e. has no confirmed order yet. Mirrors the checkout gate in
        sale_order._av_partner_has_prior_order so the banner promise matches
        what the customer actually gets."""
        self.ensure_one()
        if not self.id:
            return True
        # sudo(): a portal/public user must not read other orders; this is a
        # scoped existence check on their own partner to decide banner display.
        has_order = self.env['sale.order'].sudo().search_count([
            ('partner_id', '=', self.id),
            ('state', '=', 'sale'),
        ], limit=1)
        return not has_order
