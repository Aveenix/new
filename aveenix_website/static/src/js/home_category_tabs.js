/** @odoo-module **/

import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";

// ── Homepage "Shop by Category" tabs: Best Sellers / New Arrivals ───────────
// Both category grids are server-rendered (one per tab); clicking a tab toggles
// which grid is visible. No round-trip needed.
export class HomeCategoryTabs extends Interaction {
    static selector = ".av-categories-section";

    dynamicContent = {
        ".av-cat-tabs .av-tab": { "t-on-click": (ev) => this.onTabClick(ev) },
    };

    onTabClick(ev) {
        ev.preventDefault();
        const tab = ev.currentTarget;
        const key = tab.dataset.avCatTab;

        for (const t of this.el.querySelectorAll(".av-cat-tabs .av-tab")) {
            t.classList.toggle("av-tab-active", t === tab);
        }
        for (const panel of this.el.querySelectorAll(".av-cat-panel")) {
            panel.classList.toggle("active", panel.dataset.avCatPanel === key);
        }
    }
}

registry
    .category("public.interactions")
    .add("aveenix_website.HomeCategoryTabs", HomeCategoryTabs);
