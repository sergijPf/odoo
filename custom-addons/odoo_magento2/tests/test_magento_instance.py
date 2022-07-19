# -*- coding: utf-8 -*-

import requests

from . import common
# from unittest.mock import patch


class TestMagentoInstance(common.TestMagentoInstanceCommon):

    def setUp(self):
        res = super(TestMagentoInstance, self).setUp()

        return res

    def test_instance_general_endpoints(self):
        self.assertEqual(len(common.ACCESS_TOKEN), 32, "Access Token to Magento website is missed or not properly set")

        api_url = f'{common.MAGENTO_SITE_URL}'
        headers = {
            'Accept': '*/*',
            'Content-Type': 'application/json',
            'User-Agent': 'My User Agent 1.0',
            'Authorization': 'Bearer %s' % common.ACCESS_TOKEN
        }

        res = requests.get(f"{api_url}rest/V1/store/websites", headers=headers)
        self.assertTrue(True if res.ok else False, "Websites endpoint doesn't work")

        res = requests.get(f"{api_url}rest/V1/store/storeConfigs", headers=headers)
        self.assertTrue(True if res.ok else False, "StoreConfigs endpoint doesn't work")

        res = requests.get(f"{api_url}rest/V1/store/storeViews", headers=headers)
        self.assertTrue(True if res.ok else False, "StoreView endpoint doesn't work")

        res = requests.get(f"{api_url}rest/V1/directory/currency", headers=headers)
        self.assertTrue(True if res.ok else False, "Can't get currency endpoint")

        res = requests.get(f"{api_url}rest/V1/products/attributes/price", headers=headers)
        self.assertTrue(True if res.ok else False, "Can't get Product Price Attribute")
        content = res.json() if res.ok else {}
        self.assertTrue(content.get("scope") == 'website', "Price Attribute scope missed or doesn'tnot equal to 'website'")

        res = requests.get(f"{api_url}rest/V1/paymentmethod", headers=headers)
        self.assertTrue(True if res.ok else False, "Payment methods endpoint fails to get info")

        res = requests.get(f"{api_url}rest/V1/shippingmethod", headers=headers)
        self.assertTrue(True if res.ok else False, "Shipping methods endpoint fails to get info")
