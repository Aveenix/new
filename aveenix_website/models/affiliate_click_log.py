from odoo import fields, models


class AffiliateClickLog(models.Model):
    _name = 'affiliate.click.log'
    _description = 'Affiliate Link Click Log'
    _order = 'timestamp desc'
    _rec_name = 'product_id'

    product_id = fields.Many2one(
        comodel_name='product.template',
        string='Product',
        index=True,
        ondelete='cascade',
        help='Set for clicks on an outbound product link. Empty for clicks on '
             'an affiliate offer placed in a news article, which record '
             'offer_id instead (see aveenix_affiliate_engine).',
    )
    timestamp = fields.Datetime(
        string='Clicked On',
        default=lambda self: fields.Datetime.now(),
        readonly=True,
        index=True,
    )
    user_id = fields.Many2one(
        comodel_name='res.users',
        string='User',
        help='Logged-in user, if any. Empty for anonymous visitors.',
        index=True,
    )
    session_id = fields.Char(
        string='Session ID',
        index=True,
        help='Web session identifier for anonymous click tracking.',
    )
    referrer_url = fields.Char(
        string='Referrer URL',
        help='Page the visitor came from when clicking the affiliate link.',
    )
    affiliate_url = fields.Char(
        string='Affiliate URL',
        help='The external link that was opened.',
    )
