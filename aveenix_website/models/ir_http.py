import logging

import requests

from odoo import models
from odoo.http import request

_logger = logging.getLogger(__name__)

RECAPTCHA_VERIFY_URL = 'https://www.google.com/recaptcha/api/siteverify'
RECAPTCHA_TIMEOUT = 10


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def _verify_recaptcha_v2(self, token):
        """Server-side validation of a reCAPTCHA v2 ('I'm not a robot') token.

        Returns True if the user passed the challenge. If no secret key is
        configured, validation is skipped (returns True) so the site keeps
        working until keys are set.
        """
        get_param = request.env['ir.config_parameter'].sudo().get_param
        # Master toggle: when the feature is off, skip validation entirely.
        if get_param('aveenix_website.recaptcha_v2_enabled') != 'True':
            return True
        secret = get_param('aveenix_website.recaptcha_v2_secret_key')
        if not secret:
            # Not configured yet — don't block submissions.
            return True
        if not token:
            return False
        try:
            resp = requests.post(
                RECAPTCHA_VERIFY_URL,
                data={
                    'secret': secret,
                    'response': token,
                    'remoteip': request.httprequest.remote_addr,
                },
                timeout=RECAPTCHA_TIMEOUT,
            )
            result = resp.json()
        except Exception:  # network / parse failure
            _logger.warning('reCAPTCHA v2 verification request failed', exc_info=True)
            return False
        return bool(result.get('success'))
