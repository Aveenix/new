import json
from odoo import api, fields, models, _

class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    delivery_type = fields.Selection(
        selection_add=[('cj_dropshipping', 'CJ Dropshipping')],
        ondelete={'cj_dropshipping': 'set default'}
    )

    cj_logistic_name = fields.Char(
        string="CJ Logistic Name",
        help="Internal logistics name from CJ Dropshipping (e.g. CJPacket Ordinary)"
    )

    def cj_dropshipping_rate_shipment(self, order):
        """
        Calculates the shipping rate by reading from the sale.order's cj_shipping_rates_cache.
        The cache is populated in sale.order._get_delivery_methods() to avoid making 
        multiple API calls for each individual carrier record.
        """
        self.ensure_one()
        cache_str = order.cj_shipping_rates_cache
        
        if not cache_str:
            return {
                'success': False, 
                'price': 0.0, 
                'error_message': _('CJ Dropshipping rates are currently unavailable. Please try again.'), 
                'warning_message': False
            }
        
        try:
            rates = json.loads(cache_str)
            if self.cj_logistic_name in rates:
                price = float(rates[self.cj_logistic_name])
                return {
                    'success': True, 
                    'price': price, 
                    'error_message': False, 
                    'warning_message': False
                }
        except Exception:
            pass
            
        return {
            'success': False, 
            'price': 0.0, 
            'error_message': _('This shipping method is not available for your destination.'), 
            'warning_message': False
        }
