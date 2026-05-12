{
    'name': 'Aveenix Website',
    'version': '1.0',
    'category': 'Website',
    'summary': 'Modern eCommerce website - red & gold design',
    'description': 'Modern eCommerce website - red & gold design',
    'author': 'Custom',
    'depends': ['website', 'website_sale', 'website_crm', 'website_sale_wishlist'],
    'data': [
        'security/security.xml',
        'data/product_category_data.xml',
        'data/product_data.xml',
        'views/website_config_views.xml',
        'views/layout.xml',
        'views/templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'aveenix_website/static/src/css/theme.css',
            'aveenix_website/static/src/js/dark_mode.js',
            'aveenix_website/static/src/js/compare.js',
            'aveenix_website/static/src/js/wishlist_no_disable.js',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
