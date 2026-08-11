import json
from odoo import http, _
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

    def _get_request_data(self, kw):
        data = dict(kw)
        if request.httprequest.data:
            try:
                json_data = json.loads(request.httprequest.data)
                if isinstance(json_data, dict):
                    data.update(json_data)
            except Exception:
                pass
        return data

    def _get_current_website(self):
        if hasattr(request, 'website') and request.website:
            return request.website.sudo()
        if hasattr(request.env['website'], 'get_current_website'):
            return request.env['website'].sudo().get_current_website()
        return request.env['website'].sudo().search([], limit=1)

    def _format_address(self, partner):
        if not partner:
            return {}
        return {
            'id': partner.id,
            'name': partner.name or '',
            'street': partner.street or '',
            'street2': partner.street2 or '',
            'city': partner.city or '',
            'state': partner.state_id.name if partner.state_id else '',
            'zip': partner.zip or '',
            'country': partner.country_id.name if partner.country_id else '',
            'phone': partner.phone or '',
            'email': partner.email or '',
        }

    def _format_category(self, cat, include_products=False):
        icon_url = f'/web/image/product.public.category/{cat.id}/av_ai_icon' if getattr(cat, 'av_ai_icon', False) else f'/web/image/product.public.category/{cat.id}/image_128'
        product_count = request.env['product.template'].sudo().search_count([
            ('sale_ok', '=', True),
            ('website_published', '=', True),
            ('public_categ_ids', 'in', [cat.id])
        ])
        res = {
            'id': cat.id,
            'name': cat.name,
            'parent_id': cat.parent_id.id if cat.parent_id else False,
            'parent_name': cat.parent_id.name if cat.parent_id else '',
            'icon_url': icon_url,
            'product_count': product_count,
        }
        if include_products:
            products = request.env['product.template'].sudo().search([
                ('sale_ok', '=', True),
                ('website_published', '=', True),
                ('public_categ_ids', 'in', [cat.id])
            ], limit=6)
            res['products_preview'] = [self._format_product(p) for p in products]
        return res

    def _format_product(self, p):
        tmpl = p if p._name == 'product.template' else p.product_tmpl_id
        variant_id = p.id if p._name == 'product.product' else (tmpl.product_variant_id.id if tmpl.product_variant_id else tmpl.id)

        images = []
        if tmpl.product_template_image_ids:
            for img in tmpl.product_template_image_ids:
                images.append(f'/web/image/product.image/{img.id}/image_1024')

        category = tmpl.public_categ_ids[0] if tmpl.public_categ_ids else False

        return {
            'id': tmpl.id,
            'variant_id': variant_id,
            'name': tmpl.name,
            'price': tmpl.list_price,
            'currency': tmpl.currency_id.name if tmpl.currency_id else 'USD',
            'description': getattr(tmpl, 'desc_ai', False) or tmpl.description_sale or '',
            'main_image': f'/web/image/product.template/{tmpl.id}/image_1024',
            'image_url': f'/web/image/product.template/{tmpl.id}/image_512',
            'extra_images': images,
            'category_id': category.id if category else False,
            'category': category.name if category else '',
            'in_stock': tmpl.qty_available > 0 if hasattr(tmpl, 'qty_available') else True,
            'rating_avg': getattr(tmpl, 'rating_avg', 0.0),
            'rating_count': getattr(tmpl, 'rating_count', 0),
            'affiliate_url': getattr(tmpl, 'affiliate_url', ''),
        }

    def _format_order(self, order, is_cart=False):
        lines_data = []
        for line in order.order_line:
            if getattr(line, 'is_delivery', False) or getattr(line, 'display_type', False):
                continue
            lines_data.append({
                'line_id': line.id,
                'product_id': line.product_id.id,
                'product_template_id': line.product_id.product_tmpl_id.id,
                'name': line.name or line.product_id.display_name,
                'quantity': line.product_uom_qty,
                'price_unit': line.price_unit,
                'price_subtotal': line.price_subtotal,
                'price_total': line.price_total,
                'image_url': f'/web/image/product.product/{line.product_id.id}/image_256',
            })
        state_labels = dict(order._fields['state']._description_selection(order.env))
        res = {
            'order_id': order.id,
            'order_name': order.name,
            'state': order.state,
            'state_label': state_labels.get(order.state, str(order.state)),
            'amount_untaxed': order.amount_untaxed,
            'amount_tax': order.amount_tax,
            'amount_total': order.amount_total,
            'currency': order.currency_id.name if order.currency_id else 'USD',
            'cart_quantity': sum(l['quantity'] for l in lines_data),
            'item_count': len(lines_data),
            'lines': lines_data,
        }
        if not is_cart:
            res.update({
                'date_order': str(order.date_order) if order.date_order else '',
                'cj_order_status': getattr(order, 'cj_order_status', ''),
                'tracking_link': getattr(order, 'av_tracking_link', ''),
                'partner_name': order.partner_id.name if order.partner_id else '',
                'shipping_address': self._format_address(order.partner_shipping_id or order.partner_id),
            })
        return res

    # ==========================================
    # 1. CATEGORIES APIs
    # ==========================================
    @http.route(['/api/v1/categories', '/api/v1/categories/all'], type='http', auth='public', methods=['GET', 'POST', 'OPTIONS'], csrf=False, cors='*')
    def get_all_categories(self, **kw):
        """1. Get all categories with icons"""
        if request.httprequest.method == 'OPTIONS':
            return self._success_response({'cors': 'ok'})
        categories = request.env['product.public.category'].sudo().search([])
        data = [self._format_category(cat) for cat in categories]
        return self._success_response(data)

    @http.route(['/api/v1/categories/menu', '/api/v1/categories/header_menu'], type='http', auth='public', methods=['GET', 'POST', 'OPTIONS'], csrf=False, cors='*')
    def get_header_menu_categories(self, **kw):
        """2. Get list of Dynamic Categories with icon which are shown as menuitems on website (M2m filed in settings page)"""
        if request.httprequest.method == 'OPTIONS':
            return self._success_response({'cors': 'ok'})
        website = self._get_current_website()
        categories = getattr(website, 'aveenix_header_menu_categ_ids', False)
        if not categories:
            categories = request.env['product.public.category'].sudo().search([('parent_id', '=', False)], limit=5)
        data = [self._format_category(cat) for cat in categories]
        return self._success_response(data)

    @http.route(['/api/v1/categories/homepage', '/api/v1/categories/home'], type='http', auth='public', methods=['GET', 'POST', 'OPTIONS'], csrf=False, cors='*')
    def get_homepage_categories(self, **kw):
        """3. Get list of Dynamic Categories with icon which are shown as sections of homepage content (M2m field in settings page)"""
        if request.httprequest.method == 'OPTIONS':
            return self._success_response({'cors': 'ok'})
        website = self._get_current_website()
        categories = getattr(website, 'aveenix_home_categ_ids', False)
        if not categories:
            categories = request.env['product.public.category'].sudo().search([('parent_id', '=', False)], limit=6)
        data = [self._format_category(cat, include_products=True) for cat in categories]
        return self._success_response(data)

    # ==========================================
    # 2. PRODUCTS APIs
    # ==========================================
    @http.route(['/api/v1/products', '/api/v1/products/by_category', '/api/v1/products/category'], type='http', auth='public', methods=['GET', 'POST', 'OPTIONS'], csrf=False, cors='*')
    def get_products(self, **kw):
        """4. Get Products list and product details by a specific category passed in API payload"""
        if request.httprequest.method == 'OPTIONS':
            return self._success_response({'cors': 'ok'})
        params = self._get_request_data(kw)
        limit = int(params.get('limit', 20))
        offset = int(params.get('offset', 0))
        search = params.get('search', '')
        category_id = params.get('category_id') or params.get('category')

        domain = [('sale_ok', '=', True), ('website_published', '=', True)]
        if search:
            domain.append(('name', 'ilike', search))

        category_data = {}
        if category_id:
            try:
                cat_id_int = int(category_id)
                domain.append(('public_categ_ids', 'in', [cat_id_int]))
                cat_obj = request.env['product.public.category'].sudo().browse(cat_id_int)
                if cat_obj.exists():
                    category_data = self._format_category(cat_obj)
            except (ValueError, TypeError):
                # If category was passed as string name
                domain.append(('public_categ_ids.name', 'ilike', str(category_id)))

        products = request.env['product.template'].sudo().search(
            domain, limit=limit, offset=offset
        )
        data = [self._format_product(p) for p in products]

        if category_data:
            return self._success_response({
                'category': category_data,
                'products': data,
                'count': len(data),
            })
        return self._success_response(data)

    @http.route('/api/v1/product/<int:product_id>', type='http', auth='public', methods=['GET', 'OPTIONS'], csrf=False, cors='*')
    def get_product_details(self, product_id, **kw):
        if request.httprequest.method == 'OPTIONS':
            return self._success_response({'cors': 'ok'})
        product = request.env['product.template'].sudo().search([('id', '=', product_id), ('website_published', '=', True)], limit=1)
        if not product:
            return self._error_response('Product not found', 404)
        return self._success_response(self._format_product(product))

    # ==========================================
    # 3. CART APIs
    # ==========================================
    @http.route(['/api/v1/cart', '/api/v1/cart/get'], type='http', auth='public', methods=['GET', 'POST', 'OPTIONS'], csrf=False, cors='*')
    def get_my_cart(self, **kw):
        """5. Get my Cart"""
        if request.httprequest.method == 'OPTIONS':
            return self._success_response({'cors': 'ok'})
        params = self._get_request_data(kw)
        order = None

        # Check if order_id passed explicitly
        if params.get('order_id'):
            order = request.env['sale.order'].sudo().browse(int(params.get('order_id')))
            if not order.exists() or order.state not in ['draft', 'sent']:
                order = None

        if not order and hasattr(request, 'website') and request.website:
            order = request.website.sale_get_order(force_create=False)

        if not order:
            return self._success_response({
                'order_id': 0,
                'order_name': '',
                'state': 'draft',
                'amount_untaxed': 0.0,
                'amount_tax': 0.0,
                'amount_total': 0.0,
                'currency': request.env.company.currency_id.name,
                'cart_quantity': 0,
                'item_count': 0,
                'lines': [],
            })
        return self._success_response(self._format_order(order, is_cart=True))

    @http.route(['/api/v1/cart/add'], type='http', auth='public', methods=['POST', 'OPTIONS'], csrf=False, cors='*')
    def add_to_cart(self, **kw):
        """6. Add to Cart"""
        if request.httprequest.method == 'OPTIONS':
            return self._success_response({'cors': 'ok'})
        params = self._get_request_data(kw)
        product_id = params.get('product_id')
        if not product_id:
            return self._error_response('product_id is required', 400)
        try:
            product_id = int(product_id)
            qty = float(params.get('quantity', 1.0))
        except (ValueError, TypeError):
            return self._error_response('Invalid product_id or quantity format', 400)

        product = request.env['product.product'].sudo().browse(product_id)
        if not product.exists():
            tmpl = request.env['product.template'].sudo().browse(product_id)
            if tmpl.exists() and tmpl.product_variant_id:
                product = tmpl.product_variant_id
            else:
                return self._error_response('Product not found', 404)

        order = None
        if params.get('order_id'):
            order = request.env['sale.order'].sudo().browse(int(params.get('order_id')))
            if not order.exists() or order.state not in ['draft', 'sent']:
                order = None

        if not order:
            if hasattr(request, 'website') and request.website:
                order = request.website.sale_get_order(force_create=True)
            else:
                partner_id = request.env.user.partner_id.id
                if request.env.user._is_public():
                    partner_id = request.env.ref('base.public_partner').id
                order = request.env['sale.order'].sudo().create({
                    'partner_id': partner_id,
                    'company_id': request.env.company.id,
                })

        # Add item using Odoo 19 _cart_add
        order._cart_add(product_id=product.id, quantity=qty)
        return self._success_response(self._format_order(order, is_cart=True))

    @http.route(['/api/v1/cart/update'], type='http', auth='public', methods=['POST', 'OPTIONS'], csrf=False, cors='*')
    def update_cart_line(self, **kw):
        """Helper: Update line quantity in cart"""
        if request.httprequest.method == 'OPTIONS':
            return self._success_response({'cors': 'ok'})
        params = self._get_request_data(kw)
        line_id = params.get('line_id')
        if not line_id:
            return self._error_response('line_id is required', 400)
        try:
            line_id = int(line_id)
            qty = float(params.get('quantity', 1.0))
        except (ValueError, TypeError):
            return self._error_response('Invalid line_id or quantity format', 400)

        order = None
        if hasattr(request, 'website') and request.website:
            order = request.website.sale_get_order(force_create=False)
        if not order and params.get('order_id'):
            order = request.env['sale.order'].sudo().browse(int(params.get('order_id')))
            if not order.exists() or order.state not in ['draft', 'sent']:
                order = None
        if not order:
            return self._error_response('Active cart not found', 404)

        order._cart_update_line_quantity(line_id=line_id, quantity=qty)
        return self._success_response(self._format_order(order, is_cart=True))

    @http.route(['/api/v1/cart/remove'], type='http', auth='public', methods=['POST', 'OPTIONS'], csrf=False, cors='*')
    def remove_cart_line(self, **kw):
        """Helper: Remove line from cart"""
        if request.httprequest.method == 'OPTIONS':
            return self._success_response({'cors': 'ok'})
        params = self._get_request_data(kw)
        params['quantity'] = 0
        return self.update_cart_line(**params)

    # ==========================================
    # 4. CHECKOUT API
    # ==========================================
    @http.route(['/api/v1/cart/checkout', '/api/v1/checkout'], type='http', auth='public', methods=['POST', 'OPTIONS'], csrf=False, cors='*')
    def complete_checkout(self, **kw):
        """7. Complete shopping flow with Checkout"""
        if request.httprequest.method == 'OPTIONS':
            return self._success_response({'cors': 'ok'})
        params = self._get_request_data(kw)
        order = None
        if params.get('order_id'):
            order = request.env['sale.order'].sudo().browse(int(params.get('order_id')))
            if not order.exists() or order.state not in ['draft', 'sent']:
                order = None
        if not order and hasattr(request, 'website') and request.website:
            order = request.website.sale_get_order(force_create=False)

        if not order or not order.order_line:
            return self._error_response('Cart is empty or order not found', 400)

        # Update address if provided
        if any(k in params for k in ['street', 'city', 'phone', 'name', 'email']):
            partner = order.partner_id
            vals = {}
            for f in ['name', 'street', 'city', 'zip', 'phone', 'email']:
                if params.get(f):
                    vals[f] = params.get(f)
            if vals and partner and partner.id != request.env.ref('base.public_partner').id:
                partner.sudo().write(vals)
            elif vals:
                new_partner = request.env['res.partner'].sudo().create(vals)
                order.sudo().write({'partner_id': new_partner.id})

        # Confirm order
        order.sudo().action_confirm()

        # Reset session cart
        if hasattr(request, 'session'):
            request.session['sale_order_id'] = None

        order_data = self._format_order(order, is_cart=False)
        order_data['message'] = 'Order completed and confirmed successfully'
        return self._success_response(order_data)

    # ==========================================
    # 5. ORDERS APIs
    # ==========================================
    @http.route(['/api/v1/orders', '/api/v1/my/orders'], type='http', auth='public', methods=['GET', 'POST', 'OPTIONS'], csrf=False, cors='*')
    def get_my_orders(self, **kw):
        """8. Get My Orders List"""
        if request.httprequest.method == 'OPTIONS':
            return self._success_response({'cors': 'ok'})
        params = self._get_request_data(kw)
        domain = [('state', 'in', ['sale', 'done', 'cancel', 'sent'])]
        partner_id = params.get('partner_id')
        email = params.get('email')

        if partner_id:
            domain.append(('partner_id', '=', int(partner_id)))
        elif email:
            domain.append(('partner_id.email', '=ilike', email))
        elif not request.env.user._is_public():
            domain.append(('partner_id', '=', request.env.user.partner_id.id))
        else:
            return self._success_response([])

        orders = request.env['sale.order'].sudo().search(
            domain,
            limit=int(params.get('limit', 20)),
            offset=int(params.get('offset', 0)),
            order='date_order desc'
        )
        data = [self._format_order(o, is_cart=False) for o in orders]
        return self._success_response(data)

    @http.route(['/api/v1/order/<int:order_id>', '/api/v1/orders/<int:order_id>', '/api/v1/order/details'], type='http', auth='public', methods=['GET', 'POST', 'OPTIONS'], csrf=False, cors='*')
    def get_order_details(self, order_id=None, **kw):
        """9. Get details of an Order"""
        if request.httprequest.method == 'OPTIONS':
            return self._success_response({'cors': 'ok'})
        params = self._get_request_data(kw)
        oid = order_id or params.get('order_id')
        if not oid:
            return self._error_response('order_id is required', 400)
        order = request.env['sale.order'].sudo().browse(int(oid))
        if not order.exists():
            return self._error_response('Order not found', 404)

        return self._success_response(self._format_order(order, is_cart=False))

    # ==========================================
    # 6. AUTH, NEWS & BLOGS APIs
    # ==========================================
    @http.route('/api/v1/auth/login', type='http', auth='public', methods=['POST', 'OPTIONS'], csrf=False, cors='*')
    def api_login(self, **kw):
        if request.httprequest.method == 'OPTIONS':
            return self._success_response({'cors': 'ok'})
        try:
            data = json.loads(request.httprequest.data) if request.httprequest.data else {}
        except json.JSONDecodeError:
            return self._error_response('Invalid JSON format in request body', 400)

        login = data.get('login') or kw.get('login')
        password = data.get('password') or kw.get('password')
        db = request.db or data.get('db') or kw.get('db')

        if not db:
            db = request.env.cr.dbname

        if not login or not password:
            return self._error_response('Login and password are required', 400)

        try:
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

    @http.route('/api/v1/auth/register', type='http', auth='public', methods=['POST', 'OPTIONS'], csrf=False, cors='*')
    def api_register(self, **kw):
        if request.httprequest.method == 'OPTIONS':
            return self._success_response({'cors': 'ok'})
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
            existing = request.env['res.users'].sudo().search([('login', '=', email)])
            if existing:
                return self._error_response('User with this email already exists', 400)

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

    @http.route('/api/v1/news', type='http', auth='public', methods=['GET', 'OPTIONS'], csrf=False, cors='*')
    def get_news(self, limit=20, offset=0, category=None, **kw):
        if request.httprequest.method == 'OPTIONS':
            return self._success_response({'cors': 'ok'})
        domain = []
        if category:
            cat_map = {
                'global': 'GLOBAL',
                'lifestyle': 'STYLE',
                'fashion': 'SHOWBIZ',
                'gaming': 'FACTS',
                'fitness': 'STYLE'
            }
            db_cat = cat_map.get(category.lower(), category.upper())
            domain.append(('category', '=', db_cat))
            
        user_country_id = request.session.get('av_user_country_id')
        if user_country_id:
            user_country = request.env['res.country'].sudo().browse(user_country_id)
        else:
            user_country = request.env.user.sudo().country_id or request.website.sudo().company_id.country_id
            
        country_code = user_country.code.lower() if user_country and user_country.code else 'us'
        country_name = user_country.name.lower() if user_country and user_country.name else 'united states'
        domain.append('|')
        domain.append(('country_code', '=', country_code))
        domain.append(('country_code', '=', country_name))
            
        news = request.env['aveenix.news'].sudo().search(domain, limit=int(limit), offset=int(offset), order='published_date desc')
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

    @http.route('/api/v1/blogs', type='http', auth='public', methods=['GET', 'OPTIONS'], csrf=False, cors='*')
    def get_blogs(self, limit=20, offset=0, **kw):
        if request.httprequest.method == 'OPTIONS':
            return self._success_response({'cors': 'ok'})
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
