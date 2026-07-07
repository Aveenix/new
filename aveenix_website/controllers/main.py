from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from odoo import http
from odoo.http import request
from odoo.addons.website_sale.controllers.main import WebsiteSale
from odoo.addons.website_sale.controllers.cart import Cart

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


def _company_domain():
    """Domain leaves restricting products to the current website's company.

    Multi-company: each website is bound to a company; show that company's
    products plus company-less (shared) products. Returns [] when the website
    has no company set (single-company fallback = everything visible)."""
    website = request.env['website'].get_current_website()
    company = website.company_id
    if not company:
        return []
    return ['|', ('company_id', '=', company.id), ('company_id', '=', False)]


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
        Category = request.env['product.public.category'].sudo()
        categories = Category.search([('parent_id', '=', False)])

        # Keep only top-level categories with a published product in their
        # subtree — credit each product to the TOP-LEVEL ancestor of every
        # category it belongs to (same walk used on /shop and /categories).
        pub_templates = request.env['product.template'].sudo().search([
            ('website_published', '=', True),
            ('public_categ_ids', '!=', False),
        ] + _company_domain())
        non_empty_top_ids = set()
        for tmpl in pub_templates:
            for cat in tmpl.public_categ_ids:
                node = cat
                while node.parent_id:
                    node = node.parent_id
                non_empty_top_ids.add(node.id)
        categories = categories.filtered(lambda c: c.id in non_empty_top_ids)

        # New Arrivals: newest categories first.
        cats_new = categories.sorted(key=lambda c: c.create_date or c.id, reverse=True)

        # Best Sellers: categories ranked by the total sales of their products.
        # Aggregate sales_count per category in one batch (no per-record query).
        sales_by_cat = {}
        if categories:
            products = request.env['product.template'].sudo().search([
                ('public_categ_ids', 'in', categories.ids),
                ('sale_ok', '=', True),
            ] + _company_domain())
            # Map each product's sales onto every (top-level) category it belongs to.
            top_ids = set(categories.ids)
            for prod in products:
                for cat in prod.public_categ_ids:
                    # Walk up to the top-level ancestor we list on the homepage.
                    node = cat
                    while node and node.id not in top_ids and node.parent_id:
                        node = node.parent_id
                    if node and node.id in top_ids:
                        sales_by_cat[node.id] = sales_by_cat.get(node.id, 0) + prod.sales_count
        cats_best = categories.sorted(
            key=lambda c: sales_by_cat.get(c.id, 0), reverse=True
        )

        # ── Homepage product rows ────────────────────────────────────
        country_id = request.session.get(_LOCATION_SESSION_KEY)
        # Only list products that actually have an image (native uploads or
        # downloaded external images both land in image_1920).
        pub_products = request.env['product.template'].sudo().search([
            ('sale_ok', '=', True), ('website_published', '=', True),
            ('image_1920', '!=', False),
        ] + _company_domain())
        if country_id:
            pub_products = pub_products.filtered(
                lambda p: not p.available_country_ids
                or country_id in p.available_country_ids.ids
            )

        row_limit = 6  # product grid is 6 columns on desktop = one row

        # Trending: sponsored first, then best-selling.
        trending = pub_products.sorted(
            key=lambda p: (p.is_sponsored, p.sales_count), reverse=True
        )[:row_limit]

        # Best Sellers and New Arrivals exclude sponsored products entirely.
        non_sponsored = pub_products.filtered(lambda p: not p.is_sponsored)

        # Best Sellers: highest sales_count.
        best_sellers = non_sponsored.sorted(
            key=lambda p: p.sales_count, reverse=True
        )[:row_limit]
        # New Arrivals: newest products first.
        new_arrivals = non_sponsored.sorted(
            key=lambda p: p.create_date or p.id, reverse=True
        )[:row_limit]

        # ── Featured category rows (admin-selected in Website Settings) ──
        # Each selected category becomes one homepage row after New Arrivals,
        # showing its published products, with View All → /shop?categ=<id>.
        website = request.env['website'].get_current_website()
        featured_categories = []
        featured_cats = website.sudo().aveenix_home_categ_ids
        if featured_cats:
            # Batched queries only (no DB call inside the loop):
            #  1) every category once, to build a parent→descendant-ids map;
            #  2) all published products across the featured subtrees at once.
            all_cats = request.env['product.public.category'].sudo().search([])
            parent_of = {c.id: c.parent_id.id for c in all_cats}
            # For each featured category, collect its own id + all descendants.
            subtree_by_feat = {c.id: {c.id} for c in featured_cats}
            for cid, pid in parent_of.items():
                node = pid
                while node:
                    if node in subtree_by_feat:
                        subtree_by_feat[node].add(cid)
                    node = parent_of.get(node)

            cat_products = request.env['product.template'].sudo().search([
                ('sale_ok', '=', True), ('website_published', '=', True),
                ('image_1920', '!=', False),
                ('public_categ_ids', 'child_of', featured_cats.ids),
            ] + _company_domain())
            for cat in featured_cats:
                subtree_ids = subtree_by_feat.get(cat.id, {cat.id})
                prods = cat_products.filtered(
                    lambda p: bool(set(p.public_categ_ids.ids) & subtree_ids)
                )
                if country_id:
                    prods = prods.filtered(
                        lambda p: not p.available_country_ids
                        or country_id in p.available_country_ids.ids
                    )
                if prods:
                    featured_categories.append({
                        'category': cat,
                        'products': prods.sorted(
                            key=lambda p: p.sales_count, reverse=True
                        )[:row_limit],
                    })

        # Pass 8 categories: desktop shows 7 (the 8th card is hidden via CSS,
        # .av-cat-grid > :nth-child(8){display:none}); mobile re-shows the 8th
        # so the grid is a full 4×2. See theme.css.
        return request.render('aveenix_website.homepage', {
            'categories_best': cats_best[:8],
            'categories_new': cats_new[:8],
            'trending_products': trending,
            'best_seller_products': best_sellers,
            'new_arrival_products': new_arrivals,
            'featured_categories': featured_categories,
        })

    @http.route('/aveenix/home/products', type='jsonrpc', auth='public', website=True, readonly=True)
    def home_products(self, limit=6, **kwargs):
        country_id = request.session.get(_LOCATION_SESSION_KEY)
        products = request.env['product.template'].sudo().search(
            [('sale_ok', '=', True), ('website_published', '=', True),
             ('image_1920', '!=', False)] + _company_domain()
        )
        if not products:
            products = request.env['product.template'].sudo().search(
                [('sale_ok', '=', True), ('image_1920', '!=', False)]
                + _company_domain()
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
        # Keep only top-level categories that actually have a published product
        # somewhere in their subtree. Products usually sit on child categories,
        # so credit each published product to the TOP-LEVEL ancestor of every
        # category it belongs to (same walk as /categories).
        published_templates = request.env['product.template'].sudo().search([
            ('website_published', '=', True),
            ('public_categ_ids', '!=', False),
        ] + _company_domain())
        non_empty_top_ids = set()
        for tmpl in published_templates:
            for cat in tmpl.public_categ_ids:
                node = cat
                while node.parent_id:
                    node = node.parent_id
                non_empty_top_ids.add(node.id)
        all_categs = all_categs.filtered(lambda c: c.id in non_empty_top_ids)

        extra.update({
            'all_brands': all_brands,
            'selected_brand': brand_id,
            'selected_stock': kwargs.get('stock', ''),
            'all_categs': all_categs,
            'selected_categ': categ_id,
        })

        # The catalog has 33k+ tags; never hand the full set to the template.
        # Keep only the currently-selected tags + the first 5 others. The sidebar
        # search box loads more on demand via /aveenix/shop/tags/search.
        full_tags = values.get('all_tags')
        if full_tags:
            selected_ids = values.get('tags') or []
            selected = full_tags.filtered(lambda t: t.id in selected_ids)
            rest = (full_tags - selected)[:5]
            extra['all_tags'] = selected + rest

        return extra

    def _shop_lookup_products(self, options, post, search, website):
        fuzzy_search_term, product_count, search_result = super()._shop_lookup_products(
            options, post, search, website
        )

        if not search_result:
            return fuzzy_search_term, product_count, search_result

        # Resolve all active filters once before touching records.
        country_id = request.session.get(_LOCATION_SESSION_KEY)

        categ_id = post.get('categ')
        try:
            categ_id = int(categ_id) if categ_id else 0
        except (TypeError, ValueError):
            categ_id = 0
        child_categ_ids = set()
        if categ_id:
            child_categ_ids = set(
                request.env['product.public.category'].sudo()
                .search([('id', 'child_of', categ_id)]).ids
            )

        brand_id = post.get('brand')
        try:
            brand_id = int(brand_id) if brand_id else 0
        except (TypeError, ValueError):
            brand_id = 0

        stock = post.get('stock', '')

        # No custom filters active — skip prefetch entirely.
        if not country_id and not child_categ_ids and not brand_id and not stock:
            return fuzzy_search_term, product_count, search_result

        # Prefetch only the fields actually needed in one batch query each,
        # instead of the ORM lazy-loading them one record at a time (N queries).
        fields_to_prefetch = []
        if country_id:
            fields_to_prefetch.append('available_country_ids')
        if child_categ_ids:
            fields_to_prefetch.append('public_categ_ids')
        if brand_id:
            fields_to_prefetch.append('product_brand_id')
        if stock == 'instock':
            fields_to_prefetch.append('virtual_available')
        elif stock == 'onsale':
            fields_to_prefetch.extend(['compare_list_price', 'list_price'])

        search_result.read(fields_to_prefetch)

        # Apply filters — all field data already in cache, no further DB hits.
        if country_id:
            search_result = search_result.filtered(
                lambda p: not p.available_country_ids
                or country_id in p.available_country_ids.ids
            )

        if child_categ_ids:
            search_result = search_result.filtered(
                lambda p: bool(set(p.public_categ_ids.ids) & child_categ_ids)
            )

        if brand_id:
            search_result = search_result.filtered(
                lambda p: p.product_brand_id.id == brand_id
            )

        if stock == 'instock':
            search_result = search_result.filtered(lambda p: p.virtual_available > 0)
        elif stock == 'onsale':
            search_result = search_result.filtered(
                lambda p: p.compare_list_price and p.compare_list_price > p.list_price
            )

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
                    ] + _company_domain())
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
            [('id', 'in', id_list)] + _company_domain(), limit=50,
        )
        result = request.env['product.template'].sudo().search_read(
            [('id', 'in', id_list)] + _company_domain(),
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
        # Products are usually assigned to child categories (e.g. "Rings" under
        # "Jewelry & Watches"), so we credit each product to the TOP-LEVEL
        # ancestor of every category it belongs to. This way a top-level category
        # shows an accurate count even when all its products live in sub-categories.
        count_map = {}
        for tmpl in published_templates:
            top_ancestors = set()
            for cat in tmpl.public_categ_ids:
                node = cat
                while node.parent_id:
                    node = node.parent_id
                top_ancestors.add(node.id)
            for top_id in top_ancestors:
                count_map[top_id] = count_map.get(top_id, 0) + 1
        # Show every top-level category (directory style); counts come from the
        # ancestor walk above (0 when the subtree has no published products yet).
        categories = request.env['product.public.category'].sudo().search(
            [('parent_id', '=', False)], order='name asc',
        )
        # Show only top-level categories with at least one published product in
        # their subtree; count_map (built above) holds the per-top-level counts.
        categories = categories.filtered(lambda c: count_map.get(c.id, 0) > 0)
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
        return request.render('aveenix_website.notifications_page', {
            'is_public': request.env.user._is_public(),
        })

    @http.route('/aveenix/notifications/count', type='jsonrpc', auth='user',
                website=True, readonly=True)
    def notifications_count(self, **kwargs):
        return {'count': request.env.user.partner_id._get_needaction_count()}

    @http.route('/aveenix/notifications/mark_read', type='jsonrpc', auth='user',
                website=True)
    def notifications_mark_read(self, message_ids=None, all=False, **kwargs):
        if all:
            messages = request.env['mail.message'].search([
                ('needaction', '=', True),
            ])
        elif message_ids:
            messages = request.env['mail.message'].browse(
                [int(i) for i in message_ids]
            )
        else:
            messages = request.env['mail.message']
        messages.set_message_done()
        return {'ok': True}

    @http.route('/contactus', type='http', auth='public', website=True)
    def contact_us_page(self, **kwargs):
        return request.render('aveenix_website.contact_us_page', {})

    @http.route('/privacy', type='http', auth='public', website=True)
    def privacy_policy_page(self, **kwargs):
        return request.render('aveenix_website.privacy_policy_page', {})

    @http.route('/about', type='http', auth='public', website=True)
    def about_us_page(self, **kwargs):
        return request.render('aveenix_website.about_us_page', {})

    # ── Product review submit (logged-in users only) ──────────────
    @http.route('/shop/product/<int:product_template_id>/review',
                type='http', auth='public', website=True, methods=['POST'],
                csrf=True)
    def aveenix_submit_review(self, product_template_id, rating=None, comment=None, **kwargs):
        product = request.env['product.template'].sudo().browse(product_template_id)
        if not product.exists() or not product.website_published:
            return request.redirect('/shop')

        redirect_url = product.website_url + '#av-reviews'

        # Logged-in gate: only authenticated, non-public users may review.
        if request.env.user._is_public():
            return request.redirect('/web/login?redirect=%s' % redirect_url)

        try:
            rating_value = float(rating or 0)
        except (TypeError, ValueError):
            rating_value = 0.0
        comment = (comment or '').strip()
        if rating_value < 1 or rating_value > 5 or not comment:
            return request.redirect(redirect_url)

        # message_post creates the linked rating.rating because product.template
        # inherits the rating.mixin; this also feeds rating_avg / rating_count.
        # sudo(): public-model access is restricted, but we already enforced the
        # logged-in check above and post as the real user's partner.
        product.sudo().message_post(
            body=comment,
            author_id=request.env.user.partner_id.id,
            rating_value=rating_value,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )
        return request.redirect(redirect_url)

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

    # ── Shop tag filter search ────────────────────────────────────

    @http.route('/aveenix/shop/tags/search', type='jsonrpc', auth='public', website=True)
    def aveenix_shop_tags_search(self, query='', limit=20, selected=None, **kw):
        """Search customer-visible product tags for the shop sidebar filter.

        Returns a small list of matching tags so the sidebar never has to render
        the full (33k+) tag set. `selected` are tag ids currently applied via the
        URL — they're returned too so their checked state survives a search.
        """
        Tag = request.env['product.tag'].sudo()
        base_domain = [
            ('visible_to_customers', '=', True),
            '|',
            ('product_template_ids.is_published', '=', True),
            ('product_ids.is_published', '=', True),
        ]
        try:
            limit = max(1, min(int(limit), 50))
        except (TypeError, ValueError):
            limit = 20

        domain = list(base_domain)
        query = (query or '').strip()
        if query:
            domain.append(('name', 'ilike', query))

        tags = Tag.search_fetch(domain, ['name'], limit=limit, order='name')

        # Always include the currently-selected tags so their checkboxes stay
        # checked even if they fall outside the search results.
        selected_ids = [int(s) for s in (selected or []) if str(s).isdigit()]
        if selected_ids:
            missing = [i for i in selected_ids if i not in tags.ids]
            if missing:
                tags |= Tag.search_fetch(
                    [('id', 'in', missing)] + base_domain, ['name'])

        return {
            'tags': [{'id': t.id, 'name': t.name} for t in tags],
            'selected': selected_ids,
        }

    # ── Affiliate cart ────────────────────────────────────────────

    @http.route('/aveenix/affiliate/cart/add', type='jsonrpc', auth='public', website=True)
    def affiliate_cart_add(self, product_id=None, **kw):
        """Save an affiliate product to the visitor's affiliate cart (not the Odoo cart)."""
        if not product_id:
            return {'ok': False, 'error': 'missing product_id'}
        product = request.env['product.template'].sudo().browse(int(product_id))
        if not product.exists() or product.aveenix_product_type != 'affiliate':
            return {'ok': False, 'error': 'invalid product'}
        user = request.env.user
        # sudo() required: public users have no model access; we gate on session id.
        line = request.env['affiliate.cart.line'].sudo()._get_or_create(
            product, request.session.sid, user
        )
        # Line payload shaped for the native website_sale cart notification, so
        # an affiliate save shows the SAME popup as a real add-to-cart (without
        # ever touching the Odoo cart).
        currency = request.env.company.currency_id
        return {
            'ok': True,
            'line_id': line.id,
            'notification': {
                'lines': [{
                    'id': line.id,
                    'image_url': '/web/image/product.template/%s/image_128' % product.id,
                    'quantity': 1,
                    'name': product.name,
                    'price_total': product.list_price,
                }],
                'currency_id': currency.id,
            },
        }

    @http.route('/aveenix/affiliate/cart/remove', type='jsonrpc', auth='public', website=True)
    def affiliate_cart_remove(self, line_id=None, **kw):
        """Remove a line from the visitor's affiliate cart."""
        if not line_id:
            return {'ok': False}
        user = request.env.user
        # sudo() required: public users have no model access.
        lines = request.env['affiliate.cart.line'].sudo()._for_session(
            request.session.sid, user
        )
        line = lines.filtered(lambda l: l.id == int(line_id))
        if line:
            line.unlink()
        return {'ok': True}

    @http.route('/aveenix/affiliate/cart', type='http', auth='public', website=True, sitemap=False)
    def affiliate_cart_page(self, **kw):
        """Render the cart page with affiliate lines injected into the template context."""
        user = request.env.user
        # sudo() required: public users have no model access.
        affiliate_lines = request.env['affiliate.cart.line'].sudo()._for_session(
            request.session.sid, user
        )
        # Delegate to the standard cart controller but with extra context.
        response = super().cart(**kw)
        if hasattr(response, 'qcontext'):
            response.qcontext['affiliate_cart_lines'] = affiliate_lines
        return response

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

    @http.route('/aveenix/product_image/<int:product_id>', type='http',
                auth='public', website=True, sitemap=False)
    def product_external_image(self, product_id, index=0, **kw):
        """Redirect to a product's external image URL (by index). Lets an
        <img src> point here and land on the external CDN image."""
        product = request.env['product.template'].sudo().browse(product_id)
        urls = product.exists() and product._get_external_image_list() or []
        try:
            idx = int(index)
        except (TypeError, ValueError):
            idx = 0
        if urls and 0 <= idx < len(urls):
            return request.redirect(urls[idx], local=False)
        # Fallback to Odoo's own image (or its placeholder).
        return request.redirect('/web/image/product.template/%s/image_512' % product_id)

    @http.route('/aveenix/product_images', type='jsonrpc', auth='public',
                website=True, readonly=True)
    def product_external_images(self, ids=None, **kw):
        """Return {product_id: [external image urls]} for the given templates."""
        if not ids:
            return {}
        try:
            id_list = [int(i) for i in ids]
        except (TypeError, ValueError):
            return {}
        products = request.env['product.template'].sudo().browse(id_list).exists()
        return {
            str(p.id): p._get_external_image_list()
            for p in products if p.external_image_urls
        }

    @http.route('/aveenix/variant_images', type='jsonrpc', auth='public',
                website=True, readonly=True)
    def variant_external_images(self, ids=None, **kw):
        """Return {product.product id: [external image urls]} by resolving each
        variant to its template. Used where the page renders product.product
        images (e.g. the cart line / order summary)."""
        if not ids:
            return {}
        try:
            id_list = [int(i) for i in ids]
        except (TypeError, ValueError):
            return {}
        variants = request.env['product.product'].sudo().browse(id_list).exists()
        return {
            str(v.id): v.product_tmpl_id._get_external_image_list()
            for v in variants if v.product_tmpl_id.external_image_urls
        }


class AveenixCart(Cart):

    def add_to_cart(self, product_template_id, product_id, **kwargs):
        tmpl = request.env['product.template'].sudo().browse(product_template_id).exists()
        if tmpl and tmpl.aveenix_product_type == 'affiliate':
            user = request.env.user
            request.env['affiliate.cart.line'].sudo()._get_or_create(
                tmpl, request.session.sid, user
            )
            order_sudo = request.cart
            return {
                'cart_quantity': order_sudo.cart_quantity if order_sudo else 0,
                'notification_info': {'warning': ''},
                'quantity': 0,
                'tracking_info': [],
            }
        return super().add_to_cart(product_template_id, product_id, **kwargs)

    def _affiliate_lines(self):
        # sudo() required: public users have no model access; scoped by session.
        user = request.env.user
        return request.env['affiliate.cart.line'].sudo()._for_session(
            request.session.sid, user
        )

    def _cart_values(self, **post):
        values = super()._cart_values(**post)
        values['affiliate_cart_lines'] = self._affiliate_lines()
        return values

    def _prepare_checkout_page_values(self, order_sudo, **kwargs):
        values = super()._prepare_checkout_page_values(order_sudo, **kwargs)
        values['affiliate_cart_lines'] = self._affiliate_lines()
        return values

    def _prepare_address_form_values(self, *args, **kwargs):
        values = super()._prepare_address_form_values(*args, **kwargs)
        values['affiliate_cart_lines'] = self._affiliate_lines()
        return values

    def _get_shop_payment_values(self, order, **kwargs):
        values = super()._get_shop_payment_values(order, **kwargs)
        values['affiliate_cart_lines'] = self._affiliate_lines()
        return values
