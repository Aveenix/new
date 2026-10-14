from odoo import http
from odoo.http import request
from odoo.addons.website_sale.controllers.cart import Cart

# Session key holding a product the guest tried to add before logging in.
_PENDING_ADD_KEY = 'av_pending_cart_add'


class AveenixCartLoginGate(Cart):
    """Require a logged-in account before any product can be added to the cart.

    Guests get a `require_login` response (the frontend shows a Login/Sign up
    modal) and the attempted product is remembered so it can be auto-added once
    they authenticate.
    """

    def _is_public_user(self):
        return request.env.user._is_public()

    @http.route()
    def add_to_cart(self, product_template_id, product_id, quantity=1.0, **kwargs):
        if self._is_public_user():
            # Remember what they wanted so we can add it right after login.
            request.session[_PENDING_ADD_KEY] = {
                'product_template_id': int(product_template_id),
                'product_id': int(product_id),
                'quantity': float(quantity or 1.0),
            }
            # Return a notification-safe shape so Odoo's native cart JS does not
            # crash reading `notification_info.lines` if it ever reaches here.
            return {
                'require_login': True,
                'login_url': '/web/login',
                'signup_url': '/web/signup',
                'cart_quantity': 0,
                'quantity': 0,
                'notification_info': {'lines': [], 'warning': ''},
                'tracking_info': [],
            }
        return super().add_to_cart(
            product_template_id, product_id, quantity=quantity, **kwargs
        )

    @http.route('/aveenix/cart/save_pending', type='jsonrpc', auth='public', website=True)
    def save_pending_cart_add(self, product_template_id, product_id, quantity=1.0, **kwargs):
        """Remember a product a guest tried to add from the product page, so it
        can be auto-added after they log in."""
        request.session[_PENDING_ADD_KEY] = {
            'product_template_id': int(product_template_id),
            'product_id': int(product_id),
            'quantity': float(quantity or 1.0),
        }
        return {'ok': True}

    @http.route('/aveenix/cart/pending_add', type='jsonrpc', auth='public', website=True)
    def pending_cart_add(self, **kwargs):
        """Return (and clear) a product the user tried to add before logging in.

        The frontend calls this once after a successful login; if a pending
        product exists it is added to the cart and the result returned.
        """
        if self._is_public_user():
            return {'added': False}
        pending = request.session.pop(_PENDING_ADD_KEY, None)
        if not pending:
            return {'added': False}
        result = super().add_to_cart(
            pending['product_template_id'],
            pending['product_id'],
            quantity=pending['quantity'],
        )
        return {'added': True, 'cart': result}
