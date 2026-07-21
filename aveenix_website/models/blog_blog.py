from odoo import models, fields

class BlogBlog(models.Model):
    _inherit = 'blog.blog'

    desc = fields.Html('Description', sanitize=False, translate=True)
    av_blog_image = fields.Image("Blog Image")
    tag_category_id = fields.Many2one('blog.tag.category', string="Category")

    def action_generate_ai_content(self):
        self.ensure_one()
        import requests
        from odoo.exceptions import UserError
        
        endpoint = self.env['ir.config_parameter'].sudo().get_param('aveenix.ai_endpoint', 'https://api.groq.com/openai/v1/chat/completions')
        model = self.env['ir.config_parameter'].sudo().get_param('aveenix.ai_model', 'llama-3.3-70b-versatile').strip()
        api_key = self.env['ir.config_parameter'].sudo().get_param('aveenix.ai_api_key')
        
        if api_key:
            api_key = api_key.strip()
            
        if not api_key and 'groq' in endpoint:
            raise UserError("Please configure your AI API Key in Settings -> Technical -> System Parameters.\nCreate a parameter named 'aveenix.ai_api_key'.\nYou can get a free key for Llama 3 (Open Source) at console.groq.com!")

        headers = {
            "Content-Type": "application/json"
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
            
        prompt = f"Write an engaging, detailed, and SEO-friendly HTML-formatted content for a blog named '{self.name}'. "
        if self.subtitle:
            prompt += f"The theme/subtitle is '{self.subtitle}'. "
        if self.tag_category_id:
            prompt += f"The category is '{self.tag_category_id.name}'. "
        prompt += "Return ONLY valid HTML content (use <p>, <h2>, <h3>, <ul>, <li>, <strong>, etc.), no markdown wrappers, no explanations. Make it detailed."

        data = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a professional blog copywriter. Output only raw HTML code."},
                {"role": "user", "content": prompt}
            ]
        }
        
        try:
            response = requests.post(endpoint, headers=headers, json=data, timeout=20)
            response.raise_for_status()
            result = response.json()
            content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
            
            if content.startswith('```html'):
                content = content[7:]
            if content.endswith('```'):
                content = content[:-3]
                
            self.desc = content
        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            if hasattr(e, 'response') and e.response is not None:
                error_msg += f"\nAPI Response: {e.response.text}"
            raise UserError(f"Failed to connect to AI: {error_msg}")
        except Exception as e:
            raise UserError(f"Failed to connect to AI: {str(e)}")
