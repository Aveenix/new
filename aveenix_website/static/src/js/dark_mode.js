(function () {
    "use strict";

    var STORAGE_KEY = "av_theme";

    function applyTheme(toggle, html, dark) {
        var icon  = toggle ? toggle.querySelector(".av-toggle-icon") : null;
        var label = toggle ? toggle.querySelector(".av-toggle-label") : null;
        var nmToggle = document.getElementById("nm-theme-toggle");
        if (dark) {
            html.setAttribute("data-theme", "dark");
            html.setAttribute("data-bs-theme", "dark");
            html.style.setProperty("--av-product-img-bg", "#2a2a2a");
            html.style.setProperty("--o-wsale-card-thumb-background", "#2a2a2a");
            html.style.setProperty("--o-wsale-card-bg", "#242424");
            html.style.setProperty("--bs-card-bg", "#242424");
            html.style.setProperty("--bs-body-bg", "#181818");
            if (icon)  { icon.textContent  = "☀"; }
            if (label) { label.textContent = "Light"; }
            if (nmToggle) { nmToggle.innerHTML = '<i class="fa fa-sun-o"></i>'; }
        } else {
            html.removeAttribute("data-theme");
            html.removeAttribute("data-bs-theme");
            html.style.removeProperty("--av-product-img-bg");
            html.style.removeProperty("--o-wsale-card-thumb-background");
            html.style.removeProperty("--o-wsale-card-bg");
            html.style.removeProperty("--bs-card-bg");
            html.style.removeProperty("--bs-body-bg");
            if (icon)  { icon.textContent  = "☾"; }
            if (label) { label.textContent = "Dark"; }
            if (nmToggle) { nmToggle.innerHTML = '<i class="fa fa-moon-o"></i>'; }
        }
    }

    function init() {
        var toggle = document.getElementById("av-dark-toggle");
        if (!toggle) { return; }
        var html = document.documentElement;

        var stored = null;
        try { stored = localStorage.getItem(STORAGE_KEY); } catch (e) { /* storage blocked */ }
        var prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
        applyTheme(toggle, html, stored === "dark" || (stored === null && prefersDark));

        toggle.addEventListener("click", function () {
            var isDark = html.getAttribute("data-theme") === "dark";
            applyTheme(toggle, html, !isDark);
            try { localStorage.setItem(STORAGE_KEY, isDark ? "light" : "dark"); } catch (e) { /* ignore */ }
        });

        // ── Color Theme Logic ───────────────────────────────────────
        var COLOR_STORAGE_KEY = "av_primary_color";
        function applyColor(color) {
            if (!color) return;
            html.style.setProperty('--av-red', color);
            html.style.setProperty('--av-red-dark', "color-mix(in srgb, " + color + " 75%, black)");
            html.style.setProperty('--bs-primary', color);
            html.style.setProperty('--bs-primary-rgb', hexToRgb(color));
            
            // Highlight selected button wrapper
            document.querySelectorAll(".av-color-btn-wrapper").forEach(function(wrapper) {
                if (wrapper.getAttribute("data-color") === color) {
                    wrapper.style.borderColor = "var(--av-red)";
                    wrapper.style.backgroundColor = "color-mix(in srgb, var(--av-red) 10%, transparent)";
                    var nameSpan = document.getElementById("av-current-color-name");
                    if (nameSpan) nameSpan.textContent = wrapper.getAttribute("data-name") || "Custom";
                } else {
                    wrapper.style.borderColor = "transparent";
                    wrapper.style.backgroundColor = "transparent";
                }
            });
        }

        function hexToRgb(hex) {
            var result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
            return result ? parseInt(result[1], 16) + ", " + parseInt(result[2], 16) + ", " + parseInt(result[3], 16) : "204, 0, 0";
        }

        var storedColor = null;
        try { storedColor = localStorage.getItem(COLOR_STORAGE_KEY); } catch(e) {}
        if (storedColor) { applyColor(storedColor); }

        var popup = document.getElementById("av-color-popup");
        var DEFAULT_COLOR = popup ? popup.getAttribute("data-default-color") : null;

        document.querySelectorAll(".av-color-btn-wrapper").forEach(function(btn) {
            btn.addEventListener("click", function(e) {
                e.preventDefault();
                e.stopPropagation();
                var color = this.getAttribute("data-color");
                var isDefault = this.getAttribute("data-is-default") === "1";
                applyColor(color);
                try {
                    if (isDefault) {
                        localStorage.removeItem(COLOR_STORAGE_KEY);
                    } else {
                        localStorage.setItem(COLOR_STORAGE_KEY, color);
                    }
                } catch(e) {}
            });
        });

        // On load: if no stored color, highlight the default button
        if (!storedColor && DEFAULT_COLOR) { applyColor(DEFAULT_COLOR); }

        // NOTE: the product-card "Add to Cart" (.js_av_add_to_cart) is handled
        // by the AveenixCardAddToCart OWL interaction (cart_add.js), which uses
        // Odoo's native `cart` service so the standard add-to-cart popup shows.
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
