{
    'name': 'Aveenix Connect',
    'version': '19.0.1.0.0',
    'category': 'Website/Directory',
    'summary': 'Aveenix Connect business directory (search, listings, reviews) '
               'with Google Places, and its directory backend',
    'description': """
Aveenix Connect
===============
A fourth Aveenix site beside Aveenix Express (the shop), Aveenix News and
Aveenix Freight, reached from the footer and branded with the same logo,
"Connect" in place of "Express" / "News".

Website (/connect)
------------------
* Home: what + where search, popular categories, featured and new listings,
  browse by city
* Search results and category pages with rating filter and paging
* Business page: logo, photos, contact, hours, map, star reviews, claim and
  enquiry; live Google rating, hours and photos for listings linked to Google
* List your business: logged-in visitors submit a listing for approval

Backend (Connect menu)
----------------------
* Businesses with publish / featured flags, owner and ownership claims
* Pending approval queue, reviews, categories
* Link a listing to its Google place (only the place ID is stored, as the
  Google Maps Platform terms require)

Customer portal (My Account)
----------------------------
* Owners edit their listings: contact details, address, hours, logo, photos
    """,
    'author': 'Anantam Innovision Private Limited',
    'website': 'https://anantaminnovision.com/',
    'license': 'LGPL-3',
    'depends': [
        # aveenix_website owns the header, footer and theme this site reuses.
        'aveenix_website',
        'mail',
        'portal',
        'rating',  # star reviews on listings, as on shop products
    ],
    'data': [
        'security/connect_security.xml',
        'security/ir.model.access.csv',
        'data/connect_category_data.xml',
        'views/connect_category_views.xml',
        'views/connect_business_views.xml',
        'wizard/connect_google_link_views.xml',
        'views/res_config_settings_views.xml',
        'views/menus.xml',
        'views/layout.xml',
        'views/connect_templates.xml',
        'views/portal_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'aveenix_connect/static/src/css/connect.css',
            'aveenix_connect/static/src/js/connect_google.js',
        ],
    },
    'installable': True,
    'application': True,
}
