# Aveenix - CJ Dropshipping Integration
## End-to-End Architecture & Complete Technical Workflow

This document provides a comprehensive, step-by-step overview of the **CJ Dropshipping Integration** (`aveenix_cj_dropshipping`) in Odoo 19. It covers the entire lifecycle of products, customer orders, automated fulfillment pushing, live shipment tracking, and background scheduler jobs (Crons).

---

## 1. System Overview & Authentication

The `aveenix_cj_dropshipping` module bridges Odoo 19 eCommerce with the CJ Dropshipping API (`https://developers.cjdropshipping.com/api2.0/v1/`).

```
+------------------+         REST API (JSON)        +-------------------+
|                  | =============================> |                   |
|  Odoo 19 Server  |    1. Sync "My Products"       |  CJ Dropshipping  |
|  (Aveenix Store) |    2. Push Orders (Sandbox)    |    Fulfillment    |
|                  |    3. Fetch Live Tracking      |     Warehouse     |
|                  | <============================= |                   |
+------------------+     (Tokens / Statuses / URLs) +-------------------+
```

### 1.1 Authentication & Token Lifecycle
- **Credentials**: Stored in Odoo Backend under **Website / Settings -> CJ Dropshipping Configuration** (`CJ Email` and `CJ Password` or API Key).
- **Access Token**: Odoo authenticates via `authentication/getAccessToken` and receives a `CJ-Access-Token`.
- **Token Caching & Auto-Refresh**:
  - The token and its expiry timestamp are stored in Odoo System Parameters (`ir.config_parameter`).
  - An automated cron job (**`ir_cron_cj_refresh_token`**) runs **every 7 days** to ensure tokens never expire during live operations.

---

## 2. Product Catalog Synchronization ("My Products" Only)

To prevent cluttering Odoo with millions of irrelevant CJ products, the system **exclusively syncs products from the store's "My Products" catalog** in CJ Dropshipping.

```
[ CJ "My Products" Store ] ──(GET /product/myProduct/query)──> [ Odoo Product Template & Variants ]
                                                                 ├── cj_pid  (CJ Product ID)
                                                                 ├── cj_vid  (CJ Variant ID)
                                                                 └── default_code (SKU)
```

### 2.1 Sync Workflows
1. **Manual Import Wizard (`cj.product.import.wizard`)**:
   - Admins can import products by specific `PID`/`SKU` or batch-import up to 100 "My Products".
   - Applies an optional **Markup Percentage** (e.g., `+20%`) over CJ cost price.
2. **Automated Scheduled Action (`_cron_sync_cj_my_products`)**:
   - Runs **twice daily (every 12 hours)**.
   - Calls `client.get_my_product_list()` to fetch newly added or updated products from CJ and automatically creates/updates Odoo products and stock levels.

---

## 3. Order Placement & Automated CJ Push Workflow

The order flow seamlessly connects customer checkout on the website to CJ Dropshipping fulfillment.

```
[ Customer Checkout ] ──> [ Odoo Sale Order (Confirm) ] ──(Auto Cron / Manual)──> [ CJ API: createOrderV3 ]
  (Guest or Logged In)        state = 'sale'                                       (isSandbox=1, is_sandbox=1)
```

### 3.1 Step 1: eCommerce Checkout (`/shop/payment`)
- **Guest Checkout**: Enabled via `account_on_checkout = 'optional'`, allowing unauthenticated visitors to place orders without creating a password.
- **Demo / Test Payment**: Easily tested using Odoo's default `Demo` payment provider (instant 1-click confirmation without API keys).

### 3.2 Step 2: Order Confirmation
- When payment succeeds, Odoo transitions the order to **`state = 'sale'`**.
- The order line items are checked against Odoo products containing a valid **CJ Variant ID (`cj_vid`)**.

### 3.3 Step 3: Order Pushing to CJ API
Orders can be pushed to CJ in two ways:
1. **Manual Action**: Admin clicks **"Push to CJ Dropshipping"** button on the Sale Order form.
2. **Automated Cron (`_cron_push_cj_orders`)**: Runs **every 30 minutes** and automatically pushes any confirmed order (`state = 'sale'`) where `cj_order_id` is empty.

### 3.4 API Payload & Sandbox Verification
When pushing to `shopping/order/createOrderV3`, the payload includes:
```json
{
  "orderNumber": "S00001",
  "shippingCountryCode": "US",
  "shippingCustomerName": "Customer Name",
  "shippingAddress": "123 Street Address",
  "logisticName": "CJPacket Ordinary",
  "isSandbox": 1,
  "is_sandbox": 1,
  "products": [
    {
      "vid": "CJ_VARIANT_ID_123",
      "quantity": 1
    }
  ]
}
```
- **Sandbox Safety**: Both `"isSandbox": 1` and `"is_sandbox": 1` are explicitly passed, guaranteeing that orders pushed during testing are registered as **Test/Sandbox Orders** in CJ Dropshipping without incurring real charges.

---

## 4. Live Tracking & Customer Portal Experience

Once an order is pushed, Odoo tracks its fulfillment progress from CJ warehouse processing to customer delivery.

```
[ CJ Dropshipping ] ──(Cron: every 2 hrs)──> [ Odoo Sale Order ] ──> [ Customer Portal (/my/orders) ]
  • Status: SHIPPED                            • cj_tracking_number    • Live Badge: [ 🚚 Shipped ]
  • Carrier: CJPacket                          • cj_logistics_name     • Clickable Button:
  • Tracking URL                               • cj_tracking_link        [ 🔗 Track Status Live ]
```

### 4.1 Automated Status & Tracking Sync
- **Scheduled Action (`_cron_fetch_cj_tracking`)**: Runs **every 2 hours**.
- Queries `shopping/order/getOrderDetail` for all active CJ orders (`cj_order_id != False`).
- Automatically updates Odoo fields:
  - `cj_order_status` (`CREATED` → `PAID` → `SHIPPED` → `COMPLETED`)
  - `cj_tracking_number` (e.g., `CJ123456789CN`)
  - `cj_logistics_name` (e.g., `CJPacket Ordinary`)
  - `cj_tracking_link` / `av_tracking_link` (Direct carrier tracking URL)

### 4.2 Customer Portal (`/my/orders`)
The Odoo Customer Account portal is enhanced with dedicated tracking features:
1. **Orders List (`/my/orders`)**:
   - Features a **"Tracking & Delivery Status"** column.
   - Displays real-time status badges (`[ 📦 CREATED ]` or `[ 🚚 Shipped (CJPacket) ]`).
   - Displays an **always-visible `[ 🔗 Track Status Live ]` button**:
     - If shipped: opens the direct CJ carrier tracking link (`cj_tracking_link`).
     - If processing: opens `https://cjpacket.com/?tracking_number=<number>` or CJ universal tracking.
2. **Order Detail Page (`/my/orders/<id>`)**:
   - Displays a prominent alert banner summarizing current warehouse processing or dispatch carrier.
   - Includes full table rows for **Fulfillment Status**, **Tracking Number**, **Shipping Carrier**, and **Track Online Button**.

---

## 5. Summary of Background Scheduler Jobs (Crons)

All scheduled actions are registered in `aveenix_cj_dropshipping/data/ir_cron_data.xml` and run automatically in the background:

| Technical XML ID | Cron Name | Frequency | Python Method | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **`ir_cron_cj_fetch_tracking`** | CJ Dropshipping: Auto-Fetch Tracking Links & Status | **Every 2 Hours** | `model._cron_fetch_cj_tracking()` | Fetches tracking numbers, carrier names, and status updates for open CJ orders. |
| **`ir_cron_cj_push_orders`** | CJ Dropshipping: Auto-Push Confirmed Orders | **Every 30 Minutes** | `model._cron_push_cj_orders()` | Pushes confirmed Odoo orders (`state='sale'`) to CJ API automatically. |
| **`ir_cron_cj_sync_my_products`** | CJ Dropshipping: Auto-Sync My Products Catalog | **Every 12 Hours** | `model._cron_sync_cj_my_products()` | Imports and updates new products from the user's CJ "My Products" store catalog. |
| **`ir_cron_cj_refresh_token`** | CJ Dropshipping: Auto-Refresh Access Token | **Every 7 Days** | `model._cron_refresh_cj_token()` | Prevents authentication expiration by refreshing `CJ-Access-Token`. |

---

## 6. Testing & QA Reference Guide

- **Testing Guest Checkout**:
  1. Open a new Incognito window (`Ctrl + Shift + N`) and navigate to `/shop`.
  2. Add an item to the cart and click **Checkout**.
  3. Enter email and address as a Guest (no account creation required).
- **Testing Instant Payment**:
  1. Ensure the **`Demo`** payment provider is enabled in Test Mode (`/odoo/payment-providers`).
  2. Select **Demo** at checkout and click **Successful Payment**.
- **Verifying Sandbox Push**:
  1. Confirm the order in Odoo.
  2. The automated cron (or clicking "Push to CJ Dropshipping") sends the order to CJ.
  3. Inspect CJ API response logs to verify `"isSandbox": 1` is returned.
