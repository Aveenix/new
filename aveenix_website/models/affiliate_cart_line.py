from odoo import api, fields, models


class AffiliateCartLine(models.Model):
    _name = 'affiliate.cart.line'
    _description = 'Affiliate Cart Line'
    _order = 'create_date desc'
    _rec_name = 'product_id'

    product_id = fields.Many2one(
        comodel_name='product.template',
        string='Product',
        required=True,
        index=True,
        ondelete='cascade',
        help='Affiliate product saved to this cart line.',
    )
    user_id = fields.Many2one(
        comodel_name='res.users',
        string='User',
        index=True,
        ondelete='cascade',
        help='Logged-in user who saved this line. Empty for guest sessions.',
    )
    session_id = fields.Char(
        string='Session ID',
        index=True,
        help='Web session identifier for guest visitors.',
    )
    affiliate_url = fields.Char(
        string='Affiliate URL',
        help='Snapshot of the outbound retailer URL at the time the line was saved.',
    )
    affiliate_display_price = fields.Monetary(
        string='Retailer Price',
        currency_field='currency_id',
        help='Retailer list price shown to the customer.',
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
        ondelete='restrict',
    )
    create_date = fields.Datetime(
        string='Added On',
        readonly=True,
        index=True,
    )

    @api.model
    def _get_or_create(self, product, session_id, user):
        """Return existing line for this product+session/user, or create one."""
        domain = [('product_id', '=', product.id)]
        if user and not user._is_public():
            domain += [('user_id', '=', user.id)]
        else:
            domain += [('session_id', '=', session_id), ('user_id', '=', False)]
        line = self.search(domain, limit=1)
        if line:
            return line
        vals = {
            'product_id': product.id,
            'affiliate_url': product.affiliate_url,
            'affiliate_display_price': product.list_price,
            'currency_id': self.env.company.currency_id.id,
        }
        if user and not user._is_public():
            vals['user_id'] = user.id
        else:
            vals['session_id'] = session_id
        return self.create(vals)

    @api.model
    def _for_session(self, session_id, user):
        """Return all lines for the current visitor."""
        if user and not user._is_public():
            return self.search([('user_id', '=', user.id)])
        return self.search([('session_id', '=', session_id), ('user_id', '=', False)])
