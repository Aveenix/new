from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    is_affiliate = fields.Boolean(
        string='Affiliate Item',
        compute='_compute_is_affiliate',
        store=True,
        help='True when the line product is an affiliate product. Affiliate '
             'lines are bought on a partner site, so they are kept at price 0 '
             'and excluded from the cart total, then dropped at checkout.',
    )
    affiliate_url = fields.Char(
        string='Affiliate URL',
        compute='_compute_is_affiliate',
        store=True,
        help='Outbound retailer link for this affiliate line.',
    )
    affiliate_display_price = fields.Monetary(
        string='Affiliate Retail Price',
        compute='_compute_affiliate_display_price',
        store=True,
        currency_field='currency_id',
        help='Real retailer price shown to the customer for affiliate lines '
             '(the line itself stays at 0 so it never affects the cart total).',
    )

    @api.depends('product_id', 'product_id.aveenix_product_type',
                 'product_id.affiliate_url')
    def _compute_is_affiliate(self):
        for line in self:
            tmpl = line.product_id.product_tmpl_id
            is_aff = bool(
                tmpl
                and tmpl.aveenix_product_type == 'affiliate'
                and tmpl.affiliate_url
            )
            line.is_affiliate = is_aff
            line.affiliate_url = tmpl.affiliate_url if is_aff else False

    @api.depends('is_affiliate', 'product_id')
    def _compute_affiliate_display_price(self):
        for line in self:
            if line.is_affiliate:
                # Capture the real retail price for display only.
                line.affiliate_display_price = (
                    line.product_id.list_price
                    or line.product_id.product_tmpl_id.list_price
                )
            else:
                line.affiliate_display_price = 0.0

    def _force_affiliate_zero_price(self):
        """Affiliate lines must never add to any total — keep them at 0."""
        for line in self:
            if line.is_affiliate and (line.price_unit or line.discount):
                super(SaleOrderLine, line).write({
                    'price_unit': 0.0,
                    'discount': 0.0,
                })

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._force_affiliate_zero_price()
        return lines

    def write(self, vals):
        res = super().write(vals)
        # Re-assert only when something that could reset the price is written —
        # not on qty changes, which never affect price_unit and would cause an
        # unnecessary extra write that breaks the cart qty update flow.
        if any(k in vals for k in ('product_id', 'price_unit', 'discount')):
            self._force_affiliate_zero_price()
        return res
