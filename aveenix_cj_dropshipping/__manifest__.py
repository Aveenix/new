{
    'name': 'Aveenix CJ Dropshipping Connector',
    'version': '19.0.1.0.0',
    'category': 'Connector',
    'summary': 'Direct integration between Odoo and CJ Dropshipping API v2 (Products, Sandbox Orders & Tracking)',
    'description': """
Aveenix CJ Dropshipping Connector (Odoo 19)
===================================================
* Direct integration with CJ Dropshipping API v2.0
* 1. Pull Products from CJ to Odoo with Price Rule Markup %
* 2. Push Orders from Odoo to CJ (supports Sandbox Mode: isSandbox=1)
* 3. Fetch Order Status, Tracking Number & Tracking Link from CJ to Odoo
* Auto-sets 'aveenix_product_type' = 'dropship' on imported products
* Co-exists with WooCommerce Connector (ad_woocomerce_connector)
    """,
    'author': 'Anantam Innovision Private Limited',
    'website': 'https://anantaminnovision.com/',
    'license': 'LGPL-3',
    'depends': [
        'mail',
        'sale_management',
        'delivery',
        'stock',
        'account',
        'aveenix_rewards',
    ],
    'external_dependencies': {
        'python': ['requests'],
    },
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'views/res_config_settings_views.xml',
        'views/product_views.xml',
        'views/sale_order_views.xml',
        'views/sale_portal_templates.xml',
        'wizard/cj_product_import_wizard_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
