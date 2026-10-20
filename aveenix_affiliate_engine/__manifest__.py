{
    'name': 'Aveenix Affiliate Engine',
    'version': '19.0.1.0.0',
    'category': 'Website',
    'summary': 'One affiliate engine: CJ Affiliate + ClickBank offers matched to '
               'Aveenix News articles, placed automatically and tracked',
    'description': """
Aveenix Affiliate Engine
========================
A single engine that monetises Aveenix News articles from two affiliate
networks, rather than two separate integrations:

* **CJ Affiliate (Commission Junction)** — automated discovery through the
  publisher APIs: Product Feed, Link Search, Advertiser Lookup, Promotional
  Properties, and Commission Detail for revenue.
* **ClickBank** — an approved-offer database of HopLinks, entered and approved
  by Aveenix staff before the matcher may use them.

Both feed ONE approved-offer database, one AI/keyword article matcher, one
automatic placement step and one click & revenue tracking trail.

NOTE: "CJ" here means CJ Affiliate / Commission Junction (cj.com). It is NOT
CJdropshipping.com, which is a product supplier handled by the separate
`aveenix_cj_dropshipping` module.
    """,
    'author': 'Anantam Innovision Private Limited',
    'website': 'https://anantaminnovision.com/',
    'license': 'LGPL-3',
    'depends': [
        # mail for the offer approval trail; aveenix_website owns the news
        # articles, the click log and the AI configuration this builds on.
        'mail',
        'aveenix_website',
    ],
    'external_dependencies': {
        'python': ['requests'],
    },
    'data': [
        'security/ir.model.access.csv',
        'data/affiliate_section_data.xml',
        'data/ir_cron_data.xml',
        'views/affiliate_section_views.xml',
        'views/affiliate_advertiser_views.xml',
        'views/affiliate_offer_views.xml',
        'views/affiliate_placement_views.xml',
        'views/affiliate_commission_views.xml',
        'views/affiliate_click_log_views.xml',
        'views/res_config_settings_views.xml',
        'views/news_templates.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
