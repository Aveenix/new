/** @odoo-module **/

import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { user } from "@web/core/user";
import { _t } from "@web/core/l10n/translation";

function redirectBack() {
    return encodeURIComponent(window.location.pathname + window.location.search);
}

// ── Login gate modal + post-login auto-add ───────────────────────────
// Mounted once per page (on <body>). Exposes window.avShowLoginGate() so the
// existing add-to-cart handlers can open it when the server returns
// `require_login`, and auto-adds a pending product after the user logs in.
export class CartLoginGate extends Interaction {
    static selector = "#wrapwrap";

    start() {
        // addListener is only available once the interaction has started,
        // so all DOM wiring happens here (not in setup()).
        this._buildModal();
        // Expose opener for the vanilla add-to-cart handler(s).
        window.avShowLoginGate = () => this.open();
        // After a successful login, add whatever the guest tried to add.
        this._tryPendingAdd();
        // Guard every Add to Cart for guests.
        this._guardNativeAddToCart();
    }

    _isPublicUser() {
        // Canonical Odoo flag for an unauthenticated website visitor.
        return user.isPublic === true || !user.userId;
    }

    _guardNativeAddToCart() {
        // Capture phase so we stop every add-to-cart handler (Odoo's native
        // product button AND our custom product-card button) before any
        // request fires for a guest. The public check is done INSIDE the
        // handler so it is correct regardless of service-init timing.
        this.addListener(
            document,
            "click",
            (ev) => {
                const btn = ev.target.closest(
                    "#add_to_cart, #buy_now, .js_av_add_to_cart"
                );
                if (!btn) return;
                if (!this._isPublicUser()) return; // logged-in → normal flow
                ev.preventDefault();
                ev.stopPropagation();
                ev.stopImmediatePropagation();
                this._savePendingFromButton(btn);
                this.open();
            },
            { capture: true }
        );
    }

    _savePendingFromButton(btn) {
        // Product cards carry the ids as data attributes.
        const productId = parseInt(btn.dataset.productId || "");
        const productTemplateId = parseInt(btn.dataset.productTemplateId || "");
        if (productId && productTemplateId) {
            rpc("/aveenix/cart/save_pending", {
                product_template_id: productTemplateId,
                product_id: productId,
                quantity: 1,
            }).catch(() => {});
            return;
        }
        // Otherwise it's the product-detail form button.
        this._savePendingFromForm(btn);
    }

    _buildModal() {
        let overlay = document.getElementById("av-login-gate");
        if (!overlay) {
            overlay = document.createElement("div");
            overlay.id = "av-login-gate";
            document.body.appendChild(overlay);
        }
        overlay.className = "av-login-gate-overlay";
        // Always (re)populate so a pre-existing empty node can't leave it blank.
        overlay.innerHTML = `
            <div class="av-login-gate-box" role="dialog" aria-modal="true">
                <button type="button" class="av-login-gate-close" aria-label="${_t("Close")}">&times;</button>
                <div class="av-login-gate-icon"><i class="fa fa-user-circle"></i></div>
                <h3 class="av-login-gate-title">${_t("Sign in to continue")}</h3>
                <p class="av-login-gate-sub">${_t("Please log in or create an account to add items to your cart.")}</p>
                <div class="av-login-gate-actions">
                    <a class="av-login-gate-btn av-login-gate-btn-primary" href="/web/login?redirect=${redirectBack()}">${_t("Log in")}</a>
                    <a class="av-login-gate-btn av-login-gate-btn-outline" href="/web/signup?redirect=${redirectBack()}">${_t("Sign up")}</a>
                </div>
            </div>`;
        this.overlay = overlay;

        this.addListener(overlay, "click", (ev) => {
            if (ev.target === overlay) this.close();
        });
        const closeBtn = overlay.querySelector(".av-login-gate-close");
        if (closeBtn) {
            this.addListener(closeBtn, "click", () => this.close());
        }
        this.addListener(document, "keydown", (ev) => {
            if (ev.key === "Escape") this.close();
        });
    }

    async _savePendingFromForm(btn) {
        // Read product ids from the product-detail form so we can auto-add
        // after the guest logs in.
        const form = btn.closest("form") || document.querySelector("#product_detail form, form.js_product");
        if (!form) return;
        const tmplEl = form.querySelector('input[name="product_template_id"]');
        const prodEl = form.querySelector('input[name="product_id"], input.product_id');
        const qtyEl = form.querySelector('input[name="add_qty"]');
        const productTemplateId = tmplEl && parseInt(tmplEl.value);
        const productId = prodEl && parseInt(prodEl.value);
        if (!productTemplateId || !productId) return;
        try {
            await rpc("/aveenix/cart/save_pending", {
                product_template_id: productTemplateId,
                product_id: productId,
                quantity: qtyEl ? parseFloat(qtyEl.value) || 1 : 1,
            });
        } catch {
            // ignore
        }
    }

    open() {
        this.overlay && this.overlay.classList.add("is-open");
    }

    close() {
        this.overlay && this.overlay.classList.remove("is-open");
    }

    async _tryPendingAdd() {
        try {
            const res = await rpc("/aveenix/cart/pending_add", {});
            if (res && res.added) {
                const badge = document.querySelector(".my_cart_quantity");
                const qty = res.cart && res.cart.cart_quantity;
                if (badge && qty != null) {
                    badge.textContent = qty;
                }
            }
        } catch {
            // ignore — guest or no pending item
        }
    }
}

registry.category("public.interactions").add("CartLoginGate", CartLoginGate);
