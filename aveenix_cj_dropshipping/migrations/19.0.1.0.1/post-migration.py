"""Drop the "CJ - " prefix from CJ Dropshipping delivery method labels.

The carriers are created on the fly by sale.order._get_delivery_methods() from
the CJ freight API. They used to be named "CJ - <logisticName>"; the customer
facing label is now the bare logistics name. Records created before that change
still carry the prefix, so rename them here.

Only delivery.carrier.name is touched. cj_logistic_name is the key used for the
CJ order payload and the rate cache and is deliberately left alone. Delivery
lines on orders that are still open are relabelled too (their description is a
copy of carrier.name taken at selection time); confirmed, done and cancelled
orders keep the wording the customer actually saw.
"""

import logging

_logger = logging.getLogger(__name__)

PREFIX = 'CJ - '


def migrate(cr, version):
    if not version:
        return

    # delivery.carrier.name is a translated field -> jsonb column, one entry
    # per language. Strip the prefix from every translation that has it.
    cr.execute(
        """
        UPDATE delivery_carrier AS c
           SET name = (
                   SELECT jsonb_object_agg(
                              t.key,
                              CASE WHEN t.value LIKE %(like)s
                                   THEN substr(t.value, %(cut)s)
                                   ELSE t.value
                              END
                          )
                     FROM jsonb_each_text(c.name) AS t
               )
         WHERE c.delivery_type = 'cj_dropshipping'
           AND EXISTS (
                   SELECT 1
                     FROM jsonb_each_text(c.name) AS t
                    WHERE t.value LIKE %(like)s
               )
     RETURNING c.id
        """,
        {'like': PREFIX + '%', 'cut': len(PREFIX) + 1},
    )
    renamed = cr.rowcount
    if renamed:
        _logger.info("Removed the %r prefix from %s CJ delivery method(s).", PREFIX, renamed)

    # Delivery lines on still-open orders: keep the label in step with the
    # carrier the customer is about to be charged for.
    cr.execute(
        """
        UPDATE sale_order_line AS l
           SET name = substr(l.name, %(cut)s)
          FROM sale_order AS o, delivery_carrier AS c
         WHERE o.id = l.order_id
           AND c.id = o.carrier_id
           AND l.is_delivery
           AND o.state IN ('draft', 'sent')
           AND c.delivery_type = 'cj_dropshipping'
           AND l.name LIKE %(like)s
        """,
        {'like': PREFIX + '%', 'cut': len(PREFIX) + 1},
    )
    if cr.rowcount:
        _logger.info("Relabelled %s delivery line(s) on open orders.", cr.rowcount)
