import base64
from urllib.parse import quote

from markupsafe import Markup

from odoo import _, fields, http, tools
from odoo.exceptions import UserError
from odoo.http import request

from ..models.connect_business import WEEKDAYS

# Listings per results page.
_PPG = 12
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
    return vals


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
        values.update({
            'is_connect_page': True,
            'av_site_home': '/connect',
            'connect_nav_categories': request.env['connect.category'].search(
                [('parent_id', '=', False)], limit=8),
        })
        return values

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
        return request.render('aveenix_connect.connect_home', self._connect_values(
            active_nav='home',
            categories=request.env['connect.category'].search([('parent_id', '=', False)]),
            featured=Business.search(published + [('is_featured', '=', True)], limit=8),
            recent=Business.search(published, order='create_date desc', limit=8),
            cities=cities,
        ))

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
            domain += ['|', '|', ('name', 'ilike', what), ('description', 'ilike', what),
                       ('category_ids.name', 'ilike', what)]
        if where:
            domain += ['|', '|', '|', ('city', 'ilike', where), ('zip', 'ilike', where),
                       ('state_id.name', 'ilike', where), ('street', 'ilike', where)]
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
            recaptcha_key=self._recaptcha_site_key(),
            notice=kwargs.get('notice'),
            active_nav=business.category_ids[:1].id,
        ))

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
        # One review per visitor, and owners don't rate their own business.
        if not 1 <= rating_value <= 5 or not comment or already or business.owner_id == user:
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

    @http.route('/connect/business/<int:business_id>/claim', type='http', auth='user',
                website=True, methods=['POST'], sitemap=False)
    def connect_claim(self, business_id, **kwargs):
        business = self._visible_business(request.env['connect.business'].browse(business_id))
        if not business.owner_id and not business.claim_user_id:
            business._request_claim(request.env.user)
        return request.redirect(business.website_url + '?notice=claimed')

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
        if not request.env['ir.http']._verify_recaptcha_v2(post.get('g-recaptcha-response')):
            return request.redirect(back % 'captcha')
        name = (post.get('name') or '').strip()[:_MAX_TEXT]
        email = tools.email_normalize(post.get('email') or '')
        phone = (post.get('phone') or '').strip()[:64]
        message = (post.get('message') or '').strip()[:_MAX_NOTES]
        if not (name and email and message):
            return request.redirect(back % 'invalid')
        body = Markup('<p>%s</p>%s') % (
            _('Enquiry from %(name)s (%(contact)s) via Aveenix Connect:',
              name=name, contact=', '.join(filter(None, [email, phone]))),
            tools.plaintext2html(message),
        )
        user = request.env.user
        business.message_post(
            body=body,
            author_id=None if user._is_public() else user.partner_id.id,
            email_from=tools.formataddr((name, email)),
            reply_to=email,
            partner_ids=business.owner_id.partner_id.ids,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )
        return request.redirect(back % 'sent')

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
            active_nav='add',
        )

    @http.route('/connect/add', type='http', auth='user', website=True, methods=['GET'])
    def connect_add(self, **kwargs):
        user = request.env.user
        form = {
            'email': user.email or '',
            'phone': user.phone or '',
            'country_id': str(request.website.company_id.country_id.id or ''),
        }
        return request.render('aveenix_connect.connect_add', self._add_values(form))

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
        if errors:
            post['category_ids'] = category_ids
            return request.render('aveenix_connect.connect_add', self._add_values(post, errors))

        user = request.env.user
        vals.update({
            'category_ids': [(6, 0, categories.ids)],
            'owner_id': user.id,
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
