"""Public endpoints: the tracked redirect, and placements for the article page."""

import logging

from odoo import http
from odoo.http import request

from odoo.addons.aveenix_website.controllers.main import AveenixWebsite

from ..models.affiliate_network import verify_target_url

_logger = logging.getLogger(__name__)


class AveenixAffiliateEngine(AveenixWebsite):

    # ── Article page ─────────────────────────────────────────────────────

    @http.route()
    def news_detail(self, article_id, **kwargs):
        """Add affiliate placements and the split article body to the page.

        Extends the existing route rather than replacing it, the same way
        aveenix_website injects affiliate cart lines, so the news page keeps a
        single owner and this module can be uninstalled without taking the
        article view with it.

        Nothing is matched or fetched here: placements were decided by the cron,
        so a page view costs one read and a visitor never waits on an AI call or
        a CJ round-trip.
        """
        response = super().news_detail(article_id, **kwargs)
        if getattr(response, 'qcontext', None) is None:
            # request.not_found() — there is nothing to render into.
            return response

        # Defaults go in unconditionally, before any early return. The article
        # template now references these names, and it still renders for the mock
        # articles that have no aveenix.news record behind them — so leaving one
        # undefined would break those pages outright rather than merely skip a
        # recommendation.
        no_placements = request.env['affiliate.offer.placement'].sudo().browse()
        response.qcontext.update({
            'av_in_content_placement': no_placements,
            'av_after_body_placements': no_placements,
            'av_sidebar_placements': no_placements,
            'av_content_before': '',
            'av_content_after': '',
            'av_affiliate_disclosure': '',
        })

        article = request.env['aveenix.news'].sudo().browse(article_id)
        if not article.exists():
            return response
        settings = request.env['affiliate.offer'].sudo()._av_settings()
        if not settings['enabled']:
            return response

        placements = request.env['affiliate.offer.placement'].sudo()._av_live_for_article(article)
        if not placements:
            return response

        in_content = placements.filtered(lambda p: p.position == 'in_content')[:1]
        before, after = article._av_split_content()
        # Interrupt the body only when there is both an offer for that slot and
        # an interior to interrupt. A two-paragraph item gets the card after the
        # text instead, which reads better than splitting it in half.
        if in_content and before:
            response.qcontext['av_in_content_placement'] = in_content
            response.qcontext['av_content_before'] = before
            response.qcontext['av_content_after'] = after
        else:
            response.qcontext['av_after_body_placements'] = in_content
        response.qcontext['av_sidebar_placements'] = placements.filtered(
            lambda p: p.position == 'sidebar'
        )
        response.qcontext['av_affiliate_disclosure'] = settings['disclosure']
        return response

    # ── Tracked redirect ─────────────────────────────────────────────────

    @http.route(
        '/aveenix/affiliate/offer/<int:placement_id>',
        type='http', auth='public', website=True, sitemap=False,
    )
    def affiliate_offer_redirect(self, placement_id, **kwargs):
        """Log the click, then forward to the network's own tracked link.

        Public on purpose. The sibling product route at
        /aveenix/affiliate/<product_id> bounces anonymous visitors to the login
        page because its Buy button is only shown to members — but news readers
        are overwhelmingly anonymous, and gating this would monetise nothing.

        What replaces the login gate as a safety check is the host allowlist:
        this route 302s to a stored URL, so it re-verifies that the URL belongs
        to the network it claims before sending anyone there. Without that it
        would be an open redirector, and it is also the last line of the
        "only verified affiliate links" rule — the stored link is checked again
        at the moment it is served, not merely when it was written.
        """
        placement = request.env['affiliate.offer.placement'].sudo().browse(placement_id)
        if not placement.exists() or not placement._av_is_live():
            return request.redirect('/news')

        offer = placement.offer_id
        if not verify_target_url(offer.network, offer.target_url):
            _logger.warning(
                'Refusing to redirect: offer %s has a link that is not on a %s '
                'click domain (%s).', offer.id, offer.network, offer.target_url,
            )
            return request.redirect('/news')

        user = request.env.user
        # Created before the URL is built: the click id is what becomes the
        # tid/sid the network echoes back, and it is how a commission is traced
        # to this article months later.
        click = request.env['affiliate.click.log'].sudo().create({
            'offer_id': offer.id,
            'placement_id': placement.id,
            'news_id': placement.news_id.id,
            'network': offer.network,
            'user_id': user.id if not user._is_public() else False,
            'session_id': request.session.sid,
            'referrer_url': (request.httprequest.referrer or '')[:2000],
        })
        click.tracking_id = 'av%s' % click.id
        outbound = offer._av_outbound_url(click, placement)
        click.affiliate_url = outbound
        return request.redirect(outbound, local=False)
