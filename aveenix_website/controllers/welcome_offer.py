import re

from odoo import http
from odoo.http import request

# Basic email shape check; the browser also enforces type="email" + required,
# this is the server-side backstop.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AveenixWelcomeOffer(http.Controller):
    """Footer '$20 off your first order' email capture.

    The actual discount is the auto-applied first-order welcome promotion
    (loyalty program). This endpoint only records the visitor's email so we
    can follow up, then confirms back to them. It intentionally does not issue
    a code — the discount applies automatically on their first order.
    """

    @http.route('/aveenix/welcome-offer', type='jsonrpc', auth='public', website=True)
    def welcome_offer(self, email=None, **kw):
        email = (email or '').strip().lower()
        if not email or not _EMAIL_RE.match(email):
            return {'ok': False, 'error': 'invalid_email'}

        # find-or-create a partner for this email so the lead is captured and
        # flagged as having opted into the welcome offer.
        # sudo(): public visitors have no res.partner write access; we only
        # touch/create the single partner matching the submitted email.
        Partner = request.env['res.partner'].sudo()
        partner = Partner.search([('email', '=ilike', email)], limit=1)
        if partner:
            if not partner.aveenix_welcome_offer_optin:
                partner.aveenix_welcome_offer_optin = True
        else:
            Partner.create({
                'name': email,
                'email': email,
                'aveenix_welcome_offer_optin': True,
            })
        return {'ok': True}
