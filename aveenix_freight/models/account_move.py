from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    freight_shipment_id = fields.Many2one(
        'freight.shipment', string='Freight Shipment', copy=False, index='btree_not_null',
    )
