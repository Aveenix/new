/** @odoo-module **/

import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";

/**
 * Favourite and compare toggles on Aveenix Connect listings
 * (aveenix_connect.connect_list_buttons). The server keeps the lists
 * (controllers/main.py, connect_list_toggle); this keeps every button for
 * the same listing and the header counts in step, and reloads the
 * favourites / compare page when a listing leaves it.
 */
export class ConnectListButton extends Interaction {
    static selector = "[data-connect-list]";

    dynamicContent = {
        _root: { "t-on-click.prevent.stop": this.onClick },
    };

    async onClick() {
        const kind = this.el.dataset.connectList;
        const businessId = parseInt(this.el.dataset.businessId);
        const result = await this.waitFor(rpc("/connect/list/toggle", { kind, business_id: businessId }));
        if (result.full) {
            this.services.notification.add(
                _t("You can compare up to 4 businesses. Remove one to add another."),
                { type: "warning", title: _t("Compare list is full") },
            );
            return;
        }
        if (this.el.closest(`[data-connect-reload="${kind}"]`)) {
            window.location.reload();
            return;
        }
        for (const button of document.querySelectorAll(
            `[data-connect-list="${kind}"][data-business-id="${businessId}"]`
        )) {
            button.classList.toggle("is-active", result.active);
            button.setAttribute("aria-pressed", result.active ? "true" : "false");
        }
        for (const badge of document.querySelectorAll(`[data-connect-count="${kind}"]`)) {
            badge.textContent = result.count;
            badge.style.display = result.count ? "" : "none";
        }
    }
}

registry.category("public.interactions").add("aveenix_connect.list_button", ConnectListButton);
