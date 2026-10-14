"""Re-file stored news articles with the corrected classifier.

The old mapping asked NewsData.io for five categories and then let the *last*
matching one win, so Travel, Recipes, Fashion and Gaming could never fill up
and everything else landed more or less arbitrarily — a Kyiv strike report
filed under Style, a Galaxy S26 launch under Facts. Nothing recorded the
categories NewsData.io actually returned, so the backlog is re-classified from
the headline and summary, with Global as the honest catch-all for the local
news, obituaries and market notes that fit none of the ten sections.

New articles are classified on the way in, so this only needs to run once.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    News = env['aveenix.news']

    _normalise_country_codes(cr, News)

    before = _distribution(cr)
    changed = News.cron_reclassify_categories()
    after = _distribution(cr)

    _logger.info("Aveenix news re-classification: %s article(s) moved.", changed)
    _logger.info("  before: %s", before)
    _logger.info("  after:  %s", after)


def _normalise_country_codes(cr, News):
    """Convert stored country names to the two-letter ISO codes the news page
    and the mobile API filter on.

    The sync used to save NewsData.io's country name verbatim ("united states
    of america", "india"), while both filters compare against res.country.code
    ("us", "in"). The result was that the country leaf matched nothing at all
    for the bulk of the table, so no stored article was ever shown.
    """
    cr.execute(
        "SELECT DISTINCT country_code FROM aveenix_news "
        "WHERE country_code IS NOT NULL AND length(country_code) > 2"
    )
    stored_names = [row[0] for row in cr.fetchall()]
    for name in stored_names:
        code = News._av_resolve_country_code([name], fallback=None)
        if not code:
            _logger.warning(
                "Aveenix news: no ISO code for country %r; left as-is.", name
            )
            continue
        cr.execute(
            "UPDATE aveenix_news SET country_code = %s WHERE country_code = %s",
            (code, name),
        )
        _logger.info(
            "Aveenix news: country %r -> %r (%s article(s)).", name, code, cr.rowcount
        )


def _distribution(cr):
    cr.execute("SELECT category, count(*) FROM aveenix_news GROUP BY category")
    return dict(sorted(cr.fetchall(), key=lambda row: -row[1]))
