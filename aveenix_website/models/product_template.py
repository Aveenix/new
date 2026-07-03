import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    available_country_ids = fields.Many2many(
        'res.country',
        'product_template_country_rel',
        'product_tmpl_id',
        'country_id',
        string='Available In Countries',
        help='Leave empty = available everywhere. Set countries to restrict visibility on website.',
    )

    av_shipping_info = fields.Html(
        string='Shipping & Delivery Info',
        sanitize=False,
        help='Rich content shown in the "Shipping and Delivery" tab on the '
             'product page. Leave empty to hide the tab.',
    )

    is_sponsored = fields.Boolean(
        string='Sponsored Ad',
        default=False,
        help='Show this product in the sponsored advertisement slider on cart/checkout pages.',
    )
    sponsor_rank = fields.Integer(
        string='Sponsor Rank',
        default=0,
        help='Higher value = shown first in the sponsored ad slider. Paid placement lever.',
    )

    external_image_urls = fields.Text(
        string='External Image URLs',
        help='Comma-separated external image URLs pulled from WooCommerce '
             '(meta_data / images). Rendered directly on the website for '
             'products whose images are hosted externally (e.g. Amazon CDN).',
    )

    external_image_fetched_url = fields.Char(
        string='Fetched Image URL',
        help='The external URL that was last downloaded into the native image '
             'field. When external_image_urls changes, this differs from the '
             'first URL and the image cron re-downloads it.',
        copy=False,
    )
    external_image_fetch_state = fields.Selection(
        [('pending', 'Pending'), ('done', 'Done'), ('error', 'Error')],
        string='Image Fetch State',
        index=True,
        copy=False,
        help='Tracks the background download of the external image into the '
             'native product image field.',
    )

    external_image_preview = fields.Html(
        string='External Images',
        compute='_compute_external_image_preview',
        sanitize=False,
        help='Inline preview of all external image URLs (backend only).',
    )

    def _get_external_image_list(self):
        """Return external image URLs as a clean list (for website rendering)."""
        self.ensure_one()
        if not self.external_image_urls:
            return []
        img_list = [u.strip() for u in self.external_image_urls.split(',') if u.strip()]
        return img_list

    def _compute_external_image_preview(self):
        from markupsafe import Markup
        for rec in self:
            urls = rec._get_external_image_list()
            if not urls:
                rec.external_image_preview = False
                continue
            html = Markup("<div style='display:flex;flex-wrap:wrap;gap:8px;'>")
            for u in urls:
                html += Markup(
                    "<a href='%s' target='_blank'>"
                    "<img src='%s' style='width:120px;height:120px;object-fit:cover;"
                    "border:1px solid #dee2e6;border-radius:6px;'/></a>"
                ) % (u, u)
            html += Markup("</div>")
            rec.external_image_preview = html

    affiliate_url = fields.Char(
        string='Affiliate URL',
        help='External retailer link for affiliate products. Buyers clicking '
             '"Buy on Retailer" are redirected here (click is tracked).',
    )
    affiliate_click_count = fields.Integer(
        string='Affiliate Clicks',
        compute='_compute_affiliate_click_count',
    )

    def _compute_affiliate_click_count(self):
        data = self.env['affiliate.click.log']._read_group(
            [('product_id', 'in', self.ids)],
            groupby=['product_id'],
            aggregates=['__count'],
        )
        counts = {product.id: count for product, count in data}
        for rec in self:
            rec.affiliate_click_count = counts.get(rec.id, 0)

    # ── External image → native image (background download) ──────────────

    def _first_external_image_url(self):
        self.ensure_one()
        urls = self._get_external_image_list()
        return urls[0] if urls else False

    def write(self, vals):
        res = super().write(vals)
        # When the external URL list changes, flag the product so the image
        # cron re-downloads only the ones that actually changed (delta only —
        # the daily product pull does NOT re-download all 20k images).
        if 'external_image_urls' in vals:
            to_flag = self.filtered(
                lambda p: p._first_external_image_url()
                and p._first_external_image_url() != p.external_image_fetched_url
            )
            if to_flag:
                # Avoid recursion: write the state directly via super.
                super(ProductTemplate, to_flag).write(
                    {'external_image_fetch_state': 'pending'}
                )
        return res

    def _download_external_image(self, timeout=10):
        """Download all external image URLs for this product.

        - First URL → product.template.image_1920 (main image).
        - Remaining URLs → product.image records (eCommerce media gallery).
        - URLs already present as product.image records are skipped.
        - Never raises — flags 'error' on complete failure.
        """
        self.ensure_one()
        import base64
        import requests

        urls = self._get_external_image_list()
        if not urls:
            self.external_image_fetch_state = False
            return False

        # Collect URLs already stored as eCommerce media to avoid duplicates.
        existing_names = set(
            self.env['product.image'].search([
                ('product_tmpl_id', '=', self.id),
            ]).mapped('name')
        )

        any_success = False

        for idx, url in enumerate(urls):
            img_name = 'Image %d' % (idx + 1)
            try:
                resp = requests.get(url, timeout=timeout, stream=True)
                resp.raise_for_status()
                content = resp.content
                if not content:
                    raise ValueError('empty response body')
                encoded = base64.b64encode(content)

                if idx == 0:
                    # First image → main product image.
                    self.write({
                        'image_1920': encoded,
                        'external_image_fetched_url': url,
                    })
                    _logger.info(
                        '[AffiliateImg] main image saved for product %s: %s',
                        self.id, url,
                    )
                else:
                    # Extra images → eCommerce media gallery (skip if already present).
                    if img_name not in existing_names:
                        self.env['product.image'].create({
                            'name': img_name,
                            'product_tmpl_id': self.id,
                            'image_1920': encoded,
                            'sequence': idx * 10,
                        })
                        existing_names.add(img_name)
                        _logger.info(
                            '[AffiliateImg] extra image %d saved for product %s: %s',
                            idx + 1, self.id, url,
                        )
                    else:
                        _logger.info(
                            '[AffiliateImg] skipping duplicate %s for product %s',
                            img_name, self.id,
                        )

                any_success = True

            except Exception as exc:  # noqa: BLE001 — must never break the cron
                _logger.warning(
                    '[AffiliateImg] failed to fetch image %d (%s) for product %s: %s',
                    idx + 1, url, self.id, exc,
                )

        if any_success:
            self.external_image_fetch_state = 'done'
        else:
            self.external_image_fetch_state = 'error'

        return any_success

    def _av_auto_publish(self, product, pub_affiliate, pub_dropship, pub_regular):
        if product.website_published:
            return
        ptype = product.aveenix_product_type or 'regular'
        should = (
            (ptype == 'affiliate' and pub_affiliate) or
            (ptype == 'dropship'  and pub_dropship) or
            (ptype not in ('affiliate', 'dropship') and pub_regular)
        )
        if should:
            product.website_published = True
            _logger.info('[AffiliateImg] auto-published %s (%s)', product.id, product.name)

    @api.model
    def cron_fetch_external_images(self, batch_size=50, timeout=10):
        """Background cron: download external images into the native image
        field for products flagged 'pending'. Batched + commit-per-product so
        a slow/dead URL never blocks the catalog pull or the whole run."""
        # Read auto-publish config once per cron run.
        ICP = self.env['ir.config_parameter'].sudo()
        auto_publish_affiliate = ICP.get_param('aveenix_website.auto_publish_affiliate') == 'True'
        auto_publish_dropship  = ICP.get_param('aveenix_website.auto_publish_dropship') == 'True'
        auto_publish_regular   = ICP.get_param('aveenix_website.auto_publish_regular') == 'True'

        # --- Pass 1: products with external URLs — download image then publish.
        products_with_url = self.search(
            [('external_image_fetch_state', '=', 'pending'),
             ('external_image_urls', '!=', False)],
            limit=batch_size,
        )
        if products_with_url:
            _logger.info('[AffiliateImg] downloading %s images...', len(products_with_url))
        done = 0
        for product in products_with_url:
            product._download_external_image(timeout=timeout)
            self._av_auto_publish(product, auto_publish_affiliate, auto_publish_dropship, auto_publish_regular)
            self.env.cr.commit()  # persist + release row, resumable
            done += 1

        # --- Pass 2: products with no external URL — mark done and publish.
        products_no_url = self.search(
            [('external_image_fetch_state', '=', 'pending'),
             ('external_image_urls', '=', False)],
            limit=batch_size,
        )
        for product in products_no_url:
            product.external_image_fetch_state = 'done'
            self._av_auto_publish(product, auto_publish_affiliate, auto_publish_dropship, auto_publish_regular)
            self.env.cr.commit()
            done += 1

        if done:
            _logger.info('[AffiliateImg] processed %s products this run.', done)
        else:
            _logger.info('[AffiliateImg] nothing pending.')
        # Re-trigger immediately if more remain (self-resuming).
        remaining = self.search_count(
            [('external_image_fetch_state', '=', 'pending')]
        )
        if remaining:
            cron = self.env.ref(
                'aveenix_website.cron_fetch_external_images',
                raise_if_not_found=False,
            )
            if cron:
                cron._trigger()

    def action_fetch_external_image_now(self):
        """Manual button: download the external image for selected products."""
        for product in self:
            if product.external_image_urls:
                product._download_external_image()
        return True
