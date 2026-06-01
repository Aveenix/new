from odoo import api, fields, models
from odoo.exceptions import ValidationError


class AveenixRewardConfig(models.Model):
    _name = 'aveenix.reward.config'
    _description = 'Aveenix Reward Agreement'
    _rec_name = 'name'
    _order = 'name'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)

    pending_days = fields.Integer(
        string='Hold Period (Days)',
        default=7,
        help='Days a reward stays PENDING before cron auto-approves it.',
    )
    applicable_product_type = fields.Selection(
        selection=[
            ('all', 'All Types'),
            ('dropship', 'Dropship Only'),
            ('standard', 'Standard Only'),
            ('affiliate', 'Affiliate Only'),
        ],
        default='all',
        string='Applicable Product Type',
        required=True,
        help='When used as fallback (no direct partner assignment), only matches orders of this type.',
    )
    date_from = fields.Date(string='Valid From')
    date_to = fields.Date(string='Valid Until')

    distribution_rule_ids = fields.One2many(
        comodel_name='aveenix.reward.distribution.rule',
        inverse_name='config_id',
        string='Distribution Rules',
    )

    # ── Constraints ───────────────────────────────────────────────────────

    @api.constrains('pending_days')
    def _check_pending_days(self):
        for rec in self:
            if rec.pending_days < 0:
                raise ValidationError('Hold Period must be 0 or more days.')

    @api.constrains('distribution_rule_ids')
    def _check_distribution_total(self):
        for rec in self:
            total = sum(rec.distribution_rule_ids.mapped('percentage'))
            if rec.distribution_rule_ids and abs(total - 100.0) > 0.01:
                raise ValidationError(
                    f'Distribution percentages must sum to 100. Current: {total:.2f}%'
                )

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_from and rec.date_to and rec.date_from > rec.date_to:
                raise ValidationError('"Valid From" must be before "Valid Until".')

    # ── Matching ──────────────────────────────────────────────────────────

    @api.model
    def _get_default_config(self):
        """Read admin-selected default from company settings."""
        config = self.env.company.default_reward_config_id
        if config and config.active:
            return config
        return None

    @api.model
    def _find_config_for_order(self, order):
        """
        Priority:
          1. Partner's direct reward_config_id (if set and active)
          2. Admin-selected default from Rewards Settings
        Returns None if neither is set → caller skips reward silently.
        """
        # 1 — partner-level direct assignment
        partner_config = order.partner_id.reward_config_id
        if partner_config and partner_config.active:
            return partner_config

        # 2 — system default from Settings
        return self._get_default_config()
