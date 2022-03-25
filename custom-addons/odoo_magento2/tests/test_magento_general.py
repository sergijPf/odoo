# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from . import common
from unittest.mock import patch

from ..models.magento_instance import MagentoInstance



class TestMagentoGeneral(common.TestMagentoInstanceCommon):

    def setUp(self):
        res = super(TestMagentoGeneral, self).setUp()

        return res

    def test_website_sync(self):
        pass
        # with patch('odoo.custom-addons.odoo_magento2.MagentoInstance.sync_website') as instance:
        #     instance.sync_website