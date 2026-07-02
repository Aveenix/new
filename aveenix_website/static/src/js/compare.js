/** @odoo-module **/

import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";

// Non-storable products (consumable/service) are always in stock
function isInStock(p) {
    if (p.type === 'consu' || p.type === 'service') return true;
    return p.virtual_available > 0;
}

// ── Unified list store (compare / fav / wish) ─────────────────────
// Logged-in  → server (res.users Many2many fields) + mirrors to localStorage
// Guest      → localStorage only
// On login   → merges guest localStorage into server, then uses server
class ListStore {
    constructor(type, storageKey, changeEvent) {
        this.type = type;
        this.storageKey = storageKey;
        this.changeEvent = changeEvent;
        this._loggedIn = null; // null = unknown yet
    }

    _lsGet() {
        try { return JSON.parse(localStorage.getItem(this.storageKey) || '[]'); } catch { return []; }
    }
    _lsSet(ids) {
        try { localStorage.setItem(this.storageKey, JSON.stringify(ids)); } catch {}
    }
    _lsClear() { try { localStorage.removeItem(this.storageKey); } catch {} }

    async isLoggedIn() {
        if (this._loggedIn !== null) return this._loggedIn;
        try {
            const res = await rpc('/aveenix/list/get', { list_type: this.type });
            this._loggedIn = res.logged_in;
            if (res.logged_in) {
                // Mirror server IDs to localStorage for fast badge reads
                this._lsSet(res.ids.map(String));
            }
        } catch {
            this._loggedIn = false;
        }
        return this._loggedIn;
    }

    // Called once after login to merge guest list into server
    async mergeGuestToServer(compareIds, favIds, wishIds) {
        try {
            const res = await rpc('/aveenix/list/merge', {
                compare_ids: compareIds,
                fav_ids: favIds,
                wish_ids: wishIds,
            });
            if (res.ok) {
                // Update localStorage mirrors from merged server state
                try { localStorage.setItem('av_compare_ids', JSON.stringify(res.compare_ids.map(String))); } catch {}
                try { localStorage.setItem('av_fav_ids', JSON.stringify(res.fav_ids.map(String))); } catch {}
                try { localStorage.setItem('av_wish_ids', JSON.stringify(res.wish_ids.map(String))); } catch {}
            }
        } catch {}
    }

    getIds() { return this._lsGet(); }

    async add(id) {
        const sid = String(id);
        const ids = this._lsGet();
        if (!ids.includes(sid)) { ids.push(sid); this._lsSet(ids); }
        if (await this.isLoggedIn()) {
            try { await rpc('/aveenix/list/add', { list_type: this.type, product_id: parseInt(id) }); } catch {}
        }
        window.dispatchEvent(new CustomEvent(this.changeEvent));
    }

    async remove(id) {
        this._lsSet(this._lsGet().filter(i => i !== String(id)));
        if (await this.isLoggedIn()) {
            try { await rpc('/aveenix/list/remove', { list_type: this.type, product_id: parseInt(id) }); } catch {}
        }
        window.dispatchEvent(new CustomEvent(this.changeEvent));
    }

    async clear() {
        this._lsClear();
        // No server clear — intentional: user may want to keep server list
        // If you want server clear too, add a /aveenix/list/clear endpoint
        window.dispatchEvent(new CustomEvent(this.changeEvent));
    }

    has(id) { return this._lsGet().includes(String(id)); }
}

const compareStore = new ListStore('compare', 'av_compare_ids', 'av-compare-changed');
const favStore    = new ListStore('fav',     'av_fav_ids',     'av-fav-changed');
const wishStore   = new ListStore('wish',    'av_wish_ids',    'av-wish-changed');

// ── On-login merge: runs once when Odoo fires its login event ─────
(async function initSync() {
    // Check if just logged in by fetching server state
    try {
        const res = await rpc('/aveenix/list/get', { list_type: 'compare' });
        if (!res.logged_in) return;

        // Logged in — get guest localStorage IDs before they get overwritten
        const guestCompare = compareStore._lsGet();
        const guestFav     = favStore._lsGet();
        const guestWish    = wishStore._lsGet();

        const hasGuest = guestCompare.length || guestFav.length || guestWish.length;

        if (hasGuest) {
            // Merge guest into server
            await compareStore.mergeGuestToServer(
                guestCompare.map(Number),
                guestFav.map(Number),
                guestWish.map(Number),
            );
        } else {
            // Just sync server → localStorage mirrors
            const [rf, rw] = await Promise.all([
                rpc('/aveenix/list/get', { list_type: 'fav' }),
                rpc('/aveenix/list/get', { list_type: 'wish' }),
            ]);
            compareStore._lsSet(res.ids.map(String));
            favStore._lsSet(rf.ids.map(String));
            wishStore._lsSet(rw.ids.map(String));
        }

        // Mark all stores as logged-in so they use server on next add/remove
        compareStore._loggedIn = true;
        favStore._loggedIn     = true;
        wishStore._loggedIn    = true;

        // Fire change events to update badges
        window.dispatchEvent(new CustomEvent('av-compare-changed'));
        window.dispatchEvent(new CustomEvent('av-fav-changed'));
        window.dispatchEvent(new CustomEvent('av-wish-changed'));
    } catch {}
})();

// ── Legacy localStorage helpers (kept for badge/page reads) ──────
const STORAGE_KEY = "av_compare_ids";
function getIds()        { return compareStore.getIds(); }
function addId(id)       { compareStore.add(id); }
function removeId(id)    { compareStore.remove(id); }
function clearIds()      { compareStore.clear(); }

// ── Badge updater (runs on every page) ───────────────────────────
export class CompareHeaderBadge extends Interaction {
    static selector = "#av-compare-header-btn";

    setup() {
        this.updateBadge();
    }

    start() {
        this.addListener(window, "storage", (e) => {
            if (e.key === STORAGE_KEY) this.updateBadge();
        });
        this.addListener(window, "av-compare-changed", () => this.updateBadge());
    }

    updateBadge() {
        const ids = getIds();
        const badge = this.el.querySelector("#av-compare-count");
        if (!badge) return;
        if (ids.length > 0) {
            badge.textContent = ids.length;
            badge.style.display = "flex";
        } else {
            badge.style.display = "none";
        }
    }
}

// ── "Add to Compare" buttons on shop / product pages ─────────────
export class AddToCompareButton extends Interaction {
    static selector = '[data-action="av_add_to_compare"]';

    dynamicContent = {
        _root: { 't-on-click': (ev) => this.onClick(ev) },
    };

    setup() {
        const id = this.el.dataset.productId;
        const icon = this.el.querySelector(".fa");
        if (id && compareStore.has(id)) {
            this.el.classList.add("av-added-to-compare");
            this.el.title = "Added to Compare";
            if (icon) { icon.classList.remove("fa-plus-square-o"); icon.classList.add("fa-plus-square"); }
        }
    }

    onClick(ev) {
        ev.preventDefault();
        const id = this.el.dataset.productId;
        if (!id) return;
        const icon = this.el.querySelector(".fa");
        if (compareStore.has(id)) {
            compareStore.remove(id);
            this.el.classList.remove("av-added-to-compare");
            this.el.title = "Add to Compare";
            if (icon) { icon.classList.remove("fa-plus-square"); icon.classList.add("fa-plus-square-o"); }
        } else {
            compareStore.add(id);
            this.el.classList.add("av-added-to-compare");
            this.el.title = "Added to Compare";
            if (icon) { icon.classList.remove("fa-plus-square-o"); icon.classList.add("fa-plus-square"); }
        }
        this.el.classList.remove("av-icon-bounce");
        void this.el.offsetWidth;
        this.el.classList.add("av-icon-bounce");
        const fa = this.el.querySelector(".fa") || this.el;
        fa.addEventListener("animationend", () => this.el.classList.remove("av-icon-bounce"), { once: true });
        window.dispatchEvent(new CustomEvent("av-compare-changed"));
    }
}

// ── Compare page ─────────────────────────────────────────────────
export class ComparePage extends Interaction {
    static selector = ".av-compare-page";

    setup() {
        this.products = [];
        this.loadProducts();
    }

    start() {
        const clearBtn = this.el.querySelector("#av-cmp-clear");
        const addAllBtn = this.el.querySelector("#av-cmp-add-all");
        if (clearBtn) this.addListener(clearBtn, "click", () => this.onClear());
        if (addAllBtn) this.addListener(addAllBtn, "click", () => this.onAddAll());
    }

    async loadProducts() {
        const ids = compareStore.getIds();
        if (!ids.length) {
            this.render([]);
            return;
        }
        try {
            this.products = await rpc('/aveenix/products', { ids: ids.map(Number) }) || [];
        } catch {
            this.products = [];
        }
        this.render(this.products);
    }

    render(products) {
        this.updateStats(products);

        const grid = this.el.querySelector("#av-compare-grid");
        const empty = this.el.querySelector("#av-compare-empty");

        const prev = grid.querySelector(".av-cmp-table-wrap");
        if (prev) prev.remove();

        if (!products.length) {
            if (empty) empty.style.display = "block";
            return;
        }
        if (empty) empty.style.display = "none";

        // Factors are now COLUMNS; each product is a ROW.
        const cols = [
            { label: "Image",       key: "image" },
            { label: "Category",    key: "category" },
            { label: "Price",       key: "price" },
            { label: "Stock",       key: "stock" },
            { label: "Description", key: "desc" },
            { label: "Action",      key: "action" },
        ];

        const wrap = document.createElement("div");
        wrap.className = "av-cmp-table-wrap";

        const table = document.createElement("table");
        table.className = "av-cmp-table";

        // Header row — empty corner (product column) + one column per factor
        const thead = document.createElement("thead");
        const headerRow = document.createElement("tr");
        headerRow.innerHTML = `<th class="av-cmp-th-label"></th>`;
        cols.forEach(({ label }) => {
            const th = document.createElement("th");
            th.className = "av-cmp-th-factor";
            th.textContent = label;
            headerRow.appendChild(th);
        });
        thead.appendChild(headerRow);
        table.appendChild(thead);

        // Body rows — one per product; first cell = product name + remove
        const tbody = document.createElement("tbody");
        products.forEach((p) => {
            const tr = document.createElement("tr");

            const nameCell = document.createElement("td");
            nameCell.className = "av-cmp-row-label av-cmp-th-product";
            nameCell.innerHTML = `
                <button class="av-cmp-remove" data-id="${p.id}" title="Remove">&#10005;</button>
                <span class="av-cmp-product-name">${esc(p.name)}</span>`;
            nameCell.querySelector(".av-cmp-remove").addEventListener("click", () => {
                compareStore.remove(p.id);
                const newProducts = this.products.filter((x) => String(x.id) !== String(p.id));
                this.products = newProducts;
                this.updateStats(newProducts);
                if (!newProducts.length) {
                    wrap.remove();
                    if (empty) empty.style.display = "block";
                } else {
                    this.render(newProducts);
                }
            });
            tr.appendChild(nameCell);

            cols.forEach(({ key }) => {
                const td = document.createElement("td");
                td.className = "av-cmp-row-val";
                if (key === "image") {
                    const src = p.image_512
                        ? "data:image/png;base64," + p.image_512
                        : "/web/static/img/placeholder.png";
                    td.innerHTML = `<img src="${src}" alt="${esc(p.name)}" class="av-cmp-img"/>`;
                } else if (key === "category") {
                    td.textContent = p.public_categ_name || (p.categ_id && p.categ_id[1]) || "Uncategorized";
                } else if (key === "price") {
                    td.innerHTML = `<span class="av-cmp-price">$${(p.list_price || 0).toFixed(2)}</span>`;
                } else if (key === "stock") {
                    const ok = isInStock(p);
                    td.innerHTML = `<span class="av-cmp-stock ${ok ? "in-stock" : "out-stock"}">
                        <i class="fa ${ok ? "fa-check-circle" : "fa-times-circle"}"></i>
                        ${ok ? "In Stock" : "Out of Stock"}
                    </span>`;
                } else if (key === "desc") {
                    td.textContent = p.description_sale || "—";
                    td.className += " av-cmp-desc";
                } else if (key === "action") {
                    td.innerHTML = `<a href="${p.website_url || "/shop"}" class="av-cmp-view-btn"><i class="fa fa-eye av-cmp-view-icon"></i><span class="av-cmp-view-text">View Product</span></a>`;
                }
                tr.appendChild(td);
            });

            tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        wrap.appendChild(table);
        grid.appendChild(wrap);
    }

    updateStats(products) {
        const count = products.length;
        const total = products.reduce((s, p) => s + (p.list_price || 0), 0);
        const inStock = products.filter((p) => isInStock(p)).length;
        const onSale = products.filter((p) => false).length;

        const $ = (id) => this.el.querySelector(id);
        const set = (id, val) => { const el = $(id); if (el) el.textContent = val; };

        set("#av-cmp-count", count);
        set("#av-cmp-total", "$" + total.toFixed(2));
        set("#av-cmp-stock", inStock);
        set("#av-cmp-sale", onSale);
        set("#av-cmp-item-label", count + " item" + (count !== 1 ? "s" : ""));
    }

    onClear() {
        compareStore.clear();
        this.products = [];
        this.render([]);
    }

    async onAddAll() {
        if (!this.products || !this.products.length) return;
        const btn = this.el.querySelector("#av-cmp-add-all");
        if (btn) { btn.disabled = true; btn.textContent = "Adding..."; }
        for (const p of this.products) {
            if (!p.product_id) continue;
            try {
                await rpc('/shop/cart/add', {
                    product_template_id: p.id,
                    product_id: p.product_id,
                    quantity: 1,
                });
            } catch {}
        }
        if (btn) { btn.disabled = false; btn.textContent = "Add All to Cart"; }
        window.location.href = "/shop/cart";
    }
}

// ── Favourites storage helpers (delegates to favStore) ───────────
const FAV_KEY = "av_fav_ids";
function getFavIds()      { return favStore.getIds(); }
function addFavId(id)     { favStore.add(id); }
function removeFavId(id)  { favStore.remove(id); }
function clearFavIds()    { favStore.clear(); }

// ── Favourites header badge ────────────────────────────────────
export class FavHeaderBadge extends Interaction {
    static selector = "#av-fav-header-btn";

    setup() {
        this.updateBadge();
    }

    start() {
        this.addListener(window, "storage", (e) => { if (e.key === FAV_KEY) this.updateBadge(); });
        this.addListener(window, "av-fav-changed", () => this.updateBadge());
    }

    updateBadge() {
        const ids = getFavIds();
        const badge = this.el.querySelector("#av-fav-count");
        if (!badge) return;
        if (ids.length > 0) { badge.textContent = ids.length; badge.style.display = "flex"; }
        else { badge.style.display = "none"; }
    }
}

// ── "Add to Favourites" buttons ────────────────────────────────
export class AddToFavButton extends Interaction {
    static selector = ".av-add-to-fav";

    dynamicContent = {
        _root: { "t-on-click": (ev) => this.onClick(ev) },
    };

    setup() {
        this.el.disabled = false;
        this.el.removeAttribute("disabled");
    }

    _getProductId() {
        // data-product-id (custom cards) or data-product-template-id (Odoo shop cards)
        return this.el.dataset.productId || this.el.dataset.productTemplateId;
    }

    onClick(ev) {
        ev.preventDefault();
        const id = this._getProductId();
        if (!id) return;
        const icon = this.el.querySelector(".fa");
        if (getFavIds().includes(String(id))) {
            removeFavId(id);
            this.el.classList.remove("av-added-to-fav");
            this.el.title = "Add to favourites";
            if (icon) { icon.classList.remove("fa-heart"); icon.classList.add("fa-heart-o"); }
        } else {
            addFavId(id);
            this.el.classList.add("av-added-to-fav");
            this.el.title = "In your favourites";
            if (icon) { icon.classList.remove("fa-heart-o"); icon.classList.add("fa-heart"); }
        }
        window.dispatchEvent(new CustomEvent("av-fav-changed"));
    }
}

// ── Favourites page ────────────────────────────────────────────
export class FavouritesPage extends Interaction {
    static selector = ".av-favourites-page";

    setup() {
        this.products = [];
        this.loadProducts();
    }

    start() {
        const clearBtn = this.el.querySelector("#av-fav-clear");
        const addAllBtn = this.el.querySelector("#av-fav-add-all");
        if (clearBtn) this.addListener(clearBtn, "click", () => this.onClear());
        if (addAllBtn) this.addListener(addAllBtn, "click", () => this.onAddAll());
    }

    async loadProducts() {
        const ids = getFavIds();
        if (!ids.length) { this.render([]); return; }
        try {
            this.products = await rpc('/aveenix/products', { ids: ids.map(Number) }) || [];
        } catch { this.products = []; }
        this.render(this.products);
    }

    render(products) {
        this.updateStats(products);
        const grid = this.el.querySelector("#av-fav-grid");
        const empty = this.el.querySelector("#av-fav-empty");
        const prev = grid.querySelector(".av-fav-cards");
        if (prev) prev.remove();

        if (!products.length) { if (empty) empty.style.display = "block"; return; }
        if (empty) empty.style.display = "none";

        const wrap = document.createElement("div");
        wrap.className = "av-fav-cards";

        products.forEach((p) => {
            const imgSrc = p.image_512 ? "data:image/png;base64," + p.image_512 : "/web/static/img/placeholder.png";
            const card = document.createElement("div");
            card.className = "av-fav-card";
            card.innerHTML = `
                <button class="av-fav-card-remove" data-id="${p.id}" title="Remove">&#10005;</button>
                <img src="${imgSrc}" alt="${esc(p.name)}" class="av-fav-card-img"/>
                <div class="av-fav-card-body">
                    <div class="av-fav-card-cat">${esc(p.public_categ_name || (p.categ_id && p.categ_id[1]) || "Uncategorized")}</div>
                    <h4 class="av-fav-card-name">${esc(p.name)}</h4>
                    <div class="av-fav-card-price">$${(p.list_price || 0).toFixed(2)}</div>
                    ${p.description_sale ? `<p class="av-fav-card-desc">${esc(p.description_sale)}</p>` : ""}
                    <div class="av-fav-card-stock ${isInStock(p) ? "in-stock" : "out-stock"}">
                        <i class="fa ${isInStock(p) ? "fa-check-circle" : "fa-times-circle"}"></i>
                        ${isInStock(p) ? "In Stock" : "Out of Stock"}
                    </div>
                    ${false ? `<div class="av-fav-card-sale"><i class="fa fa-tag"></i> On Sale</div>` : ""}
                    <a href="${p.website_url || "/shop"}" class="av-fav-card-view">View Product</a>
                </div>`;

            card.querySelector(".av-fav-card-remove").addEventListener("click", () => {
                removeFavId(p.id);
                card.remove();
                window.dispatchEvent(new CustomEvent("av-fav-changed"));
                const newProducts = this.products.filter((x) => String(x.id) !== String(p.id));
                this.products = newProducts;
                this.updateStats(newProducts);
                if (!wrap.querySelectorAll(".av-fav-card").length && empty) empty.style.display = "block";
            });

            wrap.appendChild(card);
        });

        grid.appendChild(wrap);
    }

    updateStats(products) {
        const count = products.length;
        const total = products.reduce((s, p) => s + (p.list_price || 0), 0);
        const inStock = products.filter((p) => isInStock(p)).length;
        const onSale = products.filter((p) => false).length;

        const set = (id, val) => { const el = this.el.querySelector(id); if (el) el.textContent = val; };
        set("#av-fav-count", count);
        set("#av-fav-total", "$" + total.toFixed(2));
        set("#av-fav-stock", inStock);
        set("#av-fav-sale", onSale);
        set("#av-fav-item-label", count + " item" + (count !== 1 ? "s" : ""));
    }

    onClear() {
        clearFavIds();
        this.products = [];
        this.render([]);
        window.dispatchEvent(new CustomEvent("av-fav-changed"));
    }

    async onAddAll() {
        if (!this.products || !this.products.length) return;
        const btn = this.el.querySelector("#av-fav-add-all");
        if (btn) { btn.disabled = true; btn.textContent = "Adding..."; }
        for (const p of this.products) {
            if (!p.product_id) continue;
            try {
                await rpc('/shop/cart/add', {
                    product_template_id: p.id,
                    product_id: p.product_id,
                    quantity: 1,
                });
            } catch {}
        }
        if (btn) { btn.disabled = false; btn.textContent = "Add All to Cart"; }
        window.location.href = "/shop/cart";
    }
}

function esc(str) {
    return String(str || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

// ── Wishlist storage helpers (delegates to wishStore) ─────────
const WISH_KEY = "av_wish_ids";
function getWishIds()     { return wishStore.getIds(); }
function addWishId(id)    { wishStore.add(id); }
function removeWishId(id) { wishStore.remove(id); }
function clearWishIds()   { wishStore.clear(); }

// ── Wishlist header badge ─────────────────────────────────────
export class WishHeaderBadge extends Interaction {
    static selector = "#av-wish-header-btn";

    setup() {
        this.updateBadge();
    }

    start() {
        this.addListener(window, "storage", (e) => { if (e.key === WISH_KEY) this.updateBadge(); });
        this.addListener(window, "av-wish-changed", () => this.updateBadge());
    }

    updateBadge() {
        const ids = getWishIds();
        const badge = this.el.querySelector("#av-wish-count");
        if (!badge) return;
        if (ids.length > 0) { badge.textContent = ids.length; badge.style.display = "flex"; }
        else { badge.style.display = "none"; }
    }
}

// ── "Add to Wishlist" buttons ─────────────────────────────────
export class AddToWishButton extends Interaction {
    static selector = ".av-add-to-wish";

    dynamicContent = {
        _root: { "t-on-click": (ev) => this.onClick(ev) },
    };

    onClick(ev) {
        ev.preventDefault();
        const id = this.el.dataset.productId || this.el.dataset.productTemplateId;
        if (!id) return;
        const icon = this.el.querySelector(".fa");
        if (getWishIds().includes(String(id))) {
            removeWishId(id);
            this.el.classList.remove("av-added-to-wish");
            this.el.title = "Add to Wishlist";
            if (icon) { icon.classList.remove("fa-star"); icon.classList.add("fa-star-o"); }
        } else {
            addWishId(id);
            this.el.classList.add("av-added-to-wish");
            this.el.title = "Added to Wishlist";
            if (icon) { icon.classList.remove("fa-star-o"); icon.classList.add("fa-star"); }
        }
        const wishFa = this.el.querySelector(".fa") || this.el;
        this.el.classList.remove("av-icon-bounce");
        void this.el.offsetWidth;
        this.el.classList.add("av-icon-bounce");
        wishFa.addEventListener("animationend", () => this.el.classList.remove("av-icon-bounce"), { once: true });
        window.dispatchEvent(new CustomEvent("av-wish-changed"));
    }
}

// ── Wishlist page ─────────────────────────────────────────────
export class WishlistPage extends Interaction {
    static selector = ".av-wishlist-page";

    setup() {
        this.products = [];
        this.loadProducts();
    }

    start() {
        const clearBtn = this.el.querySelector("#av-wish-clear");
        const addAllBtn = this.el.querySelector("#av-wish-add-all");
        if (clearBtn) this.addListener(clearBtn, "click", () => this.onClear());
        if (addAllBtn) this.addListener(addAllBtn, "click", () => this.onAddAll());
    }

    async loadProducts() {
        const ids = getWishIds();
        if (!ids.length) { this.render([]); return; }
        try {
            this.products = await rpc('/aveenix/products', { ids: ids.map(Number) }) || [];
        } catch { this.products = []; }
        this.render(this.products);
    }

    render(products) {
        this.updateStats(products);
        const grid = this.el.querySelector("#av-wish-grid");
        const empty = this.el.querySelector("#av-wish-empty");
        const prev = grid.querySelector(".av-wish-cards");
        if (prev) prev.remove();

        if (!products.length) { if (empty) empty.style.display = "block"; return; }
        if (empty) empty.style.display = "none";

        const wrap = document.createElement("div");
        wrap.className = "av-wish-cards";

        products.forEach((p) => {
            const imgSrc = p.image_512 ? "data:image/png;base64," + p.image_512 : "/web/static/img/placeholder.png";
            const card = document.createElement("div");
            card.className = "av-wish-card";
            card.innerHTML = `
                <button class="av-wish-card-remove" data-id="${p.id}" title="Remove">&#10005;</button>
                <img src="${imgSrc}" alt="${esc(p.name)}" class="av-wish-card-img"/>
                <div class="av-wish-card-body">
                    <div class="av-wish-card-cat">${esc(p.public_categ_name || (p.categ_id && p.categ_id[1]) || "Uncategorized")}</div>
                    <h4 class="av-wish-card-name">${esc(p.name)}</h4>
                    <div class="av-wish-card-price">$${(p.list_price || 0).toFixed(2)}</div>
                    ${p.description_sale ? `<p class="av-wish-card-desc">${esc(p.description_sale)}</p>` : ""}
                    <div class="av-wish-card-stock ${isInStock(p) ? "in-stock" : "out-stock"}">
                        <i class="fa ${isInStock(p) ? "fa-check-circle" : "fa-times-circle"}"></i>
                        ${isInStock(p) ? "In Stock" : "Out of Stock"}
                    </div>
                    ${false ? `<div class="av-wish-card-sale"><i class="fa fa-tag"></i> On Sale</div>` : ""}
                    <a href="${p.website_url || "/shop"}" class="av-wish-card-view">View Product</a>
                </div>`;

            card.querySelector(".av-wish-card-remove").addEventListener("click", () => {
                removeWishId(p.id);
                card.remove();
                window.dispatchEvent(new CustomEvent("av-wish-changed"));
                const newProducts = this.products.filter((x) => String(x.id) !== String(p.id));
                this.products = newProducts;
                this.updateStats(newProducts);
                if (!wrap.querySelectorAll(".av-wish-card").length && empty) empty.style.display = "block";
            });

            wrap.appendChild(card);
        });

        grid.appendChild(wrap);
    }

    updateStats(products) {
        const count = products.length;
        const total = products.reduce((s, p) => s + (p.list_price || 0), 0);
        const inStock = products.filter((p) => isInStock(p)).length;
        const onSale = products.filter((p) => false).length;

        const set = (id, val) => { const el = this.el.querySelector(id); if (el) el.textContent = val; };
        set("#av-wish-count", count);
        set("#av-wish-total", "$" + total.toFixed(2));
        set("#av-wish-stock", inStock);
        set("#av-wish-sale", onSale);
        set("#av-wish-item-label", count + " item" + (count !== 1 ? "s" : ""));
    }

    onClear() {
        clearWishIds();
        this.products = [];
        this.render([]);
        window.dispatchEvent(new CustomEvent("av-wish-changed"));
    }

    async onAddAll() {
        if (!this.products || !this.products.length) return;
        const btn = this.el.querySelector("#av-wish-add-all");
        if (btn) { btn.disabled = true; btn.textContent = "Adding..."; }
        for (const p of this.products) {
            if (!p.product_id) continue;
            try {
                await rpc('/shop/cart/add', {
                    product_template_id: p.id,
                    product_id: p.product_id,
                    quantity: 1,
                });
            } catch {}
        }
        if (btn) { btn.disabled = false; btn.textContent = "Add All to Cart"; }
        window.location.href = "/shop/cart";
    }
}

// ── Notifications storage helpers ────────────────────────────
const NOTIF_KEY = "av_notifications";

const DEMO_NOTIFICATIONS = [
    {
        id: "n1",
        icon: "fa-shopping-cart",
        iconColor: "#2E7D52",
        title: "Order #ORD-2024-001 Delivered",
        message: "Your order containing Wireless Headphones has been successfully delivered to 123 Main Street.",
        time: Date.now() - 2 * 60 * 60 * 1000,
        tag: "Orders",
        priority: "important",
        read: false,
    },
    {
        id: "n2",
        icon: "fa-bell",
        iconColor: "#2C6B8A",
        title: "Flash Sale: 50% off Electronics",
        message: "Limited time offer on selected electronics items. Sale ends in 6 hours!",
        time: Date.now() - 4 * 60 * 60 * 1000,
        tag: "Promotions",
        priority: null,
        read: false,
    },
    {
        id: "n3",
        icon: "fa-bell",
        iconColor: "#2C6B8A",
        title: "Item Back in Stock",
        message: "Wireless Headphones from your wishlist is now available. Only 5 left in stock!",
        time: Date.now() - 24 * 60 * 60 * 1000,
        tag: "Inventory",
        priority: null,
        read: true,
    },
];

function getNotifications() {
    try {
        const raw = localStorage.getItem(NOTIF_KEY);
        if (raw) return JSON.parse(raw);
    } catch {}
    localStorage.setItem(NOTIF_KEY, JSON.stringify(DEMO_NOTIFICATIONS));
    return DEMO_NOTIFICATIONS;
}

function saveNotifications(list) {
    try { localStorage.setItem(NOTIF_KEY, JSON.stringify(list)); } catch {}
}

function getUnreadCount() {
    return getNotifications().filter((n) => !n.read).length;
}

function timeAgo(ts) {
    const diff = Math.floor((Date.now() - ts) / 1000);
    if (diff < 60) return "just now";
    if (diff < 3600) return Math.floor(diff / 60) + " minutes ago";
    if (diff < 86400) return Math.floor(diff / 3600) + " hours ago";
    return Math.floor(diff / 86400) + " day" + (Math.floor(diff / 86400) > 1 ? "s" : "") + " ago";
}

// ── Notifications header badge ────────────────────────────────
export class NotifHeaderBadge extends Interaction {
    static selector = "#av-notif-header-btn";

    setup() {
        this.updateBadge();
    }

    start() {
        this.addListener(window, "storage", (e) => { if (e.key === NOTIF_KEY) this.updateBadge(); });
        this.addListener(window, "av-notif-changed", () => this.updateBadge());
    }

    updateBadge() {
        const count = getUnreadCount();
        const badge = this.el.querySelector("#av-notif-count");
        if (!badge) return;
        if (count > 0) { badge.textContent = count; badge.style.display = "flex"; }
        else { badge.style.display = "none"; }
    }
}

// ── Notifications page ────────────────────────────────────────
export class NotificationsPage extends Interaction {
    static selector = ".av-notif-page";

    setup() {
        this.currentFilter = "all";
        this.notifications = getNotifications();
    }

    start() {
        const markAllBtn = this.el.querySelector("#av-notif-mark-all");
        const filterBtn = this.el.querySelector("#av-notif-filter-btn");
        const dropdown = this.el.querySelector("#av-notif-filter-dropdown");

        if (markAllBtn) this.addListener(markAllBtn, "click", () => this.markAll());

        if (filterBtn && dropdown) {
            this.addListener(filterBtn, "click", (e) => {
                e.stopPropagation();
                dropdown.style.display = dropdown.style.display === "none" ? "flex" : "none";
            });
            this.addListener(document, "click", () => { dropdown.style.display = "none"; });

            dropdown.querySelectorAll(".av-notif-filter-opt").forEach((btn) => {
                this.addListener(btn, "click", (e) => {
                    e.stopPropagation();
                    this.currentFilter = btn.dataset.filter;
                    dropdown.querySelectorAll(".av-notif-filter-opt").forEach((b) => b.classList.remove("av-notif-filter-active"));
                    btn.classList.add("av-notif-filter-active");
                    dropdown.style.display = "none";
                    this.render();
                });
            });
        }

        this.render();
    }

    filtered() {
        const f = this.currentFilter;
        if (f === "all") return this.notifications;
        if (f === "unread") return this.notifications.filter((n) => !n.read);
        return this.notifications.filter((n) => n.tag && n.tag.toLowerCase() === f);
    }

    render() {
        const list = this.filtered();
        const all = this.notifications;
        const unread = all.filter((n) => !n.read).length;

        const summary = this.el.querySelector("#av-notif-summary");
        if (summary) summary.textContent = list.length + " of " + all.length + " notifications";

        const newBadge = this.el.querySelector("#av-notif-new-count");
        if (newBadge) {
            if (unread > 0) { newBadge.textContent = unread + " new"; newBadge.style.display = "inline-flex"; }
            else { newBadge.style.display = "none"; }
        }

        const container = this.el.querySelector("#av-notif-list");
        const empty = this.el.querySelector("#av-notif-empty");

        const prev = container.querySelector(".av-notif-items");
        if (prev) prev.remove();

        if (!list.length) {
            if (empty) empty.style.display = "flex";
            return;
        }
        if (empty) empty.style.display = "none";

        const wrap = document.createElement("div");
        wrap.className = "av-notif-items";

        list.forEach((n) => {
            const item = document.createElement("div");
            item.className = "av-notif-item" + (n.read ? "" : " av-notif-unread");
            item.dataset.id = n.id;

            item.innerHTML = `
                <div class="av-notif-item-icon" style="background:${esc(n.iconColor || "#2E7D52")}20; color:${esc(n.iconColor || "#2E7D52")};">
                    <i class="fa ${esc(n.icon || "fa-bell")}"></i>
                </div>
                <div class="av-notif-item-body">
                    <div class="av-notif-item-header">
                        <span class="av-notif-item-title">${esc(n.title)}</span>
                        ${n.priority === "important" ? `<span class="av-notif-priority">${esc(n.priority.charAt(0).toUpperCase() + n.priority.slice(1))}</span>` : ""}
                    </div>
                    <p class="av-notif-item-msg">${esc(n.message)}</p>
                    <div class="av-notif-item-meta">
                        <span class="av-notif-item-time">${timeAgo(n.time)}</span>
                        ${n.tag ? `<span class="av-notif-item-tag">${esc(n.tag)}</span>` : ""}
                    </div>
                </div>
                <div class="av-notif-item-actions">
                    ${!n.read ? `<button class="av-notif-action-read" data-id="${esc(n.id)}" title="Mark as read"><i class="fa fa-check"></i></button>` : ""}
                    <button class="av-notif-action-delete" data-id="${esc(n.id)}" title="Dismiss"><i class="fa fa-times"></i></button>
                </div>`;

            const readBtn = item.querySelector(".av-notif-action-read");
            if (readBtn) {
                readBtn.addEventListener("click", (e) => {
                    e.stopPropagation();
                    this.markRead(n.id);
                });
            }

            item.querySelector(".av-notif-action-delete").addEventListener("click", (e) => {
                e.stopPropagation();
                this.deleteNotif(n.id);
            });

            wrap.appendChild(item);
        });

        container.appendChild(wrap);
    }

    markRead(id) {
        this.notifications = this.notifications.map((n) => n.id === id ? { ...n, read: true } : n);
        saveNotifications(this.notifications);
        window.dispatchEvent(new CustomEvent("av-notif-changed"));
        this.render();
    }

    markAll() {
        this.notifications = this.notifications.map((n) => ({ ...n, read: true }));
        saveNotifications(this.notifications);
        window.dispatchEvent(new CustomEvent("av-notif-changed"));
        this.render();
    }

    deleteNotif(id) {
        this.notifications = this.notifications.filter((n) => n.id !== id);
        saveNotifications(this.notifications);
        window.dispatchEvent(new CustomEvent("av-notif-changed"));
        this.render();
    }
}

registry.category("public.interactions").add("CompareHeaderBadge", CompareHeaderBadge);
registry.category("public.interactions").add("AddToCompareButton", AddToCompareButton);
registry.category("public.interactions").add("ComparePage", ComparePage);
registry.category("public.interactions").add("FavHeaderBadge", FavHeaderBadge);
registry.category("public.interactions").add("AddToFavButton", AddToFavButton);
registry.category("public.interactions").add("FavouritesPage", FavouritesPage);
registry.category("public.interactions").add("WishHeaderBadge", WishHeaderBadge);
registry.category("public.interactions").add("AddToWishButton", AddToWishButton);
registry.category("public.interactions").add("WishlistPage", WishlistPage);
registry.category("public.interactions").add("NotifHeaderBadge", NotifHeaderBadge);
registry.category("public.interactions").add("NotificationsPage", NotificationsPage);
