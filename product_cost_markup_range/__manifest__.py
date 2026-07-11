# -*- coding: utf-8 -*-
{
    'name': 'Product Cost Markup Range Rules',
    'version': '1.0',
    'category': 'Sales/Sales',
    'summary': 'Apply custom selling price markups based on product cost ranges',
    'description': """
Product Cost Markup Range Rules
================================

This module adds a new pricing option "Markup based on Cost Range" to Odoo Pricelist Rules.
When selected, Odoo calculates the selling price based on the product standard cost, matching
it with a range table of markup rules.

Features:
---------
* Predefined cost markup rules (e.g. 0-4.99 x4.00, 5-9.99 x3.50, etc.).
* Fully customizable range table with Min Cost, Max Cost, Multiplier, and Extra Fee (Offset).
* Validation constraints to prevent range overlaps.
* Multi-currency support and unit of measure conversion.
    """,
    'author': 'Anantam Innovision Private Limited',
    'Website': 'https://anantaminnovision.com/',
    'depends': ['product', 'sale','website_sale','website'],
    'data': [
        'security/ir.model.access.csv',
        'data/product_markup_range_data.xml',
        'views/product_markup_range_views.xml',
        'views/product_pricelist_item_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
