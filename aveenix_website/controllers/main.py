from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from odoo import http
from odoo.http import request
from odoo.addons.website_sale.controllers.main import WebsiteSale

_LOCATION_SESSION_KEY = 'av_user_country_id'


def _apply_affiliate_tag(url, tag):
    """Append/replace the Amazon Associates `tag` query param on an affiliate URL."""
    if not tag:
        return url
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query['tag'] = tag
    return urlunsplit((
        parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment,
    ))


class AveenixWebsite(WebsiteSale):

    @http.route([
        '/shop',
        '/shop/page/<int:page>',
        '/shop/category/<model("product.public.category"):category>',
        '/shop/category/<model("product.public.category"):category>/page/<int:page>',
    ], type='http', auth='public', website=True)
    def shop(self, page=0, category=None, search='', min_price=0.0, max_price=0.0, tags='', **post):
        website = request.env['website'].get_current_website()
        if website.shop_ppg != 25 or website.shop_ppr != 5:
            website.sudo().write({'shop_ppg': 25, 'shop_ppr': 5})
        return super().shop(page=page, category=category, search=search,
                            min_price=min_price, max_price=max_price, tags=tags, **post)

    @http.route('/', type='http', auth='public', website=True)
    def homepage(self, **kwargs):
        return request.render('aveenix_website.homepage', {})

    @http.route('/aveenix/home/products', type='jsonrpc', auth='public', website=True, readonly=True)
    def home_products(self, limit=6, **kwargs):
        country_id = request.session.get(_LOCATION_SESSION_KEY)
        products = request.env['product.template'].sudo().search(
            [('sale_ok', '=', True), ('website_published', '=', True)]
        )
        if not products:
            products = request.env['product.template'].sudo().search(
                [('sale_ok', '=', True)]
            )
        if country_id:
            products = products.filtered(
                lambda p: not p.available_country_ids or country_id in p.available_country_ids.ids
            )
        products = products[:int(limit)]
        return products.read(['id', 'name', 'list_price', 'website_url', 'image_512'])

    def _shop_get_query_url_kwargs(self, search, min_price, max_price, order=None, tags=None, **kwargs):
        result = super()._shop_get_query_url_kwargs(search, min_price, max_price, order=order, tags=tags, **kwargs)
        result['brand'] = kwargs.get('brand')
        result['stock'] = kwargs.get('stock')
        result['categ'] = kwargs.get('categ')
        return result

    def _get_additional_shop_values(self, values, **kwargs):
        extra = super()._get_additional_shop_values(values, **kwargs)

        Brand = request.env['product.brand']
        all_brands = Brand.sudo().search([], order='name asc')
        brand_id = kwargs.get('brand')
        try:
            brand_id = int(brand_id) if brand_id else 0
        except (TypeError, ValueError):
            brand_id = 0

        categ_id = kwargs.get('categ')
        try:
            categ_id = int(categ_id) if categ_id else 0
        except (TypeError, ValueError):
            categ_id = 0

        all_categs = request.env['product.public.category'].sudo().search(
            [('parent_id', '=', False)], order='name asc'
        )

        extra.update({
            'all_brands': all_brands,
            'selected_brand': brand_id,
            'selected_stock': kwargs.get('stock', ''),
            'all_categs': all_categs,
            'selected_categ': categ_id,
        })
        return extra

    def _shop_lookup_products(self, options, post, search, website):
        fuzzy_search_term, product_count, search_result = super()._shop_lookup_products(
            options, post, search, website
        )
        country_id = request.session.get(_LOCATION_SESSION_KEY)
        if country_id:
            # Keep products where available_country_ids is empty OR contains user country
            filtered = search_result.filtered(
                lambda p: not p.available_country_ids or country_id in p.available_country_ids.ids
            )
            product_count = len(filtered)
            search_result = filtered

        # Category filter (query-param based, independent of URL path category)
        categ_id = post.get('categ')
        try:
            categ_id = int(categ_id) if categ_id else 0
        except (TypeError, ValueError):
            categ_id = 0
        if categ_id:
            child_ids = set(
                request.env['product.public.category'].sudo()
                .search([('id', 'child_of', categ_id)]).ids
            )
            search_result = search_result.filtered(
                lambda p: bool(set(p.public_categ_ids.ids) & child_ids)
            )
            product_count = len(search_result)

        # Brand filter
        brand_id = post.get('brand')
        try:
            brand_id = int(brand_id) if brand_id else 0
        except (TypeError, ValueError):
            brand_id = 0
        if brand_id:
            search_result = search_result.filtered(
                lambda p: p.product_brand_id and p.product_brand_id.id == brand_id
            )
            product_count = len(search_result)

        # Stock filter
        stock = post.get('stock', '')
        if stock == 'instock':
            search_result = search_result.filtered(lambda p: p.virtual_available > 0)
            product_count = len(search_result)
        elif stock == 'onsale':
            search_result = search_result.filtered(lambda p: p.compare_list_price and p.compare_list_price > p.list_price)
            product_count = len(search_result)

        return fuzzy_search_term, product_count, search_result

    @http.route('/compare', type='http', auth='public', website=True)
    def compare_page(self, **kwargs):
        product_ids_raw = kwargs.get('ids', '')
        products = request.env['product.template'].sudo()
        if product_ids_raw:
            try:
                ids = [int(i) for i in product_ids_raw.split(',') if i.strip().isdigit()]
                if ids:
                    products = request.env['product.template'].sudo().search([
                        ('id', 'in', ids),
                        ('website_published', '=', True),
                    ])
            except Exception:
                pass
        return request.render('aveenix_website.compare_page', {
            'products': products,
        })

    @http.route('/favourites', type='http', auth='public', website=True)
    def favourites_page(self, **kwargs):
        return request.render('aveenix_website.favourites_page', {})

    @http.route('/aveenix/products', type='jsonrpc', auth='public', website=True, readonly=True)
    def get_products_by_ids(self, ids=None, **kwargs):
        if not ids:
            return []
        try:
            id_list = [int(i) for i in ids if str(i).strip().isdigit() or isinstance(i, int)]
        except Exception:
            return []
        templates = request.env['product.template'].sudo().search(
            [('id', 'in', id_list)], limit=50,
        )
        result = request.env['product.template'].sudo().search_read(
            [('id', 'in', id_list)],
            fields=['id', 'name', 'list_price', 'image_512', 'website_url',
                    'virtual_available', 'type', 'description_sale', 'categ_id', 'public_categ_ids'],
            limit=50,
        )
        tmpl_map = {t.id: t._get_first_possible_variant_id() for t in templates}
        pub_categ_map = {t.id: t.public_categ_ids[:1].name if t.public_categ_ids else None for t in templates}
        for r in result:
            r['product_id'] = tmpl_map.get(r['id'])
            r['public_categ_name'] = pub_categ_map.get(r['id'])
        return result

    @http.route('/categories', type='http', auth='public', website=True)
    def categories_page(self, **kwargs):
        published_templates = request.env['product.template'].sudo().search([
            ('website_published', '=', True),
            ('public_categ_ids', '!=', False),
        ])
        count_map = {}
        for tmpl in published_templates:
            for cat in tmpl.public_categ_ids:
                count_map[cat.id] = count_map.get(cat.id, 0) + 1
        categories = request.env['product.public.category'].sudo().search(
            [('id', 'in', list(count_map.keys())), ('parent_id', '=', False)],
            order='name asc',
        )
        return request.render('aveenix_website.categories_page', {
            'categories': categories,
            'count_map': count_map,
        })

    @http.route('/wishlist', type='http', auth='public', website=True)
    def wishlist_page(self, **kwargs):
        return request.render('aveenix_website.wishlist_page', {})

    @http.route('/aveenix/location/set', type='jsonrpc', auth='public', website=True)
    def location_set(self, country_code=None, **kwargs):
        if not country_code:
            request.session.pop(_LOCATION_SESSION_KEY, None)
            # Drop cached pricelist so it recomputes for the cleared location.
            request.session.pop('website_sale_current_pl', None)
            return {'ok': True}
        country = request.env['res.country'].sudo().search(
            [('code', '=', country_code.upper())], limit=1
        )
        if country:
            request.session[_LOCATION_SESSION_KEY] = country.id
            # Invalidate cached pricelist so the country-matched one is picked.
            request.session.pop('website_sale_current_pl', None)
            self._av_apply_country_pricelist(country)
        return {'ok': bool(country)}

    def _av_apply_country_pricelist(self, country):
        """Force-select the website pricelist whose currency matches `country`.

        The stock website logic keeps the partner's default pricelist whenever it
        stays globally available, so a country-specific pricelist is never
        auto-applied. We pick, among the available website pricelists, the one
        whose currency equals the detected country's currency and pin it on the
        session + current cart. Fully dynamic: the country's `currency_id` drives
        the choice, so each country resolves to its own currency's pricelist.
        """
        if not country.currency_id:
            return
        website = request.env['website'].get_current_website()
        available = website.sudo().get_pricelist_available(show_visible=True)
        match = available.filtered(
            lambda pl: pl.currency_id == country.currency_id
        )[:1]
        if not match:
            return
        request.session['website_sale_current_pl'] = match.id
        cart = request.cart
        if cart and not request.env.cr.readonly:
            cart.sudo().write({'pricelist_id': match.id})

    @http.route('/aveenix/location/get', type='jsonrpc', auth='public', website=True, readonly=True)
    def location_get(self, **kwargs):
        country_id = request.session.get(_LOCATION_SESSION_KEY)
        if not country_id:
            return {'country_id': False, 'country_name': False}
        country = request.env['res.country'].sudo().browse(country_id)
        return {'country_id': country.id, 'country_name': country.name}

    @http.route('/notifications', type='http', auth='public', website=True)
    def notifications_page(self, **kwargs):
        return request.render('aveenix_website.notifications_page', {})

    @http.route('/contactus', type='http', auth='public', website=True)
    def contact_us_page(self, **kwargs):
        return request.render('aveenix_website.contact_us_page', {})

    @http.route('/privacy', type='http', auth='public', website=True)
    def privacy_policy_page(self, **kwargs):
        return request.render('aveenix_website.privacy_policy_page', {})

    @http.route('/about', type='http', auth='public', website=True)
    def about_us_page(self, **kwargs):
        return request.render('aveenix_website.about_us_page', {})

    # ── User list sync endpoints ──────────────────────────────────

    _LIST_FIELD = {
        'compare': 'av_compare_product_ids',
        'fav':     'av_fav_product_ids',
        'wish':    'av_wish_product_ids',
    }

    def _get_user(self):
        uid = request.env.uid
        if not uid or request.env.user._is_public():
            return None
        return request.env['res.users'].sudo().browse(uid)

    @http.route('/aveenix/list/get', type='jsonrpc', auth='public', website=True, readonly=True)
    def list_get(self, list_type=None, **kwargs):
        field = self._LIST_FIELD.get(list_type)
        if not field:
            return {'logged_in': False, 'ids': []}
        user = self._get_user()
        if not user:
            return {'logged_in': False, 'ids': []}
        return {'logged_in': True, 'ids': user[field].ids}

    @http.route('/aveenix/list/add', type='jsonrpc', auth='user', website=True)
    def list_add(self, list_type=None, product_id=None, **kwargs):
        field = self._LIST_FIELD.get(list_type)
        if not field or not product_id:
            return {'ok': False}
        user = self._get_user()
        if not user:
            return {'ok': False}
        user.write({field: [(4, int(product_id))]})
        return {'ok': True}

    @http.route('/aveenix/list/remove', type='jsonrpc', auth='user', website=True)
    def list_remove(self, list_type=None, product_id=None, **kwargs):
        field = self._LIST_FIELD.get(list_type)
        if not field or not product_id:
            return {'ok': False}
        user = self._get_user()
        if not user:
            return {'ok': False}
        user.write({field: [(3, int(product_id))]})
        return {'ok': True}

    @http.route('/aveenix/list/merge', type='jsonrpc', auth='user', website=True)
    def list_merge(self, compare_ids=None, fav_ids=None, wish_ids=None, **kwargs):
        user = self._get_user()
        if not user:
            return {'ok': False}
        if compare_ids:
            user.write({'av_compare_product_ids': [(4, int(i)) for i in compare_ids]})
        if fav_ids:
            user.write({'av_fav_product_ids': [(4, int(i)) for i in fav_ids]})
        if wish_ids:
            user.write({'av_wish_product_ids': [(4, int(i)) for i in wish_ids]})
        return {
            'ok': True,
            'compare_ids': user.av_compare_product_ids.ids,
            'fav_ids':     user.av_fav_product_ids.ids,
            'wish_ids':    user.av_wish_product_ids.ids,
        }

    @http.route('/aveenix/affiliate/<int:product_id>', type='http', auth='public', website=True, sitemap=False)
    def affiliate_redirect(self, product_id, **kw):
        product = request.env['product.template'].sudo().browse(product_id)
        if not product.exists() or not product.affiliate_url:
            return request.redirect('/shop')
        # Affiliate links are only exposed to logged-in users (the Buy button is
        # hidden for guests); block direct hits from public users as a backstop.
        if request.env.user._is_public():
            return request.redirect('/web/login')
        tag = request.env.company.sudo().affiliate_amazon_tag
        target_url = _apply_affiliate_tag(product.affiliate_url, tag)
        user = request.env.user
        request.env['affiliate.click.log'].sudo().create({
            'product_id': product.id,
            'user_id': user.id if not user._is_public() else False,
            'session_id': request.session.sid,
            'referrer_url': (request.httprequest.referrer or '')[:2000],
            'affiliate_url': target_url,
        })
        return request.redirect(target_url, local=False)
