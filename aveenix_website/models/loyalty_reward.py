from odoo import api, models


class LoyaltyReward(models.Model):
    _inherit = 'loyalty.reward'

    @api.depends('program_id')
    def _compute_description(self):
        """Say "your first order" for the welcome discount.

        The core description computes "<amount> on your order"; for our
        first-order welcome reward we make the wording explicit so the cart
        promo/claim label reads "... on your first order".
        """
        super()._compute_description()
        welcome = self.env.ref(
            'aveenix_website.loyalty_reward_welcome_discount',
            raise_if_not_found=False,
        )
        if not welcome:
            return
        for reward in self.filtered(lambda r: r == welcome and r.description):
            # Core builds ".. on your order"; make it ".. on your first order".
            reward.description = reward.description.replace(
                'your order', 'your first order'
            )
