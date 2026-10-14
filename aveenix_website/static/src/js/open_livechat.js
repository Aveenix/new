/** @odoo-module **/

import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";

// ── "Live Chat" link on the About page ─────────────────────────────────────
// The im_livechat module mounts its floating chat bubble inside a shadow DOM
// (host element `.o-livechat-root`). A plain document.querySelector can't pierce
// the shadow root, so we grab the host first, then query the button inside its
// shadowRoot. Clicking our link just opens that existing bubble.
const HOST_SELECTOR = ".o-livechat-root";
const BUTTON_SELECTOR = ".o-livechat-LivechatButton";

export class OpenLivechat extends Interaction {
    static selector = ".av-open-livechat";

    dynamicContent = {
        _root: { "t-on-click": (ev) => this.onClick(ev) },
    };

    onClick(ev) {
        ev.preventDefault();
        const host = document.querySelector(HOST_SELECTOR);
        const btn = host?.shadowRoot?.querySelector(BUTTON_SELECTOR);
        if (btn) {
            btn.click();
        } else {
            // No bubble on the page — channel not published, no operator online,
            // or the widget hasn't mounted yet.
            console.warn("Live chat widget not available on this page.");
        }
    }
}

registry
    .category("public.interactions")
    .add("aveenix_website.OpenLivechat", OpenLivechat);
