from datetime import date
from odoo import api, fields, models
from odoo.exceptions import UserError


class AveenixRewardRecord(models.Model):
    _name = 'aveenix.reward.record'
    _description = 'Aveenix Reward Record'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'
    _order = 'id desc'

    name = fields.Char(
        string='Reference', readonly=True, copy=False,
        default=lambda self: self.env['ir.sequence'].next_by_code('aveenix.reward.record'),
    )
    state = fields.Selection(
        selection=[
            ('pending', 'Pending'),
            ('approved', 'Approved'),
            ('reversed', 'Reversed'),
            ('cancelled', 'Cancelled'),
        ],
        default='pending', tracking=True, required=True,
    )

    sale_order_id = fields.Many2one(
        comodel_name='sale.order', string='Sale Order',
        required=True, ondelete='restrict', index=True,
    )
    partner_id = fields.Many2one(
        comodel_name='res.partner', string='Recipient',
        required=True, index=True,
    )
    participant_type = fields.Selection(
        selection=[
            ('customer', 'Customer'),
            ('affiliate', 'Affiliate Partner'),
            ('smb', 'SMB Partner'),
            ('platform', 'Platform (Internal)'),
        ],
        required=True,
    )

    product_type = fields.Selection(
        selection=[
            ('dropship', 'Dropship'),
            ('standard', 'Standard'),
            ('affiliate', 'Affiliate'),
        ],
        string='Product Type at Confirm',
    )

    # Financial snapshot
    locked_cost = fields.Float(string='Locked Cost', digits='Product Price')
    selling_price = fields.Float(string='Selling Price (subtotal)', digits='Product Price')
    margin = fields.Float(string='Margin', digits='Product Price')
    commission_received = fields.Float(string='Commission Received', digits='Product Price')
    reward_pool_perc = fields.Float(string='Product Pool %')
    reward_pool = fields.Float(string='Reward Pool', digits='Product Price')
    reward_amount = fields.Float(string='Reward Amount', digits='Product Price', tracking=True)
    distribution_perc = fields.Float(string='Distribution %')

    # Dates
    confirm_date = fields.Datetime(string='Order Confirm Date')
    auto_approve_date = fields.Date(
        string='Eligible for Auto-Approval',
        compute='_compute_auto_approve_date', store=True,
    )
    approved_date = fields.Datetime(string='Approved Date', readonly=True)
    reversed_date = fields.Datetime(string='Reversed Date', readonly=True)

    # Wallet link
    loyalty_card_id = fields.Many2one(
        comodel_name='loyalty.card', string='eWallet Card',
        readonly=True,
    )
    config_id = fields.Many2one(
        comodel_name='aveenix.reward.config', string='Config Snapshot',
    )
    pending_days = fields.Integer(string='Hold Days (at confirm)')

    # ── computed ──────────────────────────────────────────────────────────

    def unlink(self):
        if any(rec.state != 'pending' for rec in self):
            raise UserError('Only pending rewards can be deleted.')
        return super().unlink()

    @api.depends('confirm_date', 'pending_days')
    def _compute_auto_approve_date(self):
        from datetime import timedelta
        for rec in self:
            if rec.confirm_date and rec.pending_days is not None:
                rec.auto_approve_date = rec.confirm_date.date() + timedelta(days=rec.pending_days)
            else:
                rec.auto_approve_date = False

    # ── actions ───────────────────────────────────────────────────────────

    def button_approve(self):
        """Approve reward: credit loyalty.card and set state=approved."""
        for rec in self:
            if rec.state != 'pending':
                raise UserError(f'Reward {rec.name} is not in Pending state.')
            rec._credit_wallet()
            rec.write({
                'state': 'approved',
                'approved_date': fields.Datetime.now(),
            })

    def button_cancel(self):
        for rec in self:
            if rec.state not in ('pending',):
                raise UserError('Only pending rewards can be cancelled.')
            rec.write({'state': 'cancelled'})

    def button_reset_to_draft(self):
        for rec in self:
            if rec.state != 'cancelled':
                raise UserError('Only cancelled rewards can be reset to draft.')
            rec.write({'state': 'pending'})

    def button_reverse(self):
        """Manually reverse an approved reward."""
        for rec in self:
            if rec.state != 'approved':
                raise UserError(f'Only approved rewards can be reversed. Current state: {rec.state}')
            rec._debit_wallet()
            rec.write({
                'state': 'reversed',
                'reversed_date': fields.Datetime.now(),
            })

    @api.model
    def action_auto_approve(self):
        """Called daily by ir.cron — approves all eligible pending rewards."""
        today = date.today()
        pending = self.search([
            ('state', '=', 'pending'),
            ('auto_approve_date', '<=', today),
        ])
        for rec in pending:
            try:
                rec.button_approve()
            except Exception as e:
                rec.message_post(body=f'Auto-approval failed: {e}')

    # ── wallet helpers ────────────────────────────────────────────────────

    def _get_ewallet_program(self):
        program = self.env.ref('aveenix_rewards.aveenix_ewallet_program', raise_if_not_found=False)
        if not program:
            raise UserError('Aveenix eWallet loyalty program not found. Reinstall the module or check seed data.')
        return program

    def _get_or_create_loyalty_card(self, partner):
        program = self._get_ewallet_program()
        card = self.env['loyalty.card'].search([
            ('program_id', '=', program.id),
            ('partner_id', '=', partner.id),
        ], limit=1)
        if not card:
            card = self.env['loyalty.card'].create({
                'program_id': program.id,
                'partner_id': partner.id,
            })
        return card

    def _credit_wallet(self):
        for rec in self:
            if rec.participant_type == 'platform':
                continue
            card = rec._get_or_create_loyalty_card(rec.partner_id)
            card.points += rec.reward_amount
            self.env['loyalty.history'].create({
                'card_id': card.id,
                'description': f'Reward approved: {rec.name} (Order {rec.sale_order_id.name})',
                'issued': rec.reward_amount,
                'used': 0.0,
                'order_model': 'sale.order',
                'order_id': rec.sale_order_id.id,
            })
            rec.loyalty_card_id = card

    def _debit_wallet(self):
        for rec in self:
            if rec.participant_type == 'platform':
                continue
            if rec.loyalty_card_id:
                rec.loyalty_card_id.points -= rec.reward_amount
                self.env['loyalty.history'].create({
                    'card_id': rec.loyalty_card_id.id,
                    'description': f'Reward reversed: {rec.name} (Order {rec.sale_order_id.name})',
                    'issued': 0.0,
                    'used': rec.reward_amount,
                    'order_model': 'sale.order',
                    'order_id': rec.sale_order_id.id,
                })
