from odoo import fields, models

REPORT_REASONS = [
    ('details', 'Wrong contact details or address'),
    ('closed', 'The business has closed'),
    ('duplicate', 'Duplicate listing'),
    ('remove', 'Remove this listing or hide my personal details'),
    ('other', 'Something else'),
]


class ConnectReport(models.Model):
    """"Report incorrect information", sent from a business page for the
    Connect team to check."""

    _name = 'connect.report'
    _description = 'Connect Listing Report'
    _order = 'id desc'
    _rec_name = 'business_id'

    business_id = fields.Many2one(
        'connect.business', string='Listing', required=True, readonly=True, index=True, ondelete='cascade')
    reason = fields.Selection(REPORT_REASONS, required=True, readonly=True)
    details = fields.Text(readonly=True)
    contact_name = fields.Char(string='Reported By', readonly=True)
    email = fields.Char(readonly=True)
    partner_id = fields.Many2one('res.partner', string='Account', readonly=True)
    state = fields.Selection([('new', 'To Check'), ('done', 'Checked')], default='new', required=True)
    note = fields.Text(string='Team Note')

    def action_done(self):
        self.state = 'done'

    def action_reopen(self):
        self.state = 'new'
