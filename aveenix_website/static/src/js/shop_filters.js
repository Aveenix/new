/** @odoo-module **/

import { onMounted } from "@odoo/owl";
import publicWidget from "@web/legacy/js/public/public_widget";

publicWidget.registry.AvShopStockFilter = publicWidget.Widget.extend({
    selector: ".o_wsale_products_page",
    events: {
        "change .av-stock-check": "_onStockChange",
    },

    _onStockChange(ev) {
        const href = ev.currentTarget.dataset.href;
        if (href) {
            window.location.href = href;
        }
    },
});
