from odoo import _, api, fields, models
from odoo.exceptions import UserError

FREIGHT_MODES = [
    ('ocean_fcl', 'Ocean Freight – FCL'),
    ('ocean_lcl', 'Ocean Freight – LCL'),
    ('air', 'Air Freight'),
    ('road', 'Road Freight'),
    ('rail', 'Rail Freight'),
]

CONTAINER_TYPES = [
    ('20gp', "20' Standard"),
    ('40gp', "40' Standard"),
    ('40hc', "40' High Cube"),
    ('20rf', "20' Reefer"),
    ('40rf', "40' Reefer"),
]

# The cargo fields a quote hands to the shipment it becomes; named once so the
# two models cannot drift on which details survive conversion.
_CARGO_FIELDS = (
    'mode', 'origin_port_id', 'destination_port_id', 'origin_address',
    'destination_address', 'incoterm_id', 'commodity', 'packages',
    'weight_kg', 'volume_cbm', 'container_type', 'container_qty',
    'is_hazardous', 'needs_customs', 'needs_insurance',
)


class FreightQuote(models.Model):
    """A request for a freight price, usually from the website quote form."""

    _name = 'freight.quote'
    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin']
    _description = 'Freight Quote Request'
    _order = 'create_date desc, id desc'

    name = fields.Char(
        string='Reference', required=True, copy=False, readonly=True,
        default=lambda self: _('New'),
    )
    state = fields.Selection(
        [
            ('new', 'New'),
            ('in_progress', 'In Progress'),
            ('quoted', 'Quoted'),
            ('won', 'Won'),
            ('lost', 'Lost'),
        ],
        string='Status', default='new', required=True, tracking=True, index=True,
    )
    source = fields.Selection(
        [('website', 'Website'), ('backend', 'Backend')],
        string='Source', default='backend', required=True, readonly=True,
    )
    user_id = fields.Many2one(
        'res.users', string='Freight Agent', tracking=True,
        default=lambda self: self.env.user if self.env.user._is_internal() else False,
    )
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company,
    )

    # Customer
    partner_id = fields.Many2one('res.partner', string='Customer', tracking=True)
    contact_name = fields.Char(string='Contact Name', required=True)
    company_name = fields.Char(string='Company Name')
    email = fields.Char(string='Email', required=True)
    phone = fields.Char(string='Phone')
    country_id = fields.Many2one('res.country', string='Customer Country')

    # Route and cargo
    mode = fields.Selection(FREIGHT_MODES, string='Mode', required=True, default='ocean_fcl')
    origin_port_id = fields.Many2one('freight.port', string='Origin Port / Airport')
    destination_port_id = fields.Many2one('freight.port', string='Destination Port / Airport')
    origin_address = fields.Char(string='Origin (City / Address)', required=True)
    destination_address = fields.Char(string='Destination (City / Address)', required=True)
    incoterm_id = fields.Many2one('account.incoterms', string='Incoterm')
    ready_date = fields.Date(string='Cargo Ready Date')
    commodity = fields.Char(string='Commodity')
    packages = fields.Integer(string='Packages')
    weight_kg = fields.Float(string='Gross Weight (kg)')
    volume_cbm = fields.Float(string='Volume (CBM)', digits=(16, 3))
    container_type = fields.Selection(CONTAINER_TYPES, string='Container Type')
    container_qty = fields.Integer(string='Containers', default=1)
    is_hazardous = fields.Boolean(string='Dangerous Goods')
    needs_customs = fields.Boolean(string='Customs Clearance')
    needs_insurance = fields.Boolean(string='Cargo Insurance')
    notes = fields.Text(string='Customer Notes')

    # Offer
    currency_id = fields.Many2one(
        'res.currency', string='Currency', required=True,
        default=lambda self: self.env.company.currency_id,
    )
    quoted_amount = fields.Monetary(string='Quoted Price', tracking=True)
    valid_until = fields.Date(string='Valid Until')
    transit_days = fields.Integer(string='Est. Transit (days)')
    lost_reason = fields.Char(string='Lost Reason')
    shipment_ids = fields.One2many('freight.shipment', 'quote_id', string='Shipments')
    shipment_count = fields.Integer(compute='_compute_shipment_count')

    @api.depends('shipment_ids')
    def _compute_shipment_count(self):
        for quote in self:
            quote.shipment_count = len(quote.shipment_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('freight.quote') or _('New')
        return super().create(vals_list)

    def _compute_access_url(self):
        super()._compute_access_url()
        for quote in self:
            quote.access_url = '/my/freight/quotes/%s' % quote.id

    # ── Workflow ─────────────────────────────────────────────────────────

    def action_start(self):
        self.write({'state': 'in_progress'})

    def action_mark_quoted(self):
        for quote in self:
            if not quote.quoted_amount:
                raise UserError(_('Set the quoted price on %s first.', quote.name))
        self.write({'state': 'quoted'})

    def action_mark_lost(self):
        self.write({'state': 'lost'})

    def action_reset(self):
        self.write({'state': 'new'})

    def action_quote_send(self):
        """Email the price to the customer from the usual composer.

        The message goes out in the notification layout, which adds a "View"
        button carrying this quote's access token, so a website visitor
        without an account can still open the quote and accept or decline it
        (controllers/portal.py). That button is addressed to the customer
        partner, hence matching or creating one first."""
        self.ensure_one()
        if self.state != 'quoted':
            raise UserError(_('Mark %s as quoted before sending it.', self.name))
        self._find_or_create_partner()
        template = self.env.ref('aveenix_freight.mail_template_freight_quote', raise_if_not_found=False)
        return {
            'name': _('Send Quote'),
            'type': 'ir.actions.act_window',
            'res_model': 'mail.compose.message',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {
                'default_model': 'freight.quote',
                'default_res_ids': self.ids,
                'default_template_id': template.id if template else False,
                'default_composition_mode': 'comment',
                'default_email_layout_xmlid': 'mail.mail_notification_layout_with_responsible_signature',
                'email_notification_allow_footer': True,
                'force_email': True,
            },
        }

    def _find_or_create_partner(self):
        """The customer for this request, matched on email before creating one."""
        self.ensure_one()
        if self.partner_id:
            return self.partner_id
        Partner = self.env['res.partner']
        partner = Partner.search([('email', '=ilike', self.email)], limit=1)
        if not partner:
            parent = Partner
            if self.company_name:
                parent = Partner.create({
                    'name': self.company_name, 'is_company': True,
                    'country_id': self.country_id.id,
                })
            partner = Partner.create({
                'name': self.contact_name,
                'email': self.email,
                'phone': self.phone,
                'country_id': self.country_id.id,
                'parent_id': parent.id,
            })
        self.partner_id = partner
        return partner

    def action_create_shipment(self):
        """Book the accepted quote as a shipment and open it."""
        self.ensure_one()
        if self.state not in ('quoted', 'in_progress', 'won'):
            raise UserError(_('Only a quote in progress or quoted can be booked.'))
        partner = self._find_or_create_partner()
        vals = {field: self[field] for field in _CARGO_FIELDS}
        for field in ('origin_port_id', 'destination_port_id', 'incoterm_id'):
            vals[field] = vals[field].id
        vals.update({
            'partner_id': partner.id,
            'quote_id': self.id,
            'user_id': self.user_id.id,
            'company_id': self.company_id.id,
            'currency_id': self.currency_id.id,
            'amount': self.quoted_amount,
            'cargo_description': self.notes,
        })
        shipment = self.env['freight.shipment'].create(vals)
        self.state = 'won'
        return shipment._get_form_action()

    # ── Customer answers from the portal ─────────────────────────────────

    def action_portal_accept(self):
        """The customer accepts the price: book it, as the team's Book
        Shipment button would. The portal controller calls this as sudo after
        checking the quote is theirs and still open."""
        self.ensure_one()
        if self.state != 'quoted':
            raise UserError(_('Only a quote with a price can be accepted.'))
        self.message_post(body=_('Quote accepted by the customer from the portal.'))
        self.action_create_shipment()
        return self.shipment_ids[:1]

    def action_portal_decline(self, reason=None):
        self.ensure_one()
        if self.state not in ('new', 'in_progress', 'quoted'):
            raise UserError(_('This quote can no longer be declined.'))
        self.write({
            'state': 'lost',
            'lost_reason': reason or _('Declined by the customer'),
        })
        self.message_post(body=_('Quote declined by the customer from the portal.'))

    def action_view_shipments(self):
        self.ensure_one()
        if len(self.shipment_ids) == 1:
            return self.shipment_ids._get_form_action()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Shipments'),
            'res_model': 'freight.shipment',
            'view_mode': 'list,form',
            'domain': [('quote_id', '=', self.id)],
        }
