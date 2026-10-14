/** @odoo-module **/

import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";

function esc(str) {
    return String(str ?? "").replace(/[&<>"']/g, (c) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
}

function timeAgo(ts) {
    const diff = Math.floor((Date.now() - ts) / 1000);
    if (diff < 60) return _t("just now");
    if (diff < 3600) return _t("%s minutes ago", Math.floor(diff / 60));
    if (diff < 86400) return _t("%s hours ago", Math.floor(diff / 3600));
    const days = Math.floor(diff / 86400);
    return days > 1 ? _t("%s days ago", days) : _t("%s day ago", days);
}

// ── Notifications header badge ────────────────────────────────
export class NotifHeaderBadge extends Interaction {
    static selector = "#av-notif-header-btn";

    start() {
        this.updateBadge();
        this.addListener(window, "av-notif-changed", () => this.updateBadge());
    }

    async updateBadge() {
        const badge = this.el.querySelector("#av-notif-count");
        if (!badge) return;
        let count = 0;
        try {
            const res = await rpc("/aveenix/notifications/count");
            count = res.count || 0;
        } catch {
            count = 0;
        }
        if (count > 0) { badge.textContent = count; badge.style.display = "flex"; }
        else { badge.style.display = "none"; }
    }
}

// ── Notifications page ────────────────────────────────────────
export class NotificationsPage extends Interaction {
    static selector = ".av-notif-page";

    setup() {
        this.currentFilter = "all";
        this.notifications = [];
    }

    start() {
        if (this.el.dataset.isPublic === "1") {
            // Guest: template already renders the sign-in prompt, nothing to fetch.
            return;
        }

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

        this.fetchAndRender();
    }

    async fetchAndRender() {
        try {
            const res = await rpc("/mail/inbox/messages", { fetch_params: {} });
            const messages = (res && res.messages) || res || [];
            this.notifications = messages.map((m) => ({
                id: m.id,
                title: m.subject || "Notification",
                message: (m.body || "").replace(/<[^>]*>/g, ""),
                time: m.date ? new Date(m.date).getTime() : Date.now(),
                read: !m.needaction,
            }));
        } catch {
            this.notifications = [];
        }
        this.render();
    }

    filtered() {
        const f = this.currentFilter;
        if (f === "unread") return this.notifications.filter((n) => !n.read);
        return this.notifications;
    }

    render() {
        const list = this.filtered();
        const all = this.notifications;
        const unread = all.filter((n) => !n.read).length;

        const summary = this.el.querySelector("#av-notif-summary");
        if (summary) summary.textContent = _t("%s of %s notifications", list.length, all.length);

        const newBadge = this.el.querySelector("#av-notif-new-count");
        if (newBadge) {
            if (unread > 0) { newBadge.textContent = _t("%s new", unread); newBadge.style.display = "inline-flex"; }
            else { newBadge.style.display = "none"; }
        }

        const container = this.el.querySelector("#av-notif-list");
        const empty = this.el.querySelector("#av-notif-empty");
        if (!container) return;

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
                <div class="av-notif-item-icon" style="background:#2E7D5220; color:#2E7D52;">
                    <i class="fa fa-bell"></i>
                </div>
                <div class="av-notif-item-body">
                    <div class="av-notif-item-header">
                        <span class="av-notif-item-title">${esc(n.title)}</span>
                    </div>
                    <p class="av-notif-item-msg">${esc(n.message)}</p>
                    <div class="av-notif-item-meta">
                        <span class="av-notif-item-time">${timeAgo(n.time)}</span>
                    </div>
                </div>
                <div class="av-notif-item-actions">
                    ${!n.read ? `<button class="av-notif-action-read" data-id="${esc(n.id)}" title="${esc(_t("Mark as read"))}"><i class="fa fa-check"></i></button>` : ""}
                </div>`;

            const readBtn = item.querySelector(".av-notif-action-read");
            if (readBtn) {
                readBtn.addEventListener("click", (e) => {
                    e.stopPropagation();
                    this.markRead(n.id);
                });
            }

            wrap.appendChild(item);
        });

        container.appendChild(wrap);
    }

    async markRead(id) {
        try {
            await rpc("/aveenix/notifications/mark_read", { message_ids: [id] });
        } catch {
            return;
        }
        this.notifications = this.notifications.map((n) => n.id === id ? { ...n, read: true } : n);
        window.dispatchEvent(new CustomEvent("av-notif-changed"));
        this.render();
    }

    async markAll() {
        try {
            await rpc("/aveenix/notifications/mark_read", { all: true });
        } catch {
            return;
        }
        this.notifications = this.notifications.map((n) => ({ ...n, read: true }));
        window.dispatchEvent(new CustomEvent("av-notif-changed"));
        this.render();
    }
}

registry.category("public.interactions").add("NotifHeaderBadge", NotifHeaderBadge);
registry.category("public.interactions").add("NotificationsPage", NotificationsPage);
