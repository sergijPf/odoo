# -*- coding: utf-8 -*-

from odoo.tests import common


class TestMagentoInstanceCommon(common.SavepointCase):

    @classmethod
    def setUpClass(cls):
        super(TestMagentoInstanceCommon, cls).setUpClass()

        company = cls.env['res.company'].with_context(active_test=False).search([], limit=1)
        cls.instance = cls.env['magento.instance'].create({
            'name': 'TESTNAME',
            'access_token': 'qwerty1234',
            'magento_url': 'http://testsite.com',
            'company_id': company.id,
            'magento_verify_ssl': False
        })

        cls.website = cls.env['magento.website'].create({
            'name': 'TESTWEBSITE1',
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
