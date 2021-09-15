from odoo import fields, models, api

class ProductCategory(models.Model):
    _inherit = "product.category"

    magento_attr_set = fields.Char(string='Magento Product Attribute Set', help='Magento Attribute set', default="Default")
    magento_assigned_attr = fields.Many2many('product.attribute', string="Magento Configurable Attribute(s)",
                                        help='Attribute(s) assigned as configurable for config.product in Magento')
    magento_name = fields.Char(string='Magento Product Name (SKU)', help='Configurable Product Name to be used in Magento')

    _sql_constraints = [('_magento_product_name_unique_constraint',
                        'unique(magento_name)',
                        "Magento Product Name must be unique")]

    @api.onchange('magento_name')
    def onchange_magento_name(self):
        _id = self._origin.id
        prod_to_update = self.env['magento.product.product'].search([('magento_prod_categ','=',_id)])
        prod_to_update.write({'prod_categ_name': self.magento_name})