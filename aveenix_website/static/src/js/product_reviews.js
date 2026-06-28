/** @odoo-module **/

import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";

// ── Product page tabs: Description / Reviews / Shipping ───────────
export class ProductTabs extends Interaction {
    static selector = ".av-pdp-tabs";

    dynamicContent = {
        ".av-tab-link": { "t-on-click": (ev) => this.onTabClick(ev) },
    };

    onTabClick(ev) {
        const target = ev.currentTarget.dataset.avTab;
        for (const link of this.el.querySelectorAll(".av-tab-link")) {
            link.classList.toggle("active", link === ev.currentTarget);
        }
        for (const panel of this.el.querySelectorAll(".av-tab-panel")) {
            panel.classList.toggle("active", panel.dataset.avPanel === target);
        }
    }
}

// ── Star rating input in the "write a review" form ───────────────
export class ReviewStarInput extends Interaction {
    static selector = ".av-star-input";

    dynamicContent = {
        ".av-star": {
            "t-on-mouseenter": (ev) => this.paint(this.valOf(ev.currentTarget)),
            "t-on-click": (ev) => this.onSelect(ev),
        },
        _root: { "t-on-mouseleave": () => this.paint(this.current) },
    };

    setup() {
        this.current = 0;
        this.stars = this.el.querySelectorAll(".av-star");
        this.input = this.el.querySelector('input[name="rating"]');
    }

    valOf(starEl) {
        return parseInt(starEl.dataset.val, 10) || 0;
    }

    paint(upto) {
        for (const star of this.stars) {
            const on = this.valOf(star) <= upto && upto > 0;
            star.classList.toggle("is-on", on);
            star.classList.toggle("fa-star", on);
            star.classList.toggle("fa-star-o", !on);
        }
    }

    onSelect(ev) {
        this.current = this.valOf(ev.currentTarget);
        if (this.input) {
            this.input.value = String(this.current);
        }
        this.paint(this.current);
    }
}

registry.category("public.interactions").add("ProductTabs", ProductTabs);
registry.category("public.interactions").add("ReviewStarInput", ReviewStarInput);
