# -*- coding: utf-8 -*-

from odoo import fields, models, api
from odoo.exceptions import UserError


class MagentoPricelists(models.Model):

    _name = 'magento.pricelists'
    _description = 'Magento Pricelists for products to be exported to Magento.'

    magento_instance_id = fields.Many2one('magento.instance', 'Magento Instance')
    magento_sku = fields.Char(string="Magento Simple Product SKU")
    price = fields.Float("Magento Price")

    # def export_data(self, magento_instance):
    #     # '/all/V1/products/tier-prices'
    #     data = {
    #         "prices": [{
    #             "price_type": "string",
    #             "website_id": 0,
    #             "sku": "string",
    #             "customer_group": "string",
    #             "quantity": 0,
    #             "extension_attributes": {}
    #         }]
    #     }
    #
    #     # '/all/V1/products/base-prices'
    #     data = {
    #         "prices": [{
    #             "price": 0,
    #             "store_id": 0,
    #             "sku": "string",
    #             "extension_attributes": {}
    #         }]
    #     }
    #
    #     # '/all/V1/products/special-prices'
    #     data = {
    #         "prices": [{
    #             "price": 0,
    #             "store_id": 0,
    #             "sku": "string",
    #             "price_from": "string",
    #             "price_to": "string",
    #             "extension_attributes": {}
    #         }]
    #     }
    #
    #     try:
    #         api_url = '/all/V1/products/tier-prices'
    #         response = req(magento_instance, api_url, 'POST', data)
    #     except Exception:
    #         text = "Error while prices export to Magento.\n"
