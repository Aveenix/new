# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase

class TestProductCostMarkupRange(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Create a test product
        cls.product = cls.env['product.product'].create({
            'name': 'Test Markup Product',
            'type': 'consu',
            'standard_price': 3.0,
        })
        
        # Create a test pricelist
        cls.pricelist = cls.env['product.pricelist'].create({
            'name': 'Test Markup Pricelist',
        })
        
        # Create a pricelist item using the custom range markup
        cls.pricelist_item = cls.env['product.pricelist.item'].create({
            'pricelist_id': cls.pricelist.id,
            'compute_price': 'markup_range',
            'applied_on': '3_global',
        })

    def test_markup_calculation_ranges(self):
        """Test that the price is calculated correctly for different cost ranges"""
        
        # 1. Cost = $3.00 (matches $0.00–$4.99 range -> Multiplier 4.00, Surcharge -0.01)
        # Expected price: 3.00 * 4.00 - 0.01 = 11.99
        self.product.standard_price = 3.0
        price = self.pricelist._get_product_price(self.product, 1.0)
        self.assertAlmostEqual(price, 11.99, places=2)

        # 2. Cost = $8.00 (matches $5.00–$9.99 range -> Multiplier 3.50, Surcharge -0.01)
        # Expected price: 8.00 * 3.50 - 0.01 = 27.99
        self.product.standard_price = 8.0
        price = self.pricelist._get_product_price(self.product, 1.0)
        self.assertAlmostEqual(price, 27.99, places=2)

        # 3. Cost = $15.00 (matches $10.00–$19.99 range -> Multiplier 2.80, Surcharge -0.01)
        # Expected price: 15.00 * 2.80 - 0.01 = 41.99
        self.product.standard_price = 15.0
        price = self.pricelist._get_product_price(self.product, 1.0)
        self.assertAlmostEqual(price, 41.99, places=2)

        # 4. Cost = $30.00 (matches $20.00–$39.99 range -> Multiplier 2.30, Surcharge -0.01)
        # Expected price: 30.00 * 2.30 - 0.01 = 68.99
        self.product.standard_price = 30.0
        price = self.pricelist._get_product_price(self.product, 1.0)
        self.assertAlmostEqual(price, 68.99, places=2)

        # 5. Cost = $50.00 (matches $40.00–$59.99 range -> Multiplier 2.00, Surcharge -0.01)
        # Expected price: 50.00 * 2.00 - 0.01 = 99.99
        self.product.standard_price = 50.0
        price = self.pricelist._get_product_price(self.product, 1.0)
        self.assertAlmostEqual(price, 99.99, places=2)

        # 6. Cost = $80.00 (matches $60.00–$99.99 range -> Multiplier 1.80, Surcharge -0.01)
        # Expected price: 80.00 * 1.80 - 0.01 = 143.99
        self.product.standard_price = 80.0
        price = self.pricelist._get_product_price(self.product, 1.0)
        self.assertAlmostEqual(price, 143.99, places=2)

        # 7. Cost = $150.00 (matches $100.00–$199.99 range -> Multiplier 1.60, Surcharge -0.01)
        # Expected price: 150.00 * 1.60 - 0.01 = 239.99
        self.product.standard_price = 150.0
        price = self.pricelist._get_product_price(self.product, 1.0)
        self.assertAlmostEqual(price, 239.99, places=2)

        # 8. Cost = $300.00 (matches $200.00–$399.99 range -> Multiplier 1.45, Surcharge -0.01)
        # Expected price: 300.00 * 1.45 - 0.01 = 434.99
        self.product.standard_price = 300.0
        price = self.pricelist._get_product_price(self.product, 1.0)
        self.assertAlmostEqual(price, 434.99, places=2)

        # 9. Cost = $500.00 (matches $400.00+ range -> Multiplier 1.35, Surcharge -0.01)
        # Expected price: 500.00 * 1.35 - 0.01 = 674.99
        self.product.standard_price = 500.0
        price = self.pricelist._get_product_price(self.product, 1.0)
        self.assertAlmostEqual(price, 674.99, places=2)
