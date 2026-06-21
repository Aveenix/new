import logging

_logger = logging.getLogger(__name__)

class WooExportError(Exception):
    pass

class WooRecordExporter:

    def get_endpoint(self, binding) -> str:
        raise NotImplementedError

    def get_create_endpoint(self) -> str:
        raise NotImplementedError

    def get_payload(self, binding) -> dict:
        raise NotImplementedError

    def after_export(self, binding, response_data: dict):
        pass

    def find_existing_remote_id(self, client, binding, payload):
        """Return an existing WooCommerce record id that matches this binding
        (e.g. by SKU), so we update instead of creating a duplicate.
        Default: no lookup. Overridden where a natural key exists."""
        return None

    def run(self, backend, binding):
        client = backend.get_api_client()
        payload = self.get_payload(binding)

        if not payload:
            _logger.info("Nothing to export for binding %s", binding)
            return

        try:
            # If the binding has no external_id yet, try to match an existing
            # remote record (by SKU etc.) to avoid a duplicate-key 400 on create.
            if not binding.external_id:
                existing_id = self.find_existing_remote_id(client, binding, payload)
                if existing_id:
                    binding.with_context(syncing_from_wc=True).write(
                        {"external_id": str(existing_id)})
                    _logger.info(
                        "Linked binding %s to existing WooCommerce record %s",
                        binding, existing_id)

            if binding.external_id:
                endpoint = self.get_endpoint(binding)
                result = client.put(endpoint, payload)
                _logger.info("Updated WooCommerce record at %s", endpoint)
            else:
                endpoint = self.get_create_endpoint()
                result = client.post(endpoint, payload)
                new_ext_id = str(result.get("data", {}).get("id", ""))
                if new_ext_id:
                    binding.with_context(syncing_from_wc=True).write({"external_id": new_ext_id})
                _logger.info("Created WooCommerce record %s at %s", new_ext_id, endpoint)

            self.after_export(binding, result.get("data", {}))
            return result

        except Exception as exc:
            _logger.exception("WooCommerce export failed for binding %s: %s", binding, exc)
            raise WooExportError(str(exc)) from exc

class WooOrderStatusExporter(WooRecordExporter):

    def get_endpoint(self, binding) -> str:
        return "orders/%s" % binding.external_id

    def get_create_endpoint(self) -> str:
        return "orders"

    def get_payload(self, binding) -> dict:
        status = binding.wc_fulfillment_status
        if not status:
            if binding.order_id.state == "cancel":
                status = "cancelled"
            elif binding.order_id.all_deliveries_done:
                status = "completed"
            elif binding.wc_status_id:
                status = binding.wc_status_id.code
            else:
                if binding.order_id.state in ("sale", "done"):
                    status = "processing"
                else:
                    status = "pending"
        payload = {"status": status}
        if binding.backend_id.push_tracking_info:
            tracking = getattr(binding, "carrier_tracking_ref", False)
            if not tracking and binding.order_id.picking_ids:
                pickings = binding.order_id.picking_ids.filtered(
                    lambda p: p.picking_type_code == "outgoing" and p.state == "done"
                )
                if pickings:
                    refs = [p.carrier_tracking_ref for p in pickings if p.carrier_tracking_ref]
                    if refs:
                        tracking = ", ".join(refs)
            if tracking:
                payload["meta_data"] = [
                    {"key": "_tracking_number", "value": tracking},
                ]
        return payload

    def after_export(self, binding, response_data: dict):
        if response_data and response_data.get("status"):
            code = response_data["status"]
            stage = binding.env["wc.order.stage"].search([("code", "=", code)], limit=1)
            if stage:
                binding.with_context(syncing_from_wc=True).write({
                    "wc_status_id": stage.id,
                    "wc_fulfillment_status": False,
                })

class WooFullOrderExporter(WooRecordExporter):
    """Push a full Odoo sale order to WooCommerce (create or update).

    Builds line_items, shipping_lines, fee_lines, billing/shipping and
    customer_id. Tax is left for WooCommerce to recompute (only line
    products and prices are sent).
    """

    def get_endpoint(self, binding) -> str:
        return "orders/%s" % binding.external_id

    def get_create_endpoint(self) -> str:
        return "orders"

    def _resolve_status(self, binding) -> str:
        order = binding.order_id
        if order.state == "cancel":
            return "cancelled"
        if binding.wc_status_id:
            return binding.wc_status_id.code
        if order.state in ("sale", "done"):
            return "processing"
        return "pending"

    def _partner_address(self, partner) -> dict:
        names = (partner.name or "").split(" ", 1)
        return {
            "first_name": names[0],
            "last_name": names[1] if len(names) > 1 else "",
            "address_1": partner.street or "",
            "address_2": partner.street2 or "",
            "city": partner.city or "",
            "state": partner.state_id.code if partner.state_id else "",
            "postcode": partner.zip or "",
            "country": partner.country_id.code if partner.country_id else "",
        }

    def get_payload(self, binding) -> dict:
        order = binding.order_id

        line_items = []
        shipping_lines = []
        fee_lines = []

        for line in order.order_line:
            if line.display_type:  # section / note lines
                continue

            if getattr(line, "is_delivery", False):
                shipping_lines.append({
                    "method_title": line.name or "Shipping",
                    "method_id": "flat_rate",
                    "total": str(line.price_subtotal),
                })
                continue

            product = line.product_id
            wc_prod = product.wc_bind_ids.filtered(
                lambda b: b.backend_id == binding.backend_id and b.external_id
            )[:1]

            if not wc_prod:
                # Service products with no WC mapping become fee lines.
                if product.type == "service":
                    fee_lines.append({
                        "name": line.name or product.name,
                        "total": str(line.price_subtotal),
                    })
                    continue
                raise WooExportError(
                    "Product '%s' is not mapped to WooCommerce." % product.display_name
                )

            line_items.append({
                "product_id": int(wc_prod.external_id),
                "quantity": int(line.product_uom_qty),
                "total": str(line.price_subtotal),
                "subtotal": str(line.price_subtotal),
            })

        partner = order.partner_id
        billing = self._partner_address(order.partner_invoice_id or partner)
        billing["email"] = (order.partner_invoice_id or partner).email or partner.email or ""
        billing["phone"] = partner.phone or partner.mobile or ""

        shipping = self._partner_address(order.partner_shipping_id or partner)

        payload = {
            "status": self._resolve_status(binding),
            "currency": order.currency_id.name or "",
            "customer_note": order.note or "",
            "billing": billing,
            "shipping": shipping,
            "line_items": line_items,
            "shipping_lines": shipping_lines,
            "fee_lines": fee_lines,
        }

        # Link to an existing WooCommerce customer when mapped.
        cust = partner.wc_bind_ids.filtered(
            lambda b: b.backend_id == binding.backend_id and b.external_id
        )[:1]
        if cust:
            payload["customer_id"] = int(cust.external_id)

        pm = binding.wc_payment_mode_id
        if pm and pm.external_id:
            payload["payment_method"] = pm.external_id
            payload["payment_method_title"] = pm.name or pm.external_id

        return payload

    def after_export(self, binding, response_data: dict):
        if not response_data:
            return
        vals = {}
        if response_data.get("number"):
            vals["wc_order_number"] = response_data["number"]
        if response_data.get("order_key"):
            vals["wc_order_key"] = response_data["order_key"]
        if vals:
            binding.with_context(syncing_from_wc=True).write(vals)

class WooStockExporter(WooRecordExporter):

    def get_endpoint(self, binding) -> str:
        return "products/%s" % binding.external_id

    def get_create_endpoint(self) -> str:
        return "products"

    def get_payload(self, binding) -> dict:
        return {
            "stock_quantity": int(binding.wc_stock_qty),
            "manage_stock": True,
        }

def _find_product_id_by_sku(client, sku):
    """Look up a WooCommerce product id by exact SKU. Returns id or None."""
    if not sku:
        return None
    try:
        result = client.get("products", {"sku": sku})
    except Exception:
        return None
    for rec in (result.get("data") or []):
        if str(rec.get("sku", "")) == str(sku):
            return rec.get("id")
    return None


class WooProductExporter(WooRecordExporter):

    def get_endpoint(self, binding) -> str:
        return "products/%s" % binding.external_id

    def get_create_endpoint(self) -> str:
        return "products"

    def find_existing_remote_id(self, client, binding, payload):
        return _find_product_id_by_sku(client, payload.get("sku"))

    def get_payload(self, binding) -> dict:
        product = binding.product_id
        payload = {
            "name": binding.wc_product_name or product.name,
            "type": "simple",
            "status": binding.wc_status or "publish",
            "regular_price": str(
                binding.wc_regular_price if binding.wc_regular_price
                else product.list_price
            ),
            "manage_stock": bool(binding.wc_manage_stock),
            "description": product.description_sale or "",
        }

        sku = binding.wc_sku or product.default_code
        if sku:
            payload["sku"] = sku

        if binding.wc_manage_stock:
            payload["stock_quantity"] = int(binding.wc_stock_qty or 0)

        weight = binding.wc_weight or (str(product.weight) if product.weight else "")
        if weight and str(weight) not in ("0", "0.0", ""):
            payload["weight"] = str(weight)

        if binding.wc_sale_price:
            payload["sale_price"] = str(binding.wc_sale_price)

        if binding.wc_category_ids:
            payload["categories"] = [
                {"id": int(cat.external_id)}
                for cat in binding.wc_category_ids
                if cat.external_id
            ]

        if binding.wc_tag_ids:
            payload["tags"] = [
                {"id": int(tag.external_id)}
                for tag in binding.wc_tag_ids
                if tag.external_id
            ]

        return payload

    def after_export(self, binding, response_data: dict):
        if response_data:
            vals = {}
            if response_data.get("sku"):
                vals["wc_sku"] = response_data["sku"]
            if response_data.get("status"):
                vals["wc_status"] = response_data["status"]
            if vals:
                binding.with_context(syncing_from_wc=True).write(vals)

class WooVariableProductExporter(WooRecordExporter):

    def get_endpoint(self, binding) -> str:
        return "products/%s" % binding.external_id

    def get_create_endpoint(self) -> str:
        return "products"

    def find_existing_remote_id(self, client, binding, payload):
        return _find_product_id_by_sku(client, payload.get("sku"))

    def get_payload(self, binding) -> dict:
        template = binding.template_id
        payload = {
            "name": binding.wc_product_name or template.name,
            "type": "variable",
            "status": binding.wc_status or "publish",
            "description": template.description_sale or "",
        }

        if binding.wc_sku or template.default_code:
            payload["sku"] = binding.wc_sku or template.default_code or ""

        if binding.wc_category_ids:
            payload["categories"] = [
                {"id": int(cat.external_id)}
                for cat in binding.wc_category_ids
                if cat.external_id
            ]
        if binding.wc_tag_ids:
            payload["tags"] = [
                {"id": int(tag.external_id)}
                for tag in binding.wc_tag_ids
                if tag.external_id
            ]
        return payload

class WooCustomerExporter(WooRecordExporter):

    def get_endpoint(self, binding) -> str:
        return "customers/%s" % binding.external_id

    def get_create_endpoint(self) -> str:
        return "customers"

    def get_payload(self, binding) -> dict:
        partner = binding.partner_id
        names = (partner.name or "").split(" ", 1)
        first_name = names[0]
        last_name = names[1] if len(names) > 1 else ""

        payload = {
            "first_name": first_name,
            "last_name": last_name,
            "email": partner.email or "",
        }

        billing = {
            "first_name": first_name,
            "last_name": last_name,
            "address_1": partner.street or "",
            "address_2": partner.street2 or "",
            "city": partner.city or "",
            "state": partner.state_id.code if partner.state_id else "",
            "postcode": partner.zip or "",
            "country": partner.country_id.code if partner.country_id else "",
            "email": partner.email or "",
            "phone": partner.phone or partner.mobile or "",
        }
        payload["billing"] = billing

        ship_partner = partner.child_ids.filtered(lambda c: c.type == "delivery")[:1]
        if ship_partner:
            ship_names = (ship_partner.name or "").split(" ", 1)
            payload["shipping"] = {
                "first_name": ship_names[0],
                "last_name": ship_names[1] if len(ship_names) > 1 else "",
                "address_1": ship_partner.street or "",
                "address_2": ship_partner.street2 or "",
                "city": ship_partner.city or "",
                "state": ship_partner.state_id.code if ship_partner.state_id else "",
                "postcode": ship_partner.zip or "",
                "country": ship_partner.country_id.code if ship_partner.country_id else "",
            }
        else:
            payload["shipping"] = billing.copy()
            payload["shipping"].pop("email", None)
            payload["shipping"].pop("phone", None)

        return payload

class WooCategoryExporter(WooRecordExporter):

    def get_endpoint(self, binding) -> str:
        return "products/categories/%s" % binding.external_id

    def get_create_endpoint(self) -> str:
        return "products/categories"

    def get_payload(self, binding) -> dict:
        payload = {
            "name": binding.name,
            "description": binding.wc_description or "",
            "slug": binding.wc_slug or "",
        }
        if binding.wc_parent_id and binding.wc_parent_id.external_id:
            payload["parent"] = int(binding.wc_parent_id.external_id)
        elif binding.category_id.parent_id:
            parent_binding = binding.env["wc.category.link"].search([
                ("category_id", "=", binding.category_id.parent_id.id),
                ("backend_id", "=", binding.backend_id.id),
                ("external_id", "!=", False),
            ], limit=1)
            if parent_binding:
                payload["parent"] = int(parent_binding.external_id)
        return payload

class WooTagExporter(WooRecordExporter):

    def get_endpoint(self, binding) -> str:
        return "products/tags/%s" % binding.external_id

    def get_create_endpoint(self) -> str:
        return "products/tags"

    def get_payload(self, binding) -> dict:
        return {
            "name": binding.name,
            "description": binding.description or "",
            "slug": binding.slug or "",
        }

class WooAttributeExporter(WooRecordExporter):

    def get_endpoint(self, binding) -> str:
        return "products/attributes/%s" % binding.external_id

    def get_create_endpoint(self) -> str:
        return "products/attributes"

    def get_payload(self, binding) -> dict:
        return {
            "name": binding.name,
            "type": binding.wc_type or "select",
            "order_by": binding.wc_order_by or "menu_order",
            "has_archives": bool(binding.wc_has_archives),
        }
