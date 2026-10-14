"""Take the supplier's name out of the delivery methods customers see.

The "CJ - " prefix went in 19.0.1.0.1; this covers CJ's own naming, the
"CJPacket ..." family (also spelled "CJpacket"), which still put the supplier
in front of the customer at checkout and on the order.

Only delivery_carrier.name is rewritten. cj_logistic_name on the carrier and
cj_logistics_name on the order keep the raw value — both are sent back to CJ as
"logisticName" when an order is pushed, so renaming them would break fulfilment.
"""

import logging

from odoo import SUPERUSER_ID, api

from odoo.addons.aveenix_cj_dropshipping.models.delivery_carrier import (
    av_public_logistic_name,
)

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    carriers = env['delivery.carrier'].search([
        ('delivery_type', '=', 'cj_dropshipping'),
    ])

    renamed = 0
    for carrier in carriers:
        # Prefer the raw logistics name as the source; fall back to the current
        # label for any row that predates cj_logistic_name being filled in.
        source = carrier.cj_logistic_name or carrier.name
        public = av_public_logistic_name(source)
        if public and public != carrier.name:
            _logger.info("Delivery method %r -> %r", carrier.name, public)
            carrier.name = public
            renamed += 1

    if renamed:
        _logger.info("Renamed %s delivery method(s).", renamed)

    # Delivery service product: the customer sees this on the order line when a
    # carrier has a description, and on the invoice.
    product = env['product.product'].search([
        ('default_code', '=', 'CJ_DELIVERY'),
    ], limit=1)
    if product and 'CJ' in (product.name or ''):
        _logger.info("Delivery product %r -> 'Shipping'", product.name)
        product.name = 'Shipping'
