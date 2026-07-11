# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class ProductMarkupRange(models.Model):
    _name = 'product.markup.range'
    _description = 'Product Cost Markup Range Rule'
    _order = 'min_cost'

    name = fields.Char(string="Name", compute="_compute_name", store=True)
    min_cost = fields.Float(
        string="Min Cost", 
        required=True, 
        digits='Product Price', 
        help="Minimum product cost in standard company currency"
    )
    max_cost = fields.Float(
        string="Max Cost", 
        required=True, 
        digits='Product Price', 
        help="Maximum product cost in standard company currency"
    )
    markup_percent = fields.Float(
        string="Markup %", 
        help="Markup percentage, e.g. 300% means selling price is cost + 300% of cost"
    )
    multiplier = fields.Float(
        string="Multiplier", 
        required=True, 
        default=1.0, 
        digits=(12, 4), 
        help="Multiplier applied to cost, e.g. Cost x 4.00"
    )
    extra_fee = fields.Float(
        string="Extra Fee / Offset", 
        default=-0.01, 
        digits='Product Price', 
        help="Fixed amount added to the result (e.g. -0.01 to round $12.00 to $11.99)"
    )

    @api.depends('min_cost', 'max_cost', 'multiplier')
    def _compute_name(self):
        for record in self:
            record.name = _(
                "$%(min).2f - $%(max).2f (x%(mult).2f)",
                min=record.min_cost,
                max=record.max_cost,
                mult=record.multiplier
            )

    @api.onchange('multiplier')
    def _onchange_multiplier(self):
        if self.multiplier:
            self.markup_percent = (self.multiplier - 1.0) * 100.0

    @api.onchange('markup_percent')
    def _onchange_markup_percent(self):
        self.multiplier = 1.0 + (self.markup_percent / 100.0)

    @api.constrains('min_cost', 'max_cost')
    def _check_ranges(self):
        for record in self:
            if record.min_cost < 0:
                raise ValidationError(_("Minimum Cost cannot be negative."))
            if record.max_cost <= record.min_cost:
                raise ValidationError(_("Maximum Cost must be greater than Minimum Cost."))
            
            # Check overlap
            overlap = self.search([
                ('id', '!=', record.id),
                ('min_cost', '<', record.max_cost),
                ('max_cost', '>', record.min_cost)
            ])
            if overlap:
                raise ValidationError(_(
                    "This range overlaps with an existing range: %s"
                ) % overlap[0].name)
