from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class AveenixRewardRedemption(models.Model):
    _name = 'aveenix.reward.redemption'
    _description = 'Reward Redemption Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'
    _order = 'id desc'

    name = fields.Char(string='Reference', readonly=True, copy=False, default='New')

    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('submitted', 'Submitted'),
            ('approved', 'Approved'),
            ('paid', 'Issued'),
            ('rejected', 'Rejected'),
        ],
        default='draft', tracking=True, required=True,
    )

    partner_id = fields.Many2one(
        comodel_name='res.partner', string='Requested By',
        required=True, index=True,
    )
    loyalty_card_id = fields.Many2one(
        comodel_name='loyalty.card', string='eWallet Card',
        compute='_compute_loyalty_card', compute_sudo=True,
    )
    available_points = fields.Float(
        string='Available Balance',
        compute='_compute_loyalty_card', compute_sudo=True,
    )

    mode = fields.Selection(
        selection=[
            ('platform_voucher', 'Platform Voucher (use at checkout)'),
            ('gift_voucher', 'Gift Voucher (transfer to another user)'),
            ('withdrawal', 'Cash Withdrawal (PayPal / Stripe / Bank)'),
        ],
        required=True, string='Redemption Mode', tracking=True,
    )
    points_to_redeem = fields.Float(
        string='Amount to Redeem', required=True,
    )

    # Gift Voucher
    recipient_partner_id = fields.Many2one(
        comodel_name='res.partner', string='Gift Recipient',
        help='Required for Gift Voucher. Must be an existing platform user.',
    )

    # Withdrawal
    payment_gateway = fields.Selection(
        selection=[
            ('paypal', 'PayPal'),
            ('stripe', 'Stripe'),
        ],
        string='Payment Gateway',
    )
    gateway_config_id = fields.Many2one(
        comodel_name='aveenix.payment.gateway.config',
        string='Gateway Account',
        domain="[('gateway', '=', payment_gateway), ('connection_status', '=', 'connected')]",
        help='Select the configured gateway account to use for this payout.',
    )
    gateway_account = fields.Char(
        string='Customer Account / Email',
        help="Customer's PayPal email, Stripe account ID, or bank account number to send money to.",
    )

    # Outcome
    voucher_code = fields.Char(string='Voucher Code', readonly=True)
    payout_reference = fields.Char(
        string='Payout Reference',
        help='PayPal transaction ID or reference. Admin fills this after sending payment manually.',
    )
    approved_by = fields.Many2one(comodel_name='res.users', string='Approved By', readonly=True)
    approved_date = fields.Datetime(string='Approved Date', readonly=True)
    rejection_reason = fields.Text(string='Rejection Reason')

    # ── Computed ──────────────────────────────────────────────────────────

    @api.depends('partner_id')
    def _compute_loyalty_card(self):
        program = self.env.ref('aveenix_rewards.aveenix_ewallet_program', raise_if_not_found=False)
        for rec in self:
            card = False
            if program and rec.partner_id:
                card = self.env['loyalty.card'].search([
                    ('program_id', '=', program.id),
                    ('partner_id', '=', rec.partner_id.id),
                ], limit=1)
            rec.loyalty_card_id = card
            rec.available_points = card.points if card else 0.0

    # ── Constraints ───────────────────────────────────────────────────────

    @api.constrains('points_to_redeem')
    def _check_amount(self):
        for rec in self:
            if rec.points_to_redeem <= 0:
                raise ValidationError('Redemption amount must be greater than 0.')

    @api.constrains('mode', 'recipient_partner_id', 'payment_gateway', 'gateway_account')
    def _check_mode_fields(self):
        for rec in self:
            if rec.mode == 'gift_voucher' and not rec.recipient_partner_id:
                raise ValidationError('Gift Voucher requires a recipient.')
            if rec.mode == 'withdrawal' and not rec.payment_gateway:
                raise ValidationError('Withdrawal requires a payment gateway selection.')
            if rec.mode == 'withdrawal' and not rec.gateway_account:
                raise ValidationError('Withdrawal requires an account / email.')

    def unlink(self):
        if any(rec.state not in ('draft', 'rejected') for rec in self):
            raise UserError('Only draft or rejected redemption requests can be deleted.')
        return super().unlink()

    # ── Workflow buttons ──────────────────────────────────────────────────

    def action_submit(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError('Only draft requests can be submitted.')
            card = rec.loyalty_card_id
            if not card or rec.points_to_redeem > card.points:
                raise UserError(
                    f'Insufficient balance. Available: ₹{rec.available_points:.2f}'
                )
            seq = self.env['ir.sequence'].next_by_code('aveenix.reward.redemption') or 'New'
            # Deduct immediately on submit so balance reflects the pending request
            card.points -= rec.points_to_redeem
            self.env['loyalty.history'].sudo().create({
                'card_id': card.id,
                'description': f'Redemption request submitted ({seq})',
                'issued': 0.0,
                'used': rec.points_to_redeem,
            })
            rec.write({'state': 'submitted', 'name': seq})

    def action_approve(self):
        for rec in self:
            if rec.state != 'submitted':
                raise UserError('Only submitted requests can be approved.')
            payout_ref = rec._execute_redemption()
            # Auto-payout succeeded → paid; no gateway config → approved (manual)
            if rec.mode == 'withdrawal' and not payout_ref:
                next_state = 'approved'
            else:
                next_state = 'paid'
            vals = {
                'state': next_state,
                'approved_by': self.env.user.id,
                'approved_date': fields.Datetime.now(),
            }
            if payout_ref:
                vals['payout_reference'] = payout_ref
            rec.write(vals)

    def action_mark_paid(self):
        """
        Admin calls this after manually sending money (PayPal / Stripe / bank).
        Optionally fills payout_reference before clicking.
        """
        for rec in self:
            if rec.state != 'approved':
                raise UserError('Only approved requests can be marked as paid.')
            rec.write({'state': 'paid'})

    def action_reject_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Reject Request',
            'res_model': 'aveenix.reject.redemption',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_redemption_id': self.id},
        }

    def action_reject(self):
        for rec in self:
            if rec.state not in ('submitted', 'approved'):
                raise UserError('Cannot reject a request in this state.')
            # Refund points back to wallet
            card = rec.loyalty_card_id
            if card:
                card.points += rec.points_to_redeem
                self.env['loyalty.history'].sudo().create({
                    'card_id': card.id,
                    'description': f'Refund: redemption request rejected ({rec.name})',
                    'issued': rec.points_to_redeem,
                    'used': 0.0,
                })
            rec.write({'state': 'rejected'})

    def action_reset_draft(self):
        for rec in self:
            if rec.state != 'rejected':
                raise UserError('Only rejected requests can be reset to draft.')
            rec.write({'state': 'draft'})

    # ── Execution ─────────────────────────────────────────────────────────

    def _execute_redemption(self):
        """Points already deducted at submit. Just execute the mode action."""
        self.ensure_one()
        card = self.loyalty_card_id
        if not card:
            raise UserError('No eWallet card found for this partner.')
        if self.mode == 'platform_voucher':
            self._issue_platform_voucher(card)
            return None
        elif self.mode == 'gift_voucher':
            self._issue_gift_voucher(card)
            return None
        elif self.mode == 'withdrawal':
            return self._trigger_payout()
        return None

    def _issue_platform_voucher(self, card):
        """Create coupon usable at checkout. Points already deducted at submit."""
        program = self.env.ref('aveenix_rewards.aveenix_voucher_program', raise_if_not_found=False)
        if not program:
            raise UserError('Aveenix Platform Vouchers program not found. Reinstall the module.')
        coupon = self.env['loyalty.card'].create({
            'program_id': program.id,
            'partner_id': self.partner_id.id,
            'points': self.points_to_redeem,
        })
        self.voucher_code = coupon.code

    def _issue_gift_voucher(self, card):
        """Credit recipient's wallet. Sender points already deducted at submit."""
        program = self.env.ref('aveenix_rewards.aveenix_ewallet_program')
        recipient_card = self.env['loyalty.card'].search([
            ('program_id', '=', program.id),
            ('partner_id', '=', self.recipient_partner_id.id),
        ], limit=1)
        if not recipient_card:
            recipient_card = self.env['loyalty.card'].create({
                'program_id': program.id,
                'partner_id': self.recipient_partner_id.id,
            })
        recipient_card.points += self.points_to_redeem
        self.env['loyalty.history'].create({
            'card_id': recipient_card.id,
            'description': f'Gift received from {self.partner_id.name} ({self.name})',
            'issued': self.points_to_redeem,
            'used': 0.0,
        })

    def _trigger_payout(self):
        """Trigger gateway payout. Points already deducted at submit."""
        if self.gateway_config_id and self.gateway_account:
            point_value = self.env.company.reward_point_value or 1.0
            payout_amount = self.points_to_redeem * point_value
            return self.gateway_config_id.send_payout(
                amount=payout_amount,
                destination=self.gateway_account,
                description=f'Aveenix Reward Payout - {self.name} - {self.partner_id.name} '
                            f'({self.points_to_redeem} pts × {point_value})',
            )
        return None

    def get_payment_gateway_label(self):
        return dict(self._fields['payment_gateway'].selection).get(self.payment_gateway, self.payment_gateway or '')
