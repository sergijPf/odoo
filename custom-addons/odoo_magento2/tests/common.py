# -*- coding: utf-8 -*-

from odoo.addons.base.tests.common import TransactionCase

MAGENTO_SITE_URL = 'https://lamillou-dev.ffflabel-dev.com/'
ACCESS_TOKEN = ''


class TestMagentoInstanceCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super(TestMagentoInstanceCommon, cls).setUpClass()

        company = cls.env['res.company'].with_context(active_test=False).search([], limit=1)

        cls.instance = cls.env['magento.instance'].create({
            'name': 'TESTNAME',
            'access_token': ACCESS_TOKEN,
            'magento_url': MAGENTO_SITE_URL,
            'company_id': company.id,
            'magento_verify_ssl': False
        })

        # create magento websites and storeviews
        cls.website = cls.env['magento.website'].create({
            'name': 'TESTWEBSITE_EN',
            'magento_website_id': '1',
            'magento_instance_id': cls.instance.id
        })

        lang_code = 'en'
        language = cls.env['res.lang'].with_context(active_test=False).search([('code', '=', lang_code)])
        cls.storeview = cls.env['magento.storeview'].create({
            'name': 'TESTSTOREVIEW1',
            'magento_website_id': cls.website.id,
            'magento_storeview_id': '1',
            'magento_instance_id': cls.instance.id,
            'lang_id': language.id if language else False,
            'magento_storeview_code': lang_code
        })

        cls.website = cls.env['magento.website'].create({
            'name': 'TESTWEBSITE_PL',
            'magento_website_id': '2',
            'magento_instance_id': cls.instance.id
        })

        lang_code = 'pl'
        language = cls.env['res.lang'].with_context(active_test=False).search([('code', '=', lang_code)])
        cls.storeview = cls.env['magento.storeview'].create({
            'name': 'TESTSTOREVIEW2',
            'magento_website_id': cls.website.id,
            'magento_storeview_id': '2',
            'magento_instance_id': cls.instance.id,
            'lang_id': language.id if language else False,
            'magento_storeview_code': lang_code
        })

        # create Odoo Product Templates and Variants
        cls.uom_unit = cls.env.ref('uom.product_uom_unit')

        cls.prod_attr_1 = cls.env['product.attribute'].create({'name': 'color'})
        cls.prod_attr_2 = cls.env['product.attribute'].create({'name': 'tag', 'is_ignored_in_magento': True})
        cls.prod_attr_3 = cls.env['product.attribute'].create({'name': 'material'})
        cls.prod_attr_4 = cls.env['product.attribute'].create({'name': 'collection'})
        cls.prod_attr_5 = cls.env['product.attribute'].create({'name': 'size'})

        cls.prod_attr1_v1 = cls.env['product.attribute.value'].create(
            {'name': 'red', 'attribute_id': cls.prod_attr_1.id, 'sequence': 1})
        cls.prod_attr1_v2 = cls.env['product.attribute.value'].create(
            {'name': 'blue', 'attribute_id': cls.prod_attr_1.id, 'sequence': 2})

        cls.prod_attr2_v1 = cls.env['product.attribute.value'].create(
            {'name': 'New', 'attribute_id': cls.prod_attr_2.id, 'sequence': 1})

        cls.prod_attr3_v1 = cls.env['product.attribute.value'].create(
            {'name': 'Cotton', 'attribute_id': cls.prod_attr_3.id, 'sequence': 1})
        cls.prod_attr3_v2 = cls.env['product.attribute.value'].create(
            {'name': 'Bamboo', 'attribute_id': cls.prod_attr_3.id, 'sequence': 2})

        cls.prod_attr4_v1 = cls.env['product.attribute.value'].create(
            {'name': 'FLY ME TO THE MOON', 'attribute_id': cls.prod_attr_4.id, 'sequence': 1})
        cls.prod_attr4_v2 = cls.env['product.attribute.value'].create(
            {'name': 'BEEBEE', 'attribute_id': cls.prod_attr_4.id, 'sequence': 2})

        cls.prod_attr5_v1 = cls.env['product.attribute.value'].create(
            {'name': 'XL', 'attribute_id': cls.prod_attr_5.id, 'sequence': 1})
        cls.prod_attr5_v2 = cls.env['product.attribute.value'].create(
            {'name': '110x420cm', 'attribute_id': cls.prod_attr_5.id, 'sequence': 2})
        cls.prod_attr5_v3 = cls.env['product.attribute.value'].create(
            {'name': '25', 'attribute_id': cls.prod_attr_5.id, 'sequence': 3})

        # product template 1
        cls.product_template1 = cls.env['product.template'].create({
            'name': 'Test_prod1',
            'type': 'product',
            'uom_id': cls.uom_unit.id,
            'uom_po_id': cls.uom_unit.id,
            'attribute_line_ids': [
                (0, 0, {'attribute_id': cls.prod_attr_1.id, 'value_ids': [(6, 0, [cls.prod_attr1_v1.id, cls.prod_attr1_v2.id])]}),
                (0, 0, {'attribute_id': cls.prod_attr_2.id, 'value_ids': [(6, 0, [cls.prod_attr2_v1.id])]}),
                (0, 0, {'attribute_id': cls.prod_attr_3.id, 'value_ids': [(6, 0, [cls.prod_attr3_v1.id])]}),
                (0, 0, {'attribute_id': cls.prod_attr_4.id, 'value_ids': [(6, 0, [cls.prod_attr4_v1.id])]}),
                (0, 0, {'attribute_id': cls.prod_attr_5.id, 'value_ids': [(6, 0, [cls.prod_attr5_v1.id, cls.prod_attr5_v2.id])]}),
               ]
        })

        product_attr1_v1 = cls.product_template1.attribute_line_ids[0].product_template_value_ids[0]
        product_attr1_v2 = cls.product_template1.attribute_line_ids[0].product_template_value_ids[1]
        product_attr2 = cls.product_template1.attribute_line_ids[1].product_template_value_ids[0]
        product_attr3 = cls.product_template1.attribute_line_ids[2].product_template_value_ids[0]
        product_attr4 = cls.product_template1.attribute_line_ids[3].product_template_value_ids[0]
        product_attr5_v1 = cls.product_template1.attribute_line_ids[4].product_template_value_ids[0]
        product_attr5_v2 = cls.product_template1.attribute_line_ids[4].product_template_value_ids[1]

        combination1 = product_attr1_v1 + product_attr2 + product_attr3 + product_attr4 + product_attr5_v1
        combination2 = product_attr1_v2 + product_attr2 + product_attr3 + product_attr4 + product_attr5_v1
        combination3 = product_attr1_v1 + product_attr2 + product_attr3 + product_attr4 + product_attr5_v2
        combination4 = product_attr1_v2 + product_attr2 + product_attr3 + product_attr4 + product_attr5_v2

        cls.product_1 = cls.product_template1._get_variant_for_combination(combination1)
        cls.product_1.default_code = "variant_1"
        cls.product_2 = cls.product_template1._get_variant_for_combination(combination2)
        cls.product_2.default_code = "variant_2"
        cls.product_3 = cls.product_template1._get_variant_for_combination(combination3)
        cls.product_3.default_code = "variant_3"
        cls.product_4 = cls.product_template1._get_variant_for_combination(combination4)
        cls.product_4.default_code = "variant_4"

        # product template 2
        cls.product_template2 = cls.env['product.template'].create({
            'name': 'Test_prod2',
            'type': 'product',
            'uom_id': cls.uom_unit.id,
            'uom_po_id': cls.uom_unit.id,
            'attribute_line_ids': [
                (0, 0, {'attribute_id': cls.prod_attr_1.id, 'value_ids': [(6, 0, [cls.prod_attr1_v1.id])]}),
                (0, 0, {'attribute_id': cls.prod_attr_3.id, 'value_ids': [(6, 0, [cls.prod_attr3_v1.id])]}),
                (0, 0, {'attribute_id': cls.prod_attr_3.id, 'value_ids': [(6, 0, [cls.prod_attr3_v2.id])]}),
                (0, 0, {'attribute_id': cls.prod_attr_4.id, 'value_ids': [(6, 0, [cls.prod_attr4_v1.id])]})
            ]
        })

        product_attr1 = cls.product_template2.attribute_line_ids[0].product_template_value_ids[0]
        product_attr2 = cls.product_template2.attribute_line_ids[1].product_template_value_ids[0]
        product_attr3 = cls.product_template2.attribute_line_ids[2].product_template_value_ids[0]
        product_attr4 = cls.product_template2.attribute_line_ids[3].product_template_value_ids[0]

        cls.product_5 = cls.product_template2._get_variant_for_combination(product_attr1 + product_attr2 +
                                                                           product_attr3 + product_attr4)
        cls.product_5.default_code = "variant_5"

        (cls.product_template1 + cls.product_template2).make_configurable()

        # add to Magento Layer in Odoo
        imp_exp_wiz = cls.env['magento.import.export'].create({
            'magento_instance_ids': [(6, 0, [cls.instance.id])]
        })

        cls.add_result = imp_exp_wiz.with_context({
            'active_ids': [cls.product_template1.id, cls.product_template2.id]
        }).export_products_to_magento_layer_operation()
