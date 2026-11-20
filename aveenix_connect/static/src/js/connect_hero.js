/** @odoo-module **/

import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";

const SLIDE_SECONDS = 6;

/**
 * Connect home hero: the top-level category photos take turns as the
 * background, each with its category link in the corner. Only the first
 * photo comes with the page; each next one is loaded a slide ahead (data-bg).
 * Stays on the first photo for visitors who ask for reduced motion.
 */
export class ConnectHeroSlides extends Interaction {
    static selector = ".avc-hero-photos";

    setup() {
        this.slides = [...this.el.querySelectorAll(".avc-hero-slide")];
        this.captions = [...this.el.querySelectorAll(".avc-hero-caption")];
        this.index = 0;
    }

    start() {
        if (this.slides.length < 2 || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
            return;
        }
        this.load(1);
        const timer = setInterval(() => {
            if (!document.hidden) {
                this.show((this.index + 1) % this.slides.length);
            }
        }, SLIDE_SECONDS * 1000);
        this.registerCleanup(() => clearInterval(timer));
    }

    load(index) {
        const slide = this.slides[index];
        if (slide.dataset.bg) {
            slide.style.backgroundImage = `url("${slide.dataset.bg}")`;
            delete slide.dataset.bg;
        }
    }

    show(index) {
        this.load(index);
        for (const [i, el] of [...this.slides.entries(), ...this.captions.entries()]) {
            el.classList.toggle("is-active", i === index);
        }
        this.index = index;
        this.load((index + 1) % this.slides.length);
    }
}

registry.category("public.interactions").add("aveenix_connect.hero_slides", ConnectHeroSlides);
