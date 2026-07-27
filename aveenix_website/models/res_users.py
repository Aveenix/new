from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    av_compare_product_ids = fields.Many2many(
        'product.template',
        'av_user_compare_rel',
        'user_id', 'product_id',
        string='Compare List',
    )
    av_fav_product_ids = fields.Many2many(
        'product.template',
        'av_user_fav_rel',
        'user_id', 'product_id',
        string='Favourites',
    )
    av_wish_product_ids = fields.Many2many(
        'product.template',
        'av_user_wish_rel',
        'user_id', 'product_id',
        string='Aveenix Wishlist',
    )
