/** @odoo-module **/

import { WebsiteBuilderClientAction } from "@website/client_actions/website_preview/website_builder_action";
import { patch } from "@web/core/utils/patch";

patch(WebsiteBuilderClientAction.prototype, {
    setIframeLoaded() {
        this.iframeLoaded = new Promise((resolve) => {
            this.resolveIframeLoaded = () => {
                this.hotkeyService.registerIframe(this.websiteContent.el);
                this.websiteContent.el.contentWindow.addEventListener(
                    "beforeunload",
                    this.onPageUnload.bind(this)
                );

                this.addListeners(this.websiteContent.el.contentDocument);
                
                // Safe check to avoid Odoo 19 race condition crash: 
                // "Cannot read properties of null (reading 'replaceChildren')"
                const docEl = this.iframefallback.el?.contentDocument?.documentElement;
                if (docEl && typeof docEl.replaceChildren === 'function') {
                    docEl.replaceChildren();
                }
                
                resolve(this.websiteContent.el);
            };
        });
    }
});
