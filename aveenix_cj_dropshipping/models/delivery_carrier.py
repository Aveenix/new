import json
import re

from odoo import api, fields, models, _

# The supplier's name must not reach the customer. CJ's logistics names carry it
# in two shapes — a "CJ - " prefix we used to add ourselves, and CJ's own
# "CJPacket ..." family (sometimes spelled "CJpacket") — so strip the token
# wherever it starts a word and tidy up what is left.
#
# This is display only. cj_logistic_name on the carrier and cj_logistics_name on
# the order keep the raw value, because both are sent back to CJ as
# "logisticName" when an order is pushed; renaming those would break fulfilment.
_CJ_TOKEN = re.compile(r'\bCJ[\s\-]*', re.IGNORECASE)


def av_public_logistic_name(logistic_name):
    """Return the customer-facing name for a CJ logistics option.

    "CJPacket Asia Sensitive" -> "Packet Asia Sensitive"
    "CJ - CJPacket Ordinary"  -> "Packet Ordinary"
    "CJpacket SYEUB"          -> "Packet SYEUB"
    "YunExpress Ordinary"     -> unchanged
    """
    if not logistic_name:
        return logistic_name
    name = _CJ_TOKEN.sub('', logistic_name).strip()
    name = re.sub(r'\s{2,}', ' ', name)
    if name and name[0].islower():
        # Cutting "CJ" off "CJpacket" leaves a lowercase word start.
        name = name[0].upper() + name[1:]
    # Never hand back an empty label if a name were nothing but the token.
    return name or logistic_name


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

        # Invalidate ORM cache so we always read the latest DB value.
        # This is necessary because _get_delivery_methods() may have just written
        # a fresh cache (after address change) in the same request, but the ORM
        # still holds the old value in memory.
        order.invalidate_recordset(['cj_shipping_rates_cache'])
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
