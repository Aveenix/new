from odoo import _, fields, models
from odoo.exceptions import UserError


class ConnectGoogleLink(models.TransientModel):
    """Search Google Places and link a listing to the right place. Results are
    shown to pick from and vacuumed with the wizard; only the chosen place ID
    is written on the listing."""

    _name = 'connect.google.link'
    _description = 'Link a Connect Listing to Google'

    business_id = fields.Many2one('connect.business', required=True, ondelete='cascade')
    query = fields.Char(string='Search Google for', required=True)
    line_ids = fields.One2many('connect.google.link.line', 'wizard_id', string='Places')
    searched = fields.Boolean()
    is_configured = fields.Boolean(default=lambda self: self.env['connect.google.client']._is_configured())

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Link to Google'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_search(self):
        self.ensure_one()
        places = self.env['connect.google.client'].search_text(self.query)
        self.line_ids = [(5, 0, 0)] + [(0, 0, place) for place in places]
        self.searched = True
        return self._reopen()


class ConnectGoogleLinkLine(models.TransientModel):
    _name = 'connect.google.link.line'
    _description = 'Google Place Search Result'

    wizard_id = fields.Many2one('connect.google.link', required=True, ondelete='cascade')
    place_id = fields.Char(required=True)
    name = fields.Char()
    address = fields.Char()

    def action_link(self):
        self.ensure_one()
        business = self.wizard_id.business_id
        other = self.env['connect.business'].search(
            [('google_place_id', '=', self.place_id), ('id', '!=', business.id)], limit=1)
        if other:
            raise UserError(_('This Google place is already linked to "%s".', other.name))
        business.google_place_id = self.place_id
        return {'type': 'ir.actions.act_window_close'}
