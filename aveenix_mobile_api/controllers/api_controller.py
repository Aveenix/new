import json
from odoo import http
from odoo.http import request

class AveenixMobileAPI(http.Controller):

    def _success_response(self, data):
        return request.make_response(
            json.dumps({'status': 'success', 'data': data}),
            headers=[('Content-Type', 'application/json')]
        )

    def _error_response(self, message, status=400):
        return request.make_response(
            json.dumps({'status': 'error', 'message': message}),
            headers=[('Content-Type', 'application/json')],
            status=status
        )

    @http.route('/api/v1/auth/login', type='http', auth='public', methods=['POST'], csrf=False, cors='*')
    def api_login(self, **kw):
        try:
            data = json.loads(request.httprequest.data) if request.httprequest.data else {}
        except json.JSONDecodeError:
            return self._error_response('Invalid JSON format in request body', 400)
            
        login = data.get('login') or kw.get('login')
        password = data.get('password') or kw.get('password')
        db = request.db or data.get('db') or kw.get('db')
        
        if not db:
            # Fallback to the current database if not explicitly provided
            db = request.env.cr.dbname
            
        if not login or not password:
            return self._error_response('Login and password are required', 400)
            
        try:
            # Odoo 19 authentication signature
            credential = {'login': login, 'password': password, 'type': 'password'}
            
            if not request.db or request.db != db:
                import odoo
                registry = odoo.modules.registry.Registry(db)
                with registry.cursor() as cr:
                    env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
                    auth_info = request.session.authenticate(env, credential)
            else:
                auth_info = request.session.authenticate(request.env, credential)
                
            uid = auth_info.get('uid')
            if uid:
                user = request.env['res.users'].browse(uid)
                session_id = request.session.sid
                return self._success_response({
                    'uid': uid,
                    'name': user.name,
                    'email': user.login,
                    'session_id': session_id,
                })
        except Exception as e:
            return self._error_response(f'Invalid credentials: {str(e)}', 401)
            
        return self._error_response('Invalid credentials', 401)

    @http.route('/api/v1/auth/register', type='http', auth='public', methods=['POST'], csrf=False, cors='*')
    def api_register(self, **kw):
        try:
            data = json.loads(request.httprequest.data) if request.httprequest.data else {}
        except json.JSONDecodeError:
            return self._error_response('Invalid JSON format in request body', 400)
            
        name = data.get('name') or kw.get('name')
        email = data.get('email') or kw.get('email')
        password = data.get('password') or kw.get('password')
        
        if not name or not email or not password:
            return self._error_response('Name, email, and password are required', 400)
            
        try:
            # Basic validation
            existing = request.env['res.users'].sudo().search([('login', '=', email)])
            if existing:
                return self._error_response('User with this email already exists', 400)
                
            # Create user directly with ONLY the portal group (overriding any default internal user groups)
            user = request.env['res.users'].sudo().create({
                'name': name,
                'login': email,
                'password': password,
                'group_ids': [(6, 0, [request.env.ref('base.group_portal').id])]
            })
            
            return self._success_response({
                'uid': user.id,
                'name': user.name,
                'email': user.login,
                'message': 'Registration successful'
            })
        except Exception as e:
            return self._error_response(f'Registration failed: {str(e)}', 500)

    @http.route('/api/v1/products', type='http', auth='public', methods=['GET'], csrf=False, cors='*')
    def get_products(self, limit=20, offset=0, search='', **kw):
        domain = [('sale_ok', '=', True), ('website_published', '=', True)]
        if search:
            domain.append(('name', 'ilike', search))
            
        products = request.env['product.template'].sudo().search(
            domain, limit=int(limit), offset=int(offset)
        )
        
        data = []
        for p in products:
            category = p.public_categ_ids[0].name if p.public_categ_ids else ''
            data.append({
                'id': p.id,
                'name': p.name,
                'price': p.list_price,
                'image_url': f'/web/image/product.template/{p.id}/image_512',
                'category': category,
            })
            
        return self._success_response(data)

    @http.route('/api/v1/product/<int:product_id>', type='http', auth='public', methods=['GET'], csrf=False, cors='*')
    def get_product_details(self, product_id, **kw):
        product = request.env['product.template'].sudo().search([('id', '=', product_id), ('website_published', '=', True)], limit=1)
        if not product:
            return self._error_response('Product not found', 404)
            
        images = []
        if product.product_template_image_ids:
            for img in product.product_template_image_ids:
                images.append(f'/web/image/product.image/{img.id}/image_1024')
                
        category = product.public_categ_ids[0].name if product.public_categ_ids else ''
        
        data = {
            'id': product.id,
            'name': product.name,
            'price': product.list_price,
            'currency': product.currency_id.name if product.currency_id else 'USD',
            'description': product.desc_ai or '',
            'main_image': f'/web/image/product.template/{product.id}/image_1024',
            'extra_images': images,
            'category': category,
            'affiliate_url': product.affiliate_url or '',
        }
        return self._success_response(data)

    @http.route('/api/v1/news', type='http', auth='public', methods=['GET'], csrf=False, cors='*')
    def get_news(self, limit=20, offset=0, **kw):
        news = request.env['aveenix.news'].sudo().search([], limit=int(limit), offset=int(offset), order='published_date desc')
        data = []
        for n in news:
            data.append({
                'id': n.id,
                'title': n.title,
                'description': n.description,
                'image_url': n.image_url,
                'link': n.source_url,
                'date': str(n.published_date) if n.published_date else '',
            })
        return self._success_response(data)

    @http.route('/api/v1/blogs', type='http', auth='public', methods=['GET'], csrf=False, cors='*')
    def get_blogs(self, limit=20, offset=0, **kw):
        blogs = request.env['blog.blog'].sudo().search([], limit=int(limit), offset=int(offset))
        data = []
        for b in blogs:
            data.append({
                'id': b.id,
                'name': b.name,
                'subtitle': b.subtitle,
                'content': b.desc or '',
                'category': b.tag_category_id.name if hasattr(b, 'tag_category_id') and b.tag_category_id else '',
                'image_url': f'/web/image/blog.blog/{b.id}/av_blog_image' if hasattr(b, 'av_blog_image') else '',
            })
        return self._success_response(data)
