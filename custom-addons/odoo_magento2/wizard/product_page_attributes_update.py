# -*- coding: utf-8 -*-

from odoo import fields, models


class ProductPageAttributesUpdate(models.TransientModel):
    _name = "product.page.attributes.update"
    _description = "Update Magento Product Page Attributes"

    prod_page_attr_ids = fields.Many2many('product.page.attribute', string="Product Page Attributes Update")

    def update_product_page_attributes(self):
        active_product_ids = self._context.get("active_ids", [])
        products_to_update = self.env['product.category'].browse(active_product_ids)
        update_data = {'x_attribute_ids': [(6, 0, self.prod_page_attr_ids.mapped("id"))]}
        products_to_update.write(update_data)
