/** @odoo-module **/

import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";

// Swap product images that are hosted externally (pulled from WooCommerce
// meta_data, e.g. Amazon CDN URLs) onto the page. Core templates render
// <img src="/web/image/product.template/<id>/image_*">, which is blank for
// these products; we detect those, ask the server for the external URLs, and
// repoint the <img> (and gallery thumbnails) at the real CDN images.

const IMG_RE = /\/web\/image\/product\.template\/(\d+)\//;
const VARIANT_IMG_RE = /\/web\/image\/product\.product\/(\d+)\//;

export class ExternalProductImages extends Interaction {
    // Run once per page on the document body.
    static selector = "body";

    setup() {
        this._timer = null;
    }

    start() {
        this._busy = false;
        this._runAll();
        // Re-apply after dynamic shop updates (filters, infinite scroll, sliders,
        // AJAX cart refresh). Only react when new element nodes are ADDED — our
        // own img.src writes are attribute changes and are ignored, so we never
        // feed our own mutations back into the observer (which previously fought
        // the cart quantity widget's re-render).
        this._observer = new MutationObserver((mutations) => {
            if (this._busy) return;
            const addedEls = mutations.some((m) =>
                [...m.addedNodes].some((n) => n.nodeType === 1)
            );
            if (!addedEls) return;
            clearTimeout(this._timer);
            this._timer = setTimeout(() => this._runAll(), 200);
        });
        this._observer.observe(this.el, { childList: true, subtree: true });
    }

    async _runAll() {
        // Guard so the DOM writes we do here don't retrigger ourselves.
        this._busy = true;
        try {
            await this.apply();
            await this.applyVariants();
            this.fixDescriptionImages();
        } finally {
            this._busy = false;
        }
    }

    fixDescriptionImages() {
        // Amazon A+ description HTML ships each image TWICE: a real <img> plus a
        // lazy-loaded placeholder (<img src="grey-pixel.gif" data-src="...">).
        // The real one already displays, so just remove the placeholder to avoid
        // duplicate / empty-grey images.
        const lazies = this.el.querySelectorAll(
            'img.a-lazy-loaded, img[src*="grey-pixel"]'
        );
        lazies.forEach((img) => img.remove());
    }

    destroy() {
        if (this._observer) {
            this._observer.disconnect();
        }
        clearTimeout(this._timer);
    }

    _collectBy(selector, re) {
        const map = new Map();
        this.el.querySelectorAll(selector).forEach((img) => {
            if (img.dataset.avExtDone) return;
            const m = (img.getAttribute("src") || "").match(re);
            if (!m) return;
            const id = m[1];
            if (!map.has(id)) map.set(id, []);
            map.get(id).push(img);
        });
        return map;
    }

    _applyMap(map, data) {
        for (const [id, urls] of Object.entries(data)) {
            if (!urls || !urls.length) continue;
            (map.get(id) || []).forEach((img, i) => {
                img.src = urls[i] || urls[0];
                img.srcset = "";
                img.removeAttribute("data-src");
                img.dataset.avExtDone = "1";
            });
        }
        // Mark the rest as processed so we don't re-query them.
        for (const imgs of map.values()) {
            imgs.forEach((img) => (img.dataset.avExtDone = "1"));
        }
    }

    // product.template images (shop grid, product page).
    async apply() {
        const map = this._collectBy(
            'img[src*="/web/image/product.template/"]', IMG_RE
        );
        if (!map.size) return;
        let data;
        try {
            data = await this.waitFor(
                rpc("/aveenix/product_images", { ids: [...map.keys()] })
            );
        } catch {
            return; // fail silent — keep Odoo's own images
        }
        if (data) this._applyMap(map, data);
    }

    // product.product (variant) images — cart lines & order summary card.
    async applyVariants() {
        const map = this._collectBy(
            'img[src*="/web/image/product.product/"]', VARIANT_IMG_RE
        );
        if (!map.size) return;
        let data;
        try {
            data = await this.waitFor(
                rpc("/aveenix/variant_images", { ids: [...map.keys()] })
            );
        } catch {
            return;
        }
        if (data) this._applyMap(map, data);
    }
}

registry
    .category("public.interactions")
    .add("aveenix_website.ExternalProductImages", ExternalProductImages);
