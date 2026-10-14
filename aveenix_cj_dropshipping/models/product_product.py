from odoo import fields, models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    cj_vid = fields.Char(
        string='CJ Variant ID (VID)',
        index=True,
        copy=False,
        help='Unique identifier of this specific product variant in CJ Dropshipping',
    )
    is_cj_dropship = fields.Boolean(
        string='Is CJ Dropship Variant',
        related='product_tmpl_id.is_cj_dropship',
        store=True,
        readonly=True,
    )

    def action_sync_cj_product(self):
        """Sync this product with CJ Dropshipping via its template."""
        self.ensure_one()
        return self.product_tmpl_id.action_sync_cj_product()
