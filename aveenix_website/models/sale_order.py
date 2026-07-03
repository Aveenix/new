from odoo import _, models
from odoo.tools import email_split


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _av_partner_has_prior_order(self):
        """True if this order's partner already has a confirmed order.

        Used to restrict the new-user welcome discount to a genuine first
        order. The current order is excluded so it never disqualifies itself.
        """
        self.ensure_one()
        if not self.partner_id:
            return False
        # sudo(): a public/website user must not read other orders, but we only
        # need an existence check scoped to their own partner to gate the perk.
        return bool(self.env['sale.order'].sudo().search_count([
            ('partner_id', '=', self.partner_id.id),
            ('state', '=', 'sale'),
            ('id', '!=', self.id or self._origin.id),
        ], limit=1))

    def _program_check_compute_points(self, programs):
        """Gate the welcome-discount promotion to first-time customers only.

        The loyalty engine treats a program with an 'error' key as
        not-applicable, so a returning customer's welcome discount is skipped
        (and any already-applied welcome reward is removed) automatically.
        """
        result = super()._program_check_compute_points(programs)
        welcome = self.env.ref(
            'aveenix_website.loyalty_program_welcome_discount',
            raise_if_not_found=False,
        )
        if welcome and welcome in programs and self._av_partner_has_prior_order():
            result.setdefault(welcome, {})['error'] = _(
                "The welcome discount is only valid on your first order."
            )
        return result

    def _action_confirm(self):
        """Drop affiliate lines before confirming so the real sale order,
        invoice and delivery only ever contain purchasable items. Affiliate
        items are a redirect reminder in the cart, not something we sell."""
        for order in self:
            aff_lines = order.order_line.filtered('is_affiliate')
            if aff_lines:
                aff_lines.unlink()
        return super()._action_confirm()

    def _av_admin_notify_partners(self):
        """Resolve the configured admin notification email(s) into partners."""
        raw = self.env['ir.config_parameter'].sudo().get_param(
            'aveenix_website.order_admin_cc'
        )
        if not raw or not raw.strip():
            return self.env['res.partner']
        Partner = self.env['res.partner'].sudo()
        partners = Partner.browse()
        for email in email_split(raw):
            partner = Partner.search([('email', '=ilike', email)], limit=1)
            if not partner:
                partner = Partner.create({'name': email, 'email': email})
            partners |= partner
        return partners

    def _send_order_confirmation_mail(self):
        """Send the normal customer confirmation, then a separate internal
        notification to the configured admin address(es)."""
        super()._send_order_confirmation_mail()
        self._av_send_admin_order_notification()

    def _av_send_admin_order_notification(self):
        """Send a dedicated internal 'new order' email to admin staff.

        Kept fully separate from the customer confirmation so the customer
        email stays clean and the two never interfere.
        """
        template = self.env.ref(
            'aveenix_website.mail_template_admin_new_order', raise_if_not_found=False
        )
        if not template:
            return
        for order in self:
            partners = order._av_admin_notify_partners()
            if not partners:
                continue
            template.sudo().with_context(force_send=True).send_mail(
                order.id,
                email_values={
                    'recipient_ids': [(6, 0, partners.ids)],
                    'email_to': False,
                },
            )
