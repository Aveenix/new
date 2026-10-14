"""Drop stored news rows whose title is a bare timestamp.

Some feeds send the publish time in the title field. Those rows are unusable —
they show up as "2026-09-09T06:31:11+00:00" in the trending ticker and in
headings. The sync now rejects them on the way in; this clears the ones already
stored.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    # Same rule as _TITLE_HAS_WORDS: a real headline has two runs of letters.
    cr.execute(
        r"""
        DELETE FROM aveenix_news
         WHERE title !~ '[[:alpha:]]{2,}.*[[:alpha:]]{2,}'
        """
    )
    if cr.rowcount:
        _logger.info("Aveenix news: removed %s article(s) with junk titles.", cr.rowcount)
