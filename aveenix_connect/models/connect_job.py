from markupsafe import Markup

from odoo import api, fields, models
from odoo.tools.json import scriptsafe as json_scriptsafe

EMPLOYMENT_TYPES = [
    ('full_time', 'Full time'),
    ('part_time', 'Part time'),
    ('casual', 'Casual'),
    ('contract', 'Contract'),
]
# schema.org JobPosting employmentType values.
_SCHEMA_EMPLOYMENT = {
    'full_time': 'FULL_TIME',
    'part_time': 'PART_TIME',
    'casual': 'PER_DIEM',
    'contract': 'CONTRACTOR',
}


class ConnectJob(models.Model):
    """A job ad a listing's owner posts on Aveenix Jobs (/connect/jobs).
    Applications are posted on its chatter, which emails them, CV attached,
    to the owner. Closing an ad archives it."""

    _name = 'connect.job'
    _description = 'Connect Job Ad'
    _inherit = ['mail.thread']
    _order = 'create_date desc, id desc'

    name = fields.Char(string='Job Title', required=True, tracking=True)
    business_id = fields.Many2one(
        'connect.business', string='Business', required=True, index=True, ondelete='cascade')
    description = fields.Text(required=True)
    employment_type = fields.Selection(EMPLOYMENT_TYPES, required=True, default='full_time')
    city = fields.Char(string='Location')
    pay = fields.Char(help='e.g. "$30–$34 per hour" or "$70k–$80k".')
    date_closing = fields.Date(string='Applications Close', tracking=True)
    active = fields.Boolean(default=True, tracking=True)

    @api.model
    def _cron_close_expired(self):
        """Close (archive) the ads whose closing date has passed."""
        self.search([('date_closing', '<', fields.Date.context_today(self))]).active = False

    def _website_url(self):
        self.ensure_one()
        return '/connect/jobs/%s' % self.env['ir.http']._slug(self)

    def _structured_data(self):
        """schema.org JobPosting JSON-LD, read by search engines' job listings."""
        self.ensure_one()
        business = self.business_id
        data = {
            '@context': 'https://schema.org',
            '@type': 'JobPosting',
            'title': self.name,
            'description': self.description,
            'datePosted': fields.Date.to_string(self.create_date.date()),
            'validThrough': fields.Date.to_string(self.date_closing) if self.date_closing else None,
            'employmentType': _SCHEMA_EMPLOYMENT.get(self.employment_type),
            'hiringOrganization': {
                '@type': 'Organization',
                'name': business.name,
                'sameAs': business.get_base_url() + business.website_url,
            },
            'jobLocation': {
                '@type': 'Place',
                'address': {k: v for k, v in {
                    '@type': 'PostalAddress',
                    'addressLocality': self.city or business.city,
                    'addressCountry': business.country_id.code or 'NZ',
                }.items() if v},
            },
        }
        return Markup(json_scriptsafe.dumps({k: v for k, v in data.items() if v}, ensure_ascii=False))
