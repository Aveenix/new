/** @odoo-module **/

import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";

// ── "Save to My Affiliates" button on product detail page ───────────────────
export class AffiliateSaveButton extends Interaction {
    static selector = ".av-affiliate-save-btn";

    start() {
        this.addListener(this.el, "click", () => this._onSave());
    }

    async _onSave() {
        const productId = parseInt(this.el.dataset.productId);
        const original = this.el.innerHTML;

        this.el.disabled = true;
        this.el.innerHTML = '<i class="fa fa-spinner fa-spin me-2"/>Saving…';

        try {
            const res = await rpc("/aveenix/affiliate/cart/add", { product_id: productId });
            if (res && res.ok) {
                // Product is now in the cart → lock the button to "In Cart".
                // Note: <i></i> must be closed so "In Cart" stays outside it.
                this.el.innerHTML = '<i class="fa fa-check me-2"></i>In Cart';
                this.el.classList.add("disabled");
                this.el.removeAttribute("href");
            } else {
                this.el.innerHTML = original;
                this.el.disabled = false;
            }
        } catch {
            this.el.innerHTML = original;
            this.el.disabled = false;
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
        if (item) {
            item.style.transition = "opacity .2s, transform .2s";
            item.style.opacity = "0";
            item.style.transform = "translateY(-4px)";
            setTimeout(() => {
                item.remove();
                const section = document.querySelector(".av-aff-section");
                // Update the "N items · fulfilled by partner stores" subtitle.
                const remaining = section
                    ? section.querySelectorAll(".av-aff-item").length
                    : 0;
                const subtitle = section && section.querySelector(".av-aff-section-subtitle");
                if (subtitle) {
                    subtitle.textContent =
                        remaining + " item" + (remaining !== 1 ? "s" : "") +
                        " · fulfilled by partner stores";
                }
                // Hide only the affiliate wrapper div if no items remain.
                if (section && remaining === 0) {
                    section.closest(".mb-4")?.remove();
                }
            }, 220);
        }
    }
}

registry.category("public.interactions")
    .add("aveenix_website.AffiliateSaveButton", AffiliateSaveButton)
    .add("aveenix_website.AffiliateRemoveButton", AffiliateRemoveButton);
