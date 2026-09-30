"""Open the shop on the products most recently added.

`shop_default_sort` was Odoo's own default, `website_sequence asc`. On this
catalogue website_sequence ascends with the id (10315, 10320, 10325 ...), so
every category listed its oldest imports first and new stock landed on the last
page. The sort itself is a website setting an admin can still change; this only
moves it off the core default.
"""

import logging

_logger = logging.getLogger(__name__)

NEW_SORT = 'id desc'


def migrate(cr, version):
    if not version:
        return

    cr.execute("SELECT id, shop_default_sort FROM website WHERE shop_default_sort != %s", (NEW_SORT,))
    rows = cr.fetchall()
    if not rows:
        return
    cr.execute("UPDATE website SET shop_default_sort = %s WHERE shop_default_sort != %s",
               (NEW_SORT, NEW_SORT))
    for website_id, previous in rows:
        _logger.info("Aveenix shop: website %s now sorts by %r (was %r).",
                     website_id, NEW_SORT, previous)
