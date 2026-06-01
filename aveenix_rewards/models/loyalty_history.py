from odoo import api, models


class LoyaltyHistory(models.Model):
    _inherit = 'loyalty.history'

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get('skip_zero_loyalty_history'):
            vals_list = [v for v in vals_list if v.get('issued') or v.get('used')]
        return super().create(vals_list)
