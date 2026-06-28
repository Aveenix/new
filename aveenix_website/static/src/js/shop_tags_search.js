/** @odoo-module **/

import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";

// ── Searchable Tags filter on the shop sidebar ──────────────────────────────
// The catalog has 33k+ tags. The server renders only a search box + the first 5
// tags; typing here queries /aveenix/shop/tags/search and swaps the visible list.
// Currently-selected tags (from the URL) stay checked because the server always
// returns them alongside the matches.
export class ShopTagsSearch extends Interaction {
    static selector = ".av-tags-filter";

    setup() {
        this.input = this.el.querySelector(".av-tags-search");
        this.list = this.el.querySelector(".av-tags-list");
        this.empty = this.el.querySelector(".av-tags-empty");
        this._timer = null;
        // The tags applied via the URL — kept checked across searches.
        const sel = (this.input && this.input.dataset.selected) || "";
        this.selected = sel ? sel.split(",").filter(Boolean) : [];
        // Remember the initial (server-rendered) markup so clearing the box
        // restores the default 5-tag view without a round-trip.
        this.defaultHtml = this.list ? this.list.innerHTML : "";
    }

    start() {
        if (!this.input) {
            return;
        }
        this.addListener(this.input, "input", () => this._onInput());
    }

    _onInput() {
        const query = this.input.value.trim();
        clearTimeout(this._timer);
        if (!query) {
            // Restore the default view.
            this.list.innerHTML = this.defaultHtml;
            this.empty.style.display = "none";
            return;
        }
        this._timer = setTimeout(() => this._search(query), 220);
    }

    async _search(query) {
        let res;
        try {
            res = await rpc("/aveenix/shop/tags/search", {
                query,
                limit: 20,
                selected: this.selected,
            });
        } catch {
            return;
        }
        const tags = (res && res.tags) || [];
        this._render(tags);
    }

    _render(tags) {
        if (!tags.length) {
            this.list.innerHTML = "";
            this.empty.style.display = "";
            return;
        }
        this.empty.style.display = "none";
        const selectedSet = new Set(this.selected.map(String));
        this.list.innerHTML = tags
            .map((t) => {
                const checked = selectedSet.has(String(t.id)) ? " checked" : "";
                const name = this._escape(t.name);
                return (
                    '<div class="form-check mb-1 av-tag-item">' +
                    `<input type="checkbox" name="tags" class="form-check-input" id="tag_${t.id}" value="${t.id}"${checked}/>` +
                    `<label class="form-check-label fw-normal" for="tag_${t.id}">${name}</label>` +
                    "</div>"
                );
            })
            .join("");
    }

    _escape(str) {
        const div = document.createElement("div");
        div.textContent = str == null ? "" : str;
        return div.innerHTML;
    }
}

registry
    .category("public.interactions")
    .add("aveenix_website.ShopTagsSearch", ShopTagsSearch);

// ── Expandable category tree on the shop sidebar ────────────────────────────
// Parent rows have a chevron toggle that expands/collapses their children.
// The branch containing the active category is rendered open by the server.
export class ShopCategoryTree extends Interaction {
    static selector = ".av-cat-tree";

    dynamicContent = {
        ".av-cat-toggle": { "t-on-click": (ev) => this.onToggle(ev) },
    };

    onToggle(ev) {
        ev.preventDefault();
        const parentRow = ev.currentTarget.closest(".av-cat-parent");
        if (!parentRow) {
            return;
        }
        const children = parentRow.nextElementSibling;
        const icon = ev.currentTarget.querySelector(".fa");
        const open = parentRow.classList.toggle("is-open");
        if (children && children.classList.contains("av-cat-children")) {
            children.classList.toggle("is-open", open);
        }
        if (icon) {
            icon.classList.toggle("fa-chevron-down", open);
            icon.classList.toggle("fa-chevron-right", !open);
        }
        ev.currentTarget.setAttribute("aria-expanded", open ? "true" : "false");
    }
}

registry
    .category("public.interactions")
    .add("aveenix_website.ShopCategoryTree", ShopCategoryTree);
