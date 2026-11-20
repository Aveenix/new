from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Register entries fetched per page. Every new listing costs one more API
# call for its full entry, so a page is at most 1 + _PAGE_SIZE calls.
_PAGE_SIZE = 50
# Listings refreshed from the register per cron run.
_REFRESH_PER_RUN = 50


class ConnectNzbnImport(models.Model):
    """A search of the NZBN register that the cron works through page by
    page, publishing a listing for each registered business it finds. Each
    import fills one category, e.g. "plumbing" → Trades & Services."""

    _name = 'connect.nzbn.import'
    _description = 'NZBN Bulk Import'
    _order = 'sequence, id'

    name = fields.Char(
        string='Search Term', required=True,
        help='What the NZBN register is searched for, e.g. "plumbing" or "cafe". '
             'The register matches business and trading names.',
    )
    industry_code = fields.Char(
        string='Industry Code',
        help='Optional Business Industry Classification (BIC) code, e.g. E323110, to keep '
             'only businesses in that industry.',
    )
    category_id = fields.Many2one(
        'connect.category', string='Category', required=True, ondelete='restrict',
        help='Given to every listing this import creates, and added to matching listings '
             'that have no owner yet.',
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    state = fields.Selection(
        [('running', 'Running'), ('done', 'Done')], default='running', required=True, readonly=True)
    next_page = fields.Integer(readonly=True, copy=False)
    total_items = fields.Integer(string='Register Matches', readonly=True, copy=False)
    imported_count = fields.Integer(string='Listings Created', readonly=True, copy=False)
    last_run = fields.Datetime(readonly=True, copy=False)
    last_error = fields.Char(readonly=True, copy=False)

    def action_run(self):
        if not self.env['connect.nzbn.client']._is_configured():
            raise UserError(_('Set the NZBN API key under Connect > Configuration > Settings first.'))
        for job in self.filtered(lambda j: j.state == 'running'):
            job._import_page()

    def action_restart(self):
        self.write({'state': 'running', 'next_page': 0, 'last_error': False})

    def _import_page(self):
        """Import the next page of register matches."""
        self.ensure_one()
        client = self.env['connect.nzbn.client']
        result = client.search(self.name, page=self.next_page, page_size=_PAGE_SIZE,
                               industry_code=self.industry_code)
        now = fields.Datetime.now()
        if result is None:
            self.write({'last_run': now, 'last_error': _('The register could not be searched; see the server log.')})
            return
        Business = self.env['connect.business'].sudo().with_context(
            active_test=False, mail_create_nolog=True, tracking_disable=True)
        listed = Business.search([('nzbn', 'in', [item['nzbn'] for item in result['items']])])
        # Already listed: add the category, unless an owner manages the listing.
        listed.filtered(lambda b: not b.owner_id and self.category_id not in b.category_ids).write(
            {'category_ids': [(4, self.category_id.id)]})
        listed_nzbns = set(listed.mapped('nzbn'))
        created = 0
        for item in result['items']:
            if not item['registered'] or item['nzbn'] in listed_nzbns:
                continue
            entity = client.get_entity(item['nzbn'])
            if entity is None:  # stop here and retry this page next run
                self.write({'last_run': now, 'last_error': _('The register stopped answering; see the server log.')})
                self.imported_count += created
                return
            if not entity or not client.is_registered(entity):
                continue
            Business.create(dict(
                client.listing_values(entity),
                category_ids=[(6, 0, self.category_id.ids)],
                is_published=True,
                nzbn_synced_on=now,
            ))
            created += 1
        done = not result['items'] or (self.next_page + 1) * _PAGE_SIZE >= result['total']
        self.write({
            'next_page': self.next_page + 1,
            'total_items': result['total'],
            'imported_count': self.imported_count + created,
            'last_run': now,
            'last_error': False,
            'state': 'done' if done else 'running',
        })

    @api.model
    def _cron_import(self):
        """One page of the import waiting longest, then a refresh of the
        listings synced longest ago. Small steps keep within the API's limits;
        run "Import next page" by hand to go faster."""
        if not self.env['connect.nzbn.client']._is_configured():
            return
        job = self.search([('state', '=', 'running')], order='last_run asc nulls first, sequence, id', limit=1)
        if job:
            job._import_page()
        self.env['connect.business']._cron_nzbn_refresh(_REFRESH_PER_RUN)
