# -*- coding: utf-8 -*-

from . import common
from odoo.exceptions import UserError



class TestMagentoProduct(common.TestMagentoInstanceCommon):

    def setUp(self):
        res = super(TestMagentoProduct, self).setUp()

        self.uom_unit = self.env.ref('uom.product_uom_unit')
        self.prod_attr_1 = self.env['product.attribute'].create({'name': 'Color'})
        self.prod_attr1_v1 = self.env['product.attribute.value'].create(
            {'name': 'red', 'attribute_id': self.prod_attr_1.id, 'sequence': 1})
        self.prod_attr1_v2 = self.env['product.attribute.value'].create(
            {'name': 'blue', 'attribute_id': self.prod_attr_1.id, 'sequence': 2})

        self.prod_attr_2 = self.env['product.attribute'].create({'name': 'Print', 'is_ignored_in_magento': True})
        self.prod_attr2_v1 = self.env['product.attribute.value'].create(
            {'name': 'A4', 'attribute_id': self.prod_attr_2.id, 'sequence': 1})

        self.product_template = self.env['product.template'].create({
            'name': 'Test_prod',
            'type': 'product',
            'uom_id': self.uom_unit.id,
            'uom_po_id': self.uom_unit.id,
            'attribute_line_ids': [(0, 0, {
                'attribute_id': self.prod_attr_1.id,
                'value_ids': [(6, 0, [self.prod_attr1_v1.id, self.prod_attr1_v2.id])]
            })],
            'is_magento_config': True
        })

        self.product_template.attribute_line_ids.create({
            'product_tmpl_id': self.product_template.id,
            'attribute_id': self.prod_attr_2.id,
            'value_ids': [(6, 0, [self.prod_attr2_v1.id])]
        })

        # product.template.attribute.value records
        self.product_attr1_v1 = self.product_template.attribute_line_ids[0].product_template_value_ids[0]
        self.product_attr1_v2 = self.product_template.attribute_line_ids[0].product_template_value_ids[1]
        self.product_attr2 = self.product_template.attribute_line_ids[1].product_template_value_ids[0]

        self.product_1 = self.product_template._get_variant_for_combination(self.product_attr1_v1 + self.product_attr2)
        self.product_1.default_code = "variant_1"
        self.product_2 = self.product_template._get_variant_for_combination(self.product_attr1_v2 + self.product_attr2)
        self.product_2.default_code = "variant_2"

        imp_exp_wiz = self.env['magento.import.export'].create({'magento_instance_ids': [(6, 0, [self.instance.id])]})
        self.result = imp_exp_wiz.with_context({'active_ids': self.product_template.id}).\
            export_products_to_magento_layer_operation()

        return res

    def test_adding_products_to_layer(self):

        # check if products are successfully added to Magento Layer in Odoo
        self.assertIn('effect', self.result)

        # check if product attribute line with multiple values is configurable
        self.assertTrue(self.product_template.attribute_line_ids.filtered(
            lambda x: x.attribute_id.id == self.prod_attr_1.id).magento_config)

        # check if product attribute with is_ignore_for_magento flag can't be configurable
        with self.assertRaises(UserError):
            self.product_template.attribute_line_ids.filtered(
            lambda x: x.attribute_id == self.prod_attr_2).magento_config = True

        # check if config.product is in layer
        conf_prod = self.env['magento.configurable.product'].search([
            ('magento_instance_id', '=', self.instance.id),
            ('odoo_prod_template_id', '=', self.product_template.id)
        ])
        self.assertTrue(conf_prod)

        # check if 'is_magento_config' can't be unchecked for product which is already added to layer
        with self.assertRaises(UserError):
            self.product_template.onchange_magento_config_check()

        # check if update of product specific fields changes 'force_update' field for conf.product in layer
        conf_prod.force_update = False
        self.product_template.website_description = '<p> test paragraph </p>'
        self.assertTrue(conf_prod.force_update)

        # check product variant is in magento layer and sku == internal reference
        simp_prod = self.env['magento.product.product'].search([
            ('magento_instance_id', '=', self.instance.id),
            ('magento_sku', '=', self.product_1.default_code)
        ])
        self.assertEqual(simp_prod.magento_sku if simp_prod else False, self.product_1.default_code,
                         "Can't find Product Variant in Magento Layer. Magento SKU should be equal to Internal Reference")

        # check if update of product specific field changes 'force_update' field for simple product in layer
        simp_prod.force_update = False
        self.product_1.weight = '0.1'
        self.assertTrue(simp_prod.force_update)


    def test_delete_odoo_products_exported_to_layer(self):
        with self.assertRaises(UserError):
            self.product_template.unlink()

        with self.assertRaises(UserError):
            self.product_1.unlink()