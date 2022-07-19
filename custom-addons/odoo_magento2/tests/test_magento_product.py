# -*- coding: utf-8 -*-

from odoo.exceptions import UserError

from . import common


class TestMagentoProduct(common.TestMagentoInstanceCommon):

    def setUp(self):
        res = super(TestMagentoProduct, self).setUp()

        prod1 = self.product_template1
        sku = prod1.with_context(lang='en_US').name.replace(' - ', '_').replace('-', '_').replace('%', ''). \
            replace('#', '').replace('/', '').replace('&', '').replace('  ', ' ').replace(' ', '_')

        self.conf_prod1 = self.env['magento.configurable.product'].search([
            ('magento_sku', '=', sku),
            ('magento_instance_id', '=', self.instance.id),
            ('odoo_prod_template_id', '=', prod1.id)
        ])

        return res

    def test_check_products_have_proper_setup_for_magento_export(self):
        prod1 = self.product_template1
        prod2 = self.product_template2

        self.assertTrue(prod1.is_magento_config)
        self.assertFalse(prod1.is_marketing_prod)
        self.assertTrue(prod1.attribute_line_ids[0].magento_config)
        self.assertTrue(prod1.attribute_line_ids[-1].magento_config)
        self.assertTrue(prod1.attribute_line_ids[0].main_conf_attr)

        self.assertTrue(prod2.is_magento_config)
        self.assertTrue(prod2.attribute_line_ids[0].magento_config)

    def test_check_products_were_added_to_layer(self):
        # check if products are successfully added to Magento Layer in Odoo
        self.assertIn('effect', self.add_result)

        self.assertTrue(True if self.conf_prod1 else False)

        self.assertEqual(self.product_template1.product_variant_ids, self.conf_prod1.simple_product_ids.odoo_product_id,
                         "Product Variants and Simple Products in Magento Layer do not match")

    def test_product_attributes_in_magento_layer(self):
        self.assertEqual(set(self.conf_prod1.x_magento_assign_attr_ids.mapped('name')), {'color', 'size'},
                         "Product's configurable attributes do not match with Product Template setup")

        self.assertEqual(self.conf_prod1.x_magento_main_config_attr, 'color',
                         "Product's 'hover attribute' wasn't apply properly to Configurable Product in Magento Layer")

        self.assertEqual(set(self.conf_prod1.x_magento_single_attr_ids.attribute_id.mapped('name')), {'material', 'collection'},
                         "Product single attributes do not match with Product Template setup")

    def test_product_force_update_in_layer_after_change_in_odoo(self):
        prod1 = self.product_template1

        # check if 'is_magento_config' can't be unchecked for product which is already added to layer
        with self.assertRaises(UserError):
            prod1.onchange_magento_config_check()

        # check if update of product specific fields changes 'force_update' field for conf.product in layer
        self.assertFalse(self.conf_prod1.force_update)
        prod1.website_description = '<p> test paragraph </p>'
        self.assertTrue(self.conf_prod1.force_update)

        # check if update of product specific field changes 'force_update' field for simple product in layer
        simpl_prod = self.conf_prod1.simple_product_ids[0]
        if simpl_prod:
            self.assertFalse(simpl_prod.force_update)
            simpl_prod.odoo_product_id.weight = '0.1'
            self.assertTrue(simpl_prod.force_update)

    def test_delete_odoo_products_exported_to_layer(self):
        with self.assertRaises(UserError):
            self.product_template1.unlink()

        with self.assertRaises(UserError):
            self.product_1.unlink()
