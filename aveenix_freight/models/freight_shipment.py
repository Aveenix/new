import secrets
import string

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .freight_quote import CONTAINER_TYPES, FREIGHT_MODES

SHIPMENT_STATES = [
    ('draft', 'Draft'),
    ('booked', 'Booked'),
    ('picked_up', 'Picked Up'),
    ('in_transit', 'In Transit'),
    ('arrived', 'Arrived at Destination'),
    ('customs', 'Customs Clearance'),
    ('out_for_delivery', 'Out for Delivery'),
    ('delivered', 'Delivered'),
    ('cancelled', 'Cancelled'),
]

# Uppercase letters and digits minus the look-alikes (0/O, 1/I), because a
# customer reads this off an email and types it into the tracker.
_TRACKING_ALPHABET = ''.join(
    c for c in string.ascii_uppercase + string.digits if c not in '0O1I'
)


def _new_tracking_number():
    """Random, not sequential: the public tracker must not let anyone walk
    from one customer's shipment to the next by changing a digit."""
    return 'AVF' + ''.join(secrets.choice(_TRACKING_ALPHABET) for _ in range(10))


class FreightShipment(models.Model):
    _name = 'freight.shipment'
    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin']
    _description = 'Freight Shipment'
    _order = 'create_date desc, id desc'

    name = fields.Char(
        string='Reference', required=True, copy=False, readonly=True,
        default=lambda self: _('New'),
    )
    tracking_number = fields.Char(
        string='Tracking Number', required=True, copy=False, readonly=True,
        index=True, default=lambda self: _new_tracking_number(),
        help='Shared with the customer; entered on the website tracker.',
    )
    state = fields.Selection(
        SHIPMENT_STATES, string='Status', default='draft', required=True,
        tracking=True, index=True,
    )
    partner_id = fields.Many2one('res.partner', string='Customer', required=True, tracking=True)
    quote_id = fields.Many2one('freight.quote', string='Quote', readonly=True, copy=False)
    user_id = fields.Many2one(
        'res.users', string='Freight Agent', tracking=True,
        default=lambda self: self.env.user,
    )
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company,
    )

    # Route
    mode = fields.Selection(FREIGHT_MODES, string='Mode', required=True, default='ocean_fcl')
    origin_port_id = fields.Many2one('freight.port', string='Origin Port / Airport')
    destination_port_id = fields.Many2one('freight.port', string='Destination Port / Airport')
    origin_address = fields.Char(string='Origin (City / Address)')
    destination_address = fields.Char(string='Destination (City / Address)')
    incoterm_id = fields.Many2one('account.incoterms', string='Incoterm')

    # Carriage
    carrier = fields.Char(string='Carrier / Airline')
    vessel_flight = fields.Char(string='Vessel / Flight No.')
    bl_awb_number = fields.Char(string='B/L / AWB No.', copy=False)
    container_numbers = fields.Char(string='Container No(s).', copy=False)
    etd = fields.Date(string='ETD', tracking=True)
    eta = fields.Date(string='ETA', tracking=True)
    atd = fields.Date(string='Actual Departure')
    ata = fields.Date(string='Actual Arrival')

    # Cargo
    commodity = fields.Char(string='Commodity')
    cargo_description = fields.Text(string='Cargo Description')
    packages = fields.Integer(string='Packages')
    weight_kg = fields.Float(string='Gross Weight (kg)')
    volume_cbm = fields.Float(string='Volume (CBM)', digits=(16, 3))
    container_type = fields.Selection(CONTAINER_TYPES, string='Container Type')
    container_qty = fields.Integer(string='Containers', default=1)
    is_hazardous = fields.Boolean(string='Dangerous Goods')
    needs_customs = fields.Boolean(string='Customs Clearance')
    needs_insurance = fields.Boolean(string='Cargo Insurance')

    currency_id = fields.Many2one(
        'res.currency', string='Currency', required=True,
        default=lambda self: self.env.company.currency_id,
    )
    amount = fields.Monetary(string='Freight Charges')

    event_ids = fields.One2many('freight.shipment.event', 'shipment_id', string='Tracking Events')
    invoice_ids = fields.One2many('account.move', 'freight_shipment_id', string='Invoices')
    invoice_count = fields.Integer(compute='_compute_invoice_count')

    _tracking_number_uniq = models.Constraint(
        'UNIQUE(tracking_number)', 'Tracking numbers must be unique.',
    )

    @api.depends('invoice_ids')
    def _compute_invoice_count(self):
        for shipment in self:
            shipment.invoice_count = len(shipment.invoice_ids)

    def _compute_access_url(self):
        super()._compute_access_url()
        for shipment in self:
            shipment.access_url = '/my/freight/shipments/%s' % shipment.id

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('freight.shipment') or _('New')
        return super().create(vals_list)

    def write(self, vals):
        res = super().write(vals)
        if 'state' in vals:
            # Every status change becomes a milestone on the customer's
            # tracker, so the timeline never lags behind the backend.
            self._log_status_event(vals['state'])
        return res

    def _log_status_event(self, state):
        location_for = {
            'booked': lambda s: s.origin_port_id,
            'picked_up': lambda s: s.origin_port_id,
            'in_transit': lambda s: s.origin_port_id,
            'arrived': lambda s: s.destination_port_id,
            'customs': lambda s: s.destination_port_id,
            'out_for_delivery': lambda s: s.destination_port_id,
        }
        label = dict(SHIPMENT_STATES)[state]
        events = []
        for shipment in self:
            if state == 'draft':
                continue
            port = location_for.get(state, lambda s: s.browse())(shipment)
            location = port.display_name if port else (
                shipment.destination_address if state == 'delivered' else ''
            )
            events.append({
                'shipment_id': shipment.id,
                'status': state,
                'location': location or '',
                'description': _('Shipment status: %s', label),
            })
        if events:
            self.env['freight.shipment.event'].create(events)

    # ── Workflow buttons ─────────────────────────────────────────────────

    def action_book(self):
        self.state = 'booked'

    def action_pick_up(self):
        self.state = 'picked_up'

    def action_depart(self):
        self.write({'state': 'in_transit', 'atd': fields.Date.context_today(self)})

    def action_arrive(self):
        self.write({'state': 'arrived', 'ata': fields.Date.context_today(self)})

    def action_customs(self):
        self.state = 'customs'

    def action_out_for_delivery(self):
        self.state = 'out_for_delivery'

    def action_deliver(self):
        self.state = 'delivered'

    def action_cancel(self):
        self.state = 'cancelled'

    def action_reset_draft(self):
        self.state = 'draft'

    # ── Invoicing ────────────────────────────────────────────────────────

    def action_create_invoice(self):
        """Bill the freight charges. The customer pays the invoice from the
        portal with any published payment provider (card, PayPal, bank
        transfer), through Odoo's own invoice payment flow."""
        self.ensure_one()
        if self.amount <= 0:
            raise UserError(_('Set the freight charges on %s first.', self.name))
        if self.invoice_ids.filtered(lambda m: m.state != 'cancel'):
            raise UserError(_('%s is already invoiced.', self.name))
        product = self.env.ref('aveenix_freight.product_freight_charges')
        route = ' → '.join(filter(None, [
            self.origin_port_id.display_name or self.origin_address,
            self.destination_port_id.display_name or self.destination_address,
        ]))
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_id.id,
            'currency_id': self.currency_id.id,
            'company_id': self.company_id.id,
            'invoice_origin': self.name,
            'freight_shipment_id': self.id,
            'invoice_line_ids': [(0, 0, {
                'product_id': product.id,
                'name': _('Freight charges %(ref)s (%(mode)s) %(route)s',
                          ref=self.name, mode=dict(FREIGHT_MODES)[self.mode], route=route),
                'quantity': 1,
                'price_unit': self.amount,
            })],
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': invoice.id,
        }

    def action_view_invoices(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Invoices'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.invoice_ids.ids)],
            'context': {'default_move_type': 'out_invoice'},
        }

    def _get_form_action(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': 'freight.shipment',
            'view_mode': 'form',
            'res_id': self.id,
        }

    def action_open_tracker(self):
        """Open the customer's view of this shipment on the website."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/freight/track?number=%s' % self.tracking_number,
            'target': 'new',
        }

    def _public_events(self):
        self.ensure_one()
        return self.event_ids.filtered('is_public').sorted('date', reverse=True)


class FreightShipmentEvent(models.Model):
    """One milestone on a shipment's journey, as the customer sees it."""

    _name = 'freight.shipment.event'
    _description = 'Shipment Tracking Event'
    _order = 'date desc, id desc'

    shipment_id = fields.Many2one(
        'freight.shipment', string='Shipment', required=True, ondelete='cascade', index=True,
    )
    date = fields.Datetime(string='Date', required=True, default=fields.Datetime.now)
    status = fields.Selection(SHIPMENT_STATES, string='Status', required=True)
    location = fields.Char(string='Location')
    description = fields.Char(string='Description')
    is_public = fields.Boolean(
        string='Show on Tracker', default=True,
        help='Uncheck for internal notes that the customer must not see.',
    )
