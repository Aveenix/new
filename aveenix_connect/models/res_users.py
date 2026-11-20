from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    # Written only by the Connect controller, for the logged-in user.
    connect_favourite_ids = fields.Many2many(
        'connect.business', 'connect_business_favourite_rel', 'user_id', 'business_id',
        string='Favourite Connect Listings',
    )
