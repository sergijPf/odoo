from odoo import fields, models, api

class ProductCategory(models.Model):
    _inherit = "product.category"

    magento_attr_set = fields.Char(string='Magento Product Attribute Set', help='Magento Attribute set', default="Default")
    magento_assigned_attr = fields.Many2many('product.attribute', string="Magento Configurable Attribute(s)",
                                        help='Attribute(s) assigned as configurable for config.product in Magento')
    magento_sku = fields.Char(string='Magento Conf.Product SKU', help='Configurable Product SKU to be used in Magento')
    magento_name = fields.Char(string='Magento Conf.Product Name', help='Configurable Product Name to be used in Magento')
    do_not_create_in_magento = fields.Boolean(string="Don't create Product in Magento", default=False,
                                              help="If checked the Configurable Product won't be created on Magento side")

    _sql_constraints = [('_magento_product_name_unique_constraint',
                        'unique(magento_sku)',
                        "Magento Product SKU must be unique")]

    @api.onchange('magento_name')
    def onchange_magento_name(self):
        _id = self._origin.id
        prod_to_update = self.env['magento.product.product'].search([('magento_prod_categ','=',_id)])
        prod_to_update.write({'prod_categ_name': self.magento_name})