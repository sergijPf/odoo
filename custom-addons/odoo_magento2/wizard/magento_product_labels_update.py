# -*- coding: utf-8 -*-

from odoo import fields, models


class MagentoProductLabelsUpdate(models.TransientModel):
    _name = "magento.product.labels.update"
    _description = "Update Magento Product Labels"

    product_label_ids = fields.Many2many('magento.product.label', string="Product Labels")

    def update_product_labels(self):
        active_product_ids = self._context.get("active_ids", [])
        products_to_update = self.env['magento.configurable.product'].browse(active_product_ids)
        products_to_update.write({'product_label_ids': [(6, 0, self.product_label_ids.mapped("id"))]})
