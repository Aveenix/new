"""Affiliate engine settings.

Every credential here is stored as a system parameter and read server-side only
(see `affiliate.cj.client._av_credentials`). None of them is ever placed in a
template context, a website field or an asset bundle, which is what keeps the CJ
token out of the frontend.
"""

from odoo import _, fields, models
from odoo.exceptions import UserError

from .affiliate_offer import (
    PARAM_CJ_DISCOVERY,
    PARAM_CLICKBANK_NICKNAME,
    PARAM_DISCLOSURE,
    PARAM_ENABLED,
    PARAM_MAX_OFFERS,
    PARAM_MIN_RELEVANCE,
)
from .cj_client import (
    PARAM_ADS_ENDPOINT,
    PARAM_COMMISSION_ENDPOINT,
    PARAM_COMPANY_ID,
    PARAM_TOKEN,
    PARAM_WEBSITE_ID,
)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # ── Engine ───────────────────────────────────────────────────────────

    aveenix_affiliate_enabled = fields.Boolean(
        string='Enable Affiliate Engine',
        config_parameter=PARAM_ENABLED,
        help='Master switch. When off, no offers are matched to articles and no '
             'existing placement is shown.',
    )
    aveenix_affiliate_min_relevance = fields.Integer(
        string='Minimum Relevance Score',
        config_parameter=PARAM_MIN_RELEVANCE,
        help='0-100. An offer is only placed in an article when it scores at '
             'least this. A section match alone scores 40, so a value above 40 '
             'requires a keyword match as well.',
    )
    aveenix_affiliate_max_offers = fields.Integer(
        string='Max Offers per Article',
        config_parameter=PARAM_MAX_OFFERS,
        help='1-4. The best offer goes inside the article; the rest go in the '
             'sidebar.',
    )
    aveenix_affiliate_disclosure = fields.Char(
        string='Affiliate Disclosure',
        config_parameter=PARAM_DISCLOSURE,
        help='Shown with every affiliate recommendation. Required by advertising '
             'rules in most markets, so placement renders it unconditionally.',
    )

    # ── CJ Affiliate (Commission Junction) ───────────────────────────────

    aveenix_affiliate_cj_token = fields.Char(
        string='CJ Personal Access Token',
        config_parameter=PARAM_TOKEN,
        help='From developers.cj.com. Server-side only — it is never sent to a '
             'browser. CJ shows a new token once, so store it elsewhere too.',
    )
    aveenix_affiliate_cj_company_id = fields.Char(
        string='CJ Publisher ID (CID)',
        config_parameter=PARAM_COMPANY_ID,
        help='Your CJ publisher company id. Required alongside the token by '
             'every CJ call.',
    )
    aveenix_affiliate_cj_website_id = fields.Char(
        string='CJ Promotional Property ID',
        config_parameter=PARAM_WEBSITE_ID,
        help='The property id CJ issued for aveenix.com. Needed by Link Search; '
             'use the button below to list your properties.',
    )
    aveenix_affiliate_cj_discovery = fields.Boolean(
        string='Automatic CJ Product Discovery',
        config_parameter=PARAM_CJ_DISCOVERY,
        help='Let the matcher search CJ for products when no stored offer is '
             'relevant enough for an article. Turn off to work only from offers '
             'already in the database.',
    )
    aveenix_affiliate_cj_ads_endpoint = fields.Char(
        string='CJ Ads API Endpoint',
        config_parameter=PARAM_ADS_ENDPOINT,
        help='Leave empty unless CJ moves the GraphQL endpoint.',
    )
    aveenix_affiliate_cj_commission_endpoint = fields.Char(
        string='CJ Commission API Endpoint',
        config_parameter=PARAM_COMMISSION_ENDPOINT,
        help='Leave empty unless CJ moves the GraphQL endpoint.',
    )

    # ── ClickBank ────────────────────────────────────────────────────────

    aveenix_affiliate_clickbank_nickname = fields.Char(
        string='ClickBank Affiliate Nickname',
        config_parameter=PARAM_CLICKBANK_NICKNAME,
        help='Your ClickBank account nickname. Used to build HopLinks for '
             'approved vendors, so nobody has to assemble one by hand.',
    )

    # ── Actions ──────────────────────────────────────────────────────────

    def action_av_load_cj_properties(self):
        """List CJ promotional properties so the right property id can be picked.

        CJ's Link Search is keyed on a promotional property, not on the account,
        and picking the wrong id silently returns links attributed to another
        property. Showing the real list is cheaper than asking an admin to find
        it in the CJ dashboard and retype it.
        """
        self.ensure_one()
        properties = self.env['affiliate.cj.client']._av_list_promotional_properties()
        if not properties:
            raise UserError(_(
                'CJ returned no promotional properties. Check the token and '
                'Publisher ID, then look in the server log for the exact reply '
                'from CJ.'
            ))
        lines = '\n'.join(
            '  %s  —  %s (%s)' % (
                prop.get('id') or '?', prop.get('name') or '?',
                prop.get('status') or '',
            )
            for prop in properties
        )
        # A successful lookup is not an error, so it is shown as a sticky
        # notification rather than through UserError's "Invalid Operation".
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('CJ promotional properties'),
                'message': _(
                    '%s\n\nCopy the id for aveenix.com into "CJ Promotional '
                    'Property ID".', lines,
                ),
                'type': 'success',
                'sticky': True,
            },
        }

    def action_av_sync_cj_advertisers(self):
        self.ensure_one()
        count = self.env['affiliate.advertiser']._av_cron_sync_cj_advertisers()
        if count is None:
            raise UserError(_(
                'Could not read advertisers from CJ. Check the token and '
                'Publisher ID, then look in the server log for the exact reply '
                'from CJ.'
            ))
        if not count:
            raise UserError(_(
                'CJ is reachable, but no advertiser has approved Aveenix yet.\n\n'
                'In the CJ dashboard, apply to programs under Partners → '
                'Advertisers. Once an advertiser approves you, sync again.'
            ))
        return {
            'type': 'ir.actions.act_window',
            'name': _('CJ Advertisers'),
            'res_model': 'affiliate.advertiser',
            'view_mode': 'list,form',
            'domain': [('network', '=', 'cj')],
        }
