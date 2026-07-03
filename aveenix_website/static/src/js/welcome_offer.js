/** @odoo-module **/

import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";

// Footer "$20 off your first order" form.
// On submit, records the visitor's email as a lead (opt-in), then redirects
// to the signup page with the email pre-filled. The $20 itself auto-applies
// at checkout on their first order via the loyalty welcome program.
export class WelcomeOfferForm extends Interaction {
    static selector = ".av-promo-form";

    dynamicContent = {
        _root: { "t-on-submit": (ev) => this.onSubmit(ev) },
    };

    setup() {
        this.input = this.el.querySelector('input[name="email"]');
    }

    async onSubmit(ev) {
        ev.preventDefault();
        const email = (this.input && this.input.value || "").trim();
        // Rely on the browser's required + type=email validation first.
        if (!email || (this.input && !this.input.checkValidity())) {
            if (this.input) { this.input.reportValidity(); }
            return;
        }
        // Capture the lead before leaving; ignore failures so the redirect
        // always happens (the discount doesn't depend on this call).
        try {
            await rpc("/aveenix/welcome-offer", { email });
        } catch {
            // non-blocking
        }
        // Redirect to signup with the email pre-filled (`login` is the signup
        // email field and is a whitelisted signup query param).
        window.location.href = "/web/signup?login=" + encodeURIComponent(email);
    }
}

registry.category("public.interactions").add("WelcomeOfferForm", WelcomeOfferForm);
