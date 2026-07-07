/** @odoo-module **/

import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";

// ── Affiliate "Add to cart" button on product detail page ───────────────────
// Looks like the native add-to-cart. Every click saves the product to the
// affiliate cart (never the real Odoo cart) and shows the SAME native popup.
export class AffiliateSaveButton extends Interaction {
    static selector = ".av-affiliate-save-btn";

    start() {
        // Capture-phase on document so no other handler / overlay can swallow
        // the click before us (mirrors the pattern used by the login gate).
        this._onDocClick = (ev) => {
            const btn = ev.target.closest(".av-affiliate-save-btn");
            if (btn !== this.el) {
                return;
            }
            ev.preventDefault();
            ev.stopPropagation();
            this._onSave();
        };
        document.addEventListener("click", this._onDocClick, { capture: true });
        this.registerCleanup(() =>
            document.removeEventListener("click", this._onDocClick, { capture: true })
        );
    }

    async _onSave() {
        const productId = parseInt(this.el.dataset.productId);
        if (!productId) {
            return;
        }
        const original = this.el.innerHTML;
        this.el.classList.add("disabled");
        this.el.innerHTML = '<i class="fa fa-spinner fa-spin me-2"/>Adding…';

        try {
            const res = await rpc("/aveenix/affiliate/cart/add", { product_id: productId });
            if (res && res.ok) {
                this._showCartPopup(res.notification);
            }
        } catch {
            // ignore — restore below
        }
        // Always restore to a clickable "Add to cart" so it can be clicked again.
        this.el.innerHTML = original;
        this.el.classList.remove("disabled");
    }

    _showCartPopup(notification) {
        if (!notification || !notification.lines) {
            return;
        }
        // Coerce to the exact prop shape the native popup validates against
        // (id/quantity/price_total numbers, image_url/name strings).
        const lines = notification.lines.map((l) => ({
            id: Number(l.id),
            image_url: String(l.image_url || ""),
            quantity: Number(l.quantity || 1),
            name: String(l.name || ""),
            price_total: Number(l.price_total || 0),
        }));
        const notif = this.services.cartNotificationService;
        if (notif) {
            notif.add("", {
                lines: lines,
                currency_id: Number(notification.currency_id),
            });
        }
    }
}

// ── Affiliate "Add to cart" on the /shop grid tile ───────────────────────────
// The native tile button (o_wsale_product_btn_primary) is left completely
// untouched — no class/tag change, so every tile looks identical. For
// affiliate products it's flagged with data-aveenix-affiliate="1" (see
// av_shop_product_btn_affiliate_flag in templates.xml). Core's own
// WebsiteSale interaction would otherwise route this click through the real
// cart service, which always adds 0 qty for affiliate products by design
// (see AveenixCart.add_to_cart) and shows no popup. Intercept in capture
// phase — same as the login gate pattern — and reuse the exact same
// affiliate-cart RPC + popup as the product detail page instead.
export class AffiliateSaveButtonGrid extends Interaction {
    static selector = "#products_grid";

    start() {
        this._onDocClick = (ev) => {
            const btn = ev.target.closest(
                'button.o_wsale_product_btn_primary[data-aveenix-affiliate="1"]'
            );
            if (!btn || !this.el.contains(btn)) {
                return;
            }
            ev.preventDefault();
            ev.stopPropagation();
            ev.stopImmediatePropagation();
            this._onSave(btn);
        };
        document.addEventListener("click", this._onDocClick, { capture: true });
        this.registerCleanup(() =>
            document.removeEventListener("click", this._onDocClick, { capture: true })
        );
    }

    async _onSave(btn) {
        const input = btn.closest("form")?.querySelector('input[name="product_template_id"]');
        const productId = input && parseInt(input.value);
        if (!productId) {
            return;
        }
        try {
            const res = await rpc("/aveenix/affiliate/cart/add", { product_id: productId });
            if (res && res.ok) {
                this._showCartPopup(res.notification);
            }
        } catch {
            // ignore — button already looks like a normal add-to-cart, no
            // loading state to restore since we never touch its markup.
        }
    }

    _showCartPopup(notification) {
        if (!notification || !notification.lines) {
            return;
        }
        const lines = notification.lines.map((l) => ({
            id: Number(l.id),
            image_url: String(l.image_url || ""),
            quantity: Number(l.quantity || 1),
            name: String(l.name || ""),
            price_total: Number(l.price_total || 0),
        }));
        const notif = this.services.cartNotificationService;
        if (notif) {
            notif.add("", {
                lines: lines,
                currency_id: Number(notification.currency_id),
            });
        }
    }
}

// ── Remove button on affiliate cart section (QWeb-rendered server-side) ──────
export class AffiliateRemoveButton extends Interaction {
    static selector = ".av-aff-remove-btn";

    start() {
        this.addListener(this.el, "click", () => this._onRemove());
    }

    async _onRemove() {
        const lineId = parseInt(this.el.dataset.lineId);
        this.el.disabled = true;
        this.el.style.opacity = "0.5";

        try {
            await rpc("/aveenix/affiliate/cart/remove", { line_id: lineId });
        } catch {
            this.el.disabled = false;
            this.el.style.opacity = "";
            return;
        }

        const item = this.el.closest(".av-aff-item");
        if (!item) {
            return;
        }
        const section = document.querySelector(".av-aff-section");
        // If this is the last item, drop the whole section immediately (no
        // 220ms item-fade wait) so the "Buy from Our Trusted Partner" block
        // disappears without a trailing pause.
        const isLast = section
            ? section.querySelectorAll(".av-aff-item").length <= 1
            : true;
        if (isLast && section) {
            (section.parentElement || section).remove();
            return;
        }

        // Otherwise fade just this row out, then update the subtitle count.
        item.style.transition = "opacity .2s, transform .2s";
        item.style.opacity = "0";
        item.style.transform = "translateY(-4px)";
        setTimeout(() => {
            item.remove();
            const remaining = section
                ? section.querySelectorAll(".av-aff-item").length
                : 0;
            const subtitle = section && section.querySelector(".av-aff-section-subtitle");
            if (subtitle) {
                subtitle.textContent = (remaining !== 1
                    ? _t("%s items · fulfilled by partner stores", remaining)
                    : _t("%s item · fulfilled by partner stores", remaining));
            }
        }, 220);
    }
}

// ── Affiliate product page: hide native qty + Add-to-cart + Buy-now ─────────
// The native CTA wrapper is rendered for EVERY product so the heart / star /
// compare buttons are identical everywhere. For affiliate products we show our
// own .av-affiliate-buy button instead, so the native purchase controls must be
// hidden. Done in JS so it never depends on CSS :has() support or class merges.
export class AffiliateHideNativeCta extends Interaction {
    static selector = ".av-affiliate-buy";

    start() {
        this._applyCta();
        // Native website_sale interactions update the CTA area shortly after
        // load (variant/price resolution) and can re-hide our button. Re-assert
        // a few times so the affiliate button stays visible and native stays
        // hidden regardless of that timing.
        [100, 400, 1200].forEach((ms) =>
            this.waitForTimeout(() => this._applyCta(), ms)
        );
    }

    _applyCta() {
        const scope =
            this.el.closest(".o_wsale_product_details_content_section_cta") ||
            this.el.closest("#product_detail") ||
            document;
        // Hide the native add-to-cart + qty (our affiliate button now lives
        // inside #add_to_cart_wrap alongside them). Do NOT hide the wrap itself.
        scope
            .querySelectorAll(".css_quantity, #add_to_cart, #buy_now, .o_we_buy_now")
            .forEach((node) => {
                if (
                    node.classList.contains("av-affiliate-buy") ||
                    node.querySelector(".av-affiliate-buy")
                ) {
                    return;
                }
                node.style.setProperty("display", "none", "important");
            });
        // Force our affiliate button visible (beats any late inline hide).
        this.el.style.setProperty("display", "flex", "important");
    }
}

registry.category("public.interactions")
    .add("aveenix_website.AffiliateSaveButton", AffiliateSaveButton)
    .add("aveenix_website.AffiliateSaveButtonGrid", AffiliateSaveButtonGrid)
    .add("aveenix_website.AffiliateRemoveButton", AffiliateRemoveButton)
    .add("aveenix_website.AffiliateHideNativeCta", AffiliateHideNativeCta);
