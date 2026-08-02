import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    cj_order_id = fields.Char(
        string='CJ Order ID',
        copy=False,
        index=True,
        help='Unique order ID returned by CJ Dropshipping API',
    )
    cj_order_number = fields.Char(
        string='CJ Order Number',
        copy=False,
        index=True,
        help='Order number reference in CJ Dropshipping',
    )
    cj_order_status = fields.Selection(
        selection=[
            ('draft', 'Not Pushed'),
            ('CREATED', 'Created in CJ'),
            ('UNPAID', 'Unpaid'),
            ('PAID', 'Paid'),
            ('UNSHIPPED', 'Unshipped / Processing'),
            ('PROCESSING', 'Processing'),
            ('IN_PROCESS', 'In Process'),
            ('DISPATCHED', 'Dispatched'),
            ('SHIPPED', 'Shipped'),
            ('DELIVERED', 'Delivered'),
            ('COMPLETED', 'Completed'),
            ('CLOSED', 'Closed'),
            ('CANCELLED', 'Cancelled'),
            ('REFUNDED', 'Refunded'),
            ('FAILED', 'Failed'),
        ],
        string='CJ Status',
        default='draft',
        copy=False,
        tracking=True,
    )
    cj_tracking_number = fields.Char(
        string='CJ Tracking Number',
        copy=False,
        tracking=True,
        help='Shipping tracking number provided by CJ Dropshipping',
    )
    cj_tracking_link = fields.Char(
        string='CJ Tracking Link',
        copy=False,
        tracking=True,
        help='URL to track package shipment',
    )
    cj_logistics_name = fields.Char(
        string='CJ Logistics Name',
        default=lambda self: self.env['ir.config_parameter'].sudo().get_param(
            'aveenix_cj_dropshipping.cj_default_logistics', 'CJPacket Ordinary'
        ),
        help='Carrier / shipping method name in CJ Dropshipping',
    )
    cj_error_message = fields.Text(
        string='CJ Error Log',
        copy=False,
        readonly=True,
    )
    has_cj_dropship_lines = fields.Boolean(
        string='Has CJ Dropship Lines',
        compute='_compute_has_cj_dropship_lines',
        store=True,
    )

    @api.depends('order_line.product_id.is_cj_dropship', 'order_line.product_id.cj_vid', 'order_line.product_id.cj_pid', 'order_line.product_id.default_code')
    def _compute_has_cj_dropship_lines(self):
        for order in self:
            is_dropship = False
            for line in order.order_line:
                product = line.product_id
                sku = product.default_code or ''
                if product.is_cj_dropship or product.cj_vid or product.cj_pid or product.product_tmpl_id.cj_pid or sku.upper().startswith('CJ'):
                    is_dropship = True
                    break
            order.has_cj_dropship_lines = is_dropship

    def _prepare_cj_order_payload(self):
        """Prepare JSON payload for CJ createOrderV3 / createOrderV2."""
        self.ensure_one()
        ICP = self.env['ir.config_parameter'].sudo()
        is_sandbox = 1 if ICP.get_param('aveenix_cj_dropshipping.cj_is_sandbox', 'True') == 'True' else 0
        default_carrier = ICP.get_param('aveenix_cj_dropshipping.cj_default_logistics', 'CJPacket Ordinary')

        partner = self.partner_shipping_id or self.partner_id
        country_code = getattr(partner.country_id, 'code', 'US') or 'US'
        country_name = getattr(partner.country_id, 'name', 'United States') or 'United States'
        state_name = getattr(partner.state_id, 'name', '') or getattr(partner, 'city', '') or 'State'
        city_name = getattr(partner, 'city', '') or 'City'
        zip_code = getattr(partner, 'zip', '') or '00000'
        phone = getattr(partner, 'phone', False) or getattr(partner, 'mobile', False) or getattr(partner, 'phone_sanitized', False) or '0000000000'
        address = getattr(partner, 'street', '') or 'Address Line 1'
        address2 = getattr(partner, 'street2', '') or ''

        # Collect dropship products
        products_payload = []
        for line in self.order_line:
            product = line.product_id
            sku = product.default_code or ''
            if product.is_cj_dropship or product.cj_vid or product.cj_pid or product.product_tmpl_id.cj_pid or sku.upper().startswith('CJ'):
                vid_val = product.cj_vid or product.cj_pid or product.product_tmpl_id.cj_pid or product.default_code
                if not vid_val:
                    raise UserError(_("Product '%s' is marked as dropship but has no CJ VID or SKU.") % product.display_name)
                products_payload.append({
                    "vid": str(vid_val),
                    "quantity": int(line.product_uom_qty),
                    "storeLineItemId": str(line.id),
                })

        if not products_payload:
            raise UserError(_("No valid CJ Dropshipping items found on this order."))

        payload = {
            "orderNumber": str(self.name),
            "shippingCountryCode": country_code,
            "shippingCountry": country_name,
            "shippingProvince": state_name,
            "shippingCity": city_name,
            "shippingZip": zip_code,
            "shippingPhone": phone,
            "shippingCustomerName": partner.name or "Customer",
            "shippingAddress": address,
            "shippingAddress2": address2,
            "email": partner.email or "",
            "remark": self.note or "Odoo Order",
            "logisticName": self.cj_logistics_name or default_carrier,
            "fromCountryCode": "CN",
            "isSandbox": is_sandbox,
            "is_sandbox": is_sandbox,
            "products": products_payload,
        }
        return payload

    def action_push_to_cj(self):
        """Push Sale Order to CJ Dropshipping API."""
        client = self.env['cj.api.client']
        for order in self:
            if not order.has_cj_dropship_lines:
                raise UserError(_("Order %s does not contain any CJ Dropship products.") % order.name)

            try:
                payload = order._prepare_cj_order_payload()
                res = client.create_order(payload)

                order_id = res.get('orderId') or res.get('orderNumber') or str(order.name)
                order_num = res.get('orderNumber') or res.get('orderId') or str(order.name)

                order.write({
                    'cj_order_id': str(order_id),
                    'cj_order_number': str(order_num),
                    'cj_order_status': 'CREATED',
                    'cj_error_message': False,
                })

                is_sandbox_str = _("Yes (Sandbox Test Mode)") if payload.get('isSandbox') == 1 else _("No (Live Mode)")
                order.message_post(
                    body=_("<b>Order Pushed to CJ Dropshipping!</b><br/>"
                           "<b>CJ Order ID:</b> %s<br/>"
                           "<b>CJ Order Number:</b> %s<br/>"
                           "<b>Sandbox Mode:</b> %s") % (order.cj_order_id, order.cj_order_number, is_sandbox_str)
                )
            except Exception as e:
                err_msg = str(e)
                order.write({'cj_error_message': err_msg})
                order.message_post(
                    body=_("<b>CJ Dropshipping Order Push Failed:</b><br/><code>%s</code>") % err_msg
                )
                _logger.error("Failed to push Sale Order %s to CJ: %s", order.name, err_msg)
                if len(self) == 1:
                    raise UserError(_("Failed to push to CJ Dropshipping:\n%s") % err_msg)

    def action_fetch_cj_tracking(self):
        """Fetch tracking number and tracking link from CJ Dropshipping API."""
        client = self.env['cj.api.client']
        for order in self:
            if not order.cj_order_id:
                raise UserError(_("Order %s has not been pushed to CJ Dropshipping yet.") % order.name)

            data = client.get_order_detail(order.cj_order_id)
            status = data.get('orderStatus') or 'CREATED'
            track_num = data.get('trackNumber') or data.get('trackNumber') or order.cj_tracking_number

            track_data = {}
            if track_num:
                track_data = client.get_track_info(track_number=track_num)

            track_url = data.get('trackingUrl') or track_data.get('trackingUrl') or track_data.get('trackUrl')

            vals = {}
            if status:
                status_str = str(status).upper().strip()
                valid_keys = [s[0] for s in order._fields['cj_order_status'].selection]
                if status_str not in valid_keys:
                    status_map = {
                        'PENDING': 'CREATED',
                        'AWAITING_PAYMENT': 'UNPAID',
                        'AWAITING_SHIPMENT': 'UNSHIPPED',
                        'NOT_SHIPPED': 'UNSHIPPED',
                        'IN_TRANSIT': 'SHIPPED',
                        'SUCCESS': 'COMPLETED',
                    }
                    status_str = status_map.get(status_str, 'PROCESSING')
                    if status_str not in valid_keys:
                        status_str = 'CREATED'
                vals['cj_order_status'] = status_str
            if track_num:
                vals['cj_tracking_number'] = str(track_num)
            if track_url:
                vals['cj_tracking_link'] = str(track_url)

            if vals:
                order.write(vals)

            if track_num or track_url:
                msg = _("<b>CJ Tracking Update Received:</b><br/>")
                if track_num:
                    msg += _("<b>Tracking Number:</b> %s<br/>") % track_num
                if track_url:
                    msg += _("<b>Tracking Link:</b> <a href='%s' target='_blank'>%s</a>") % (track_url, track_url)
                order.message_post(body=msg)

        if len(self) == 1:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('CJ Tracking Fetched!'),
                    'message': _('Updated order status and tracking details from CJ Dropshipping.'),
                    'type': 'success',
                    'sticky': False,
                }
            }

    def action_confirm(self):
        """Override confirm to automatically push dropship orders if setting is enabled."""
        res = super().action_confirm()
        ICP = self.env['ir.config_parameter'].sudo()
        auto_push = ICP.get_param('aveenix_cj_dropshipping.cj_auto_push_order', 'True') == 'True'

        if auto_push:
            for order in self:
                if order.has_cj_dropship_lines and order.cj_order_status == 'draft':
                    try:
                        order.action_push_to_cj()
                    except Exception as e:
                        _logger.warning("Auto push to CJ failed for order %s: %s", order.name, str(e))
        return res

    @api.model
    def _cron_fetch_cj_tracking(self):
        """Cron job to automatically check tracking links & status for open CJ orders."""
        orders = self.search([
            ('cj_order_id', '!=', False),
            ('cj_order_status', 'not in', ['COMPLETED', 'CLOSED', 'CANCELLED']),
        ], limit=50)
        for order in orders:
            try:
                order.action_fetch_cj_tracking()
                self.env.cr.commit()
            except Exception as e:
                _logger.warning("Cron fetch tracking failed for order %s: %s", order.name, str(e))

    @api.model
    def _cron_push_cj_orders(self):
        """Cron job to automatically push confirmed CJ orders that have not been pushed yet."""
        orders = self.search([
            ('state', '=', 'sale'),
            ('cj_order_id', '=', False),
        ], limit=50)
        for order in orders:
            if order.has_cj_dropship_lines:
                try:
                    order.action_push_to_cj()
                    self.env.cr.commit()
                except Exception as e:
                    _logger.warning("Cron push failed for order %s: %s", order.name, str(e))


    @api.model
    def _cron_refresh_cj_token(self):
        """Cron job to refresh CJ access token."""
        try:
            self.env['cj.api.client'].get_access_token(force_refresh=True)
            _logger.info("Successfully executed cron to refresh CJ Access Token.")
        except Exception as e:
            _logger.error("Failed to refresh CJ access token in cron: %s", str(e))

    def write(self, vals):
        res = super().write(vals)
        if 'cj_tracking_link' in vals and 'av_tracking_link' in self._fields:
            for order in self:
                if order.cj_tracking_link and not order.av_tracking_link:
                    order.av_tracking_link = order.cj_tracking_link
        return res
