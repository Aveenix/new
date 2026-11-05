from odoo import _, http, tools
from odoo.exceptions import UserError
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal

from ..models.connect_business import WEEKDAYS
from .main import parse_listing_details, read_image

_MAX_PHOTOS = 12


class ConnectPortal(CustomerPortal):
    """My Account > Connect Listings: owners update their own listings.

    Everything runs as the owner, so the record rules
    (security/connect_security.xml) limit them to their listings and
    connect.business.write to the fields an owner may change."""

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'connect_listing_count' in counters:
            Business = request.env['connect.business']
            values['connect_listing_count'] = Business.search_count(
                [('owner_id', '=', request.env.user.id)]) if Business.has_access('read') else 0
        return values

    def _owned_business(self, business_id):
        return request.env['connect.business'].search(
            [('id', '=', business_id), ('owner_id', '=', request.env.user.id)])

    @http.route('/my/connect', type='http', auth='user', website=True)
    def portal_my_connect(self, **kw):
        values = self._prepare_portal_layout_values()
        values.update({
            'listings': request.env['connect.business'].search([('owner_id', '=', request.env.user.id)]),
            'page_name': 'connect_listings',
        })
        return request.render('aveenix_connect.portal_my_connect', values)

    def _edit_values(self, business, form=None, errors=None, saved=False):
        values = self._prepare_portal_layout_values()
        hours = {h.dayofweek: h for h in business.hours_ids}
        values.update({
            'business': business,
            'form': form or {},
            'errors': errors or {},
            'saved': saved,
            'weekdays': WEEKDAYS,
            'hours': {day: (h.hour_from, h.hour_to) for day, h in hours.items()},
            'format_hour': request.env['connect.business.hours']._format_hour,
            'description_text': tools.html2plaintext(business.description or ''),
            'countries': request.env['res.country'].sudo().search([]),
            'page_name': 'connect_listing',
        })
        return values

    @http.route('/my/connect/<int:business_id>', type='http', auth='user', website=True, methods=['GET'])
    def portal_my_connect_listing(self, business_id, saved=None, **kw):
        business = self._owned_business(business_id)
        if not business:
            return request.redirect('/my/connect')
        return request.render('aveenix_connect.portal_my_connect_listing',
                              self._edit_values(business, saved=bool(saved)))

    @http.route('/my/connect/<int:business_id>', type='http', auth='user', website=True,
                methods=['POST'], sitemap=False)
    def portal_my_connect_listing_save(self, business_id, **post):
        business = self._owned_business(business_id)
        if not business:
            return request.redirect('/my/connect')

        errors = {}
        vals = parse_listing_details(post, errors)
        # The form edits plain text; leave rich text from the team alone
        # unless the owner actually changed it.
        posted = (post.get('description') or '').replace('\r\n', '\n').strip()
        if posted == tools.html2plaintext(business.description or '').strip():
            vals.pop('description', None)
        elif 'description' not in vals:
            vals['description'] = False
        hours = self._parse_hours(post, errors)
        files = request.httprequest.files
        logo = read_image(files.get('logo'), errors, 'logo')
        photos = [read_image(f, errors, 'photos') for f in files.getlist('photos')]
        remove_ids = {int(i) for i in request.httprequest.form.getlist('remove_photo_ids') if i.isdigit()}
        kept = business.image_ids.filtered(lambda p: p.id not in remove_ids)
        if len(kept) + len(photos) > _MAX_PHOTOS:
            errors['photos'] = _('A listing can show up to %s photos.', _MAX_PHOTOS)
        if errors:
            return request.render('aveenix_connect.portal_my_connect_listing',
                                  self._edit_values(business, post, errors))

        if logo:
            vals['image_1920'] = logo
        try:
            with request.env.cr.savepoint():
                business.write(vals)
                business.hours_ids.unlink()
                request.env['connect.business.hours'].create([
                    {'business_id': business.id, 'dayofweek': day, 'hour_from': start, 'hour_to': end}
                    for day, (start, end) in hours.items()
                ])
                (business.image_ids - kept).unlink()
                request.env['connect.business.image'].create([
                    {'business_id': business.id, 'image_1920': photo} for photo in photos if photo
                ])
        except UserError as e:  # also AccessError / ValidationError, e.g. an unreadable image
            return request.render('aveenix_connect.portal_my_connect_listing',
                                  self._edit_values(business, post, {'save': str(e)}))
        return request.redirect('/my/connect/%s?saved=1' % business.id)

    def _parse_hours(self, post, errors):
        """{day: (opens, closes)} from the HH:MM inputs; closed days are left out."""
        def to_float(value):
            hours, _sep, minutes = (value or '').partition(':')
            if not (hours.isdigit() and minutes.isdigit()):
                return None
            return int(hours) + int(minutes) / 60

        hours = {}
        for day, label in WEEKDAYS:
            if post.get('closed_%s' % day):
                continue
            start, end = to_float(post.get('from_%s' % day)), to_float(post.get('to_%s' % day))
            if start is None and end is None:
                continue
            if start is None or end is None or not 0 <= start < end <= 24:
                errors['hours'] = _('Check the hours for %s: opening must come before closing.', label)
                continue
            hours[day] = (start, end)
        return hours
