import base64
import json
import logging
import re
import requests
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


def _download_image_base64(url):
    """Download an image from a URL and return it as base64 ascii string."""
    if not url or not isinstance(url, str):
        return False
    url = url.strip()
    if not (url.startswith('http://') or url.startswith('https://')):
        return False
    try:
        resp = requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        if resp.status_code == 200 and resp.content:
            return base64.b64encode(resp.content).decode('ascii')
    except Exception as e:
        _logger.warning("Failed to download image from %s: %s", url, str(e))
    return False


def _parse_image_urls(prod_dict):
    """Extract a clean, ordered list of unique image URLs from CJ product dictionary."""
    if not prod_dict:
        return []
    urls = []

    def _add_url(u):
        if u and isinstance(u, str):
            u = u.strip()
            if u.startswith('http://') or u.startswith('https://'):
                if u not in urls:
                    urls.append(u)

    def _parse_val(val):
        if not val:
            return
        if isinstance(val, list):
            for item in val:
                _parse_val(item)
        elif isinstance(val, str):
            val_str = val.strip()
            if val_str.startswith('[') and val_str.endswith(']'):
                try:
                    arr = json.loads(val_str)
                    if isinstance(arr, list):
                        for item in arr:
                            _parse_val(item)
                        return
                except Exception:
                    pass
            for part in re.split(r'[,;\n\r]+', val_str):
                _add_url(part)

    # 1. Primary image fields in CJ API
    _parse_val(prod_dict.get('productImageSet'))
    _parse_val(prod_dict.get('productImage'))
    _parse_val(prod_dict.get('image'))
    _parse_val(prod_dict.get('img'))
    _parse_val(prod_dict.get('productImageEn'))
    _parse_val(prod_dict.get('images'))

    # 2. Variant images as additional/fallback
    for var in (prod_dict.get('variants') or []):
        if isinstance(var, dict):
            _parse_val(var.get('variantImage'))
            _parse_val(var.get('img'))
            _parse_val(var.get('image'))

    return urls



def _parse_price(val):
    if not val:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).split('--')[0].split('-')[0].strip()
    m = re.search(r'[\d.]+', s)
    try:
        return float(m.group(0)) if m else 0.0
    except Exception:
        return 0.0


def _parse_name(val, default_name):
    if not val:
        return default_name
    if isinstance(val, list) and val:
        return str(val[0])
    s = str(val).strip()
    if s.startswith('[') and s.endswith(']'):
        try:
            arr = json.loads(s)
            if isinstance(arr, list) and arr:
                return str(arr[0])
        except Exception:
            pass
    return s


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    cj_pid = fields.Char(
        string='CJ Product ID (PID)',
        index=True,
        copy=False,
        help='Unique identifier of the product in CJ Dropshipping',
    )
    cj_cost_price = fields.Float(
        string='CJ Supplier Cost ($)',
        default=0.0,
        help='Original cost price provided by CJ Dropshipping',
    )
    cj_markup_percentage = fields.Float(
        string='Price Rule Markup (%)',
        default=0.0,
        help='Specific markup percentage applied to CJ cost. If 0.0, default system markup is used.',
    )
    is_cj_dropship = fields.Boolean(
        string='Is CJ Dropship Product',
        compute='_compute_is_cj_dropship',
        store=True,
    )

    @api.depends('aveenix_product_type', 'cj_pid')
    def _compute_is_cj_dropship(self):
        for rec in self:
            rec.is_cj_dropship = bool(rec.cj_pid) or (rec.aveenix_product_type == 'dropship')

    @api.onchange('cj_cost_price', 'cj_markup_percentage')
    def _onchange_cj_price_rule(self):
        for rec in self:
            if rec.cj_cost_price > 0:
                markup = rec.cj_markup_percentage
                if markup <= 0:
                    ICP = self.env['ir.config_parameter'].sudo()
                    markup = float(ICP.get_param('aveenix_cj_dropshipping.cj_default_markup_percentage', '20.0'))
                rec.list_price = round(rec.cj_cost_price * (1.0 + (markup / 100.0)), 2)
                rec.standard_price = rec.cj_cost_price

    @api.model
    def import_cj_product_dict(self, prod_dict, markup_perc=None):
        """Create or update an Odoo product from a CJ API dictionary."""
        if not prod_dict:
            return False

        pid = str(prod_dict.get('id') or prod_dict.get('pid') or prod_dict.get('productId') or '').strip()
        if not pid:
            raise UserError(_("Invalid CJ product data: missing PID."))

        sku = str(prod_dict.get('sku') or prod_dict.get('productSku') or '').strip()

        ICP = self.env['ir.config_parameter'].sudo()
        if markup_perc is None:
            markup_perc = float(ICP.get_param('aveenix_cj_dropshipping.cj_default_markup_percentage', '20.0'))

        # Check if already imported by PID or SKU to prevent duplicates
        domain = [('cj_pid', '=', pid)]
        if sku and pid:
            domain = ['|', ('cj_pid', '=', pid), ('default_code', '=', sku)]
        existing = self.search(domain, limit=1)

        raw_name = prod_dict.get('nameEn') or prod_dict.get('productNameEng') or prod_dict.get('productNameEn') or prod_dict.get('productName')
        name = _parse_name(raw_name, _("CJ Product %s") % pid)
        cost = _parse_price(prod_dict.get('sellPrice') or prod_dict.get('productPrice'))
        sale_price = round(cost * (1.0 + (markup_perc / 100.0)), 2)

        vals = {
            'name': name,
            'cj_pid': pid,
            'default_code': sku or pid,
            'cj_cost_price': cost,
            'cj_markup_percentage': markup_perc,
            'list_price': sale_price,
            'standard_price': cost,
            'aveenix_product_type': 'dropship',
            'type': 'consu',  # Consumable / Physical in Odoo 19
        }

        # Weight if available
        weight = _parse_price(prod_dict.get('productWeight') or prod_dict.get('weight'))
        if weight > 0:
            vals['weight'] = weight / 1000.0 if weight > 100 else weight

        if existing:
            existing.write(vals)
            template = existing
        else:
            template = self.create(vals)

        # Handle Variants if present
        variants = prod_dict.get('variants') or []
        if not variants and not (prod_dict.get('vid') or prod_dict.get('sku') or prod_dict.get('productSku')):
            try:
                variants = self.env['cj.api.client'].get_product_variants(pid=pid)
            except Exception as e:
                _logger.warning("Could not fetch variants for CJ product %s: %s", pid, str(e))

        if len(template.product_variant_ids) == 1:
            first_variant = template.product_variant_ids[0]
            vid_val = False
            sku_val = False
            if variants and isinstance(variants, list) and len(variants) > 0 and variants[0]:
                vid_val = variants[0].get('vid')
                sku_val = variants[0].get('variantSku') or variants[0].get('sku')
            
            if not vid_val:
                vid_val = prod_dict.get('vid') or prod_dict.get('defaultVid') or pid
            if not sku_val:
                sku_val = prod_dict.get('sku') or prod_dict.get('productSku') or pid

            first_variant.write({
                'cj_vid': str(vid_val),
                'default_code': str(sku_val),
            })

        # --- 3. Sync Product Images (Main Image + 7-8 Extra Gallery Images) ---
        try:
            image_urls = _parse_image_urls(prod_dict)
            # If we only got 0 or 1 image from a summary list and Odoo has no extra media yet, fetch full details from CJ API
            if len(image_urls) <= 1 and len(template.product_template_image_ids) == 0:
                try:
                    full_detail = self.env['cj.api.client'].get_product_detail(pid=pid)
                    if full_detail:
                        more_urls = _parse_image_urls(full_detail)
                        if len(more_urls) > len(image_urls):
                            image_urls = more_urls
                except Exception as ex_detail:
                    _logger.warning("Could not fetch full product detail for extra images of PID %s: %s", pid, str(ex_detail))

            if image_urls:
                # 1. Main product image (image_1920)
                if not template.image_1920 and image_urls[0]:
                    img_b64 = _download_image_base64(image_urls[0])
                    if img_b64:
                        template.image_1920 = img_b64

                # 2. Extra media gallery (product_template_image_ids -> product.image)
                existing_count = len(template.product_template_image_ids)
                if existing_count < len(image_urls) - 1:
                    ProductImage = self.env['product.image'].sudo()
                    for idx, img_url in enumerate(image_urls[1:], start=1):
                        if idx > existing_count:
                            img_b64 = _download_image_base64(img_url)
                            if img_b64:
                                ProductImage.create({
                                    'name': f"{template.name} - Image {idx+1}",
                                    'image_1920': img_b64,
                                    'product_tmpl_id': template.id,
                                    'sequence': idx * 10,
                                })
        except Exception as e_img:
            _logger.warning("Error importing images for CJ product %s: %s", pid, str(e_img))

        return template

    def action_sync_cj_product(self):
        """Fetch latest cost price and details from CJ Dropshipping API."""
        self.ensure_one()
        if not self.cj_pid:
            raise UserError(_("This product does not have a CJ Product ID (PID) configured."))

        client = self.env['cj.api.client']
        data = client.get_product_detail(pid=self.cj_pid)
        if data:
            self.import_cj_product_dict(data, markup_perc=self.cj_markup_percentage or None)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Product Synced!'),
                    'message': _('Successfully synced "%s" from CJ Dropshipping.') % self.name,
                    'type': 'success',
                    'sticky': False,
                }
            }
        raise UserError(_("Could not retrieve product details from CJ."))

    @api.model
    def _cron_sync_cj_my_products(self):
        """Cron job to automatically sync My Products from CJ Dropshipping into Odoo."""
        client = self.env['cj.api.client']
        try:
            res = client.get_my_product_list(page_num=1, page_size=50)
            prod_list = res.get('content') or res.get('list') or []
            imported_count = 0
            for item in prod_list:
                try:
                    tmpl = self.import_cj_product_dict(prod_dict=item, markup_perc=0.0)
                    if tmpl:
                        imported_count += 1
                except Exception as e:
                    _logger.warning("Cron sync product failed for PID %s: %s", item.get('pid'), str(e))
            _logger.info("CJ Cron Product Sync completed: imported/updated %d products", imported_count)
        except Exception as e:
            _logger.error("Failed to run CJ cron product sync: %s", str(e))

