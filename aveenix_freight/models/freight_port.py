from odoo import api, fields, models

PORT_TYPES = [
    ('sea', 'Seaport'),
    ('air', 'Airport'),
    ('inland', 'Inland Depot / Rail'),
]


class FreightPort(models.Model):
    """A seaport, airport or inland depot cargo moves through."""

    _name = 'freight.port'
    _description = 'Freight Port / Airport'
    _order = 'country_id, name'

    name = fields.Char(string='Name', required=True)
    code = fields.Char(
        string='Code', required=True, index=True,
        help='UN/LOCODE for seaports and depots (e.g. INNSA), IATA code for '
             'airports (e.g. BOM).',
    )
    port_type = fields.Selection(PORT_TYPES, string='Type', required=True, default='sea')
    country_id = fields.Many2one('res.country', string='Country', required=True)
    city = fields.Char(string='City')
    active = fields.Boolean(default=True)

    _code_type_uniq = models.Constraint(
        'UNIQUE(code, port_type)',
        'A port with this code and type already exists.',
    )

    @api.depends('name', 'code')
    def _compute_display_name(self):
        for port in self:
            port.display_name = '%s (%s)' % (port.name, port.code) if port.code else port.name
