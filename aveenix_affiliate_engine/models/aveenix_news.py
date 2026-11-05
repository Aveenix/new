"""Article-side half of the engine: keywords, matching, and content splitting."""

import logging
import re

from markupsafe import Markup

from odoo import api, fields, models
from odoo.fields import Domain

_logger = logging.getLogger(__name__)

# Keyword extraction is bounded on both ends: too few terms and nothing
# matches, too many and a long article matches everything. Eight AI terms plus
# the vocabulary hits is enough to describe what an article is about without
# turning the score into noise.
_MAX_AI_KEYWORDS = 8
_MAX_KEYWORDS = 14
_MAX_KEYWORD_LEN = 40

_KEYWORD_SYSTEM_PROMPT = (
    'You extract shopping keywords from news articles for an affiliate product '
    'search. Reply with ONLY a JSON array of short lowercase keyword strings. '
    'No URLs, no links, no product names you are not certain about, no prose.'
)

# Anything URL-shaped is dropped before a keyword is used. Keywords are only
# ever search terms and can never become an outbound link, so this is belt and
# braces for the "AI must never invent affiliate URLs" rule — the real
# enforcement is that links come solely from affiliate.offer.target_url, which
# is checked against the network's click domains.
_URLISH = re.compile(r'(https?:|//|www\.|\.com|\.net|\.org|\.io)', re.IGNORECASE)


class AveenixNews(models.Model):
    _inherit = 'aveenix.news'

    av_affiliate_keywords = fields.Char(
        string='Affiliate Keywords',
        help='Topic keywords this article was matched on. Computed once per '
             'article by the matcher, not on every page view.',
    )
    av_placement_ids = fields.One2many(
        comodel_name='affiliate.offer.placement',
        inverse_name='news_id',
        string='Affiliate Placements',
    )
    av_placement_count = fields.Integer(
        string='Placements', compute='_compute_av_placement_count',
    )
    av_affiliate_matched_on = fields.Datetime(
        string='Offers Matched On',
        readonly=True,
        help='Set once the matcher has considered this article, whether or not '
             'it found anything. Stops the cron reconsidering the same article '
             'every night; clear it (or use Re-match) to try again.',
    )

    @api.depends('av_placement_ids')
    def _compute_av_placement_count(self):
        for article in self:
            article.av_placement_count = len(article.av_placement_ids)

    # ── Keywords ─────────────────────────────────────────────────────────

    def _av_affiliate_keywords_list(self):
        """Topic keywords for this article: AI terms plus vocabulary hits.

        Two sources on purpose. The AI contributes open-ended commercial terms
        ("noise cancelling headphones") that no fixed list could hold, and is
        what makes CJ product search useful. The existing section vocabulary in
        `aveenix_website` contributes terms we already know are commercially
        meaningful, and is what keeps matching working at all when there is no
        AI key, when the endpoint is down, or when the model returns nonsense.
        """
        self.ensure_one()
        text = ' '.join(filter(None, [self.title or '', self.description or '']))
        if not text.strip():
            return []

        keywords = []
        reply = self.env['aveenix.affiliate.ai']._av_chat_json_list(
            _KEYWORD_SYSTEM_PROMPT,
            'Article headline: %s\n\nSummary: %s\n\nReturn up to %s shopping '
            'keywords for products a reader of this article might buy. If the '
            'article has no plausible commercial angle, return [].' % (
                self.title or '', (self.description or '')[:1200], _MAX_AI_KEYWORDS,
            ),
        )
        for term in reply[:_MAX_AI_KEYWORDS]:
            term = term.strip().lower()
            if not term or len(term) > _MAX_KEYWORD_LEN or _URLISH.search(term):
                continue
            keywords.append(term)

        # Deterministic fallback/supplement — see aveenix_website's
        # aveenix_news._av_keyword_terms, which owns this vocabulary.
        keywords.extend(self._av_keyword_terms(text))

        seen, unique = set(), []
        for term in keywords:
            if term not in seen:
                seen.add(term)
                unique.append(term)
        return unique[:_MAX_KEYWORDS]

    # ── Matching ─────────────────────────────────────────────────────────

    def _av_candidate_offers(self, keywords):
        """Approved offers worth scoring for this article.

        Narrowed in SQL first — section match, or a keyword appearing in the
        offer's name or keywords — so scoring stays over a handful of rows
        rather than the whole offer table, which CJ discovery grows steadily.
        """
        self.ensure_one()
        reachable = Domain([('state', '=', 'approved'), ('active', '=', True)]) & (
            Domain([('advertiser_id', '=', False)])
            | Domain([('advertiser_id.active', '=', True)])
        )
        relevant = []
        if self.category:
            relevant.append(Domain([('section_ids.code', '=', self.category)]))
        for term in keywords:
            relevant.append(Domain([('keywords', 'ilike', term)]))
            relevant.append(Domain([('name', 'ilike', term)]))
        if not relevant:
            return self.env['affiliate.offer'].browse()
        return self.env['affiliate.offer'].search(reachable & Domain.OR(relevant))

    def _av_rank_offers(self, keywords, min_relevance):
        """Candidate offers scoring at or above `min_relevance`, best first."""
        self.ensure_one()
        ranked = []
        for offer in self._av_candidate_offers(keywords):
            score, matched = offer._av_relevance(self, keywords)
            if score >= min_relevance:
                ranked.append((score, matched, offer))
        ranked.sort(key=lambda row: (-row[0], row[2].id))
        return ranked

    def _av_match_offers(self):
        """Match offers to these articles and store the resulting placements.

        The flow the brief describes, in one method: keywords from the article,
        a look in the local offer database, a CJ search only if nothing local is
        good enough, then placement. Discovery happens here rather than on a
        schedule of its own so the offer database fills from articles that
        actually need an offer, instead of from a seed keyword list somebody has
        to maintain.
        """
        Offer = self.env['affiliate.offer']
        Placement = self.env['affiliate.offer.placement']
        Section = self.env['affiliate.section']
        settings = Offer._av_settings()
        now = fields.Datetime.now()

        for article in self:
            if not settings['enabled']:
                continue
            # Stamped even when skipped, so a disabled category is not
            # reconsidered nightly for the rest of the article's life.
            if not Section._av_allows(article.category):
                article.av_affiliate_matched_on = now
                continue

            keywords = article._av_affiliate_keywords_list()
            article.av_affiliate_keywords = ', '.join(keywords)[:1000]
            if not keywords:
                article.av_affiliate_matched_on = now
                continue

            ranked = article._av_rank_offers(keywords, settings['min_relevance'])
            if not ranked and settings['cj_discovery']:
                Offer._av_discover_for_keywords(keywords)
                ranked = article._av_rank_offers(keywords, settings['min_relevance'])

            placed = article.av_placement_ids.mapped('offer_id')
            positions = ['in_content', 'sidebar']
            created = 0
            for score, matched, offer in ranked:
                if created >= settings['max_offers']:
                    break
                if offer in placed:
                    continue
                Placement.create({
                    'news_id': article.id,
                    'offer_id': offer.id,
                    'position': positions[min(created, len(positions) - 1)],
                    'score': score,
                    'matched_keywords': ', '.join(matched)[:255] or False,
                })
                created += 1
            article.av_affiliate_matched_on = now
            if created:
                _logger.info(
                    'Affiliate engine placed %s offer(s) in article %s (%s).',
                    created, article.id, article.category,
                )
        return True

    def action_av_match_offers(self):
        """Re-run matching for the selected articles, ignoring the stamp."""
        self._av_match_offers()
        return True

    @api.model
    def _av_cron_match_offers(self, batch_size=40):
        """Match offers to articles the engine has not considered yet.

        Newest first: a fresh article is the one readers are arriving on, and
        the one whose topic a current CJ product search will match best.
        """
        if not self.env['affiliate.offer']._av_settings()['enabled']:
            return 0
        articles = self.search(
            [('av_affiliate_matched_on', '=', False)],
            order='published_date desc, id desc',
            limit=batch_size,
        )
        if articles:
            articles._av_match_offers()
        return len(articles)

    # ── Rendering ────────────────────────────────────────────────────────

    def _av_split_content(self):
        """Split this article's HTML in two at a paragraph boundary near the middle.

        Returns (before, after) as Markup. The stored content is never touched:
        the offer card is rendered *between* the halves at request time, so
        re-syncing an article from NewsData.io cannot clobber a placement, and
        uninstalling this module leaves every article exactly as it was.

        An article with fewer than three paragraphs returns ('', '') — there is
        no interior to interrupt, and breaking up a two-paragraph item reads
        worse than putting the card after it.
        """
        self.ensure_one()
        html = self.content or ''
        ends = [match.end() for match in re.finditer(r'</p\s*>', html, re.IGNORECASE)]
        if len(ends) < 3:
            return Markup(''), Markup('')
        cut = ends[len(ends) // 2]
        return Markup(html[:cut]), Markup(html[cut:])
