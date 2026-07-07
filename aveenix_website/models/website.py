from odoo import fields, models
from odoo.http import request

_LOCATION_SESSION_KEY = 'av_user_country_id'


class Website(models.Model):
    _inherit = 'website'

    def _get_geoip_country_code(self):
        """Prefer the browser-detected country stored in session over GeoIP.

        The header "Enable location" flow reverse-geocodes the visitor's
        browser location and saves the matching res.country id in the session
        (av_user_country_id). Using it here makes Odoo's pricelist selection
        follow the detected location, not just the IP-based GeoIP guess.
        """
        if request:
            country_id = request.session.get(_LOCATION_SESSION_KEY)
            if country_id:
                country = self.env['res.country'].sudo().browse(country_id)
                if country.exists() and country.code:
                    return country.code
        return super()._get_geoip_country_code()

    aveenix_primary_color = fields.Char(
        string='Primary Color',
        default='#CC0000',
        help='Main brand color (header buttons, badges, search button). Hex value e.g. #CC0000',
    )
    aveenix_accent_color = fields.Char(
        string='Accent Color',
        default='#FFB300',
        help='Accent / highlight color (CTA buttons, stars, promo). Hex value e.g. #FFB300',
    )

    # Categories whose products get a dedicated "featured" row on the homepage,
    # shown after New Arrivals. Each selected category renders one product row
    # with a "View All" button linking to /shop filtered by that category.
    aveenix_home_categ_ids = fields.Many2many(
        'product.public.category',
        'aveenix_website_home_categ_rel',
        'website_id',
        'category_id',
        string='Homepage Featured Categories',
        help='Select categories to feature on the homepage (after New Arrivals). '
             'Each shows a row of its published products with a View All link to '
             'the shop filtered by that category.',
    )

    # Categories shown as menu items in the header nav bar, right after the
    # "Shop" link. Each renders as "<name>" linking to /shop?category=<id>.
    aveenix_header_menu_categ_ids = fields.Many2many(
        'product.public.category',
        'aveenix_website_header_menu_categ_rel',
        'website_id',
        'category_id',
        string='Header Menu Categories',
        help='Select categories to show as menu links in the header, right '
             'after the Shop link. Each links to /shop filtered by that category.',
    )

    def _product_domain(self):
        """Scope /shop and all website_sale product queries to this website's
        company (multi-company). Core `website_domain` only filters by
        website_id — and the shop lookup runs sudo(), so company record rules
        don't apply. Add the company leaves explicitly here so the same website
        UI serves different data per company. Company-less (shared) products
        stay visible everywhere. No company on the website = no restriction."""
        domain = super()._product_domain()
        company = self.company_id
        if company:
            domain = domain + [
                '|', ('company_id', '=', company.id), ('company_id', '=', False),
            ]
        return domain

    def _av_ensure_currency_pricelists(self):
        """Guarantee one selectable, empty website pricelist per ACTIVE currency
        so the header switcher lists every active currency.

        A currency being active in Settings is not enough to appear on the
        website — Odoo only offers pricelists that are selectable and available
        to the site. An *empty* pricelist (no rules) automatically converts each
        product's list price into its currency using the currency's exchange
        rate (see product.pricelist.item._compute_base_price), so prices are
        shown correctly in the chosen currency — PROVIDED the currency has a
        real rate. Currencies left at rate 1.0 will display the base number
        relabelled; keep exchange rates up to date (Settings → Currencies, or
        enable automatic rate updates) for accurate conversion.

        Idempotent: skips currencies already covered by a usable pricelist.
        """
        self.ensure_one()
        Pricelist = self.env['product.pricelist'].sudo()
        currencies = self.env['res.currency'].sudo().search([('active', '=', True)])
        existing = Pricelist.search([
            '|', ('website_id', '=', self.id), ('website_id', '=', False),
            ('selectable', '=', True),
        ])
        covered = existing.mapped('currency_id')
        to_create = [{
            'name': 'Website %s' % currency.name,
            'currency_id': currency.id,
            'selectable': True,
            'website_id': self.id,
            'company_id': self.company_id.id,
        } for currency in currencies - covered]
        if to_create:
            Pricelist.create(to_create)

    def action_av_sync_currency_pricelists(self):
        """Button/server-action entry point to (re)create the per-currency
        website pricelists after activating new currencies."""
        for website in self:
            website._av_ensure_currency_pricelists()
        return True

    def get_currency_pricelist_options(self):
        """One pricelist per currency for the header currency switcher.

        We deliberately DON'T use `get_pricelist_available` here: that method
        applies GeoIP/country filtering — once the visitor's country matches a
        country-restricted pricelist, Odoo returns only those and hides every
        unrestricted one, so the switcher would show just 1–2 currencies.

        The switcher's purpose is to let the user pick ANY currency, so we list
        all selectable, website-compliant pricelists directly (one per currency,
        the current one always included even if it were restricted).
        """
        self.ensure_one()
        Pricelist = self.env['product.pricelist'].sudo()
        pricelists = Pricelist.search([
            ('active', '=', True),
            ('selectable', '=', True),
            ('company_id', 'in', [False, self.company_id.id]),
            '|', ('website_id', '=', self.id), ('website_id', '=', False),
        ])
        # Always include the currently-applied pricelist so its currency shows
        # selected even if it isn't otherwise selectable.
        current = getattr(request, 'pricelist', False) if request else False
        if current:
            pricelists |= current
        seen_currencies = self.env['res.currency']
        options = self.env['product.pricelist']
        for pl in pricelists.sorted('name'):
            if pl.currency_id and pl.currency_id not in seen_currencies:
                seen_currencies |= pl.currency_id
                options |= pl
        return options
