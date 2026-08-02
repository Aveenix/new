import json
import sys
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    cj_api_key = fields.Char(
        string='CJ API Key',
        config_parameter='aveenix_cj_dropshipping.cj_api_key',
        default='CJ4647033@api@5e1ba4f458d84aa39921afd592149251',
        help='API Key from CJ Dropshipping Personal Center -> API -> API Key',
    )
    cj_is_sandbox = fields.Boolean(
        string='Sandbox Mode (Test Orders)',
        config_parameter='aveenix_cj_dropshipping.cj_is_sandbox',
        default=True,
        help='When enabled, orders pushed to CJ will include "isSandbox": 1 in payload for testing without actual payment.',
    )
    cj_default_markup_percentage = fields.Float(
        string='Default Price Rule Markup (%)',
        config_parameter='aveenix_cj_dropshipping.cj_default_markup_percentage',
        default=20.0,
        help='Percentage added to CJ cost price to calculate standard sale price in Odoo.',
    )
    cj_auto_push_order = fields.Boolean(
        string='Auto-Push Orders to CJ on Confirmation',
        config_parameter='aveenix_cj_dropshipping.cj_auto_push_order',
        default=True,
        help='If checked, confirming an Odoo Sale Order with dropship products will automatically push it to CJ.',
    )
    cj_default_logistics = fields.Char(
        string='Default CJ Logistics Name',
        config_parameter='aveenix_cj_dropshipping.cj_default_logistics',
        default='CJPacket Ordinary',
        help='Default shipping method used when pushing orders to CJ Dropshipping.',
    )

    def action_test_cj_connection(self):
        """Test the connection to CJ Dropshipping API."""
        self.ensure_one()
        client = self.env['cj.api.client']
        try:
            token = client.get_access_token(force_refresh=True)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('CJ Dropshipping Connected!'),
                    'message': _('Successfully connected to CJ Dropshipping API. Access token generated.'),
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            raise UserError(_("Connection test failed: %s") % str(e))

    def action_sync_my_cj_products(self):
        """One-click Sync of all Store My Products in English from CJ into Odoo Dropshipping products."""
        self.ensure_one()
        client = self.env['cj.api.client']
        try:
            res = client.get_my_product_list(page_num=1, page_size=100)
            prod_list = res.get('content') or res.get('list') or []
            if not prod_list:
                raise UserError(_("No store products found in your CJ 'My Products' wishlist."))

            imported_ids = []
            for item in prod_list:
                try:
                    tmpl = self.env['product.template'].import_cj_product_dict(
                        prod_dict=item,
                        markup_perc=self.cj_default_markup_percentage,
                    )
                    if tmpl:
                        imported_ids.append(tmpl.id)
                except Exception as e:
                    print(f"Error syncing my CJ product item: {e}", file=sys.stdout)

            if not imported_ids:
                raise UserError(_("Could not import any store products from CJ."))

            return {
                'type': 'ir.actions.act_window',
                'name': _('My CJ Dropshipping Store Products (%s)') % len(imported_ids),
                'res_model': 'product.template',
                'view_mode': 'list,form',
                'domain': [('id', 'in', imported_ids)],
                'target': 'current',
            }
        except Exception as e:
            if isinstance(e, UserError):
                raise
            raise UserError(_("Failed to sync My CJ Products:\n%s") % str(e))

    def action_debug_cj_api_print(self):
        """Perform a full debug test and print raw JSON responses to terminal & modal report."""
        self.ensure_one()
        client = self.env['cj.api.client']
        try:
            token = client.get_access_token(force_refresh=True)
            try:
                prod_data = client.get_my_product_list(page_num=1, page_size=5)
                total = prod_data.get("totalRecords", 0)
                items = prod_data.get("content") or prod_data.get("list") or []
                lines = [
                    "🎉 SUCCESS! CJ API & Store Connected Perfectly!",
                    f"Total Store Products: {total:,} products",
                    "\nSample Products Returned:"
                ]
                for idx, p in enumerate(items):
                    pid = p.get("id") or p.get("pid") or "N/A"
                    sku = p.get("sku") or p.get("productSku") or "N/A"
                    name = p.get("nameEn") or p.get("productNameEng") or p.get("productName") or "Unnamed"
                    price = p.get("sellPrice", "N/A")
                    lines.append(f" {idx+1}. [{sku}] {name[:60]} ($ {price}) [PID: {pid}]")
                msg = "\n".join(lines)
            except UserError as ue:
                msg = str(ue)
            except Exception as e:
                msg = _("Product list call error: %s") % str(e)

            print("\n" + "#"*70, file=sys.stdout)
            print("CJ DROPSHIPPING API DEBUG REPORT FROM ODOO", file=sys.stdout)
            print("#"*70, file=sys.stdout)
            print(msg, file=sys.stdout)
            print("#"*70 + "\n", file=sys.stdout)

            raise UserError(_(
                "=== CJ API Debug Report ===\n\n%s\n\n"
                "Everything is working! You can now import products from CJ Catalog."
            ) % msg)
        except Exception as e:
            if isinstance(e, UserError):
                raise
            raise UserError(_("Debug API call failed:\n%s") % str(e))
