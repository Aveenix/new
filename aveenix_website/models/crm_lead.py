from markupsafe import Markup

from odoo import _, models


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
        """Redirect the 'You have been assigned' notification to the sales team
        email (To), keeping the assigned salesperson in Cc.

        Falls back to the default behaviour when no team email is configured.
        """
        for record in self:
            team_partner = record._av_team_email_partner()
            if not team_partner:
                # No team email → default behaviour (notify the assignee).
                super(CrmLead, record)._message_auto_subscribe_notify(partner_ids, template)
                continue

            # Notify the team email (primary) plus the assigned salesperson(s)
            # so both receive the assignment alert. (Odoo's notification layer
            # does not expose a reliable header-level Cc, so each notified
            # partner gets their own copy.)
            recipient_ids = set(team_partner.ids)
            recipient_ids.update(partner_ids)

            model_description = self.env['ir.model']._get(record._name).display_name
            company = record.company_id.sudo() if 'company_id' in record else self.env.company
            values = {
                'access_link': record._notify_get_action_link('view'),
                'company': company,
                'model_description': model_description,
                'object': record,
            }
            body = self.env['ir.qweb']._render(template, values, minimal_qcontext=True)
            body = self.env['mail.render.mixin']._replace_local_links(body)

            # The team email is a plain mailbox (not a user), so Odoo's layout
            # won't add its auto "View" button. Add an explicit one ourselves.
            base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
            lead_url = '%s/odoo/crm/%s' % (base_url, record.id)
            view_button = Markup(
                '<div style="margin-top:16px;">'
                '<a href="%s" style="display:inline-block;background:#875A7B;'
                'color:#ffffff;text-decoration:none;padding:9px 18px;'
                'border-radius:4px;font-weight:bold;font-size:13px;">View Lead</a>'
                '</div>'
            ) % lead_url
            body = Markup(body or '') + view_button

            record.message_notify(
                subject=_('New assignment: %s', record.display_name),
                body=body,
                partner_ids=list(recipient_ids),
                email_layout_xmlid='mail.mail_notification_layout',
                model_description=model_description,
            )
