"""Standalone WooCommerce connection tester.

Run OUTSIDE Odoo to debug connectivity / SSL / auth without the server.

    python test_wc_connection.py

Edit the CONFIG block below with your store URL + keys.
"""

import sys
import requests

# ----------------------------------------------------------------------
# CONFIG — edit these
# ----------------------------------------------------------------------
STORE_URL = "https://shop.aveenix.com"
CONSUMER_KEY = "ck_17b5b31c1d4ecac83d89416bd2fcabcd6e8f0913"
CONSUMER_SECRET = "cs_5cfa9b86d87d8b543bfdf030b29211059149499d"
API_VERSION = "wc/v3"
VERIFY_SSL = True          # set False to bypass cert check (debug only)
TIMEOUT = (10, 60)         # (connect, read) seconds
# ----------------------------------------------------------------------


def call(endpoint, params=None, verify=VERIFY_SSL):
    url = "%s/wp-json/%s/%s" % (STORE_URL.rstrip("/"), API_VERSION, endpoint)
    p = dict(params or {})
    p["consumer_key"] = CONSUMER_KEY
    p["consumer_secret"] = CONSUMER_SECRET
    resp = requests.get(url, params=p, timeout=TIMEOUT, verify=verify,
                        headers={"accept": "application/json"})
    return resp


def main():
    print("=" * 60)
    print("Testing:", STORE_URL)
    print("=" * 60)

    # 1) Plain TLS reachability
    try:
        r = requests.get(STORE_URL, timeout=TIMEOUT, verify=VERIFY_SSL)
        print(f"[1] Reach {STORE_URL} -> HTTP {r.status_code}")
    except requests.exceptions.SSLError as exc:
        print(f"[1] SSL ERROR: {exc}")
        print("    -> Certificate problem (hostname mismatch / untrusted).")
        print("    -> Retry with VERIFY_SSL=False to confirm it's only the cert.")
    except Exception as exc:
        print(f"[1] CONNECT ERROR: {exc}")

    # 2) Authenticated WC API call
    try:
        r = call("system_status")
        print(f"[2] WC system_status -> HTTP {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            env = data.get("environment", {})
            print("    WC version:", env.get("version"))
            print("    WP version:", env.get("wp_version"))
            print("    SUCCESS: connection + auth OK")
        elif r.status_code in (401, 403):
            print("    AUTH FAILED: check consumer key/secret + permissions.")
            print("    Body:", r.text[:300])
        else:
            print("    Body:", r.text[:300])
    except requests.exceptions.SSLError as exc:
        print(f"[2] SSL ERROR: {exc}")
    except Exception as exc:
        print(f"[2] ERROR: {exc}")

    # 3) Count a sample resource (products)
    try:
        r = call("products", {"per_page": 1})
        total = r.headers.get("X-WP-Total")
        print(f"[3] products -> HTTP {r.status_code}, X-WP-Total={total}")
    except Exception as exc:
        print(f"[3] ERROR: {exc}")

    print("=" * 60)


if __name__ == "__main__":
    main()
