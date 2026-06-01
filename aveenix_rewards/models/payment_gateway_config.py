import json
import urllib.request
import urllib.parse
import urllib.error
import base64

from odoo import api, fields, models
from odoo.exceptions import UserError


class AveenixPaymentGatewayConfig(models.Model):
    _name = 'aveenix.payment.gateway.config'
    _description = 'Aveenix Payment Gateway Configuration'
    _rec_name = 'name'

    name = fields.Char(string='Name', required=True)
    company_id = fields.Many2one(
        comodel_name='res.company',
        required=True,
        default=lambda self: self.env.company,
        ondelete='cascade',
    )
    gateway = fields.Selection(
        selection=[
            ('paypal', 'PayPal'),
            ('stripe', 'Stripe'),
        ],
        required=True,
        string='Gateway',
    )
    mode = fields.Selection(
        selection=[('live', 'Live'), ('sandbox', 'Sandbox')],
        string='Mode',
        required=True,
        default='live',
    )
    api_key = fields.Char(
        string='Client ID / Secret Key',
        help='PayPal Client ID  or  Stripe Secret Key (sk_live_... / sk_test_...)',
    )
    api_secret = fields.Char(
        string='Client Secret',
        help='PayPal Client Secret. Leave blank for Stripe.',
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Payout Currency',
        default=lambda self: self.env.company.currency_id,
        help='Currency used for payouts. Auto-detected from Stripe on Test Connection.',
    )
    connection_status = fields.Selection(
        selection=[
            ('not_configured', 'Not Configured'),
            ('connected', 'Connected'),
            ('failed', 'Failed'),
        ],
        default='not_configured',
        string='Status',
        readonly=True,
    )
    connection_message = fields.Char(string='Last Test Result', readonly=True)
    last_tested = fields.Datetime(string='Last Tested', readonly=False)

    _sql_constraints = [
        ('unique_gateway_company', 'UNIQUE(gateway, company_id)',
         'Only one configuration per gateway per company is allowed.'),
    ]

    # ── URL helpers ──────────────────────────────────────────────────────

    def _paypal_base_url(self):
        if self.mode == 'sandbox':
            return 'https://api-m.sandbox.paypal.com'
        return 'https://api-m.paypal.com'

    def _stripe_base_url(self):
        return 'https://api.stripe.com'

    # ── Connection Test ───────────────────────────────────────────────────

    def action_test_connection(self):
        self.ensure_one()
        if not self.api_key:
            self.write({
                'connection_status': 'not_configured',
                'connection_message': 'API key is not set.',
                'last_tested': fields.Datetime.now(),
            })
            return
        if self.gateway == 'paypal':
            self._test_paypal()
        elif self.gateway == 'stripe':
            self._test_stripe()

    def _test_paypal(self):
        if not self.api_secret:
            self.write({
                'connection_status': 'not_configured',
                'connection_message': 'PayPal requires both Client ID and Client Secret.',
                'last_tested': fields.Datetime.now(),
            })
            return
        try:
            credentials = base64.b64encode(
                f'{self.api_key}:{self.api_secret}'.encode()
            ).decode()
            data = urllib.parse.urlencode({'grant_type': 'client_credentials'}).encode()
            req = urllib.request.Request(
                f'{self._paypal_base_url()}/v1/oauth2/token',
                data=data,
                headers={
                    'Authorization': f'Basic {credentials}',
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                method='POST',
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                body       = json.loads(resp.read().decode())
                app_id     = body.get('app_id', '-')
                token_type = body.get('token_type', '-')
                expires_in = body.get('expires_in', '-')
                # scope lists granted permissions — unique per account/app
                scope_list = body.get('scope', '').split()
                # Extract readable permission names from URLs
                permissions = ', '.join(
                    s.rstrip('/').split('/')[-1] for s in scope_list
                ) or '-'

            msg = (
                f'Authenticated'
            )
            self.write({
                'connection_status': 'connected',
                'connection_message': msg,
                'last_tested': fields.Datetime.now(),
            })
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            try:
                msg = json.loads(body).get('error_description', body)
            except Exception:
                msg = body[:120]
            self.write({
                'connection_status': 'failed',
                'connection_message': f'HTTP {e.code}: {msg}',
                'last_tested': fields.Datetime.now(),
            })
        except Exception as e:
            self.write({
                'connection_status': 'failed',
                'connection_message': str(e)[:120],
                'last_tested': fields.Datetime.now(),
            })

    def _test_stripe(self):
        try:
            req = urllib.request.Request(
                f'{self._stripe_base_url()}/v1/account',
                headers={'Authorization': f'Bearer {self.api_key}'},
                method='GET',
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = json.loads(resp.read().decode())
                account_id   = body.get('id', '-')
                display      = body.get('display_name') or body.get('business_profile', {}).get('name') or '-'
                email        = body.get('email') or '-'
                country      = body.get('country', '-').upper()
                currency     = body.get('default_currency', '-').upper()
                charges_ok   = '✓' if body.get('charges_enabled') else '✗'
                payouts_ok   = '✓' if body.get('payouts_enabled') else '✗'
                detected_currency_code = body.get('default_currency', '').upper()
                currency_rec = self.env['res.currency'].search(
                    [('name', '=', detected_currency_code)], limit=1
                )
                msg = (
                    f'Account: {display} ({account_id}) | '
                    f'Email: {email} | '
                    f'Country: {country} | '
                    f'Currency: {currency} | '
                    f'Charges: {charges_ok} | '
                    f'Payouts: {payouts_ok}'
                )
                vals = {
                    'connection_status': 'connected',
                    'connection_message': msg,
                    'last_tested': fields.Datetime.now(),
                }
                if currency_rec:
                    vals['currency_id'] = currency_rec.id
                self.write(vals)
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            try:
                msg = json.loads(body).get('error', {}).get('message', body)
            except Exception:
                msg = body[:120]
            self.write({
                'connection_status': 'failed',
                'connection_message': f'HTTP {e.code}: {msg}',
                'last_tested': fields.Datetime.now(),
            })
        except Exception as e:
            self.write({
                'connection_status': 'failed',
                'connection_message': str(e)[:120],
                'last_tested': fields.Datetime.now(),
            })

    # ── Payout ────────────────────────────────────────────────────────────

    def send_payout(self, amount, destination, description='Aveenix Reward Payout'):
        """
        Send money to customer.
        - Stripe: destination = Connected Account ID (acct_xxx)
        - PayPal: destination = customer PayPal email
        Returns payout reference string on success, raises UserError on failure.
        """
        self.ensure_one()
        if self.connection_status != 'connected':
            raise UserError(
                f'Gateway "{self.gateway}" is not connected. '
                'Please test the connection first in Configuration → Payment Gateways.'
            )
        if self.gateway == 'stripe':
            return self._stripe_payout(amount, destination, description)
        elif self.gateway == 'paypal':
            return self._paypal_payout(amount, destination, description)
        raise UserError(f'Unsupported gateway: {self.gateway}')

    def _stripe_payout(self, amount, destination, description):
        """
        Stripe Transfer to a Connected Account.
        amount  : float (INR rupees)
        destination : Stripe Connected Account ID e.g. acct_1ABC...
        Stripe amounts are in smallest currency unit (paise for INR).
        """
        amount_in_paise = int(round(amount * 100))
        currency = (self.currency_id.name or 'USD').lower()
        data = urllib.parse.urlencode({
            'amount': amount_in_paise,
            'currency': currency,
            'destination': destination,
            'description': description,
        }).encode()
        try:
            req = urllib.request.Request(
                f'{self._stripe_base_url()}/v1/transfers',
                data=data,
                headers={
                    'Authorization': f'Bearer {self.api_key}',
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                method='POST',
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode())
                transfer_id = body.get('id', '')
                return f'STRIPE:{transfer_id}'
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            try:
                msg = json.loads(body).get('error', {}).get('message', body)
            except Exception:
                msg = body[:200]
            raise UserError(f'Stripe Transfer failed: {msg}')
        except Exception as e:
            raise UserError(f'Stripe error: {e}')

    def _paypal_payout(self, amount, destination, description):
        """
        PayPal Payout to customer email.
        Requires PayPal Payouts API enabled on the account.
        """
        import uuid
        # Get access token first
        try:
            credentials = base64.b64encode(
                f'{self.api_key}:{self.api_secret}'.encode()
            ).decode()
            token_data = urllib.parse.urlencode(
                {'grant_type': 'client_credentials'}
            ).encode()
            token_req = urllib.request.Request(
                f'{self._paypal_base_url()}/v1/oauth2/token',
                data=token_data,
                headers={
                    'Authorization': f'Basic {credentials}',
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                method='POST',
            )
            with urllib.request.urlopen(token_req, timeout=10) as resp:
                token_body = json.loads(resp.read().decode())
                access_token = token_body['access_token']
        except Exception as e:
            raise UserError(f'PayPal authentication failed: {e}')

        # Send payout
        currency = (self.currency_id.name or 'USD').upper()
        payload = json.dumps({
            'sender_batch_header': {
                'sender_batch_id': str(uuid.uuid4()),
                'email_subject': 'Aveenix Reward Payout',
            },
            'items': [{
                'recipient_type': 'EMAIL',
                'amount': {'value': f'{amount:.2f}', 'currency': currency},
                'receiver': destination,
                'note': description,
                'sender_item_id': str(uuid.uuid4()),
            }],
        }).encode()
        try:
            payout_req = urllib.request.Request(
                f'{self._paypal_base_url()}/v1/payments/payouts',
                data=payload,
                headers={
                    'Authorization': f'Bearer {access_token}',
                    'Content-Type': 'application/json',
                },
                method='POST',
            )
            with urllib.request.urlopen(payout_req, timeout=30) as resp:
                body = json.loads(resp.read().decode())
                batch_id = body.get('batch_header', {}).get('payout_batch_id', '')
                return f'PAYPAL:{batch_id}'
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            try:
                msg = json.loads(body).get('message', body)
            except Exception:
                msg = body[:200]
            raise UserError(f'PayPal Payout failed: {msg}')
        except Exception as e:
            raise UserError(f'PayPal error: {e}')
