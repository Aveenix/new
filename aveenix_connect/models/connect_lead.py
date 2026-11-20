from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.tools import formataddr, plaintext2html

# Businesses a quote request goes to, featured listings first.
QUOTE_MATCHES = 5


class ConnectLead(models.Model):
    """A customer getting in touch through Aveenix Connect: an enquiry to one
    business, or a quote request sent to the matching local businesses. It
    reaches each business's owner by email and, later, lets the customer
    review the businesses they contacted."""

    _name = 'connect.lead'
    _description = 'Connect Enquiry or Quote Request'
    _order = 'id desc'
    _rec_name = 'contact_name'

    kind = fields.Selection(
        [('enquiry', 'Enquiry'), ('quote', 'Quote Request')], required=True, readonly=True)
    business_ids = fields.Many2many('connect.business', string='Sent To', readonly=True)
    partner_id = fields.Many2one(
        'res.partner', string='Customer Account', readonly=True, index='btree_not_null',
        help='Set when the customer was logged in.')
    contact_name = fields.Char(string='Name', required=True, readonly=True)
    email = fields.Char(required=True, readonly=True, index=True)
    phone = fields.Char(readonly=True)
    message = fields.Text(required=True, readonly=True)
    category_id = fields.Many2one('connect.category', string='Category', readonly=True)
    location = fields.Char(string='Where', readonly=True)

    @api.model
    def _match_businesses(self, category, location):
        """Published, claimed listings of `category` (or a subcategory) that
        are based in or serve `location`; featured listings first."""
        location = (location or '').strip()
        if not category or not location:
            return self.env['connect.business']
        return self.env['connect.business'].sudo().search([
            ('is_published', '=', True),
            ('owner_id', '!=', False),
            ('category_ids', 'child_of', category.id),
            '|', '|', '|',
            ('city', 'ilike', location),
            ('zip', '=', location),
            ('service_areas', 'ilike', location),
            ('state_id.name', '=ilike', location),
        ], limit=QUOTE_MATCHES)

    def _notify_businesses(self):
        """Email the request to each business owner, on the listing's chatter
        so the team sees it too. One message per business: owners never see
        who else was asked."""
        for lead in self:
            contact = ', '.join(filter(None, [lead.email, lead.phone]))
            if lead.kind == 'quote':
                intro = _('Quote request from %(name)s (%(contact)s) via Aveenix Connect: '
                          '%(category)s in %(location)s.',
                          name=lead.contact_name, contact=contact,
                          category=lead.category_id.name, location=lead.location)
            else:
                intro = _('Enquiry from %(name)s (%(contact)s) via Aveenix Connect:',
                          name=lead.contact_name, contact=contact)
            body = Markup('<p>%s</p>%s') % (intro, plaintext2html(lead.message))
            for business in lead.business_ids.sudo().filtered('owner_id'):
                business.message_post(
                    body=body,
                    author_id=lead.partner_id.id or None,
                    email_from=formataddr((lead.contact_name, lead.email)),
                    reply_to=lead.email,
                    partner_ids=business.owner_id.partner_id.ids,
                    message_type='comment',
                    subtype_xmlid='mail.mt_comment',
                )
