from odoo import models


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    def _av_team_email_partner(self):
        """Return a partner representing the lead's sales team email (alias),
        creating one if needed so it can be used as a mail recipient."""
        self.ensure_one()
        team = self.team_id
        team_email = False
        if team and team.alias_id and team.alias_domain_id:
            team_email = team.alias_id.alias_full_name
        if not team_email:
            return self.env['res.partner']
        Partner = self.env['res.partner'].sudo()
        partner = Partner.search([('email', '=ilike', team_email)], limit=1)
        if not partner:
            partner = Partner.create({
                'name': team.name or team_email,
                'email': team_email,
            })
        return partner

    def _message_auto_subscribe_notify(self, partner_ids, template):
        """Send the native 'You have been assigned' email unchanged, but to the
        sales team email instead of the individual salesperson.

        We only swap the recipient list; Odoo renders the email (button, label,
        layout) exactly as it normally would. Falls back to default when no team
        email is configured.
        """
        for record in self:
            team_partner = record._av_team_email_partner()
            target_ids = team_partner.ids if team_partner else partner_ids
            # Flag so _notify_get_recipients_groups shows the access button even
            # though the team email recipient is a plain partner, not a user.
            record = record.with_context(av_team_assign_button=True)
            super(CrmLead, record)._message_auto_subscribe_notify(target_ids, template)

    def _notify_get_recipients_groups(self, message, model_description, msg_vals=False):
        """Show the native 'View Lead' access button for the sales-team email
        recipient (a plain partner) on assignment notifications."""
        groups = super()._notify_get_recipients_groups(
            message, model_description, msg_vals=msg_vals
        )
        if self.env.context.get('av_team_assign_button'):
            for group in groups:
                # group = [name, func, data]
                if group[0] == 'customer':
                    group[2]['has_button_access'] = True
        return groups
