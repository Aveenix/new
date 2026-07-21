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

    @api.model
    def sync_news_from_api(self):
        """Fetch latest news from NewsData.io and save them to the database."""
        _logger.info("NewsData.io sync: Starting news synchronization.")
        api_key = self.env['ir.config_parameter'].sudo().get_param('aveenix_website.newsdata_api_key')
        if not api_key:
            _logger.warning("NewsData.io API Key is not configured. Skipping sync.")
            return

        # NewsData.io latest news endpoint
        url = "https://newsdata.io/api/1/news"
        
        # Free tier query parameters
        params = {
            'apikey': api_key,
            'language': 'en',
            'category': 'world,tourism,entertainment,technology,business',
            'size': 10,  # sync 10 articles per execution
        }
        
        # Retrieve target countries from the website record
        website = self.env['website'].sudo().search([], limit=1)
        if website and website.aveenix_newsdata_country_ids:
            country_codes = [c.code.lower() for c in website.aveenix_newsdata_country_ids if c.code]
            if country_codes:
                params['country'] = ",".join(country_codes)
                _logger.info("NewsData.io sync: Configured target country filters: %s", params['country'])
        else:
            _logger.info("NewsData.io sync: No country filters configured. Fetching global news.")

        # Log parameters (mask api key for security)
        masked_params = dict(params)
        if 'apikey' in masked_params and masked_params['apikey']:
            masked_params['apikey'] = masked_params['apikey'][:6] + '...' + masked_params['apikey'][-4:]
        _logger.info("NewsData.io sync: Request parameters: %s", masked_params)

        try:
            response = requests.get(url, params=params, timeout=10)
            _logger.info("NewsData.io sync: API response status code: %s", response.status_code)
            
            if response.status_code != 200:
                _logger.error("Failed to fetch news from NewsData.io: Status %s, Response: %s", 
                              response.status_code, response.text)
                return
            
            data = response.json()
            if data.get('status') != 'success':
                _logger.error("NewsData.io returned error status: %s", data)
                return

            results = data.get('results', [])
            _logger.info("NewsData.io sync: API returned %s articles.", len(results))
            synced_count = 0

            for article in results:
                api_id = article.get('article_id')
                article_title = article.get('title') or "Untitled"
                article_countries = article.get('country', [])
                
                _logger.info("NewsData.io sync: Processing article ID: %s | Title: %s | Country source: %s", 
                             api_id, article_title, article_countries)
                
                if not api_id:
                    continue

                # Prevent duplicates
                existing = self.search([('api_article_id', '=', api_id)], limit=1)
                if existing:
                    _logger.info("NewsData.io sync: Article %s already exists. Skipping.", api_id)
                    continue

                # Map API categories to our predefined list
                api_categories = article.get('category', [])
                category = 'GLOBAL'
                if api_categories:
                    first_cat = api_categories[0].upper()
                    if first_cat in ['STYLE', 'FASHION', 'LIFESTYLE', 'BEAUTY']:
                        category = 'STYLE'
                    elif first_cat in ['TRAVEL', 'TOURISM', 'OUTDOORS']:
                        category = 'TRAVEL'
                    elif first_cat in ['ENTERTAINMENT', 'SHOWBIZ', 'CELEBRITY', 'MOVIES']:
                        category = 'SHOWBIZ'
                    elif first_cat in ['SCIENCE', 'FACTS', 'EDUCATION', 'ENVIRONMENT']:
                        category = 'FACTS'
                    else:
                        category = 'GLOBAL'

                title = article.get('title') or "Untitled Article"
                description = article.get('description')
                content = article.get('content')
                if not content or "ONLY AVAILABLE IN PAID PLANS" in content:
                    content = description or ""
                
                # Format plain text content into HTML paragraphs if necessary
                if content and not content.startswith('<'):
                    paragraphs = content.split('\n\n')
                    content = "".join(f"<p>{p.strip()}</p>" for p in paragraphs if p.strip())

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
                # Standard high quality fallback image
                if not image_url:
                    image_url = "https://images.unsplash.com/photo-1504711434969-e33886168f5c?auto=format&fit=crop&w=800&q=80"

                source_url = article.get('link')

                self.create({
                    'title': title,
                    'description': description,
                    'content': content,
                    'category': category,
                    'author': author,
                    'published_date': published_date,
                    'image_url': image_url,
                    'source_url': source_url,
                    'api_article_id': api_id,
                })
                _logger.info("NewsData.io sync: Created new article ID %s: %s", api_id, title)
                synced_count += 1

            _logger.info("Successfully synced %s news articles from NewsData.io", synced_count)

        except Exception as e:
            _logger.exception("Error syncing news from NewsData.io: %s", str(e))
