import logging
import re

import requests

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

NEWSDATA_URL = "https://newsdata.io/api/1/news"

# A usable headline has at least two runs of letters. An ISO timestamp
# ("2026-09-09T06:31:11+00:00") has one — the "T" — so this rejects it.
_TITLE_HAS_WORDS = re.compile(r'[^\W\d_]{2,}.*[^\W\d_]{2,}', re.DOTALL)

# ── Category model ────────────────────────────────────────────────────────
#
# The site has ten sections. NewsData.io has its own, different taxonomy
# (business, crime, domestic, education, entertainment, environment, food,
# health, lifestyle, other, politics, science, sports, technology, top,
# tourism, world) and no category at all for Gaming or Fashion. So an article
# is placed in three passes:
#
#   1. keyword rules on the headline + summary — these decide the sections
#      NewsData.io cannot express, and they also override a too-broad API
#      category (a PlayStation story arrives as "technology" but belongs in
#      Gaming, not Gadgets);
#   2. the API category, walked in a fixed specific-to-general order so a
#      multi-category article always lands in the same place;
#   3. Global, as the catch-all.
#
# Note that "sports" is deliberately absent from the map below. There is no
# sports section, and mapping it onto Fitness is what filled Fitness with
# match reports instead of health and training stories.

_API_CATEGORY_TO_SECTION = {
    'food': 'RECIPES',
    'tourism': 'TRAVEL',
    'health': 'FITNESS',
    'technology': 'GADGETS',
    'science': 'FACTS',
    'environment': 'FACTS',
    'education': 'FACTS',
    'entertainment': 'SHOWBIZ',
    'lifestyle': 'STYLE',
    'world': 'GLOBAL',
    # Co-tags rather than topics: NewsData.io attaches these alongside a real
    # category (34 of 46 articles in one sample carried 'top'). 'breaking' is
    # not in NewsData.io's documented list at all but does come back, so it is
    # mapped here to keep it from being silently ignored.
    'top': 'GLOBAL',
    'other': 'GLOBAL',
    'breaking': 'GLOBAL',
}

# Specific first: an article tagged ['technology', 'world'] is a tech story
# that also happens to be international, so it belongs in Gadgets. The co-tags
# come last, which is what stops 'top' — attached to most articles — from
# swallowing everything into Global.
_API_CATEGORY_PRIORITY = (
    'food', 'tourism', 'health', 'technology', 'science',
    'environment', 'education', 'entertainment', 'lifestyle',
    'world', 'top', 'breaking', 'other',
)

# Ordered: the first section whose keywords match the text wins. Precedence
# runs Gaming, Travel, Fitness, Recipes, Fashion, Gadgets, Showbiz, Facts,
# Style — narrow topics before broad ones. Terms are
# matched on word boundaries, so "gym" does not match "gymnasium reports" by
# accident and "ai" never matches "said".
_SECTION_KEYWORDS = (
    ('GAMING', (
        'gaming', 'gamer', 'gamers', 'video game', 'video games', 'videogame',
        'playstation', 'ps5', 'ps6', 'xbox', 'nintendo', 'steam deck', 'esports',
        'e-sports', 'twitch', 'valorant', 'fortnite', 'minecraft', 'roblox',
        'call of duty', 'gta', 'rpg', 'rpgs', 'mmorpg', 'epic games', 'ubisoft',
        'blizzard', 'riot games', 'dlc', 'speedrun', 'game pass', 'switch 2',
        'nintendo switch', 'gameplay', 'game console', 'game consoles',
        'arcade', 'expansion pack', 'battle royale', 'modding',
        'game of the year', 'indie game', 'mobile game', 'pc game',
        'game studio', 'game developer', 'game review', 'game launch',
        'game update', 'game trailer', 'game series', 'in-game',
    )),
    ('TRAVEL', (
        'traveller', 'traveler', 'travellers', 'travelers', 'tourism',
        'tourist', 'tourists', 'vacation', 'itinerary', 'flight', 'flights',
        'airline', 'airlines', 'airport', 'hotel', 'hotels', 'resort',
        'resorts', 'backpacking', 'road trip', 'cruise', 'destination',
        'destinations', 'sightseeing', 'sightsee', 'getaway', 'getaways',
        'hiking', 'trekking', 'safari', 'homestay', 'staycation', 'layover',
        'boarding pass', 'travel guide', 'travel tips', 'travel habits',
        'travel industry', 'travel advisory', 'air travel', 'luxury travel',
        'budget travel', 'travel plans',
    )),
    ('FITNESS', (
        'fitness', 'workout', 'workouts', 'exercises', 'exercise routine',
        'physical exercise', 'aerobic exercise', 'gym',
        'yoga', 'pilates', 'weight loss', 'weight-loss', 'nutrition',
        'nutritional', 'nutritionist', 'diet', 'diets', 'dietary',
        'dietitian', 'calories', 'protein',
        'muscle', 'muscles', 'cardio', 'wellness', 'meditation',
        'mindfulness', 'mental health', 'immunity', 'cholesterol', 'diabetes',
        'blood pressure', 'strength training', 'superfood', 'superfoods',
        'sleep', 'insomnia', 'stretching', 'physiotherapy',
        'metabolism', 'hydration', 'vitamin', 'vitamins',
        'obesity', 'heart health', 'gut health',
    )),
    ('RECIPES', (
        'recipe', 'recipes', 'cook', 'cooks', 'cooking', 'bake', 'baked',
        'baking', 'bakery', 'chef', 'chefs', 'cuisine',
        'culinary', 'ingredient', 'ingredients', 'breakfast', 'lunch',
        'dinner', 'dessert', 'desserts', 'snack', 'snacks',
        'flavour', 'flavor', 'marinade', 'roast', 'grill', 'grilled',
        'homemade', 'meal prep', 'sourdough', 'gastronomy', 'coffee',
        'espresso', 'brunch', 'restaurant', 'restaurants', 'michelin',
        'pizza', 'curry', 'noodles', 'vegan', 'plant-based', 'cocktail',
        'cocktails', 'wine', 'brewery', 'foodie', 'tasting menu',
    )),
    ('FASHION', (
        'fashion', 'runway', 'couture', 'catwalk', 'wardrobe', 'outfit',
        'outfits', 'styling', 'stylist', 'apparel', 'clothing', 'sneaker',
        'sneakers', 'handbag', 'handbags', 'jewellery', 'jewelry', 'makeup',
        'cosmetics', 'skincare', 'met gala', 'vogue', 'lookbook', 'streetwear',
        'denim', 'lipstick', 'perfume', 'fragrance', 'moisturizing',
        'moisturiser', 'moisturizer', 'lotion', 'lotions', 'serum', 'shampoo',
        'haircare', 'hairstyle', 'manicure', 'dress', 'dresses', 'saree',
        'lehenga', 'kurta', 'menswear', 'womenswear', 'boutique', 'upcycling',
        'sunglasses',
    )),
    ('GADGETS', (
        'gadget', 'gadgets', 'smartphone', 'smartphones', 'iphone', 'android',
        'laptop', 'laptops', 'tablet', 'headphone', 'headphones', 'earbuds',
        'smartwatch', 'processor', 'chipset', 'gpu', 'ios', 'macbook',
        'samsung', 'galaxy', 'pixel', 'xiaomi', 'oneplus', 'chatgpt', 'robot',
        'robots', 'robotics', 'drone', 'drones', 'electric vehicle', 'evs',
        'wearable', 'wearables', 'foldable', 'foldables', 'apple', 'google',
        'microsoft', 'meta', 'nvidia', 'tesla', 'openai', 'app', 'apps',
        'software', 'firmware', 'cybersecurity', 'malware', 'github',
        'cloud', 'server', 'servers', 'data centre', 'data center',
        'artificial intelligence', 'machine learning', 'ai model', 'battery',
        'charger', 'charging', 'quantum computing', 'streaming device',
        'appliance', 'appliances', 'headset', 'vr',
        'virtual reality', 'augmented reality',
    )),
    ('SHOWBIZ', (
        'actor', 'actors', 'actress', 'film', 'films', 'movie', 'movies',
        'box office', 'celebrity', 'celebrities', 'singer', 'singers',
        'album', 'albums', 'song', 'songs', 'concert', 'tour dates',
        'episode', 'episodes', 'tv series', 'web series', 'series premiere',
        'season finale', 'netflix', 'prime video',
        'disney', 'hbo', 'trailer', 'teaser', 'bollywood', 'hollywood',
        'tollywood', 'premiere', 'director', 'casting', 'co-star', 'co-stars',
        'sitcom', 'reality show', 'tv show', 'showbiz', 'red carpet',
        'oscars', 'grammy', 'emmy', 'wrestling', 'wwe', 'aew', 'rapper',
        'soap opera', 'spin-off', 'biopic', 'screenplay', 'theatre', 'theater',
    )),
    ('FACTS', (
        'study', 'studies', 'research', 'researcher', 'researchers',
        'scientist', 'scientists', 'discovery', 'discoveries', 'discovered',
        'nasa', 'telescope', 'fossil', 'fossils', 'species', 'archaeologist',
        'archaeologists', 'archaeology', 'experiment', 'astronomer',
        'astronomers', 'astronomy', 'physics', 'chemistry', 'biology',
        'genome', 'dna', 'evolution', 'asteroid', 'galaxy cluster',
        'black hole', 'climate change', 'ecosystem', 'wildlife',
        'conservation', 'extinct', 'excavation', 'spacecraft', 'satellite',
    )),
    ('STYLE', (
        'interior design', 'home design', 'home decor', 'decor', 'furniture',
        'architecture', 'rooftop', 'minimalist', 'slow-living', 'gardening',
        'garden', 'parenting', 'relationship', 'relationships', 'marriage',
        'lifestyle', 'daily habits', 'habits', 'self-care', 'declutter',
        'feng shui', 'houseplant', 'houseplants', 'renovation', 'apartment',
        'workspace', 'ergonomic',
    )),
)

# One compiled alternation per section, built once at import.
_SECTION_PATTERNS = tuple(
    (section, re.compile(
        r'\b(?:%s)\b' % '|'.join(re.escape(term) for term in terms),
        re.IGNORECASE,
    ))
    for section, terms in _SECTION_KEYWORDS
)

# NewsData.io caps the free tier at 5 categories per request, so the pull is
# split into groups. Each group is aimed at the sections it can feed, which is
# what guarantees Travel, Recipes, Fitness and Gaming actually get articles —
# the old single request only asked for world/lifestyle/entertainment/
# technology/health, so four sections could never fill up.
# Invariant: every category fetched here must appear in
# _API_CATEGORY_TO_SECTION, so nothing we pull is left unhandled. The reverse
# does not hold — 'breaking' is a co-tag that only ever arrives attached to
# another category, so it is mapped but not worth requesting.
#
# Keep this in step with the map when editing either: 'environment',
# 'education', 'top' and 'other' were all mapped but never requested, so Facts
# was fed only by 'science' (819 articles — the smallest of the seventeen
# pools) and Global was missing 'top' entirely, by far the largest (70k+).
#
# Deliberately NOT fetched: business, politics, crime, domestic and sports
# (~73k articles between them). The site has no section for any of them, so
# they would all land in Global. Add them here — and to
# _API_CATEGORY_TO_SECTION — if Global should carry general news too.
_FETCH_GROUPS = (
    ('top,world,other', 'GLOBAL'),
    ('lifestyle,entertainment', 'STYLE / SHOWBIZ / FASHION'),
    ('technology,science', 'GADGETS / GAMING / FACTS'),
    ('health,food,tourism', 'FITNESS / RECIPES / TRAVEL'),
    ('environment,education', 'FACTS'),
)

# country_code holds a two-letter ISO code, which is what the /news page and
# /api/v1/news filter on. NewsData.io answers with full country names instead,
# and most of them match a res.country name outright — but not the big one:
# it says "United States of America" where Odoo says "United States", so every
# US article used to be invisible to the country filter and the page fell back
# to placeholder articles. These are the names that need spelling out.
_COUNTRY_NAME_ALIASES = {
    'united states of america': 'us',
    'usa': 'us',
    'russia': 'ru',
    'south korea': 'kr',
    'north korea': 'kp',
    'turkey': 'tr',
    'czech republic': 'cz',
    'ivory coast': 'ci',
    'democratic republic of congo': 'cd',
    'republic of the congo': 'cg',
    'bolivia': 'bo',
    'venezuela': 've',
    'tanzania': 'tz',
    'syria': 'sy',
    'laos': 'la',
    'moldova': 'md',
    'macau': 'mo',
    'hong kong': 'hk',
    'vatican': 'va',
    'palestine': 'ps',
    'cape verde': 'cv',
    'swaziland': 'sz',
    'burma': 'mm',
    'myanmar': 'mm',
}


class AveenixNews(models.Model):
    _name = 'aveenix.news'
    _description = 'Aveenix News Article'
    _order = 'published_date desc, id desc'

    title = fields.Char(string='Title', required=True)
    description = fields.Text(string='Description')
    content = fields.Html(string='Content')
    category = fields.Selection([
        ('STYLE', 'Style'),
        ('TRAVEL', 'Travel'),
        ('SHOWBIZ', 'Showbiz'),
        ('FASHION', 'Fashion'),
        ('FITNESS', 'Fitness'),
        ('GAMING', 'Gaming'),
        ('GADGETS', 'Gadgets'),
        ('RECIPES', 'Recipes'),
        ('FACTS', 'Facts'),
        ('GLOBAL', 'Global'),
    ], string='Category', default='GLOBAL', required=True)
    author = fields.Char(string='Author')
    published_date = fields.Datetime(string='Published Date', default=fields.Datetime.now)
    image_url = fields.Char(string='Image URL')
    source_url = fields.Char(string='Source URL')
    api_article_id = fields.Char(string='API Article ID', index=True)
    country_code = fields.Char(string='Country Code', index=True, default='us')
    api_category = fields.Char(
        string='Source Categories',
        help="Comma-separated categories exactly as NewsData.io returned them. "
             "Kept so articles can be re-classified later without re-fetching.",
    )

    # ── Classification ───────────────────────────────────────────────────

    @api.model
    def _av_classify_category(self, api_categories, title, description=None):
        """Pick the site section for one article.

        :param api_categories: categories as returned by NewsData.io — a list,
            a comma-separated string, or falsy.
        :param title: the headline (carries most of the signal).
        :param description: the summary, used as a weaker second signal.
        :return: a value of the ``category`` selection field.
        """
        if isinstance(api_categories, str):
            api_categories = api_categories.split(',')
        api_categories = {
            (c or '').strip().lower() for c in (api_categories or [])
        }

        # 1. Keyword rules. The headline alone decides first: a summary is
        #    long enough that a passing mention ("...unlike the hotel industry")
        #    would otherwise drag the article into the wrong section.
        for text in (title, description):
            if not text:
                continue
            for section, pattern in _SECTION_PATTERNS:
                if pattern.search(text):
                    return section

        # 2. The API category, most specific first.
        for api_category in _API_CATEGORY_PRIORITY:
            if api_category in api_categories:
                return _API_CATEGORY_TO_SECTION[api_category]

        # 3. Catch-all.
        return 'GLOBAL'

    def action_reclassify_category(self):
        """Re-run the classifier over these articles.

        Uses the stored api_category where there is one. Rows imported before
        that field existed are classified on their text alone and otherwise
        fall to Global: the section they are currently in is not evidence of
        anything, because the old mapping filed a Kyiv strike report under
        Style and a Galaxy S26 launch under Facts. Guessing an API category
        back out of that would only preserve the mistake.
        """
        changed = 0
        for record in self:
            section = self._av_classify_category(
                record.api_category, record.title, record.description
            )
            if section != record.category:
                record.category = section
                changed += 1
        return changed

    @api.model
    def cron_reclassify_categories(self, batch_size=500):
        """Re-file stored articles in batches, newest first."""
        offset = 0
        changed = 0
        while True:
            batch = self.search([], limit=batch_size, offset=offset)
            if not batch:
                break
            changed += batch.action_reclassify_category()
            self.env.cr.commit()
            self.env.invalidate_all()
            offset += batch_size
        _logger.info("Aveenix news: re-classified %s article(s).", changed)
        return changed

    # ── Sync ─────────────────────────────────────────────────────────────

    # Enough articles to fill every section of the news layout (hero 5,
    # global 5, travel 3, gadgets 4, recipes 4, style 4, fitness 5, gaming 1,
    # latest 6, popular 10, must-read 5).
    AV_NEWS_MIN_ARTICLES = 52

    @api.model
    def _av_country_scope(self, country_code, minimum=None):
        """Domain leaves restricting news to the visitor's country.

        News is only pulled for the countries listed in Website Settings, so a
        visitor from anywhere else has almost nothing to read. Filtering
        strictly on their country then left the page to pad itself out with
        placeholder articles while the sidebar counted the handful of real
        rows — an Australian visitor saw roughly sixty Fashion and Travel
        headlines above a sidebar reading "Fashion 0, Travel 0", because
        Australia had four articles in total.

        So: use the country when it can actually fill the page, and drop the
        restriction when it cannot. Returning [] rather than a short list keeps
        the article list and the category counts describing the same set, which
        is what makes the counts trustworthy.
        """
        if not country_code:
            return []
        if minimum is None:
            minimum = self.AV_NEWS_MIN_ARTICLES
        leaves = [('country_code', '=', country_code)]
        if self.search_count(leaves) >= minimum:
            return leaves
        return []

    @api.model
    def _av_resolve_country_code(self, country_names, fallback='us'):
        """Turn NewsData.io's country names into a two-letter ISO code.

        Tries the alias table first, then a res.country name lookup, and
        finally falls back to the code that was actually requested — so an
        unrecognised name is still filed somewhere sensible rather than
        becoming un-filterable.
        """
        Country = self.env['res.country']
        for raw in country_names or []:
            name = (raw or '').strip().lower()
            if not name:
                continue
            if len(name) == 2:  # already a code
                return name
            if name in _COUNTRY_NAME_ALIASES:
                return _COUNTRY_NAME_ALIASES[name]
            country = Country.search([('name', '=ilike', name)], limit=1)
            if country and country.code:
                return country.code.lower()
        return fallback

    @api.model
    def _av_newsdata_countries(self, target_country=None):
        """Resolve which countries to pull news for.

        Priority: explicit argument, then the countries picked in Website
        Settings, then a guess from the active website currencies.
        """
        if target_country:
            return [target_country]

        website = self.env['website'].search([], limit=1)
        if website and website.aveenix_newsdata_country_ids:
            codes = [
                c.code.lower()
                for c in website.aveenix_newsdata_country_ids if c.code
            ]
            if codes:
                return codes[:5]  # free tier: at most 5 countries per request

        currency_to_country = {
            'USD': 'us', 'INR': 'in', 'GBP': 'gb', 'AUD': 'au',
            'NZD': 'nz', 'JPY': 'jp', 'CAD': 'ca',
        }
        currencies = (
            website.get_currency_pricelist_options().mapped('currency_id.name')
            if website else []
        )
        codes = sorted({
            currency_to_country[c] for c in currencies if c in currency_to_country
        })
        return codes[:5] or ['us']

    @api.model
    def sync_news_from_api(self, target_country=None, pages_per_group=3):
        """Fetch the latest articles from NewsData.io and store them.

        One request per entry in _FETCH_GROUPS (the free tier allows at most 5
        categories per call), each paged up to ``pages_per_group`` times.
        """
        _logger.info("NewsData.io sync: starting.")
        api_key = self.env['ir.config_parameter'].sudo().get_param(
            'aveenix_website.newsdata_api_key'
        )
        if not api_key:
            _logger.warning("NewsData.io API key is not configured. Skipping sync.")
            return

        country_codes = self._av_newsdata_countries(target_country)
        country_param = ','.join(country_codes)
        _logger.info("NewsData.io sync: countries=%s", country_param)

        created = updated = 0
        for categories, sections in _FETCH_GROUPS:
            group_created, group_updated = self._av_sync_group(
                api_key, country_param, categories, pages_per_group,
                default_country=country_codes[0],
            )
            created += group_created
            updated += group_updated
            _logger.info(
                "NewsData.io sync: %s -> %s | created %s, updated %s",
                categories, sections, group_created, group_updated,
            )

        _logger.info(
            "NewsData.io sync complete: created %s, updated %s.", created, updated
        )

    @api.model
    def _av_sync_group(self, api_key, country_param, categories, pages,
                       default_country='us'):
        """Pull and store one category group. Never raises."""
        params = {
            'apikey': api_key,
            'language': 'en',
            'country': country_param,
            'category': categories,
            'image': '1',           # only articles that come with an image
            'removeduplicate': '1',
        }
        created = updated = 0
        next_page = None
        try:
            for _page in range(pages):
                if next_page:
                    params['page'] = next_page
                response = requests.get(NEWSDATA_URL, params=params, timeout=20)
                if response.status_code != 200:
                    _logger.error(
                        "NewsData.io %s: HTTP %s", categories, response.status_code
                    )
                    break
                data = response.json()
                if data.get('status') != 'success' or not data.get('results'):
                    break
                for article in data['results']:
                    outcome = self._av_store_article(article, default_country)
                    if outcome == 'created':
                        created += 1
                    elif outcome == 'updated':
                        updated += 1
                next_page = data.get('nextPage')
                if not next_page:
                    break
        except Exception:
            _logger.exception("NewsData.io sync failed for category group %s", categories)
        return created, updated

    @api.model
    def _av_store_article(self, article, default_country='us'):
        """Create or update one article. Returns 'created'/'updated'/None."""
        title = (article.get('title') or '').strip()
        if not title:
            return None
        # Some feeds (dailynews.com among them) occasionally send the publish
        # timestamp in the title field. Those rows are unusable — they surface
        # as "2026-09-09T06:31:11+00:00" in the trending ticker and headings —
        # so drop anything without real words in it.
        if not _TITLE_HAS_WORDS.search(title):
            _logger.info("NewsData.io: skipping article with junk title %r", title)
            return None

        image_url = article.get('image_url')
        if not image_url or 'stimg.co' in image_url:
            return None

        api_categories = article.get('category') or []
        description = article.get('description') or ''
        content = article.get('content') or description or ''
        if content and not content.startswith('<'):
            content = ''.join(
                '<p>%s</p>' % p.strip()
                for p in content.split('\n\n') if p.strip()
            )

        published_date = fields.Datetime.now()
        if article.get('pubDate'):
            try:
                published_date = fields.Datetime.to_datetime(article['pubDate'])
            except Exception:
                pass

        creators = article.get('creator') or []
        countries = article.get('country') or []

        vals = {
            'title': title,
            'description': description,
            'content': content,
            'category': self._av_classify_category(api_categories, title, description),
            'api_category': ','.join(api_categories),
            'author': creators[0] if creators else 'Staff Reporter',
            'published_date': published_date,
            'image_url': image_url,
            'source_url': article.get('link'),
            'api_article_id': article.get('article_id'),
            'country_code': self._av_resolve_country_code(countries, default_country),
        }

        existing = self.search([
            '|',
            ('api_article_id', '=', article.get('article_id')),
            ('title', '=', title),
        ], limit=1)
        if existing:
            existing.write(vals)
            return 'updated'
        self.create(vals)
        return 'created'
