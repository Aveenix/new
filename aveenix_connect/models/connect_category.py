from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ConnectCategory(models.Model):
    """A directory category (Restaurants, Plumbers, ...). Top-level categories
    make up the Connect nav; searching a category includes its subcategories."""

    _name = 'connect.category'
    _description = 'Connect Category'
    _parent_store = True
    _order = 'sequence, name'

    name = fields.Char(string='Name', required=True, translate=True)
    parent_id = fields.Many2one('connect.category', string='Parent Category', index=True, ondelete='cascade')
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many('connect.category', 'parent_id', string='Subcategories')
    sequence = fields.Integer(default=10)
    icon = fields.Char(
        string='Icon', default='fa-briefcase',
        help='Font Awesome 4 icon class shown on the website, e.g. fa-cutlery.',
    )
    active = fields.Boolean(default=True)
    business_count = fields.Integer(string='Published Listings', compute='_compute_business_count')

    @api.constrains('parent_id')
    def _check_parent_id(self):
        if self._has_cycle():
            raise ValidationError(_('A category cannot be its own parent.'))

    def _compute_business_count(self):
        counts = dict(self.env['connect.business'].sudo()._read_group(
            [('is_published', '=', True), ('category_ids', 'in', self.ids)],
            ['category_ids'], ['__count'],
        ))
        for category in self:
            category.business_count = counts.get(category, 0)
