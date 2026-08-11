import logging
import requests
from odoo import api, fields, models

_logger = logging.getLogger(__name__)

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
        ('FACTS', 'Facts'),
        ('GLOBAL', 'Global'),
    ], string='Category', default='GLOBAL', required=True)
    author = fields.Char(string='Author')
    published_date = fields.Datetime(string='Published Date', default=fields.Datetime.now)
    image_url = fields.Char(string='Image URL')
    source_url = fields.Char(string='Source URL')
    api_article_id = fields.Char(string='API Article ID', index=True)
    country_code = fields.Char(string='Country Code', index=True, default='us')

    @api.model
    def sync_news_from_api(self, target_country=None):
        """Fetch latest news from NewsData.io and save them to the database."""
        _logger.info("NewsData.io sync: Starting news synchronization.")
        api_key = self.env['ir.config_parameter'].sudo().get_param('aveenix_website.newsdata_api_key')
        if not api_key:
            _logger.warning("NewsData.io API Key is not configured. Skipping sync.")
            return

        # NewsData.io latest news endpoint
        url = "https://newsdata.io/api/1/news"
        
        # Map active website currencies to News API country codes (max 5 for free tier)
        if target_country:
            country_codes = [target_country]
        else:
            active_currencies = self.env['website'].search([], limit=1).get_currency_pricelist_options().mapped('currency_id.name') if self.env['website'].search([]) else []
            currency_map = {'USD': 'us', 'INR': 'in', 'GBP': 'gb', 'AUD': 'au', 'NZD': 'nz', 'JPY': 'jp', 'CAD': 'ca'}
            country_codes = list(set([currency_map[c] for c in active_currencies if c in currency_map]))
        
        # Free tier only allows up to 5 countries in one request
        country_codes = country_codes[:5] if country_codes else ['us']
        country_param = ','.join(country_codes)

        # Free tier query parameters
        params = {
            'apikey': api_key,
            'language': 'en',
            'country': country_param,
            'category': 'world,lifestyle,entertainment,technology,health',
            'image': '1', # Only fetch articles with images!
            'removeduplicate': '1',
        }
        
        # Log parameters (mask api key for security)
        masked_params = dict(params)
        if 'apikey' in masked_params and masked_params['apikey']:
            masked_params['apikey'] = masked_params['apikey'][:6] + '...' + masked_params['apikey'][-4:]
        _logger.info("NewsData.io sync: Request parameters: %s", masked_params)

        articles_created = 0
        articles_updated = 0
        next_page = None

        try:
            for page in range(8): # Fetch up to 8 pages (~80 articles)
                if next_page:
                    params['page'] = next_page
                    
                response = requests.get(url, params=params, timeout=20)
                if response.status_code != 200:
                    _logger.error("Failed to fetch news: Status %s", response.status_code)
                    break
                    
                data = response.json()
                if data.get('status') == 'success' and data.get('results'):
                    results = data['results']
                    for article in results:
                        article_id = article.get('article_id')
                        title = article.get('title')
                        if not title: continue
                        existing = self.search(['|', ('api_article_id', '=', article_id), ('title', '=', title)], limit=1)

                        api_categories = article.get('category', [])
                        category = 'GLOBAL'
                        for ac in api_categories:
                            ac = ac.lower()
                            if ac == 'lifestyle': category = 'STYLE'
                            elif ac in ('entertainment', 'fashion'): category = 'SHOWBIZ'
                            elif ac == 'technology': category = 'FACTS' # Maps to Gaming/Facts
                            elif ac == 'health': category = 'STYLE' # Maps to Fitness/Style
                            elif ac == 'world': category = 'GLOBAL'

                        creators = article.get('creator') or []
                        author = creators[0] if creators else "Staff Reporter"
                        
                        pub_date_str = article.get('pubDate')
                        published_date = fields.Datetime.now()
                        if pub_date_str:
                            try:
                                published_date = fields.Datetime.to_datetime(pub_date_str)
                            except Exception:
                                pass

                        image_url = article.get('image_url')
                        if not image_url or 'stimg.co' in image_url:
                            continue

                        description = article.get('description') or ''
                        content = article.get('content') or description or ''
                        
                        article_countries = article.get('country') or []
                        country_code = article_countries[0].lower() if article_countries else 'us'
                        
                        if content and not content.startswith('<'):
                            paragraphs = content.split('\n\n')
                            content = "".join(f"<p>{p.strip()}</p>" for p in paragraphs if p.strip())

                        vals = {
                            'title': title,
                            'description': description,
                            'content': content,
                            'category': category,
                            'author': author,
                            'published_date': published_date,
                            'image_url': image_url,
                            'source_url': article.get('link'),
                            'api_article_id': article_id,
                            'country_code': country_code,
                        }

                        if existing:
                            existing.write(vals)
                            articles_updated += 1
                        else:
                            self.create(vals)
                            articles_created += 1
                            
                    next_page = data.get('nextPage')
                    if not next_page:
                        break
                else:
                    break
                    
        except Exception as e:
            _logger.exception("Error syncing news from NewsData.io: %s", str(e))
            
        _logger.info("NewsData.io sync complete: Created %s, Updated %s.", articles_created, articles_updated)
