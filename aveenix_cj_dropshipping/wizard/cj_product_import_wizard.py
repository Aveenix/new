import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class CjProductImportWizard(models.TransientModel):
    _name = 'cj.product.import.wizard'
    _description = 'Import CJ Dropshipping Products'

    import_mode = fields.Selection(
        selection=[
            ('by_my_products', 'Import My Store Products (in English)'),
            ('by_limit', 'Bulk Import My Store Products (in English)'),
            ('by_pid', 'Specific Product (by PID or SKU)'),
        ],
        string='Import Mode',
        default='by_my_products',
        required=True,
    )
    limit_count = fields.Integer(
        string='Number of Products to Import',
        default=20,
        help='How many products to fetch and import (1 to 100).',
    )
    category_id_str = fields.Char(
        string='CJ Category ID (Optional)',
        help='Filter by specific CJ Category ID, or leave empty to import across all products.',
    )
    cj_pid_or_sku = fields.Char(
        string='CJ Product ID (PID) or SKU',
        help='Enter the CJ Product ID (PID) or product SKU from CJ Dropshipping.',
    )
    markup_percentage = fields.Float(
        string='Price Rule Markup (%)',
        default=lambda self: float(
            self.env['ir.config_parameter'].sudo().get_param('aveenix_cj_dropshipping.cj_default_markup_percentage', '20.0')
        ),
        help='Markup percentage to apply over CJ cost price.',
    )

    def action_import_product(self):
        self.ensure_one()
        client = self.env['cj.api.client']

        if self.import_mode in ('by_limit', 'by_my_products'):
            limit = max(1, min(100, self.limit_count or 20))
            res = client.get_my_product_list(
                page_num=1,
                page_size=limit,
            )
            prod_list = res.get('content') or res.get('list') or []

            if not prod_list:
                raise UserError(_("No products returned from CJ Dropshipping catalog."))

            imported_ids = []
            errors = []
            for idx, item in enumerate(prod_list):
                try:
                    tmpl = self.env['product.template'].import_cj_product_dict(
                        prod_dict=item,
                        markup_perc=self.markup_percentage,
                    )
                    if tmpl:
                        imported_ids.append(tmpl.id)
                except Exception as e:
                    pid_err = item.get('pid') or item.get('productId') or idx
                    errors.append(f"PID {pid_err}: {str(e)}")
                    _logger.warning("Failed to import product item from CJ list: %s", str(e))

            if not imported_ids:
                err_msg = "\n".join(errors[:5])
                raise UserError(_("Could not import products from CJ Dropshipping.\nErrors:\n%s") % err_msg)

            return {
                'type': 'ir.actions.act_window',
                'name': _('Imported CJ Products (%s)') % len(imported_ids),
                'res_model': 'product.template',
                'view_mode': 'list,form',
                'domain': [('id', 'in', imported_ids)],
                'target': 'current',
            }
        else:
            val = (self.cj_pid_or_sku or '').strip()
            if not val:
                raise UserError(_("Please enter a CJ Product ID (PID) or SKU."))

            prod_data = False
            try:
                prod_data = client.get_product_detail(pid=val)
            except Exception:
                try:
                    prod_data = client.get_product_detail(sku=val)
                except Exception as e:
                    raise UserError(_("Could not find CJ product with ID/SKU '%s': %s") % (val, str(e)))

            if not prod_data:
                raise UserError(_("No product returned from CJ Dropshipping for '%s'.") % val)

            template = self.env['product.template'].import_cj_product_dict(
                prod_dict=prod_data,
                markup_perc=self.markup_percentage,
            )

            return {
                'type': 'ir.actions.act_window',
                'name': _('Imported CJ Product'),
                'res_model': 'product.template',
                'res_id': template.id,
                'view_mode': 'form',
                'target': 'current',
            }
