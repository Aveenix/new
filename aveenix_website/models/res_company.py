from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    # Odoo ships native social_* fields (facebook, instagram, linkedin,
    # youtube, tiktok, twitter, github, discord) but not Pinterest, so we add
    # it here to complete the website footer social links.
    social_pinterest = fields.Char(
        string='Pinterest Account',
        help='Full Pinterest profile URL shown in the website footer.',
    )

    def _av_welcome_discount_info(self):
        """Single source of truth for the new-user welcome-discount banner.

        Returns a dict the frontend templates and backend views can share so
        the amount / on-off / label always match the real first-order discount
        configured in Settings → Website. ``label`` is the display string like
        "$20 OFF".
        """
        # sudo(): config parameters are admin-restricted, but the banner must
        # render for public/portal visitors too — read-only, non-sensitive.
        icp = self.env['ir.config_parameter'].sudo()
        enabled = icp.get_param('aveenix_website.welcome_discount_enabled') == 'True'
        amount = float(icp.get_param('aveenix_website.welcome_discount_amount') or 0.0)
        symbol = (self or self.env.company).currency_id.symbol or ''
        return {
            'enabled': bool(enabled and amount > 0),
            'amount': amount,
            'symbol': symbol,
            'label': '%s%g OFF' % (symbol, amount),
        }
