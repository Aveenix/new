import json

from odoo import _, http
from odoo.http import request
from odoo.addons.website.controllers.form import WebsiteForm
from odoo.addons.auth_signup.controllers.main import AuthSignupHome


class AveenixWebsiteForm(WebsiteForm):

    @http.route()
    def website_form(self, model_name, **kwargs):
        """Validate the reCAPTCHA v2 token before processing the website form.

        Only enforced for the contact form (crm.lead). Other website forms are
        left untouched.
        """
        if model_name == 'crm.lead':
            token = request.params.get('g-recaptcha-response')
            if not request.env['ir.http']._verify_recaptcha_v2(token):
                return json.dumps({
                    'error': _('Captcha verification failed. Please confirm you are not a robot and try again.'),
                })
        return super().website_form(model_name, **kwargs)


class AveenixAuthSignup(AuthSignupHome):

    _CAPTCHA_ERROR = 'Captcha verification failed. Please confirm you are not a robot and try again.'

    @http.route()
    def web_login(self, *args, **kw):
        """Validate reCAPTCHA v2 on the login POST before authenticating."""
        if request.httprequest.method == 'POST' and request.params.get('login'):
            token = request.params.get('g-recaptcha-response')
            if not request.env['ir.http']._verify_recaptcha_v2(token):
                # Re-render the login form with an error, without authenticating.
                values = {k: v for k, v in request.params.items() if k != 'password'}
                values['error'] = _(self._CAPTCHA_ERROR)
                return request.render('web.login', values)
        return super().web_login(*args, **kw)

    @http.route()
    def web_auth_signup(self, *args, **kw):
        """Validate reCAPTCHA v2 on the signup POST before creating the account."""
        if request.httprequest.method == 'POST':
            token = request.params.get('g-recaptcha-response')
            if not request.env['ir.http']._verify_recaptcha_v2(token):
                qcontext = self.get_auth_signup_qcontext()
                qcontext['error'] = _(self._CAPTCHA_ERROR)
                response = request.render('auth_signup.signup', qcontext)
                response.headers['X-Frame-Options'] = 'SAMEORIGIN'
                response.headers['Content-Security-Policy'] = "frame-ancestors 'self'"
                return response
        return super().web_auth_signup(*args, **kw)

    @http.route()
    def web_auth_reset_password(self, *args, **kw):
        """Validate reCAPTCHA v2 on the reset-password POST."""
        if request.httprequest.method == 'POST':
            token = request.params.get('g-recaptcha-response')
            if not request.env['ir.http']._verify_recaptcha_v2(token):
                qcontext = self.get_auth_signup_qcontext()
                qcontext['error'] = _(self._CAPTCHA_ERROR)
                response = request.render('auth_signup.reset_password', qcontext)
                response.headers['X-Frame-Options'] = 'SAMEORIGIN'
                response.headers['Content-Security-Policy'] = "frame-ancestors 'self'"
                return response
        return super().web_auth_reset_password(*args, **kw)
