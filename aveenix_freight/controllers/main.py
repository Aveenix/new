from odoo import fields, http, tools
from odoo.http import request

from ..models.freight_quote import CONTAINER_TYPES, FREIGHT_MODES
from ..models.freight_shipment import SHIPMENT_STATES

# The services the site sells, in nav order. Each page is rendered from this
# one table, and `mode` pre-selects the matching option on the quote form.
SERVICES = [
    {
        'slug': 'ocean-freight',
        'mode': 'ocean_fcl',
        'icon': 'fa-ship',
        'title': 'Ocean Freight',
        'nav': 'Ocean',
        'tagline': 'FCL and LCL sailings on every major trade lane.',
        'intro': 'Move full containers or share space on consolidated sailings. '
                 'We book with leading carriers, handle the paperwork end to end '
                 'and keep you posted at every port call.',
        'features': [
            ('fa-cube', 'Full Container Load (FCL)', "20', 40' and 40' High Cube dry boxes, plus reefers for temperature-controlled cargo."),
            ('fa-cubes', 'Less than Container Load (LCL)', 'Pay only for the cubic metres you use, with weekly consolidations from major hubs.'),
            ('fa-calendar-check-o', 'Fixed sailing schedules', 'Weekly departures with carrier space allocations, even in peak season.'),
            ('fa-file-text-o', 'Bills of lading', 'Original, telex-release and sea waybill documentation handled for you.'),
        ],
        'specs': [
            ("20' Standard", '33 CBM · up to 28 t'),
            ("40' Standard", '67 CBM · up to 26.7 t'),
            ("40' High Cube", '76 CBM · up to 26.5 t'),
            ("Reefer 20' / 40'", '-30 °C to +30 °C'),
        ],
    },
    {
        'slug': 'air-freight',
        'mode': 'air',
        'icon': 'fa-plane',
        'title': 'Air Freight',
        'nav': 'Air',
        'tagline': 'Time-critical cargo, door to door in days.',
        'intro': 'When speed matters, our air desk books consolidated, direct and '
                 'charter capacity with major airlines, with customs pre-clearance '
                 'so cargo moves the moment it lands.',
        'features': [
            ('fa-bolt', 'Express & next-flight-out', 'Priority uplift for urgent spare parts, samples and launches.'),
            ('fa-clock-o', 'Deferred economy', 'Lower rates on consolidated services when a few extra days are fine.'),
            ('fa-snowflake-o', 'Pharma & perishables', 'Cool-chain handling with temperature monitoring from pickup to delivery.'),
            ('fa-exclamation-triangle', 'Dangerous goods', 'IATA DGR-certified staff for batteries, chemicals and other regulated cargo.'),
        ],
        'specs': [
            ('Typical transit', '1 – 5 days'),
            ('Chargeable weight', 'Greater of actual or volume (1 CBM = 167 kg)'),
            ('Documents', 'Master & house air waybill'),
            ('Charter', 'Part and full freighter charters on request'),
        ],
    },
    {
        'slug': 'road-rail',
        'mode': 'road',
        'icon': 'fa-truck',
        'title': 'Road & Rail Freight',
        'nav': 'Road & Rail',
        'tagline': 'Inland haulage, cross-border trucking and rail.',
        'intro': 'First and last-mile haulage to and from the port, full and part '
                 'truckloads across borders, and container rail to inland depots '
                 'for a lower-cost, lower-carbon option.',
        'features': [
            ('fa-truck', 'FTL & LTL trucking', 'Dedicated trucks or shared loads, with live dispatch updates.'),
            ('fa-train', 'Container rail', 'Port-to-ICD rail on scheduled block trains.'),
            ('fa-road', 'Cross-border', 'Transit documentation and border clearance handled for you.'),
            ('fa-leaf', 'Lower emissions', 'Rail moves cut CO₂ per tonne-km sharply compared with road.'),
        ],
        'specs': [
            ('Vehicle types', 'Container chassis, flatbed, curtain-sider, box'),
            ('Payload', 'Up to 28 t per truck'),
            ('Rail', 'Double-stack container trains to major ICDs'),
            ('Tracking', 'GPS updates on the Aveenix tracker'),
        ],
    },
    {
        'slug': 'customs-clearance',
        'mode': 'ocean_fcl',
        'icon': 'fa-id-card-o',
        'title': 'Customs Clearance',
        'nav': 'Customs',
        'tagline': 'Licensed brokers at origin and destination.',
        'intro': 'Our customs team classifies your goods, files the declarations, '
                 'pays duties on your behalf and resolves holds, so your cargo is '
                 'not stuck at the border.',
        'features': [
            ('fa-search', 'HS classification', 'The right tariff codes the first time, to avoid penalties and overpayment.'),
            ('fa-file-text', 'Import & export filing', 'Bills of entry, shipping bills and certificates of origin.'),
            ('fa-percent', 'Duty & tax planning', 'Free-trade agreement and duty-drawback advice.'),
            ('fa-shield', 'Compliance', 'Sanctions screening and licence checks before your cargo ships.'),
        ],
        'specs': [
            ('Coverage', 'Origin and destination clearance'),
            ('Typical clearance', 'Same day for complete documents'),
            ('Support', 'Inspections, assessments and holds'),
            ('Bonded', 'Bonded transport and warehousing available'),
        ],
    },
    {
        'slug': 'warehousing',
        'mode': 'road',
        'icon': 'fa-building',
        'title': 'Warehousing & Distribution',
        'nav': 'Warehousing',
        'tagline': 'Storage, fulfilment and value-added services.',
        'intro': 'Short and long-term storage near the ports, with pick-and-pack, '
                 'labelling, kitting and onward distribution to stores, '
                 'marketplaces and end customers.',
        'features': [
            ('fa-archive', 'Storage', 'Racked, bulk and bonded space by the pallet or by the square metre.'),
            ('fa-dropbox', 'Fulfilment', 'B2B and e-commerce order picking, packing and dispatch.'),
            ('fa-tags', 'Value-added services', 'Labelling, re-packing, kitting and quality inspection.'),
            ('fa-bar-chart', 'Inventory visibility', 'Stock reports and cycle counts on request.'),
        ],
        'specs': [
            ('Storage types', 'Ambient, bonded, temperature-controlled'),
            ('Handling', 'Container de-stuffing and cross-docking'),
            ('Security', '24/7 CCTV and access control'),
            ('Distribution', 'Same-day and next-day regional delivery'),
        ],
    },
]
SERVICES_BY_SLUG = {s['slug']: s for s in SERVICES}

# Caps on what an anonymous visitor can post into the quote's text fields.
_MAX_TEXT = 255
_MAX_NOTES = 4000


class AveenixFreight(http.Controller):

    def _freight_values(self, **values):
        """Every freight page renders inside the Aveenix layout as a freight
        page, so the header swaps its logo and nav (see views/layout.xml)."""
        values.update({
            'is_freight_page': True,
            'freight_services': SERVICES,
            'freight_modes': FREIGHT_MODES,
        })
        return values

    @http.route('/freight', type='http', auth='public', website=True)
    def freight_home(self, **kwargs):
        return request.render('aveenix_freight.freight_home', self._freight_values(
            active_nav='home',
        ))

    @http.route('/freight/services/<string:slug>', type='http', auth='public', website=True)
    def freight_service(self, slug, **kwargs):
        service = SERVICES_BY_SLUG.get(slug)
        if not service:
            raise request.not_found()
        return request.render('aveenix_freight.freight_service', self._freight_values(
            service=service,
            active_nav=slug,
        ))

    # ── Quote request ────────────────────────────────────────────────────

    def _quote_form_values(self, form, errors=None):
        env = request.env
        return self._freight_values(
            form=form,
            errors=errors or {},
            active_nav='quote',
            container_types=CONTAINER_TYPES,
            ports=env['freight.port'].sudo().search([]),
            incoterms=env['account.incoterms'].sudo().search([]),
            countries=env['res.country'].sudo().search([]),
        )

    @http.route('/freight/quote', type='http', auth='public', website=True,
                methods=['GET'])
    def freight_quote(self, **kwargs):
        # The home widget and the service pages link here with mode / origin /
        # destination prefilled; anything else in the query string is ignored.
        form = {k: kwargs[k] for k in ('mode', 'origin_address', 'destination_address') if kwargs.get(k)}
        user = request.env.user
        if not user._is_public():
            form.setdefault('contact_name', user.name)
            form.setdefault('email', user.email or '')
            form.setdefault('phone', user.phone or '')
            form.setdefault('company_name', user.parent_id.name or '')
        return request.render('aveenix_freight.freight_quote', self._quote_form_values(form))

    @http.route('/freight/quote', type='http', auth='public', website=True,
                methods=['POST'], sitemap=False)
    def freight_quote_submit(self, **post):
        # Honeypot: real visitors never see this field, bots fill everything.
        if post.get('website_url'):
            return request.redirect('/freight/quote/thanks')
        if not request.env['ir.http']._verify_recaptcha_v2(post.get('g-recaptcha-response')):
            return request.render('aveenix_freight.freight_quote', self._quote_form_values(
                post, {'captcha': 'Please confirm you are not a robot and try again.'},
            ))

        vals, errors = self._parse_quote(post)
        if errors:
            return request.render('aveenix_freight.freight_quote', self._quote_form_values(post, errors))

        user = request.env.user
        if not user._is_public():
            vals['partner_id'] = user.partner_id.id
        quote = request.env['freight.quote'].sudo().create(vals)
        request.session['freight_quote_ref'] = quote.name
        return request.redirect('/freight/quote/thanks')

    @http.route('/freight/quote/thanks', type='http', auth='public', website=True, sitemap=False)
    def freight_quote_thanks(self, **kwargs):
        return request.render('aveenix_freight.freight_quote_thanks', self._freight_values(
            quote_ref=request.session.pop('freight_quote_ref', None),
            active_nav='quote',
        ))

    def _parse_quote(self, post):
        """Website form → freight.quote values. Everything is posted by an
        anonymous visitor, so each value is checked against what the model
        allows rather than trusted."""
        errors = {}

        def text(name, limit=_MAX_TEXT):
            return (post.get(name) or '').strip()[:limit]

        def number(name, cast):
            raw = (post.get(name) or '').strip()
            if not raw:
                return 0
            try:
                value = cast(raw)
            except ValueError:
                errors[name] = 'Enter a number.'
                return 0
            if value < 0:
                errors[name] = 'Must not be negative.'
                return 0
            return value

        def record(model, name, domain=()):
            raw = post.get(name)
            if not raw or not raw.isdigit():
                return False
            rec = request.env[model].sudo().search([('id', '=', int(raw)), *domain], limit=1)
            return rec.id

        mode = post.get('mode')
        if mode not in dict(FREIGHT_MODES):
            errors['mode'] = 'Choose a shipping mode.'
        container_type = post.get('container_type')
        if container_type not in dict(CONTAINER_TYPES):
            container_type = False

        vals = {
            'source': 'website',
            'mode': mode,
            'contact_name': text('contact_name'),
            'company_name': text('company_name'),
            'email': tools.email_normalize(post.get('email') or ''),
            'phone': text('phone', 64),
            'country_id': record('res.country', 'country_id'),
            'origin_address': text('origin_address'),
            'destination_address': text('destination_address'),
            'origin_port_id': record('freight.port', 'origin_port_id'),
            'destination_port_id': record('freight.port', 'destination_port_id'),
            'incoterm_id': record('account.incoterms', 'incoterm_id'),
            'commodity': text('commodity'),
            'container_type': container_type if mode == 'ocean_fcl' else False,
            'container_qty': number('container_qty', int) or 1,
            'packages': number('packages', int),
            'weight_kg': number('weight_kg', float),
            'volume_cbm': number('volume_cbm', float),
            'is_hazardous': bool(post.get('is_hazardous')),
            'needs_customs': bool(post.get('needs_customs')),
            'needs_insurance': bool(post.get('needs_insurance')),
            'notes': text('notes', _MAX_NOTES),
        }
        ready = (post.get('ready_date') or '').strip()
        if ready:
            try:
                vals['ready_date'] = fields.Date.to_date(ready)
            except ValueError:
                errors['ready_date'] = 'Enter a valid date.'

        for name, label in (('contact_name', 'your name'),
                            ('origin_address', 'where the cargo ships from'),
                            ('destination_address', 'where it is going')):
            if not vals[name]:
                errors[name] = 'Please enter %s.' % label
        if not vals['email']:
            errors['email'] = 'Enter a valid email address.'
        return vals, errors

    # ── Tracking ─────────────────────────────────────────────────────────

    @http.route('/freight/track', type='http', auth='public', website=True)
    def freight_track(self, number=None, **kwargs):
        number = (number or '').strip().upper()
        shipment = request.env['freight.shipment']
        if number:
            # Exact match on the random tracking number only: the reference
            # (AVS/2026/0001) is sequential and must not open the tracker.
            shipment = shipment.sudo().search([('tracking_number', '=', number)], limit=1)
        states = [s for s, _label in SHIPMENT_STATES if s not in ('draft', 'cancelled')]
        return request.render('aveenix_freight.freight_track', self._freight_values(
            number=number,
            shipment=shipment,
            events=shipment._public_events() if shipment else [],
            progress_states=states,
            state_labels=dict(SHIPMENT_STATES),
            active_nav='track',
        ))
