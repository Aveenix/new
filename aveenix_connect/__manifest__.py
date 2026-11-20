{
    'name': 'Aveenix Connect',
    'version': '19.0.1.1.0',
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
  browse by city, FAQ
* Search results and category pages with rating filter and paging
* Business page: logo, photos, services, service areas, contact, hours, map,
  trust badges (Verified Business, checked licences), star reviews, job ads,
  claim, enquiry and "Report incorrect information"; schema.org data for
  search engines; live Google rating, hours and photos for listings linked
  to Google
* Claim a listing with a code emailed to its address, or by team review
* Get quotes: a request goes to the matching claimed businesses by category
  and city / service area
* Reviews only from customers who sent the business an enquiry or a quote
  request
* Aveenix Jobs (/connect/jobs): job ads from listings, with applications
* List your business: logged-in visitors submit a listing for approval,
  filled in from the NZBN register when they enter their NZBN

Backend (Connect menu)
----------------------
* Businesses with publish / featured / verified flags, owner and ownership
  claims
* Pending approval queue, reviews, categories
* Enquiries & quotes, reports, licence checks, job ads
* NZBN register: search and import, bulk imports run by a scheduled action
  that also refreshes imported listings
* Link a listing to its Google place (only the place ID is stored, as the
  Google Maps Platform terms require)

Customer portal (My Account)
----------------------------
* Owners edit their listings: contact details, address, hours, logo, photos,
  services, service areas, licences; and post job ads
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
        'data/connect_data.xml',
        'views/connect_category_views.xml',
        'views/connect_business_views.xml',
        'views/connect_lead_views.xml',
        'views/connect_licence_views.xml',
        'views/connect_job_views.xml',
        'views/connect_nzbn_views.xml',
        'wizard/connect_google_link_views.xml',
        'wizard/connect_nzbn_search_views.xml',
        'views/res_config_settings_views.xml',
        'views/menus.xml',
        'views/layout.xml',
        'views/connect_templates.xml',
        'views/connect_job_templates.xml',
        'views/portal_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'aveenix_connect/static/src/css/connect.css',
            'aveenix_connect/static/src/js/connect_google.js',
            'aveenix_connect/static/src/js/connect_lists.js',
            'aveenix_connect/static/src/js/connect_hero.js',
        ],
    },
    'installable': True,
    'application': True,
}
