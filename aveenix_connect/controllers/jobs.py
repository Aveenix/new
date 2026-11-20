from markupsafe import Markup

from odoo import _, http, tools
from odoo.http import request

from ..models.connect_job import EMPLOYMENT_TYPES
from .main import _MAX_NOTES, _MAX_TEXT, AveenixConnect, read_contact, recaptcha_ok

_JOBS_PER_PAGE = 20
_MAX_CV_BYTES = 5 * 1024 * 1024
_CV_TYPES = ('.pdf', '.doc', '.docx', '.odt', '.rtf', '.txt')


class AveenixConnectJobs(AveenixConnect):
    """Aveenix Jobs: job ads from Connect listings, and applications to them."""

    @http.route(['/connect/jobs', '/connect/jobs/page/<int:page>'],
                type='http', auth='public', website=True)
    def connect_jobs(self, page=1, what='', where='', **kwargs):
        what = (what or '').strip()[:_MAX_TEXT]
        where = (where or '').strip()[:_MAX_TEXT]
        domain = self._open_jobs_domain()
        if what:
            domain += ['|', '|', ('name', 'ilike', what), ('description', 'ilike', what),
                       ('business_id.name', 'ilike', what)]
        if where:
            domain += ['|', ('city', 'ilike', where), ('business_id.city', 'ilike', where)]
        Job = request.env['connect.job'].sudo()
        total = Job.search_count(domain)
        url_args = {k: v for k, v in (('what', what), ('where', where)) if v}
        pager = request.website.pager(url='/connect/jobs', total=total, page=page,
                                      step=_JOBS_PER_PAGE, scope=5, url_args=url_args)
        return request.render('aveenix_connect.connect_jobs', self._connect_values(
            jobs=Job.search(domain, limit=_JOBS_PER_PAGE, offset=pager['offset']),
            pager=pager,
            total=total,
            what=what,
            where=where,
            employment_types=dict(EMPLOYMENT_TYPES),
            active_nav='jobs',
        ))

    def _visible_job(self, job):
        job = job.sudo().exists()
        if not job or not job.search_count(self._open_jobs_domain() + [('id', '=', job.id)]):
            raise request.not_found()
        return job

    @http.route('/connect/jobs/<model("connect.job"):job>', type='http', auth='public', website=True)
    def connect_job(self, job, **kwargs):
        job = self._visible_job(job)
        return request.render('aveenix_connect.connect_job', self._connect_values(
            job=job,
            business=job.business_id,
            employment_types=dict(EMPLOYMENT_TYPES),
            is_owner=job.business_id.owner_id == request.env.user,
            recaptcha_key=self._recaptcha_site_key(),
            notice=kwargs.get('notice'),
            active_nav='jobs',
        ))

    @http.route('/connect/jobs/<int:job_id>/apply', type='http', auth='public',
                website=True, methods=['POST'], sitemap=False)
    def connect_job_apply(self, job_id, **post):
        job = self._visible_job(request.env['connect.job'].browse(job_id))
        back = job._website_url() + '?notice=%s#avc-apply'
        if post.get('website_url'):
            return request.redirect(back % 'applied')
        if not recaptcha_ok(post):
            return request.redirect(back % 'captcha')
        name, email, phone = read_contact(post)
        message = (post.get('message') or '').strip()[:_MAX_NOTES]
        if not (name and email and message):
            return request.redirect(back % 'invalid')
        attachments = []
        cv = request.httprequest.files.get('cv')
        if cv and cv.filename:
            data = cv.read(_MAX_CV_BYTES + 1)
            if len(data) > _MAX_CV_BYTES or not cv.filename.lower().endswith(_CV_TYPES):
                return request.redirect(back % 'cv_invalid')
            attachments.append((cv.filename[-_MAX_TEXT:], data))
        user = request.env.user
        body = Markup('<p>%s</p>%s') % (
            _('Application for %(job)s from %(name)s (%(contact)s) via Aveenix Jobs:',
              job=job.name, name=name, contact=', '.join(filter(None, [email, phone]))),
            tools.plaintext2html(message),
        )
        job.message_post(
            body=body,
            author_id=None if user._is_public() else user.partner_id.id,
            email_from=tools.formataddr((name, email)),
            reply_to=email,
            partner_ids=job.business_id.owner_id.partner_id.ids,
            attachments=attachments,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )
        return request.redirect(back % 'applied')
