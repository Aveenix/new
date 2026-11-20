from odoo import _, fields, models
from odoo.exceptions import UserError

from ..models.connect_nzbn_client import NZBN_RE


class ConnectNzbnSearch(models.TransientModel):
    """Find businesses on the NZBN register, by name or NZBN, and publish
    the right ones as listings. Results are vacuumed with the wizard."""

    _name = 'connect.nzbn.search'
    _description = 'Import Businesses from NZBN'

    query = fields.Char(string='Name or NZBN', required=True)
    category_id = fields.Many2one('connect.category', string='Category', required=True,
                                  help='Category of the listings you import.')
    line_ids = fields.One2many('connect.nzbn.search.line', 'wizard_id', string='Register Entries')
    searched = fields.Boolean()
    is_configured = fields.Boolean(default=lambda self: self.env['connect.nzbn.client']._is_configured())

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Import from NZBN'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_search(self):
        self.ensure_one()
        client = self.env['connect.nzbn.client']
        query = self.query.strip()
        if NZBN_RE.match(query):
            entity = client.get_entity(query)
            if entity is None:
                raise UserError(_('The NZBN register could not be reached; check the API key and the server log.'))
            items = [{
                'nzbn': query,
                'name': client.listing_values(entity).get('name'),
                'status': entity.get('entityStatusDescription') or '',
            }] if entity else []
        else:
            result = client.search(query, page_size=25)
            if result is None:
                raise UserError(_('The NZBN register could not be reached; check the API key and the server log.'))
            items = [{key: item[key] for key in ('nzbn', 'name', 'status')} for item in result['items']]
        listed = {
            business.nzbn: business.id
            for business in self.env['connect.business'].search([('nzbn', 'in', [i['nzbn'] for i in items])])
        }
        self.line_ids = [(5, 0, 0)] + [
            (0, 0, dict(item, business_id=listed.get(item['nzbn']))) for item in items
        ]
        self.searched = True
        return self._reopen()


class ConnectNzbnSearchLine(models.TransientModel):
    _name = 'connect.nzbn.search.line'
    _description = 'NZBN Register Entry'

    wizard_id = fields.Many2one('connect.nzbn.search', required=True, ondelete='cascade')
    nzbn = fields.Char(string='NZBN', required=True)
    name = fields.Char()
    status = fields.Char()
    business_id = fields.Many2one('connect.business', string='Listing')

    def action_import(self):
        """Publish the entry as a listing, or open the listing it already has."""
        self.ensure_one()
        if not self.business_id:
            client = self.env['connect.nzbn.client']
            entity = client.get_entity(self.nzbn)
            if not entity:
                raise UserError(_('The NZBN register did not return %s; see the server log.', self.nzbn))
            if not client.is_registered(entity):
                raise UserError(_('%s is no longer a registered business.', self.name or self.nzbn))
            self.business_id = self.env['connect.business'].create(dict(
                client.listing_values(entity),
                category_ids=[(6, 0, self.wizard_id.category_id.ids)],
                is_published=True,
                nzbn_synced_on=fields.Datetime.now(),
            ))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'connect.business',
            'res_id': self.business_id.id,
            'view_mode': 'form',
        }
