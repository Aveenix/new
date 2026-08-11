import json
import logging
import sys
from datetime import datetime, timedelta
import requests

from odoo import api, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

CJ_API_BASE_URL = "https://developers.cjdropshipping.com/api2.0/v1"


class CjApiClient(models.AbstractModel):
    _name = "cj.api.client"
    _description = "CJ Dropshipping API Client v2"

    def _get_api_key(self):
        ICP = self.env["ir.config_parameter"].sudo()
        default_key = "CJ4647033@api@5e1ba4f458d84aa39921afd592149251"
        api_key = ICP.get_param("aveenix_cj_dropshipping.cj_api_key", default=default_key)
        if not api_key:
            raise UserError(_("Please configure your CJ Dropshipping API Key in General / Website Settings."))
        return api_key.strip()

    def get_access_token(self, force_refresh=False):
        """Get valid access token from ir.config_parameter or from CJ authentication API."""
        ICP = self.env["ir.config_parameter"].sudo()
        token = ICP.get_param("aveenix_cj_dropshipping.cj_access_token")
        expiry_str = ICP.get_param("aveenix_cj_dropshipping.cj_access_token_expiry")

        if token and not force_refresh:
            if expiry_str:
                try:
                    expiry_dt = datetime.fromisoformat(expiry_str[:19])
                    if datetime.now() < expiry_dt - timedelta(hours=1):
                        return token
                except Exception:
                    pass
            else:
                return token

        api_key = self._get_api_key()
        url = f"{CJ_API_BASE_URL}/authentication/getAccessToken"
        headers = {"Content-Type": "application/json"}
        payload = {"apiKey": api_key}

        try:
            print("\n" + "="*60, file=sys.stdout)
            print(f"[CJ API DEBUG] Calling GET ACCESS TOKEN: {url}", file=sys.stdout)
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            res_json = response.json()
            print(f"[CJ API DEBUG] Auth Response Code: {response.status_code}", file=sys.stdout)
            print(f"[CJ API DEBUG] Auth JSON:\n{json.dumps(res_json, indent=2)}", file=sys.stdout)
            print("="*60 + "\n", file=sys.stdout)
        except Exception as e:
            _logger.error("CJ API Token request failed: %s", str(e))
            raise UserError(_("Could not connect to CJ Dropshipping API: %s") % str(e))

        if res_json.get("code") == 200 and res_json.get("result"):
            data = res_json.get("data") or {}
            access_token = data.get("accessToken")
            refresh_token = data.get("refreshToken")
            access_expiry = data.get("accessTokenExpiryDate")
            refresh_expiry = data.get("refreshTokenExpiryDate")

            if access_token:
                ICP.set_param("aveenix_cj_dropshipping.cj_access_token", access_token)
            if refresh_token:
                ICP.set_param("aveenix_cj_dropshipping.cj_refresh_token", refresh_token)
            if access_expiry:
                ICP.set_param("aveenix_cj_dropshipping.cj_access_token_expiry", access_expiry)
            if refresh_expiry:
                ICP.set_param("aveenix_cj_dropshipping.cj_refresh_token_expiry", refresh_expiry)

            _logger.info("Successfully obtained new CJ Dropshipping access token.")
            return access_token
        else:
            msg = res_json.get("message") or "Unknown error"
            raise UserError(_("CJ Dropshipping Authentication Failed:\nCode: %s\nMessage: %s\nFull Response:\n%s") % (
                res_json.get("code"), msg, json.dumps(res_json, indent=2)
            ))

    def refresh_access_token(self):
        """Refresh CJ access token using refreshToken."""
        ICP = self.env["ir.config_parameter"].sudo()
        refresh_token = ICP.get_param("aveenix_cj_dropshipping.cj_refresh_token")
        if not refresh_token:
            return self.get_access_token(force_refresh=True)

        url = f"{CJ_API_BASE_URL}/authentication/refreshAccessToken"
        headers = {"Content-Type": "application/json"}
        payload = {"refreshToken": refresh_token}

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            res_json = response.json()
            if res_json.get("code") == 200 and res_json.get("result"):
                data = res_json.get("data") or {}
                access_token = data.get("accessToken")
                if access_token:
                    ICP.set_param("aveenix_cj_dropshipping.cj_access_token", access_token)
                    ICP.set_param("aveenix_cj_dropshipping.cj_access_token_expiry", data.get("accessTokenExpiryDate", ""))
                    return access_token
        except Exception as e:
            _logger.warning("CJ refreshAccessToken failed: %s, falling back to getAccessToken.", str(e))

        return self.get_access_token(force_refresh=True)

    def _make_request(self, endpoint, method="GET", data=None, params=None, auth_required=True, retry_auth=True):
        """Generic method to call CJ API v2 endpoints with auto token management and DEBUG PRINT."""
        url = f"{CJ_API_BASE_URL}/{endpoint.lstrip('/')}"
        headers = {"Content-Type": "application/json"}

        if auth_required:
            token = self.get_access_token()
            headers["CJ-Access-Token"] = token
            headers["platformToken"] = token

        print("\n" + "="*60, file=sys.stdout)
        print(f"[CJ API DEBUG] Requesting: {method.upper()} {url}", file=sys.stdout)
        print(f"[CJ API DEBUG] Headers: CJ-Access-Token={headers.get('CJ-Access-Token', '')[:20]}...", file=sys.stdout)
        if params:
            print(f"[CJ API DEBUG] Params: {json.dumps(params)}", file=sys.stdout)
        if data:
            print(f"[CJ API DEBUG] Payload: {json.dumps(data)}", file=sys.stdout)
        print("="*60, file=sys.stdout)

        try:
            if method.upper() == "GET":
                response = requests.get(url, params=params or {}, headers=headers, timeout=30)
            else:
                response = requests.post(url, json=data or {}, headers=headers, timeout=30)
            res_json = response.json()
        except Exception as e:
            _logger.error("CJ API request to %s failed: %s", endpoint, str(e))
            raise UserError(_("CJ API request failed (%s): %s") % (endpoint, str(e)))

        print(f"[CJ API DEBUG] Response ({endpoint}): Code={res_json.get('code')}, Message={res_json.get('message')}", file=sys.stdout)
        print(f"[CJ API DEBUG] Full Response JSON:\n{json.dumps(res_json, indent=2)}", file=sys.stdout)
        print("="*60 + "\n", file=sys.stdout)

        if res_json.get("code") in [1600001, 1600003, 1600004] and retry_auth and auth_required:
            _logger.warning("CJ Access Token expired during call to %s, refreshing...", endpoint)
            self.refresh_access_token()
            return self._make_request(
                endpoint=endpoint,
                method=method,
                data=data,
                params=params,
                auth_required=auth_required,
                retry_auth=False,
            )

        return res_json

    # =========================================================================
    # 1. PULL PRODUCTS FROM CJ TO ODOO
    # =========================================================================
    def get_my_product_list(self, page_num=1, page_size=50):
        """List products from My CJ Store (Store Listed Products in English) using GET request (product/myProduct/query)."""
        params = {
            "pageNumber": int(page_num),
            "pageSize": int(page_size),
        }
        res = self._make_request("product/myProduct/query", method="GET", params=params)
        if res.get("code") == 200 and res.get("result"):
            return res.get("data") or {}
        raise UserError(_(
            "[CJ Dropshipping Error Report]\n"
            "Action: My Product List (/product/myProduct/query)\n"
            "Error Code: %s\n"
            "Message: %s\n"
            "Request ID: %s\n\n"
            "Raw API Response:\n%s"
        ) % (
            res.get("code"),
            res.get("message", "Unknown error"),
            res.get("requestId", "N/A"),
            json.dumps(res, indent=2),
        ))

    def get_product_list(self, page_num=1, page_size=50, category_id=None):
        """List products from CJ Dropshipping using GET request (product/list)."""
        params = {
            "pageNum": int(page_num),
            "pageSize": int(page_size),
        }
        if category_id:
            params["categoryId"] = category_id

        res = self._make_request("product/list", method="GET", params=params)
        if res.get("code") == 200 and res.get("result"):
            return res.get("data") or {}

        raise UserError(_(
            "[CJ Dropshipping Error Report]\n"
            "Action: Product List (/product/list)\n"
            "Error Code: %s\n"
            "Message: %s\n"
            "Request ID: %s\n\n"
            "Raw API Response:\n%s"
        ) % (
            res.get("code"),
            res.get("message", "Unknown error"),
            res.get("requestId", "N/A"),
            json.dumps(res, indent=2),
        ))

    def get_product_detail(self, pid=None, sku=None):
        """Query single product detail from CJ by PID or SKU using GET request."""
        params = {}
        if pid:
            params["pid"] = pid
        elif sku:
            params["productSku"] = sku
        else:
            raise UserError(_("Please provide either PID or SKU to query CJ product."))

        res = self._make_request("product/query", method="GET", params=params)
        if res.get("code") == 200 and res.get("result"):
            return res.get("data")
        raise UserError(_(
            "[CJ Dropshipping Error Report]\n"
            "Action: Product Detail (/product/query)\n"
            "Error Code: %s\n"
            "Message: %s\n"
            "Request ID: %s\n\n"
            "Raw API Response:\n%s"
        ) % (
            res.get("code"),
            res.get("message", "Unknown error"),
            res.get("requestId", "N/A"),
            json.dumps(res, indent=2),
        ))

    def get_product_variants(self, pid=None, sku=None):
        """Query product variants from CJ by PID or SKU using GET request."""
        params = {}
        if pid:
            params["pid"] = pid
        elif sku:
            params["sku"] = sku

        res = self._make_request("product/variant/query", method="GET", params=params)
        if res.get("code") == 200 and res.get("result"):
            return res.get("data") or []
        return []

    # =========================================================================
    # 2. PUSH ORDERS FROM ODOO TO CJ
    # =========================================================================
    def create_order(self, order_payload):
        """Create order in CJ Dropshipping (createOrderV3 / createOrderV2) using POST."""
        res = self._make_request("shopping/order/createOrderV3", method="POST", data=order_payload)
        if res.get("code") == 200 and res.get("result"):
            return res.get("data") or {}
        else:
            if res.get("code") in [404, 500]:
                res_v2 = self._make_request("shopping/order/createOrderV2", method="POST", data=order_payload)
                if res_v2.get("code") == 200 and res_v2.get("result"):
                    return res_v2.get("data") or {}
                res = res_v2
            raise UserError(_(
                "[CJ Dropshipping Order Push Failed]\n"
                "Error Code: %s\n"
                "Message: %s\n"
                "Request ID: %s\n\n"
                "Raw API Response:\n%s"
            ) % (
                res.get("code"),
                res.get("message", "Unknown error"),
                res.get("requestId", "N/A"),
                json.dumps(res, indent=2),
            ))

    def calculate_freight(self, start_country, end_country, products, zip_code=None):
        """
        Calculate freight from CJ API.
        products: list of dicts {"vid": "...", "quantity": 1}
        """
        if not products:
            return []
            
        payload = {
            "startCountryCode": start_country,
            "endCountryCode": end_country,
            "products": products
        }
        if zip_code:
            payload["zip"] = zip_code
            
        res = self._make_request("logistic/freightCalculate", method="POST", data=payload)
        if res.get("code") == 200 and res.get("result"):
            return res.get("data") or []
        
        # If simple mode fails or has no results, try freightCalculateTip or just return empty
        # Usually freightCalculate works for standard routing.
        return []

    # =========================================================================
    # 3. FETCH ORDER DETAILS & TRACKING LINK
    # =========================================================================
    def get_order_detail(self, order_id):
        """Get order details from CJ by orderId using GET."""
        if not order_id:
            return {}
        res = self._make_request(
            "shopping/order/getOrderDetail",
            method="GET",
            params={"orderId": str(order_id)},
        )
        if res.get("code") == 200 and res.get("result"):
            return res.get("data") or {}
        return {}

    def get_track_info(self, track_number=None, order_id=None):
        """Query tracking info from CJ using GET."""
        params = {}
        if track_number:
            params["trackNumber"] = track_number
        if order_id:
            params["orderId"] = str(order_id)

        res = self._make_request("logistic/trackInfo", method="GET", params=params)
        if res.get("code") == 200 and res.get("result"):
            return res.get("data") or {}
        res_old = self._make_request("logistic/getTrackInfo", method="GET", params=params)
        if res_old.get("code") == 200 and res_old.get("result"):
            return res_old.get("data") or {}
        return {}
