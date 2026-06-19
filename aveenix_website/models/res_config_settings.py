from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

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
