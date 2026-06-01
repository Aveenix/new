from odoo import http, _
from odoo.http import request
from odoo.exceptions import UserError, ValidationError
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager


class AveenixRewardsPortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'reward_count' in counters:
            values['reward_count'] = request.env['aveenix.reward.redemption'].sudo().search_count([
                ('partner_id', '=', request.env.user.partner_id.id),
            ])
        return values

    # ── Wallet / Dashboard ────────────────────────────────────────────────

    @http.route('/my/rewards', type='http', auth='user', website=True)
    def portal_rewards(self, **kwargs):
        partner = request.env.user.partner_id
        program = request.env.ref('aveenix_rewards.aveenix_ewallet_program', raise_if_not_found=False)
        card = False
        history = []
        if program:
            card = request.env['loyalty.card'].sudo().search([
                ('program_id', '=', program.id),
                ('partner_id', '=', partner.id),
            ], limit=1)
            if card:
                history = request.env['loyalty.history'].sudo().search([
                    ('card_id', '=', card.id),
                ], order='id desc', limit=20)

        redemptions = request.env['aveenix.reward.redemption'].sudo().search([
            ('partner_id', '=', partner.id),
        ], order='id desc', limit=10)

        return request.render('aveenix_rewards.portal_rewards_dashboard', {
            'partner': partner,
            'card': card,
            'balance': card.points if card else 0.0,
            'history': history,
            'redemptions': redemptions,
            'page_name': 'rewards',
        })

    # ── Redemption Request Form ───────────────────────────────────────────

    @http.route('/my/rewards/redeem', type='http', auth='user', website=True)
    def portal_redeem_form(self, **kwargs):
        partner = request.env.user.partner_id
        program = request.env.ref('aveenix_rewards.aveenix_ewallet_program', raise_if_not_found=False)
        card = False
        if program:
            card = request.env['loyalty.card'].sudo().search([
                ('program_id', '=', program.id),
                ('partner_id', '=', partner.id),
            ], limit=1)

        return request.render('aveenix_rewards.portal_redeem_form', {
            'partner': partner,
            'card': card,
            'balance': card.points if card else 0.0,
            'error': kwargs.get('error', ''),
            'success': kwargs.get('success', ''),
            'page_name': 'redeem',
        })

    @http.route('/my/rewards/redeem/submit', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_redeem_submit(self, **post):
        partner = request.env.user.partner_id
        mode = post.get('mode', '')
        amount_str = post.get('points_to_redeem', '0')
        payment_gateway = post.get('payment_gateway', '')
        gateway_account = post.get('gateway_account', '').strip()
        recipient_email = post.get('recipient_email', '').strip()

        # Validate amount
        try:
            amount = float(amount_str)
        except (ValueError, TypeError):
            return request.redirect('/my/rewards/redeem?error=Invalid+amount+entered.')

        if amount <= 0:
            return request.redirect('/my/rewards/redeem?error=Amount+must+be+greater+than+zero.')

        # Check balance
        program = request.env.ref('aveenix_rewards.aveenix_ewallet_program', raise_if_not_found=False)
        card = False
        if program:
            card = request.env['loyalty.card'].sudo().search([
                ('program_id', '=', program.id),
                ('partner_id', '=', partner.id),
            ], limit=1)

        balance = card.points if card else 0.0
        if amount > balance:
            return request.redirect(
                f'/my/rewards/redeem?error=Insufficient+balance.+Available:+{balance:.2f}'
            )

        # Mode-specific validation
        if mode == 'withdrawal':
            if not payment_gateway:
                return request.redirect('/my/rewards/redeem?error=Please+select+a+payment+gateway.')
            if not gateway_account:
                return request.redirect('/my/rewards/redeem?error=Please+enter+your+account+ID+or+email.')
        elif mode == 'gift_voucher':
            if not recipient_email:
                return request.redirect('/my/rewards/redeem?error=Please+enter+recipient+email+for+gift+voucher.')
            recipient = request.env['res.partner'].sudo().search([
                ('email', '=', recipient_email),
            ], limit=1)
            if not recipient:
                return request.redirect('/my/rewards/redeem?error=No+user+found+with+that+email.')
        elif mode not in ('platform_voucher', 'gift_voucher', 'withdrawal'):
            return request.redirect('/my/rewards/redeem?error=Invalid+redemption+mode.')

        # Build vals
        vals = {
            'partner_id': partner.id,
            'mode': mode,
            'points_to_redeem': amount,
            'state': 'draft',
        }
        if mode == 'withdrawal':
            vals['payment_gateway'] = payment_gateway
            vals['gateway_account'] = gateway_account
        elif mode == 'gift_voucher':
            recipient = request.env['res.partner'].sudo().search([
                ('email', '=', recipient_email),
            ], limit=1)
            vals['recipient_partner_id'] = recipient.id

        try:
            redemption = request.env['aveenix.reward.redemption'].sudo().create(vals)
            redemption.sudo().action_submit()
        except (UserError, ValidationError) as e:
            error_msg = str(e.args[0]).replace(' ', '+')
            return request.redirect(f'/my/rewards/redeem?error={error_msg}')
        except Exception as e:
            return request.redirect(f'/my/rewards/redeem?error=Unexpected+error:+{str(e)[:80]}')

        return request.redirect(f'/my/rewards?success=1')

    # ── Request Detail ────────────────────────────────────────────────────

    @http.route('/my/rewards/request/<int:redemption_id>', type='http', auth='user', website=True)
    def portal_redemption_detail(self, redemption_id, **kwargs):
        partner = request.env.user.partner_id
        redemption = request.env['aveenix.reward.redemption'].sudo().search([
            ('id', '=', redemption_id),
            ('partner_id', '=', partner.id),
        ], limit=1)
        if not redemption:
            return request.redirect('/my/rewards')
        return request.render('aveenix_rewards.portal_redemption_detail', {
            'redemption': redemption,
            'page_name': 'redemption',
        })

    # ── Edit rejected request ─────────────────────────────────────────────

    @http.route('/my/rewards/request/<int:redemption_id>/edit', type='http', auth='user', website=True)
    def portal_redemption_edit(self, redemption_id, **kwargs):
        partner = request.env.user.partner_id
        redemption = request.env['aveenix.reward.redemption'].sudo().search([
            ('id', '=', redemption_id),
            ('partner_id', '=', partner.id),
            ('state', 'in', ('rejected', 'draft')),
        ], limit=1)
        if not redemption:
            return request.redirect('/my/rewards')

        # Reset to draft if still rejected
        if redemption.state == 'rejected':
            redemption.sudo().action_reset_draft()

        # Balance includes the refunded points (already refunded on rejection)
        program = request.env.ref('aveenix_rewards.aveenix_ewallet_program', raise_if_not_found=False)
        card = False
        if program:
            card = request.env['loyalty.card'].sudo().search([
                ('program_id', '=', program.id),
                ('partner_id', '=', partner.id),
            ], limit=1)

        return request.render('aveenix_rewards.portal_redemption_edit', {
            'redemption': redemption,
            'balance': card.points if card else 0.0,
            'error': kwargs.get('error', ''),
            'page_name': 'redemption',
        })

    @http.route('/my/rewards/request/<int:redemption_id>/resubmit', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_redemption_resubmit(self, redemption_id, **post):
        partner = request.env.user.partner_id
        redemption = request.env['aveenix.reward.redemption'].sudo().search([
            ('id', '=', redemption_id),
            ('partner_id', '=', partner.id),
            ('state', '=', 'draft'),
        ], limit=1)
        if not redemption:
            return request.redirect('/my/rewards')

        amount_str = post.get('points_to_redeem', '0')
        try:
            amount = float(amount_str)
        except (ValueError, TypeError):
            return request.redirect(f'/my/rewards/request/{redemption_id}/edit?error=Invalid+amount.')

        if amount <= 0:
            return request.redirect(f'/my/rewards/request/{redemption_id}/edit?error=Amount+must+be+greater+than+zero.')

        vals = {'points_to_redeem': amount}

        if redemption.mode == 'withdrawal':
            gateway_account = post.get('gateway_account', '').strip()
            payment_gateway = post.get('payment_gateway', '')
            if not gateway_account:
                return request.redirect(f'/my/rewards/request/{redemption_id}/edit?error=Please+enter+your+account+details.')
            vals['payment_gateway'] = payment_gateway
            vals['gateway_account'] = gateway_account

        elif redemption.mode == 'gift_voucher':
            recipient_email = post.get('recipient_email', '').strip()
            recipient = request.env['res.partner'].sudo().search([('email', '=', recipient_email)], limit=1)
            if not recipient:
                return request.redirect(f'/my/rewards/request/{redemption_id}/edit?error=No+user+found+with+that+email.')
            vals['recipient_partner_id'] = recipient.id

        try:
            redemption.sudo().write(vals)
            redemption.sudo().action_submit()
        except (UserError, ValidationError) as e:
            error_msg = str(e.args[0]).replace(' ', '+')
            return request.redirect(f'/my/rewards/request/{redemption_id}/edit?error={error_msg}')

        return request.redirect(f'/my/rewards/request/{redemption_id}')
