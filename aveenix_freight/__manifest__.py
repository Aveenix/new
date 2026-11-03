{
    'name': 'Aveenix Freight',
    'version': '19.0.1.0.3',
    'category': 'Inventory/Freight',
    'summary': 'Aveenix Freight website (quotes, tracking, services) and '
               'freight management backend',
    'description': """
Aveenix Freight
===============
A third Aveenix site beside Aveenix Express (the shop) and Aveenix News,
reached from the footer and branded with the same logo, "Freight" in place
of "Express" / "News".

Website (/freight)
------------------
* Home: quote and tracking widget, services, how it works, why Aveenix
* Service pages: Ocean FCL / LCL, Air, Road & Rail, Customs, Warehousing
* Get a Quote form, creating a quote request for the freight team
* Shipment tracking by tracking number, with the milestone timeline

Backend (Freight menu)
----------------------
* Quote requests: qualify, price, send and convert into a shipment
* Shipments: modes, ports, carrier, containers, ETD / ETA, milestones
* Tracking events published to the website tracker
* Ports & airports master data, with a starter set of major hubs
* Road services (FCL / LCL trucks, Hiab, linehaul, courier), managed by the
  team and offered on the website when a customer picks Road Freight
* Invoices from shipments, paid online from the customer portal

Customer portal (My Account)
----------------------------
* Freight quotes: see the price, accept (books the shipment) or decline
* Freight shipments: status, history, invoices with Pay now
    """,
    'author': 'Anantam Innovision Private Limited',
    'website': 'https://anantaminnovision.com/',
    'license': 'LGPL-3',
    'depends': [
        # aveenix_website owns the header, footer and theme this site reuses.
        'aveenix_website',
        'account',  # account.incoterms on quotes and shipments
        # Freight invoices are paid from the customer portal ("Pay now") with
        # the published payment providers: card, PayPal, bank transfer.
        'account_payment',
        'mail',
        'portal',
    ],
    'data': [
        'security/freight_security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/freight_port_data.xml',
        'data/freight_road_service_data.xml',
        'data/product_data.xml',
        'data/mail_template_data.xml',
        'views/freight_port_views.xml',
        'views/freight_road_service_views.xml',
        'views/freight_quote_views.xml',
        'views/freight_shipment_views.xml',
        'views/menus.xml',
        'views/layout.xml',
        'views/freight_templates.xml',
        'views/portal_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'aveenix_freight/static/src/css/freight.css',
        ],
    },
    'installable': True,
    'application': True,
}
