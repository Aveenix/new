# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class ProductPricelistItem(models.Model):
    _inherit = 'product.pricelist.item'

    compute_price = fields.Selection(
        selection_add=[('markup_range', "Markup based on Cost Range")],
        ondelete={'markup_range': 'set default'}
    )

    @api.depends('compute_price')
    def _compute_price_label(self):
        super()._compute_price_label()
        for item in self:
            if item.compute_price == 'markup_range':
                item.price = _("Markup based on Cost Range")

    def _compute_price(self, product, quantity, uom, date, currency=None, **kwargs):
        self and self.ensure_one()
        product.ensure_one()
        uom.ensure_one()

        if self.compute_price == 'markup_range':
            # Cost of product (in product's cost currency, usually company currency)
            cost = product.standard_price
            cost_currency = product.cost_currency_id or self.env.company.currency_id
            
            # Find the active rule matching the product cost range
            rule = self.env['product.markup.range'].search([
                ('min_cost', '<=', cost),
                ('max_cost', '>=', cost)
            ], limit=1)
            
            # Fallback to the largest/closest range rule if no exact match found
            if not rule:
                rule = self.env['product.markup.range'].search([], order='min_cost desc', limit=1)
            
            if rule:
                # Apply the markup formula: (Cost * Multiplier) + Extra Fee/Offset
                raw_price = (cost * rule.multiplier) + rule.extra_fee
                if raw_price < 0.0:
                    raw_price = 0.0
                
                # Convert the price from product cost currency to pricelist currency if different
                target_currency = currency or self.currency_id or self.env.company.currency_id
                if cost_currency != target_currency:
                    price = cost_currency._convert(
                        raw_price, target_currency, self.env.company, date, round=False
                    )
                else:
                    price = raw_price
                
                # Handle Unit of Measure conversion if the requested UoM is different from the product's default UoM
                product_uom = product.uom_id
                if product_uom != uom:
                    price = product_uom._compute_price(price, uom)
                
                return price
            
        return super()._compute_price(product, quantity, uom, date, currency=currency, **kwargs)
