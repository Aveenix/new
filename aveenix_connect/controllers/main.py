import base64
from urllib.parse import quote, urlencode

from odoo import _, fields, http, tools
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.http import request

from ..models.connect_business import WEEKDAYS
from ..models.connect_nzbn_client import NZBN_RE
from ..models.connect_report import REPORT_REASONS

# Listings per results page.
_PPG = 12
# Visitor lists of listings, kept in the session: compare always, favourites
# until the visitor logs in (then on their account, see _visitor_list).
_LIST_SESSION_KEYS = {'fav': 'connect_fav_ids', 'compare': 'connect_compare_ids'}
MAX_COMPARE = 4
# Caps on what a visitor can post into text fields.
_MAX_TEXT = 255
_MAX_NOTES = 4000
_MAX_CATEGORIES = 3
_MAX_IMAGE_BYTES = 5 * 1024 * 1024


# ── Form helpers (also used by the owner portal) ─────────────────────────

def parse_listing_details(post, errors):
    """Website form → the listing details an owner may set. Everything is
    posted by a visitor, so each value is capped or checked, never
    trusted."""
    def text(name, limit=_MAX_TEXT):
        return (post.get(name) or '').strip()[:limit]

    vals = {
        'street': text('street'),
        'city': text('city'),
        'zip': text('zip', 32),
        'phone': text('phone', 64),
        'business_url': text('business_url'),
    }
    email = (post.get('email') or '').strip()
    vals['email'] = tools.email_normalize(email) or False
    if email and not vals['email']:
        errors['email'] = _('Enter a valid email address.')
    if vals['business_url'] and not vals['business_url'].startswith(('http://', 'https://')):
        vals['business_url'] = 'https://' + vals['business_url']
    country = post.get('country_id') or ''
    vals['country_id'] = int(country) if country.isdigit() and \
        request.env['res.country'].sudo().browse(int(country)).exists() else False
    if not vals['city']:
        errors['city'] = _('Enter the city.')
    description = text('description', _MAX_NOTES)
    if description:
        vals['description'] = tools.plaintext2html(description)
    vals['services'] = text('services', _MAX_NOTES).replace('\r\n', '\n') or False
    vals['service_areas'] = text('service_areas') or False
    return vals


def read_contact(post):
    """(name, normalized email, phone) a visitor typed into a contact form."""
    return (
        (post.get('name') or '').strip()[:_MAX_TEXT],
        tools.email_normalize(post.get('email') or ''),
        (post.get('phone') or '').strip()[:64],
    )


def recaptcha_ok(post):
    return request.env['ir.http']._verify_recaptcha_v2(post.get('g-recaptcha-response'))


def read_image(upload, errors, key):
    """An uploaded file as base64 for an Image field, or None."""
    if not upload or not upload.filename:
        return None
    data = upload.read(_MAX_IMAGE_BYTES + 1)
    if len(data) > _MAX_IMAGE_BYTES:
        errors[key] = _('Images must be 5 MB or smaller.')
        return None
    if not (upload.mimetype or '').startswith('image/'):
        errors[key] = _('Upload a JPG, PNG or WebP image.')
        return None
    return base64.b64encode(data)


class AveenixConnect(http.Controller):

    def _connect_values(self, **values):
        """Every Connect page renders inside the Aveenix layout as a sister
        site: av_site_home makes the shared header hide the shop logo word,
        search and nav, and views/layout.xml adds the Connect ones."""
        favourites = self._visitor_list('fav')
        compare = self._visitor_list('compare')
        path = request.httprequest.full_path.rstrip('?')
        values.update({
            'is_connect_page': True,
            'av_site_home': '/connect',
            'connect_nav_categories': request.env['connect.category'].search(
                [('parent_id', '=', False)], limit=8),
            # Header Favourites / Compare counts and the heart / compare
            # buttons' state; Login brings the visitor back to this page.
            'connect_fav_ids': set(favourites.ids),
            'connect_compare_ids': set(compare.ids),
            'connect_login_url': '/web/login?' + urlencode({'redirect': path}),
        })
        return values

    def _visitor_list(self, kind):
        """The listings in the visitor's favourites ('fav') or compare list,
        as sudo for rendering, in the order added. Listings they can no
        longer see (unpublished, deleted) drop out."""
        user = request.env.user
        key = _LIST_SESSION_KEYS[kind]
        ids = [i for i in request.session.get(key) or [] if isinstance(i, int)]
        if kind == 'fav' and not user._is_public():
            if ids:
                # Favourites saved before logging in move to the account.
                request.session.pop(key)
                user.sudo().connect_favourite_ids = [
                    Command.link(b.id) for b in request.env['connect.business'].search([('id', 'in', ids)])]
            ids = user.sudo().connect_favourite_ids.ids
        visible = request.env['connect.business'].search([('id', 'in', ids)])
        return visible.sudo().sorted(lambda b: ids.index(b.id))

    def _visible_business(self, business):
        """The listing, as sudo for rendering, if the record rules let the
        visitor see it (published, their own, or the Connect team's)."""
        if not business.exists() or not business.has_access('read'):
            raise request.not_found()
        return business.sudo()

    # ── Home / search ────────────────────────────────────────────────────

    @http.route('/connect', type='http', auth='public', website=True)
    def connect_home(self, **kwargs):
        Business = request.env['connect.business'].sudo()
        published = [('is_published', '=', True)]
        cities = Business._read_group(
            published + [('city', '!=', False)], ['city'], ['__count'],
            order='__count desc', limit=12,
        )
        Category = request.env['connect.category']
        return request.render('aveenix_connect.connect_home', self._connect_values(
            active_nav='home',
            categories=Category.search([('parent_id', '=', False)]),
            hero_categories=Category.search([('parent_id', '=', False), ('image_1920', '!=', False)]),
            featured=Business.search(published + [('is_featured', '=', True)], limit=8),
            recent=Business.search(published, order='create_date desc', limit=8),
            latest_reviews=self._latest_reviews(6),
            cities=cities,
        ))

    def _latest_reviews(self, limit):
        """[(rating, business)] of the newest written reviews of published
        listings, for the home page."""
        ratings = request.env['rating.rating'].sudo().search([
            ('res_model', '=', 'connect.business'),
            ('consumed', '=', True),
            ('rating', '>', 0),
            ('feedback', '!=', False),
        ], order='write_date desc', limit=limit * 5)
        businesses = request.env['connect.business'].sudo().browse(ratings.mapped('res_id')).exists()
        published = {b.id: b for b in businesses if b.is_published}
        return [(r, published[r.res_id]) for r in ratings if r.res_id in published][:limit]

    @http.route(['/connect/search', '/connect/search/page/<int:page>'],
                type='http', auth='public', website=True, sitemap=False)
    def connect_search(self, page=1, what='', where='', rating=None, **kwargs):
        return self._results('/connect/search', page, what, where, rating)

    @http.route(['/connect/category/<model("connect.category"):category>',
                 '/connect/category/<model("connect.category"):category>/page/<int:page>'],
                type='http', auth='public', website=True)
    def connect_category(self, category, page=1, what='', where='', rating=None, **kwargs):
        if not category.exists() or not category.active:
            raise request.not_found()
        return self._results('/connect/category/%s' % request.env['ir.http']._slug(category),
                             page, what, where, rating, category=category)

    def _results(self, url, page, what, where, rating, category=None):
        what = (what or '').strip()[:_MAX_TEXT]
        where = (where or '').strip()[:_MAX_TEXT]
        try:
            min_rating = min(max(int(rating or 0), 0), 5)
        except ValueError:
            min_rating = 0

        domain = [('is_published', '=', True)]
        if what:
            domain += ['|', '|', '|', ('name', 'ilike', what), ('description', 'ilike', what),
                       ('category_ids.name', 'ilike', what), ('services', 'ilike', what)]
        if where:
            domain += ['|', '|', '|', '|', ('city', 'ilike', where), ('zip', 'ilike', where),
                       ('state_id.name', 'ilike', where), ('street', 'ilike', where),
                       ('service_areas', 'ilike', where)]
        if category:
            domain += [('category_ids', 'child_of', category.id)]
        if min_rating:
            domain += [('rating_avg', '>=', min_rating)]

        Business = request.env['connect.business'].sudo()
        total = Business.search_count(domain)
        url_args = {k: v for k, v in (('what', what), ('where', where), ('rating', min_rating)) if v}
        pager = request.website.pager(url=url, total=total, page=page, step=_PPG, scope=5, url_args=url_args)
        return request.render('aveenix_connect.connect_results', self._connect_values(
            businesses=Business.search(domain, limit=_PPG, offset=pager['offset']),
            pager=pager,
            total=total,
            what=what,
            where=where,
            rating=min_rating,
            category=category,
            results_url=url,
            quote_url='/connect/quote?' + urlencode(
                {k: v for k, v in (('category', category.id if category else None), ('where', where)) if v}),
            active_nav=category.id if category else 'search',
        ))

    # ── Business page ────────────────────────────────────────────────────

    @http.route('/connect/business/<model("connect.business"):business>',
                type='http', auth='public', website=True)
    def connect_business(self, business, **kwargs):
        business = self._visible_business(business)
        user = request.env.user
        partner = user.partner_id
        maps_key = request.website.sudo().google_maps_api_key
        reviews = business.rating_ids.filtered(lambda r: r.consumed and r.rating > 0) \
            .sorted('write_date', reverse=True)
        return request.render('aveenix_connect.connect_business', self._connect_values(
            business=business,
            main_object=business,
            reviews=reviews,
            hours=business.hours_ids,
            today=str(fields.Date.context_today(business).weekday()),
            weekdays=WEEKDAYS,
            maps_key=maps_key,
            embed_url=business._google_embed_url(maps_key),
            is_owner=not user._is_public() and business.owner_id == user,
            has_reviewed=not user._is_public() and bool(reviews.filtered(lambda r: r.partner_id == partner)),
            can_review=business._can_review(user),
            jobs=request.env['connect.job'].sudo().search(self._open_jobs_domain(business)),
            report_reasons=REPORT_REASONS,
            recaptcha_key=self._recaptcha_site_key(),
            notice=kwargs.get('notice'),
            active_nav=business.category_ids[:1].id,
        ))

    @staticmethod
    def _open_jobs_domain(business=None):
        """Job ads open for applications, of published listings."""
        domain = [
            ('business_id.is_published', '=', True),
            '|', ('date_closing', '=', False),
            ('date_closing', '>=', fields.Date.context_today(request.env.user)),
        ]
        return domain + [('business_id', '=', business.id)] if business else domain

    @http.route('/connect/business/<int:business_id>/review', type='http', auth='public',
                website=True, methods=['POST'], sitemap=False)
    def connect_review(self, business_id, rating=None, comment=None, **kwargs):
        business = self._visible_business(request.env['connect.business'].browse(business_id))
        back = business.website_url + '#avc-reviews'
        user = request.env.user
        if user._is_public():
            return request.redirect('/web/login?redirect=%s' % quote(back))
        try:
            rating_value = float(rating or 0)
        except ValueError:
            rating_value = 0.0
        comment = (comment or '').strip()[:_MAX_NOTES]
        already = business.rating_ids.filtered(lambda r: r.consumed and r.partner_id == user.partner_id)
        # One review per customer who contacted the business through Aveenix
        # (which also keeps owners from rating their own business).
        if not 1 <= rating_value <= 5 or not comment or already or not business._can_review(user):
            return request.redirect(back)
        # rating.mixin turns a rated message into a rating.rating, which feeds
        # rating_avg / rating_count. `business` is sudo (visitors cannot post
        # on listings); the login check above stands in for that right.
        business.message_post(
            body=comment,
            author_id=user.partner_id.id,
            rating_value=rating_value,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )
        return request.redirect(back)

    # ── Favourites and compare ───────────────────────────────────────────

    @http.route('/connect/list/toggle', type='jsonrpc', auth='public', website=True)
    def connect_list_toggle(self, kind, business_id):
        """Add a listing to, or take it out of, the visitor's favourites or
        compare list. Returns {'active', 'count'}, or {'full': True} when the
        compare list already holds MAX_COMPARE listings."""
        if kind not in _LIST_SESSION_KEYS:
            raise request.not_found()
        business = request.env['connect.business'].browse(int(business_id))
        if not business.exists() or not business.has_access('read'):
            raise request.not_found()
        current = self._visitor_list(kind)
        active = business.id not in current.ids
        if kind == 'compare' and active and len(current) >= MAX_COMPARE:
            return {'active': False, 'full': True, 'count': len(current)}
        user = request.env.user
        if kind == 'fav' and not user._is_public():
            user.sudo().connect_favourite_ids = [
                Command.link(business.id) if active else Command.unlink(business.id)]
        else:
            ids = [i for i in current.ids if i != business.id]
            request.session[_LIST_SESSION_KEYS[kind]] = ids + [business.id] if active else ids
        return {'active': active, 'count': len(current) + (1 if active else -1)}

    @http.route('/connect/favourites', type='http', auth='public', website=True, sitemap=False)
    def connect_favourites(self, **kwargs):
        return request.render('aveenix_connect.connect_favourites', self._connect_values(
            businesses=self._visitor_list('fav'),
            active_nav='favourites',
        ))

    @http.route('/connect/compare', type='http', auth='public', website=True, sitemap=False)
    def connect_compare(self, **kwargs):
        businesses = self._visitor_list('compare')
        return request.render('aveenix_connect.connect_compare', self._connect_values(
            businesses=businesses,
            open_jobs=dict(request.env['connect.job'].sudo()._read_group(
                self._open_jobs_domain() + [('business_id', 'in', businesses.ids)],
                ['business_id'], ['__count'])),
            weekdays=WEEKDAYS,
            max_compare=MAX_COMPARE,
            active_nav='compare',
        ))

    # ── Claiming ─────────────────────────────────────────────────────────

    @http.route('/connect/business/<int:business_id>/claim', type='http', auth='user',
                website=True, methods=['POST'], sitemap=False)
    def connect_claim(self, business_id, method=None, **kwargs):
        """Claim a listing: by a code emailed to the listing's address when it
        has one, else (or when asked) by the team checking the claim."""
        business = self._visible_business(request.env['connect.business'].browse(business_id))
        user = request.env.user
        if business.owner_id or business.claim_user_id:
            return request.redirect(business.website_url)
        if method != 'review' and tools.email_normalize(business.email) and not business._claim_code_locked():
            business._send_claim_code(user)
            return request.redirect('/connect/business/%s/claim/verify' % business.id)
        business._request_claim(user)
        return request.redirect(business.website_url + '?notice=claimed')

    def _claim_verify_values(self, business, error=None):
        return self._connect_values(
            business=business,
            masked_email=business._masked_email(),
            locked=business._claim_code_locked(),
            error=error,
        )

    @http.route('/connect/business/<int:business_id>/claim/verify', type='http', auth='user',
                website=True, sitemap=False, methods=['GET'])
    def connect_claim_verify(self, business_id, **kwargs):
        business = self._visible_business(request.env['connect.business'].browse(business_id))
        if business.owner_id:
            return request.redirect(business.website_url)
        return request.render('aveenix_connect.connect_claim_verify', self._claim_verify_values(business))

    @http.route('/connect/business/<int:business_id>/claim/verify', type='http', auth='user',
                website=True, sitemap=False, methods=['POST'])
    def connect_claim_verify_submit(self, business_id, code=None, **kwargs):
        business = self._visible_business(request.env['connect.business'].browse(business_id))
        if business._check_claim_code(request.env.user, code):
            return request.redirect('/my/connect/%s?claimed=1' % business.id)
        if business.owner_id:
            return request.redirect(business.website_url)
        return request.render('aveenix_connect.connect_claim_verify', self._claim_verify_values(
            business, _('That code is not right or has expired. Check the email, or ask for a new code.')))

    # ── Enquiries, reports ───────────────────────────────────────────────

    @http.route('/connect/business/<int:business_id>/enquiry', type='http', auth='public',
                website=True, methods=['POST'], sitemap=False)
    def connect_enquiry(self, business_id, **post):
        business = self._visible_business(request.env['connect.business'].browse(business_id))
        back = business.website_url + '?notice=%s#avc-enquiry'
        # Enquiries go to the owner, so only claimed listings take them.
        if not business.owner_id:
            return request.redirect(business.website_url)
        # Honeypot: real visitors never see this field, bots fill everything.
        if post.get('website_url'):
            return request.redirect(back % 'sent')
        if not recaptcha_ok(post):
            return request.redirect(back % 'captcha')
        name, email, phone = read_contact(post)
        message = (post.get('message') or '').strip()[:_MAX_NOTES]
        if not (name and email and message):
            return request.redirect(back % 'invalid')
        user = request.env.user
        request.env['connect.lead'].sudo().create({
            'kind': 'enquiry',
            'business_ids': [(6, 0, business.ids)],
            'partner_id': False if user._is_public() else user.partner_id.id,
            'contact_name': name,
            'email': email,
            'phone': phone,
            'message': message,
        })._notify_businesses()
        return request.redirect(back % 'sent')

    @http.route('/connect/business/<int:business_id>/report', type='http', auth='public',
                website=True, methods=['POST'], sitemap=False)
    def connect_report(self, business_id, **post):
        business = self._visible_business(request.env['connect.business'].browse(business_id))
        back = business.website_url + '?notice=%s#avc-report'
        if post.get('website_url'):
            return request.redirect(back % 'reported')
        if not recaptcha_ok(post):
            return request.redirect(back % 'captcha')
        reason = post.get('reason')
        details = (post.get('details') or '').strip()[:_MAX_NOTES]
        if reason not in dict(REPORT_REASONS) or (reason == 'other' and not details):
            return request.redirect(back % 'report_invalid')
        name, email, _phone = read_contact(post)
        user = request.env.user
        request.env['connect.report'].sudo().create({
            'business_id': business.id,
            'reason': reason,
            'details': details,
            'contact_name': name,
            'email': email,
            'partner_id': False if user._is_public() else user.partner_id.id,
        })
        return request.redirect(back % 'reported')

    # ── Quotes ───────────────────────────────────────────────────────────

    def _quote_values(self, form, errors=None):
        return self._connect_values(
            form=form,
            errors=errors or {},
            quote_categories=request.env['connect.category'].search([]),
            recaptcha_key=self._recaptcha_site_key(),
            active_nav='quote',
        )

    @http.route('/connect/quote', type='http', auth='public', website=True, methods=['GET'])
    def connect_quote(self, category=None, where=None, **kwargs):
        user = request.env.user
        form = {
            'category_id': category if (category or '').isdigit() else '',
            'where': (where or '')[:_MAX_TEXT],
        }
        if not user._is_public():
            form.update(name=user.name, email=user.email or '', phone=user.phone or '')
        return request.render('aveenix_connect.connect_quote', self._quote_values(form))

    @http.route('/connect/quote', type='http', auth='public', website=True, methods=['POST'], sitemap=False)
    def connect_quote_submit(self, **post):
        if post.get('website_url'):
            return request.redirect('/connect/quote/thanks')
        if not recaptcha_ok(post):
            return request.render('aveenix_connect.connect_quote', self._quote_values(
                post, {'captcha': _('Please confirm you are not a robot and try again.')}))
        errors = {}
        category_id = post.get('category_id') or ''
        category = request.env['connect.category'].browse(int(category_id)).exists() \
            if category_id.isdigit() else request.env['connect.category']
        where = (post.get('where') or '').strip()[:_MAX_TEXT]
        message = (post.get('message') or '').strip()[:_MAX_NOTES]
        name, email, phone = read_contact(post)
        if not category:
            errors['category_id'] = _('Choose what kind of business you need.')
        if not where:
            errors['where'] = _('Enter your city, suburb or postcode.')
        if not message:
            errors['message'] = _('Describe the job.')
        if not name:
            errors['name'] = _('Enter your name.')
        if not email:
            errors['email'] = _('Enter a valid email address.')
        if errors:
            return request.render('aveenix_connect.connect_quote', self._quote_values(post, errors))

        Lead = request.env['connect.lead'].sudo()
        user = request.env.user
        lead = Lead.create({
            'kind': 'quote',
            'business_ids': [(6, 0, Lead._match_businesses(category, where).ids)],
            'partner_id': False if user._is_public() else user.partner_id.id,
            'contact_name': name,
            'email': email,
            'phone': phone,
            'message': message,
            'category_id': category.id,
            'location': where,
        })
        lead._notify_businesses()
        request.session['connect_quote_matches'] = len(lead.business_ids)
        return request.redirect('/connect/quote/thanks')

    @http.route('/connect/quote/thanks', type='http', auth='public', website=True, sitemap=False)
    def connect_quote_thanks(self, **kwargs):
        return request.render('aveenix_connect.connect_quote_thanks', self._connect_values(
            matches=request.session.pop('connect_quote_matches', None),
            active_nav='quote',
        ))

    def _recaptcha_site_key(self):
        get_param = request.env['ir.config_parameter'].sudo().get_param
        if get_param('aveenix_website.recaptcha_v2_enabled') != 'True':
            return False
        return get_param('aveenix_website.recaptcha_v2_site_key') or False

    # ── List your business ───────────────────────────────────────────────

    def _add_values(self, form, errors=None):
        return self._connect_values(
            form=form,
            errors=errors or {},
            all_categories=request.env['connect.category'].search([]),
            countries=request.env['res.country'].sudo().search([]),
            recaptcha_key=self._recaptcha_site_key(),
            nzbn_enabled=request.env['connect.nzbn.client']._is_configured(),
            active_nav='add',
        )

    @http.route('/connect/add', type='http', auth='user', website=True, methods=['GET'])
    def connect_add(self, nzbn=None, **kwargs):
        user = request.env.user
        form = {
            'email': user.email or '',
            'phone': user.phone or '',
            'country_id': str(request.website.company_id.country_id.id or ''),
        }
        errors = {}
        nzbn = (nzbn or '').strip().replace(' ', '')
        if nzbn:
            # Fill the form in from the NZBN register.
            listed = request.env['connect.business'].sudo().search([('nzbn', '=', nzbn)], limit=1)
            if listed.is_published:
                return request.redirect(listed.website_url + '?notice=listed')
            entity = request.env['connect.nzbn.client'].get_entity(nzbn) if not listed else {}
            if listed:
                errors['nzbn'] = _('This business was already submitted and is waiting for approval.')
            elif entity is None:
                errors['nzbn'] = _('The NZBN register is not answering right now; fill the form in yourself.')
            elif not entity:
                errors['nzbn'] = _('We could not find this NZBN on the register.')
            else:
                values = request.env['connect.nzbn.client'].listing_values(entity)
                form.update({k: v for k, v in values.items() if k != 'country_id'})
                if values.get('country_id'):
                    form['country_id'] = str(values['country_id'])
            form['nzbn'] = nzbn if not errors else ''
        return request.render('aveenix_connect.connect_add', self._add_values(form, errors))

    @http.route('/connect/add', type='http', auth='user', website=True, methods=['POST'], sitemap=False)
    def connect_add_submit(self, **post):
        if post.get('website_url'):
            return request.redirect('/connect/add/thanks')
        if not request.env['ir.http']._verify_recaptcha_v2(post.get('g-recaptcha-response')):
            return request.render('aveenix_connect.connect_add', self._add_values(
                post, {'captcha': _('Please confirm you are not a robot and try again.')}))

        errors = {}
        vals = parse_listing_details(post, errors)
        vals['name'] = (post.get('name') or '').strip()[:_MAX_TEXT]
        if not vals['name']:
            errors['name'] = _('Enter the business name.')
        category_ids = [int(c) for c in request.httprequest.form.getlist('category_ids') if c.isdigit()]
        categories = request.env['connect.category'].search([('id', 'in', category_ids)], limit=_MAX_CATEGORIES)
        if not categories:
            errors['category_ids'] = _('Choose at least one category.')
        logo = read_image(request.httprequest.files.get('logo'), errors, 'logo')
        nzbn = (post.get('nzbn') or '').strip()
        if nzbn:
            # Only keep an NZBN the register knows and no listing has yet;
            # the team still checks the listing before it goes live.
            if not NZBN_RE.match(nzbn) \
                    or request.env['connect.business'].sudo().search_count([('nzbn', '=', nzbn)]) \
                    or not request.env['connect.nzbn.client'].get_entity(nzbn):
                nzbn = False
        if errors:
            post['category_ids'] = category_ids
            return request.render('aveenix_connect.connect_add', self._add_values(post, errors))

        user = request.env.user
        vals.update({
            'category_ids': [(6, 0, categories.ids)],
            'owner_id': user.id,
            'nzbn': nzbn or False,
        })
        if logo:
            vals['image_1920'] = logo
        # sudo(): visitors cannot create listings; this one stays unpublished
        # until the Connect team approves it.
        try:
            business = request.env['connect.business'].sudo().create(vals)
        except UserError:  # an image Odoo can't read
            return request.render('aveenix_connect.connect_add', self._add_values(
                post, {'logo': _('This file is not an image we can use.')}))
        business.message_post(
            body=_('Submitted from the website by %s, waiting for approval.', user.name),
            subtype_xmlid='mail.mt_note',
        )
        request.session['connect_listing_name'] = business.name
        return request.redirect('/connect/add/thanks')

    @http.route('/connect/add/thanks', type='http', auth='user', website=True, sitemap=False)
    def connect_add_thanks(self, **kwargs):
        return request.render('aveenix_connect.connect_add_thanks', self._connect_values(
            listing_name=request.session.pop('connect_listing_name', None),
            active_nav='add',
        ))
