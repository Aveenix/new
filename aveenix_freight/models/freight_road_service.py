from odoo import api, fields, models

# Which cargo details the website quote form asks for once a road service is
# chosen. Packages, weight and volume are always asked for; these add to them.
ROAD_CARGO_TYPES = [
    ('loose', 'Packages / pallets'),
    ('container', 'Full containers'),
    ('heavy_lift', 'Heavy lift'),
]


class FreightRoadService(models.Model):
    """A kind of road freight the team sells (FCL trucks, Hiab, courier…).
    Managed from Freight > Configuration; listed on the Road Freight page and
    offered on the quote form when the customer picks Road Freight."""

    _name = 'freight.road.service'
    _description = 'Road Freight Service'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    icon = fields.Char(
        default='fa-truck',
        help='Font Awesome 4 icon class shown on the website, e.g. fa-truck.',
    )
    description = fields.Text(translate=True, help='One or two lines for the Road Freight page.')
    cargo_type = fields.Selection(
        ROAD_CARGO_TYPES, string='Quote Form Asks For', required=True, default='loose',
        help='Full containers: container type and number. '
             'Heavy lift: weight of the heaviest item and site access. '
             'Packages, weight and volume are asked for every service.',
    )


class FreightRoadCargoMixin(models.AbstractModel):
    """Road service details shared by quotes and shipments, so a quote hands
    them to the shipment it becomes (see _CARGO_FIELDS) and both decide alike
    when container or heavy-lift details apply. Inheritors define `mode`."""

    _name = 'freight.road.cargo.mixin'
    _description = 'Freight Road Service Details'

    road_service_id = fields.Many2one(
        'freight.road.service', string='Road Service', ondelete='restrict', index='btree_not_null',
    )
    road_cargo_type = fields.Selection(related='road_service_id.cargo_type')
    max_item_weight_kg = fields.Float(string='Heaviest Item (kg)')
    site_access = fields.Text(
        string='Site Access',
        help='What the crane truck crew should know: ground, overhead lines, '
             'distance from where the truck can park.',
    )
    is_container_load = fields.Boolean(
        compute='_compute_is_container_load',
        help='Moves whole containers: ocean FCL, or a road service for full containers.',
    )

    @api.depends('mode', 'road_service_id.cargo_type')
    def _compute_is_container_load(self):
        for record in self:
            record.is_container_load = record.mode == 'ocean_fcl' or (
                record.mode == 'road' and record.road_cargo_type == 'container')

    @api.onchange('mode')
    def _onchange_mode_road_service(self):
        if self.mode != 'road':
            self.road_service_id = False

    def _mode_label(self):
        """'Road Freight – Hiab Trucks', or just the mode."""
        self.ensure_one()
        label = dict(self._fields['mode']._description_selection(self.env))[self.mode]
        if self.mode == 'road' and self.road_service_id:
            label = '%s – %s' % (label, self.road_service_id.name)
        return label
