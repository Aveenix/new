from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

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
