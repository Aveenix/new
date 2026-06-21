import logging
import socket
import urllib.error

import requests
from woocommerce import API

_logger = logging.getLogger(__name__)

RETRYABLE_HTTP_CODES = {502, 503, 504}
ERROR_HTTP_CODES = {400, 401, 403, 404, 405, 500}

class WooConnectionError(Exception):
    pass

class WooAPIError(Exception):
    pass

class WooStoreLocation:

    def __init__(self, url, consumer_key, consumer_secret, version="wc/v3"):
        self.url = url.rstrip("/")
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
        self.version = version

    def __repr__(self):
        return f"<WooStoreLocation url={self.url} version={self.version}>"

class WooRESTClient:

    # (connect, read) timeout. Short values so a stalled connection or a
    # server that accepts the request but never responds fails fast instead
    # of hanging the worker until the request watchdog kills it.
    _TIMEOUT = (10, 45)

    def __init__(self, location: WooStoreLocation):
        self._location = location
        self._api = None
        self._session = None
        self._deadline = None  # shared wall-clock deadline across pulls

    @property
    def session(self) -> requests.Session:
        # One pooled session per client → the TLS handshake happens once and
        # the connection is reused across pages (instead of a new, slow
        # handshake on every API call).
        if self._session is None:
            sess = requests.Session()
            # No retries: a retry on a server that hangs mid-response just
            # multiplies the wait (3 × read timeout) and trips the watchdog.
            adapter = requests.adapters.HTTPAdapter(
                pool_connections=4, pool_maxsize=4, max_retries=0,
            )
            sess.mount("https://", adapter)
            sess.mount("http://", adapter)
            self._session = sess
        return self._session

    @property
    def api(self) -> API:
        if self._api is None:
            self._api = API(
                url=self._location.url,
                consumer_key=self._location.consumer_key,
                consumer_secret=self._location.consumer_secret,
                version=self._location.version,
                wp_api=True,
                query_string_auth=True,
                timeout=self._TIMEOUT,
            )
        return self._api

    def get(self, endpoint: str, params: dict = None) -> dict:
        return self._call("get", endpoint, params=params or {})

    def post(self, endpoint: str, payload: dict) -> dict:
        return self._call("post", endpoint, payload=payload)

    def put(self, endpoint: str, payload: dict) -> dict:
        return self._call("put", endpoint, payload=payload)

    def delete(self, endpoint: str, params: dict = None) -> dict:
        return self._call("delete", endpoint, params=params or {})

    # Set by the store/wizard so every paginated pull honors the same
    # Start Page / Max Records chunk controls without per-endpoint plumbing.
    sync_start_page = 1
    sync_max_records = 0
    # Wall-clock budget (seconds) for one paginated pull. 0 = unlimited.
    # Set below the request watchdog (limit_time_real, default 120s) so a big
    # catalog stops gracefully instead of being killed and restarting the worker.
    sync_time_budget = 0

    def get_all_pages(self, endpoint: str, params: dict = None, per_page: int = 100,
                      max_pages: int = 1000, start_page: int = None, max_records: int = None,
                      time_budget: float = None):
        if start_page is None:
            start_page = self.sync_start_page or 1
        if max_records is None:
            max_records = self.sync_max_records or 0
        if time_budget is None:
            time_budget = self.sync_time_budget or 0
        params = dict(params or {})
        # When a small max_records is requested, shrink the page size too so we
        # fetch only what's needed instead of a full 100-record page.
        if max_records and max_records < per_page:
            per_page = max_records
        params.setdefault("per_page", per_page)
        page = params.pop("page", start_page)

        import time
        seen_first_ids = None
        pages_done = 0
        fetched = 0
        # Deadline may be preset (shared across a multi-type pull) or derived
        # from this call's budget.
        if time_budget and not self._deadline:
            self._deadline = time.time() + time_budget
        while True:
            if self._deadline and time.time() > self._deadline:
                _logger.warning(
                    "WC API %s: time budget reached after %d page(s); stopping. "
                    "Re-run / next cron continues from the last sync.",
                    endpoint, pages_done,
                )
                break
            params["page"] = page
            _t = time.time()
            result = self.get(endpoint, params)
            records = result.get("data", [])
            _logger.info(
                "WC API %s page %d -> %d records in %.2fs",
                endpoint, page, len(records), time.time() - _t,
            )
            if not records:
                break

            # Respect a max_records cap (from the sync wizard) across any endpoint.
            if max_records and fetched + len(records) > max_records:
                records = records[: max_records - fetched]

            # Guard against a server that ignores the `page` param and keeps
            # returning the SAME records: that would loop forever (each call
            # ~1-2s) until the request watchdog kills the worker. Detect a
            # repeated page by its record ids and stop.
            first_ids = tuple(r.get("id") for r in records[:5])
            if first_ids == seen_first_ids:
                _logger.warning(
                    "WooCommerce returned a repeated page for %s (page %s); "
                    "stopping pagination to avoid an infinite loop.",
                    endpoint, page,
                )
                break
            seen_first_ids = first_ids

            yield records
            fetched += len(records)

            # Stop once the wizard's max_records cap is reached.
            if max_records and fetched >= max_records:
                break

            pages_done += 1
            if pages_done >= max_pages:
                _logger.warning(
                    "WooCommerce pagination hit max_pages=%s for %s; stopping.",
                    max_pages, endpoint,
                )
                break

            # Stop when the last page is short. Do NOT trust the total header —
            # with query-string auth it is often absent.
            if len(records) < per_page:
                break
            page += 1

    def test_connection(self) -> bool:
        try:
            result = self.get("system_status")
            return bool(result.get("data"))
        except Exception as exc:
            _logger.warning("WooCommerce connection test failed: %s", exc)
            return False

    def _build_url(self, endpoint: str) -> str:
        loc = self._location
        return "%s/wp-json/%s/%s" % (loc.url, loc.version, endpoint.lstrip("/"))

    def _call(self, method: str, endpoint: str, params: dict = None, payload: dict = None) -> dict:
        # Use a pooled session with a (connect, read) timeout. This keeps the
        # TLS connection alive across pages (one handshake, not one per call)
        # and makes a stalled handshake fail fast instead of hanging the worker.
        loc = self._location
        req_params = dict(params or {})
        req_params["consumer_key"] = loc.consumer_key
        req_params["consumer_secret"] = loc.consumer_secret
        url = self._build_url(endpoint)
        headers = {"accept": "application/json", "user-agent": "odoo-woo-connector"}
        try:
            response = self.session.request(
                method.upper(), url,
                params=req_params,
                json=payload if payload is not None else None,
                headers=headers,
                timeout=self._TIMEOUT,
            )
            return self._parse_response(response)
        except (OSError, socket.gaierror, socket.timeout,
                requests.exceptions.RequestException) as exc:
            raise WooConnectionError(
                "Network error while calling WooCommerce API: %s" % exc
            ) from exc

    def _parse_response(self, response: requests.Response) -> dict:
        status = response.status_code

        if status == 201:
            return {"data": response.json(), "total": 1}

        if status == 200:
            body = response.json()
            total = response.headers.get("X-WP-Total", None)
            total_pages = response.headers.get("X-WP-TotalPages", None)
            return {
                "data": body,
                "total": int(total) if total else (len(body) if isinstance(body, list) else 1),
                "total_pages": int(total_pages) if total_pages else 1,
            }

        if status == 204:
            return {"data": {}, "total": 0}

        if status in ERROR_HTTP_CODES:
            try:
                error_body = response.json()
            except Exception:
                error_body = response.text
            raise WooAPIError(
                "WooCommerce API error (HTTP %s): %s" % (status, error_body)
            )

        if status in RETRYABLE_HTTP_CODES:
            raise WooConnectionError(
                "Temporary WooCommerce server error (HTTP %s)" % status
            )

        response.raise_for_status()
        return {"data": response.json(), "total": 1}
