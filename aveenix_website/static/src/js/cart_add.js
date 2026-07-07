/** @odoo-module **/

import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";

// Product-card "Add to Cart" (.js_av_add_to_cart) on shop grids / rows.
// Uses Odoo's native `cart` service so the product is added to the real cart
// AND the standard website_sale add-to-cart popup is shown — identical to the
// native product page behaviour.
//
// Guests are intercepted earlier by CartLoginGate (capture-phase on document,
// stops propagation), so this handler only runs for logged-in users.
export class AveenixCardAddToCart extends Interaction {
    static selector = ".js_av_add_to_cart";

    dynamicContent = {
        _root: { "t-on-click.prevent": (ev) => this.onClick(ev) },
    };

    async onClick() {
        const productId = parseInt(this.el.dataset.productId || "");
        const productTemplateId = parseInt(this.el.dataset.productTemplateId || "");
        if (!productTemplateId) {
            return;
        }
        await this.services["cart"].add({
            productTemplateId: productTemplateId,
            productId: productId || undefined,
            quantity: 1,
        });
    }
}

registry.category("public.interactions")
    .add("aveenix_website.CardAddToCart", AveenixCardAddToCart);
