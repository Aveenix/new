from odoo import _, fields, models


class ConnectLicenceType(models.Model):
    """A licence or registration the team can check on its public register
    (e.g. Licensed Building Practitioners). Its name is the badge shown on
    listings whose licence was checked."""

    _name = 'connect.licence.type'
    _description = 'Connect Licence Type'
    _order = 'sequence, name'

    name = fields.Char(string='Badge', required=True, translate=True, help='e.g. "Licensed Builder".')
    register_name = fields.Char(string='Register', translate=True,
                                help='Who issues it, e.g. "Licensed Building Practitioners (LBP)".')
    register_url = fields.Char(string='Register Website', help='Where the team checks the licence number.')
    icon = fields.Char(default='fa-certificate', help='Font Awesome 4 icon class shown on the badge.')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)


class ConnectLicence(models.Model):
    """A licence an owner added to their listing. It shows as a badge once
    the team has checked the number on the register."""

    _name = 'connect.licence'
    _description = 'Connect Licence'
    _order = 'id desc'
    _rec_name = 'number'

    business_id = fields.Many2one('connect.business', string='Listing', required=True, index=True, ondelete='cascade')
    type_id = fields.Many2one('connect.licence.type', string='Licence', required=True, ondelete='restrict')
    register_url = fields.Char(related='type_id.register_url')
    number = fields.Char(string='Licence Number', required=True)
    state = fields.Selection(
        [('pending', 'To Check'), ('verified', 'Checked'), ('rejected', 'Rejected')],
        default='pending', required=True, readonly=True)
    checked_on = fields.Date(readonly=True)

    _type_uniq = models.Constraint(
        'UNIQUE(business_id, type_id)',
        'A listing holds each licence once.',
    )

    def action_verify(self):
        self.write({'state': 'verified', 'checked_on': fields.Date.context_today(self)})
        for licence in self:
            licence.business_id.message_post(
                body=_('Licence checked: %(type)s %(number)s.', type=licence.type_id.name, number=licence.number),
                subtype_xmlid='mail.mt_note',
            )

    def action_reject(self):
        self.write({'state': 'rejected', 'checked_on': fields.Date.context_today(self)})
