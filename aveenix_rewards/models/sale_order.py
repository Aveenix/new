from odoo import api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    reward_record_ids = fields.One2many(
        comodel_name='aveenix.reward.record',
        inverse_name='sale_order_id',
        string='Reward Records',
    )
    reward_count = fields.Integer(compute='_compute_reward_count')

    commission_received = fields.Float(
        string='Commission Received',
        digits='Product Price',
        help='Amount received from external affiliate network. Fill to trigger affiliate reward calculation.',
    )
    commission_confirmed = fields.Boolean(
        string='Commission Confirmed', default=False, readonly=True,
    )

    has_affiliate_lines = fields.Boolean(compute='_compute_has_affiliate_lines')

    @api.depends('reward_record_ids')
    def _compute_reward_count(self):
        for order in self:
            order.reward_count = len(order.reward_record_ids)

    @api.depends('order_line.product_id.product_tmpl_id.aveenix_product_type')
    def _compute_has_affiliate_lines(self):
        for order in self:
            order.has_affiliate_lines = any(
                l.product_id.product_tmpl_id.aveenix_product_type == 'affiliate'
                for l in order.order_line
            )

    def _add_loyalty_history_lines(self):
        self = self.with_context(skip_zero_loyalty_history=True)
        super()._add_loyalty_history_lines()

    # ── action_confirm override ───────────────────────────────────────────

    def action_confirm(self):
        res = super().action_confirm()
        for order in self:
            order._generate_rewards_on_confirm()
        return res

    def _generate_rewards_on_confirm(self):
        """
        Per order line: lock cost, calc margin, find matching config, create reward records.
        Reward pool % comes from the product itself (product.reward_pool_perc).
        Affiliate lines skip — wait for action_confirm_commission().
        """
        ConfigModel = self.env['aveenix.reward.config']

        for line in self.order_line:
            product = line.product_id.product_tmpl_id
            ptype = product.aveenix_product_type
            if ptype not in ('dropship', 'standard'):
                continue
            if not product.reward_pool_perc:
                continue  # product has no pool % configured — skip silently

            config = ConfigModel._find_config_for_order(self)
            if not config:
                continue  # no matching agreement — skip silently

            locked_cost = line.product_id.standard_price
            subtotal = line.price_subtotal
            margin = subtotal - (locked_cost * line.product_uom_qty)
            if margin <= 0:
                continue

            reward_pool = margin * product.reward_pool_perc / 100.0
            self._create_reward_records(
                config=config,
                reward_pool=reward_pool,
                product_type=ptype,
                locked_cost=locked_cost,
                selling_price=subtotal,
                margin=margin,
                commission_received=0.0,
                reward_pool_perc=product.reward_pool_perc,
            )

    def action_confirm_commission(self):
        """UI button — admin confirms affiliate commission received from external network."""
        self.ensure_one()
        if self.commission_confirmed:
            raise UserError('Commission has already been confirmed for this order.')
        if not self.commission_received or self.commission_received <= 0:
            raise UserError('Enter a positive Commission Received amount before confirming.')

        affiliate_lines = [
            l for l in self.order_line
            if l.product_id.product_tmpl_id.aveenix_product_type == 'affiliate'
        ]
        if not affiliate_lines:
            raise UserError('No affiliate-type products found on this order.')

        ConfigModel = self.env['aveenix.reward.config']

        for line in affiliate_lines:
            product = line.product_id.product_tmpl_id
            if not product.reward_pool_perc:
                continue

            config = ConfigModel._find_config_for_order(self)
            if not config:
                continue

            # Distribute received commission proportionally across affiliate lines
            line_ratio = line.price_subtotal / sum(
                l.price_subtotal for l in affiliate_lines
            ) if len(affiliate_lines) > 1 else 1.0
            line_commission = self.commission_received * line_ratio
            reward_pool = line_commission * product.reward_pool_perc / 100.0

            self._create_reward_records(
                config=config,
                reward_pool=reward_pool,
                product_type='affiliate',
                locked_cost=0.0,
                selling_price=line.price_subtotal,
                margin=0.0,
                commission_received=line_commission,
                reward_pool_perc=product.reward_pool_perc,
            )

        self.commission_confirmed = True

    def _create_reward_records(
        self, config, reward_pool, product_type,
        locked_cost, selling_price, margin, commission_received, reward_pool_perc,
    ):
        RecordModel = self.env['aveenix.reward.record']
        for rule in config.distribution_rule_ids:
            amount = reward_pool * rule.percentage / 100.0
            partner = self._resolve_rule_partner(rule)
            if not partner:
                continue
            RecordModel.create({
                'name': self.env['ir.sequence'].next_by_code('aveenix.reward.record'),
                'state': 'pending',
                'sale_order_id': self.id,
                'partner_id': partner.id,
                'participant_type': rule.participant_type,
                'product_type': product_type,
                'locked_cost': locked_cost,
                'selling_price': selling_price,
                'margin': margin,
                'commission_received': commission_received,
                'reward_pool': reward_pool,
                'reward_pool_perc': reward_pool_perc,
                'reward_amount': amount,
                'distribution_perc': rule.percentage,
                'confirm_date': self.date_order or fields.Datetime.now(),
                'config_id': config.id,
                'pending_days': config.pending_days,
            })

    def _resolve_rule_partner(self, rule):
        if rule.partner_id:
            return rule.partner_id
        if rule.participant_type == 'customer':
            return self.partner_id
        if rule.participant_type == 'affiliate':
            affiliate = self.partner_id if self.partner_id.affiliated else False
            if not affiliate and self.partner_id.parent_id and self.partner_id.parent_id.affiliated:
                affiliate = self.partner_id.parent_id
            return affiliate or False
        if rule.participant_type == 'smb':
            return self.user_id.partner_id if self.user_id else False
        if rule.participant_type == 'platform':
            return self.company_id.partner_id
        return False

    def action_view_rewards(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Reward Records',
            'res_model': 'aveenix.reward.record',
            'view_mode': 'list,form',
            'domain': [('sale_order_id', '=', self.id)],
            'context': {'default_sale_order_id': self.id},
        }
