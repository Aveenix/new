(function () {
    "use strict";

    var STORAGE_KEY = "av_theme";

    function applyTheme(toggle, html, dark) {
        var icon  = toggle.querySelector(".av-toggle-icon");
        var label = toggle.querySelector(".av-toggle-label");
        if (dark) {
            html.setAttribute("data-theme", "dark");
            html.setAttribute("data-bs-theme", "dark");
            if (icon)  { icon.textContent  = "☀"; }
            if (label) { label.textContent = "Light"; }
        } else {
            html.removeAttribute("data-theme");
            html.removeAttribute("data-bs-theme");
            if (icon)  { icon.textContent  = "☾"; }
            if (label) { label.textContent = "Dark"; }
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

        document.querySelectorAll(".av-color-btn-wrapper").forEach(function(btn) {
            btn.addEventListener("click", function(e) {
                e.preventDefault();
                e.stopPropagation();
                var color = this.getAttribute("data-color");
                applyColor(color);
                try { localStorage.setItem(COLOR_STORAGE_KEY, color); } catch(e) {}
            });
        });

        // ── Direct Add to Cart (AJAX) ───────────────────────────────
        document.addEventListener("click", function(e) {
            var btn = e.target.closest(".js_av_add_to_cart");
            if (btn) {
                e.preventDefault();
                var productId = btn.getAttribute("data-product-id");
                var productTemplateId = btn.getAttribute("data-product-template-id");
                if (!productId) return;

                // Show loading state
                var originalHtml = btn.innerHTML;
                btn.innerHTML = '<i class="fa fa-spinner fa-spin"></i> Adding...';
                btn.style.pointerEvents = "none";
                btn.style.opacity = "0.7";

                // Get CSRF token from the page or odoo object
                var csrfToken = document.querySelector('input[name="csrf_token"]')?.value || (window.odoo && window.odoo.csrf_token) || "";

                fetch('/shop/cart/add', {
                    method: 'POST',
                    headers: { 
                        'Content-Type': 'application/json',
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    body: JSON.stringify({
                        jsonrpc: "2.0",
                        method: "call",
                        params: {
                            product_template_id: parseInt(productTemplateId),
                            product_id: parseInt(productId),
                            quantity: 1,
                            csrf_token: csrfToken
                        }
                    })
                })
                .then(function(res) { 
                    if (!res.ok) throw new Error("HTTP error " + res.status);
                    return res.json(); 
                })
                .then(function(data) {
                    if (data.error) {
                        console.error("Server error:", data.error);
                        throw new Error(data.error.message || "Server Error");
                    }
                    if (data.result) {
                        btn.innerHTML = '<i class="fa fa-check"></i> Added!';
                        btn.style.backgroundColor = "#2E7D52"; // Success green
                        
                        // Update cart badge without reload
                        var badge = document.querySelector(".my_cart_quantity");
                        if (badge) {
                            badge.textContent = data.result.cart_quantity;
                        }

                        // Reset button after 2 seconds
                        setTimeout(function() {
                            btn.innerHTML = originalHtml;
                            btn.style.pointerEvents = "auto";
                            btn.style.opacity = "1";
                            btn.style.backgroundColor = "var(--av-red)";
                        }, 2000);
                    } else {
                        throw new Error("No result in response");
                    }
                })
                .catch(function(err) {
                    console.error("Cart AJAX Error:", err);
                    btn.innerHTML = '<i class="fa fa-exclamation-triangle"></i> ' + (err.message || "Error");
                    btn.style.backgroundColor = "#C62828"; // Error red
                    setTimeout(function() {
                        btn.innerHTML = originalHtml;
                        btn.style.pointerEvents = "auto";
                        btn.style.opacity = "1";
                        btn.style.backgroundColor = "var(--av-red)";
                    }, 4000); // Show for longer
                });
            }
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
