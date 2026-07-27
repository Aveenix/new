from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # ── Welcome discount for new users ────────────────────────────────
    # A first-order-only fixed discount, applied automatically at checkout
    # through the loyalty "welcome" promotion program. The amount here is
    # pushed onto that program's reward so admins can tune it with no code
    # change (fully dynamic from the backend).
    aveenix_welcome_discount_enabled = fields.Boolean(
        string='Enable New-User Welcome Discount',
        config_parameter='aveenix_website.welcome_discount_enabled',
        help='Give first-time customers a fixed discount on their first order, '
             'applied automatically at checkout. Turn off to disable.',
    )
    aveenix_welcome_discount_amount = fields.Float(
        string='Welcome Discount Amount',
        config_parameter='aveenix_website.welcome_discount_amount',
        help='Fixed amount taken off the customer first order (e.g. 20.00). '
             'Only granted once, on the first order of a new account.',
    )
    aveenix_newsdata_api_key = fields.Char(
        string='NewsData.io API Key',
        config_parameter='aveenix_website.newsdata_api_key',
        help='Your API Key from NewsData.io to fetch live news articles.',
    )
    aveenix_newsdata_country_ids = fields.Many2many(
        related='website_id.aveenix_newsdata_country_ids',
        readonly=False,
        string='NewsData.io Countries',
    )
    aveenix_news_ad1_image = fields.Image(
        related='website_id.aveenix_news_ad1_image',
        readonly=False,
    )
    aveenix_news_ad1_url = fields.Char(
        related='website_id.aveenix_news_ad1_url',
        readonly=False,
    )
    aveenix_news_ad2_image = fields.Image(
        related='website_id.aveenix_news_ad2_image',
        readonly=False,
    )
    aveenix_news_ad2_url = fields.Char(
        related='website_id.aveenix_news_ad2_url',
        readonly=False,
    )
    currency_id = fields.Many2one(
        related='company_id.currency_id',
        string='Currency',
        readonly=True,
        help='Company currency, used to display the welcome discount amount.',
    )

    def set_values(self):
        super().set_values()
        # Keep the welcome promotion program in sync with the settings so the
        # amount is dynamic: saving Settings updates the reward + active flag.
        self._av_sync_welcome_discount_program()

    def _av_sync_welcome_discount_program(self):
        # sudo(): loyalty programs are restricted; settings are edited by an
        # admin who may not hold loyalty-manager rights, and the program is a
        # single system-owned record we keep aligned with the config values.
        program = self.env.ref(
            'aveenix_website.loyalty_program_welcome_discount',
            raise_if_not_found=False,
        )
        if not program:
            return
        program = program.sudo()
        enabled = self.aveenix_welcome_discount_enabled
        amount = self.aveenix_welcome_discount_amount or 0.0
        program.active = bool(enabled and amount > 0)
        reward = program.reward_ids[:1]
        if reward and amount > 0:
            reward.discount = amount

    # Admin notification: CC these address(es) on website order confirmation
    # emails so staff are alerted when an order comes in.
    aveenix_order_admin_cc = fields.Char(
        string='Order Notification Email',
        config_parameter='aveenix_website.order_admin_cc',
        help='Comma-separated admin email address(es) that receive a separate '
             'internal notification when a website order is placed. Leave empty '
             'to disable.',
    )

    # Master on/off switch for the reCAPTCHA feature across the website.
    aveenix_recaptcha_v2_enabled = fields.Boolean(
        string='Enable Website Captcha',
        config_parameter='aveenix_website.recaptcha_v2_enabled',
        help='Show and validate reCAPTCHA v2 on contact, login, signup and reset-password forms.',
    )

    # Google reCAPTCHA v2 ("I'm not a robot" checkbox) keys.
    # Stored as system parameters so they're configurable and not hardcoded.
    aveenix_recaptcha_v2_site_key = fields.Char(
        string='reCAPTCHA v2 Site Key',
        config_parameter='aveenix_website.recaptcha_v2_site_key',
        help='Public site key from https://www.google.com/recaptcha/admin (reCAPTCHA v2 checkbox).',
    )
    aveenix_recaptcha_v2_secret_key = fields.Char(
        string='reCAPTCHA v2 Secret Key',
        config_parameter='aveenix_website.recaptcha_v2_secret_key',
        help='Private secret key used server-side to verify the token.',
    )

    # Auto-publish after image download — one toggle per product type.
    aveenix_auto_publish_affiliate = fields.Boolean(
        string='Auto-publish Affiliate Products',
        config_parameter='aveenix_website.auto_publish_affiliate',
        help='Publish affiliate products to the website automatically once '
             'their image is successfully downloaded by the image cron.',
    )
    aveenix_auto_publish_dropship = fields.Boolean(
        string='Auto-publish Dropship Products',
        config_parameter='aveenix_website.auto_publish_dropship',
        help='Publish dropship products to the website automatically once '
             'their image is successfully downloaded by the image cron.',
    )
    aveenix_auto_publish_regular = fields.Boolean(
        string='Auto-publish Regular Products',
        config_parameter='aveenix_website.auto_publish_regular',
        help='Publish regular (non-affiliate, non-dropship) products to the '
             'website automatically once their image is downloaded.',
    )

    # Homepage featured categories — proxied from the current website record so
    # admins pick them in Settings. related+readonly=False writes back to website.
    aveenix_home_categ_ids = fields.Many2many(
        related='website_id.aveenix_home_categ_ids',
        readonly=False,
        string='Homepage Featured Categories',
        help='Categories featured on the homepage after New Arrivals, each as a '
             'product row with a View All link to the filtered shop.',
    )

    # Header menu categories — proxied from the current website record so
    # admins pick them in Settings. related+readonly=False writes back to website.
    aveenix_header_menu_categ_ids = fields.Many2many(
        related='website_id.aveenix_header_menu_categ_ids',
        readonly=False,
        string='Header Menu Categories',
        help='Categories shown as menu links in the header, right after Shop.',
    )
