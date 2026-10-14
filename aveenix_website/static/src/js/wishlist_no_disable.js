/** @odoo-module **/

import { rpc } from '@web/core/network/rpc';
import { patch } from '@web/core/utils/patch';
import { Interaction } from '@web/public/interaction';
import { registry } from '@web/core/registry';
import { AddProductToWishlistButton } from '@website_sale_wishlist/interactions/add_product_to_wishlist_button';
import { ProductDetail } from '@website_sale_wishlist/interactions/product_detail';
import wSaleUtils from '@website_sale/js/website_sale_utils';
import wishlistUtils from '@website_sale_wishlist/js/website_sale_wishlist_utils';

const FAV_KEY = 'av_fav_ids';
const WISH_KEY = 'av_wish_ids';

function getFromStorage(key) {
    try { return JSON.parse(localStorage.getItem(key) || '[]'); } catch { return []; }
}
function bounce(el) {
    el.classList.remove('av-icon-bounce');
    void el.offsetWidth; // reflow to restart animation
    el.classList.add('av-icon-bounce');
    el.addEventListener('animationend', () => el.classList.remove('av-icon-bounce'), { once: true });
}

function addToStorage(key, id) {
    try {
        const ids = getFromStorage(key);
        const s = String(id);
        if (!ids.includes(s)) { ids.push(s); localStorage.setItem(key, JSON.stringify(ids)); }
    } catch {}
}

// ── Heart btn → Favourites page ───────────────────────────────────
patch(AddProductToWishlistButton.prototype, {

    async addProduct(ev) {
        const el = ev.currentTarget;
        if (!el.classList.contains('o_add_wishlist_dyn')) {
            return super.addProduct(ev);
        }
        const templateId = el.dataset.productTemplateId;

        const icon = el.querySelector('.fa');
        const favIds = getFromStorage(FAV_KEY);
        if (favIds.includes(String(templateId))) {
            // Deactivate.
            const ids = favIds.filter(i => i !== String(templateId));
            try { localStorage.setItem(FAV_KEY, JSON.stringify(ids)); } catch {}
            if (icon) { icon.classList.remove('fa-heart'); icon.classList.add('fa-heart-o'); }
            el.title = 'Add to favourites';
            bounce(el);
            window.dispatchEvent(new CustomEvent('av-fav-changed'));
            return;
        }
        addToStorage(FAV_KEY, templateId);
        window.dispatchEvent(new CustomEvent('av-fav-changed'));
        if (icon) { icon.classList.remove('fa-heart-o'); icon.classList.add('fa-heart'); }
        bounce(el);
        el.title = 'Added to favourites';

        try {
            let productId = parseInt(el.dataset.productProductId);
            const form = wSaleUtils.getClosestProductForm(el);
            if (!productId) {
                productId = await this.waitFor(rpc('/sale/create_product_variant', {
                    product_template_id: parseInt(templateId),
                    product_template_attribute_value_ids: wSaleUtils.getSelectedAttributeValues(form),
                }));
            }
            if (productId) {
                const existingIds = await this.waitFor(rpc('/shop/wishlist/get_product_ids'));
                if (!existingIds.includes(productId)) {
                    await this.waitFor(rpc('/shop/wishlist/add', { product_id: productId }));
                }
                wishlistUtils.addWishlistProduct(productId);
                wishlistUtils.updateWishlistNavBar();
            }
        } catch {}
    },
});

// ── Star btn → Wishlist page ──────────────────────────────────────
export class AvAddToWishlistButton extends Interaction {
    static selector = '[data-action="av_add_to_wishlist"]';
    dynamicContent = {
        _root: { 't-on-click': this.onClick },
    };

    onClick(ev) {
        ev.preventDefault();
        const el = ev.currentTarget;
        const templateId = el.dataset.productTemplateId;
        if (!templateId) return;

        const icon = el.querySelector('.fa');
        const wishIds = getFromStorage(WISH_KEY);
        if (wishIds.includes(String(templateId))) {
            const ids = wishIds.filter(i => i !== String(templateId));
            try { localStorage.setItem(WISH_KEY, JSON.stringify(ids)); } catch {}
            if (icon) { icon.classList.remove('fa-star'); icon.classList.add('fa-star-o'); }
            el.title = 'Add to wishlist';
        } else {
            addToStorage(WISH_KEY, templateId);
            if (icon) { icon.classList.remove('fa-star-o'); icon.classList.add('fa-star'); }
            el.title = 'Added to wishlist';
        }
        bounce(el);
        window.dispatchEvent(new CustomEvent('av-wish-changed'));
    }
}

registry
    .category('public.interactions')
    .add('aveenix_website.av_add_to_wishlist_button', AvAddToWishlistButton);

// ── Keep o_add_wishlist_dyn always enabled on variant change ──────
patch(ProductDetail.prototype, {
    onChangeVariant(ev) {
        super.onChangeVariant(ev);
        const input = ev.target;
        const button = input.closest('.js_product')?.querySelector('.o_add_wishlist_dyn');
        if (button) {
            button.disabled = false;
            button.classList.remove('disabled');
        }
    },
});
