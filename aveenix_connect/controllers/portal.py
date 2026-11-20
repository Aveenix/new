from odoo import _, fields, http, tools
from odoo.exceptions import UserError
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal

from ..models.connect_business import WEEKDAYS
from ..models.connect_job import EMPLOYMENT_TYPES
from .main import _MAX_NOTES, _MAX_TEXT, parse_listing_details, read_image

_MAX_PHOTOS = 12
_MAX_LICENCES = 10


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

    def _edit_values(self, business, form=None, errors=None, saved=False, claimed=False):
        values = self._prepare_portal_layout_values()
        hours = {h.dayofweek: h for h in business.hours_ids}
        values.update({
            'business': business,
            'form': form or {},
            'errors': errors or {},
            'saved': saved,
            'claimed': claimed,
            # Licences are the team's to check: owners see and add them
            # through this controller only, never by direct access.
            'licences': business.sudo().licence_ids,
            'licence_types': request.env['connect.licence.type'].search([]),
            'weekdays': WEEKDAYS,
            'hours': {day: (h.hour_from, h.hour_to) for day, h in hours.items()},
            'format_hour': request.env['connect.business.hours']._format_hour,
            'description_text': tools.html2plaintext(business.description or ''),
            'countries': request.env['res.country'].sudo().search([]),
            'page_name': 'connect_listing',
        })
        return values

    @http.route('/my/connect/<int:business_id>', type='http', auth='user', website=True, methods=['GET'])
    def portal_my_connect_listing(self, business_id, saved=None, claimed=None, **kw):
        business = self._owned_business(business_id)
        if not business:
            return request.redirect('/my/connect')
        return request.render('aveenix_connect.portal_my_connect_listing',
                              self._edit_values(business, saved=bool(saved), claimed=bool(claimed)))

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
        licences = business.sudo().licence_ids
        remove_licence_ids = {int(i) for i in request.httprequest.form.getlist('remove_licence_ids') if i.isdigit()}
        kept_licences = licences.filtered(lambda lic: lic.id not in remove_licence_ids)
        new_licence = self._parse_licence(post, kept_licences, errors)
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
                (licences - kept_licences).unlink()
                if new_licence:
                    # A new licence always waits for the team's check.
                    request.env['connect.licence'].sudo().create(dict(new_licence, business_id=business.id))
        except UserError as e:  # also AccessError / ValidationError, e.g. an unreadable image
            return request.render('aveenix_connect.portal_my_connect_listing',
                                  self._edit_values(business, post, {'save': str(e)}))
        return request.redirect('/my/connect/%s?saved=1' % business.id)

    def _parse_licence(self, post, kept_licences, errors):
        """{'type_id', 'number'} of the licence the owner adds, or None."""
        type_id = post.get('licence_type_id') or ''
        number = (post.get('licence_number') or '').strip()[:64]
        if not type_id and not number:
            return None
        licence_type = request.env['connect.licence.type'].browse(int(type_id)).exists() \
            if type_id.isdigit() else None
        if not licence_type or not number:
            errors['licence'] = _('Choose the licence and enter its number.')
        elif licence_type in kept_licences.type_id:
            errors['licence'] = _('This listing already has a %s licence; remove it first to change the number.',
                                  licence_type.name)
        elif len(kept_licences) >= _MAX_LICENCES:
            errors['licence'] = _('A listing can hold up to %s licences.', _MAX_LICENCES)
        else:
            return {'type_id': licence_type.id, 'number': number}
        return None

    # ── Job ads ──────────────────────────────────────────────────────────
    # Owners manage the ads of their own listings through these routes only,
    # which check ownership and then write with sudo.

    def _owned_jobs(self, job_id=None):
        domain = [('business_id.owner_id', '=', request.env.user.id)]
        if job_id is not None:
            domain.append(('id', '=', job_id))
        return request.env['connect.job'].sudo().with_context(active_test=False).search(domain)

    @http.route('/my/connect/jobs', type='http', auth='user', website=True)
    def portal_my_connect_jobs(self, **kw):
        values = self._prepare_portal_layout_values()
        values.update({
            'jobs': self._owned_jobs(),
            'has_listings': bool(request.env['connect.business'].search_count(
                [('owner_id', '=', request.env.user.id)])),
            'today': fields.Date.context_today(request.env.user),
            'page_name': 'connect_jobs',
        })
        return request.render('aveenix_connect.portal_my_connect_jobs', values)

    def _job_values(self, job, form=None, errors=None):
        values = self._prepare_portal_layout_values()
        values.update({
            'job': job,
            'form': form or {},
            'errors': errors or {},
            'businesses': request.env['connect.business'].search([('owner_id', '=', request.env.user.id)]),
            'employment_types': EMPLOYMENT_TYPES,
            'page_name': 'connect_job',
        })
        return values

    @http.route(['/my/connect/jobs/new', '/my/connect/jobs/<int:job_id>'],
                type='http', auth='user', website=True, methods=['GET'])
    def portal_my_connect_job(self, job_id=None, **kw):
        job = self._owned_jobs(job_id) if job_id else request.env['connect.job']
        if job_id and not job:
            return request.redirect('/my/connect/jobs')
        return request.render('aveenix_connect.portal_my_connect_job', self._job_values(job))

    @http.route(['/my/connect/jobs/new', '/my/connect/jobs/<int:job_id>'],
                type='http', auth='user', website=True, methods=['POST'], sitemap=False)
    def portal_my_connect_job_save(self, job_id=None, **post):
        job = self._owned_jobs(job_id) if job_id else request.env['connect.job']
        if job_id and not job:
            return request.redirect('/my/connect/jobs')
        values = self._job_values(job, post)
        errors = values['errors']
        business_id = post.get('business_id') or ''
        business = values['businesses'].filtered(lambda b: str(b.id) == business_id)
        vals = {
            'business_id': business.id,
            'name': (post.get('name') or '').strip()[:_MAX_TEXT],
            'description': (post.get('description') or '').strip()[:_MAX_NOTES * 2],
            'employment_type': post.get('employment_type'),
            'city': (post.get('city') or '').strip()[:_MAX_TEXT] or business.city,
            'pay': (post.get('pay') or '').strip()[:_MAX_TEXT] or False,
            'date_closing': False,
        }
        if not business:
            errors['business_id'] = _('Choose the business that is hiring.')
        if not vals['name']:
            errors['name'] = _('Enter the job title.')
        if not vals['description']:
            errors['description'] = _('Describe the job.')
        if vals['employment_type'] not in dict(EMPLOYMENT_TYPES):
            errors['employment_type'] = _('Choose the type of work.')
        if post.get('date_closing'):
            try:
                vals['date_closing'] = fields.Date.to_date(post['date_closing'])
            except ValueError:
                errors['date_closing'] = _('Enter a valid date.')
        if errors:
            return request.render('aveenix_connect.portal_my_connect_job', values)
        if job:
            job.write(vals)
        else:
            request.env['connect.job'].sudo().create(vals)
        return request.redirect('/my/connect/jobs')

    @http.route('/my/connect/jobs/<int:job_id>/toggle', type='http', auth='user', website=True,
                methods=['POST'], sitemap=False)
    def portal_my_connect_job_toggle(self, job_id, **kw):
        """Close an open ad, or reopen a closed one."""
        job = self._owned_jobs(job_id)
        if job:
            job.active = not job.active
        return request.redirect('/my/connect/jobs')

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
