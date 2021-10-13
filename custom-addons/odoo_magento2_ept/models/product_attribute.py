from odoo import fields, models, api
from datetime import datetime

class ProductAttribute(models.Model):
    _inherit = "product.attribute"

    is_ignored_in_magento = fields.Boolean(string="Ignore for Magento", default=False,
                                              help="The attribute will be ignored while Product's Export to Magento")


    @api.onchange('is_ignored_in_magento')
    def onchange_magento_data(self):
        attr_id = self._origin.id
        magento_products = self.env['magento.product.product'].search([])
        prod_ids = []

        for p in magento_products:
            if attr_id in p.product_template_attribute_value_ids.product_attribute_value_id.mapped('attribute_id').mapped('id'):
                prod_ids.append(p.id)
        if prod_ids:
            magento_products = magento_products.browse(prod_ids)
            magento_products.write({'update_date': datetime.now()})