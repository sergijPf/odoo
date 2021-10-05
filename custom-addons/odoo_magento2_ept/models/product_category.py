from odoo import fields, models, api

class ProductCategory(models.Model):
    _inherit = "product.category"

    magento_assigned_attr = fields.Many2many('product.attribute', string="Configurable Attribute(s)",
                                        help='Attribute(s) assigned as configurable for config.product in Magento')
    magento_sku = fields.Char(string='Configurable Product SKU', help='Configurable Product SKU to be used in Magento')
    do_not_create_in_magento = fields.Boolean(string="Don't create Product in Magento", default=False,
                                              help="If checked the Configurable Product won't be created on Magento side")

    _sql_constraints = [('_magento_product_name_unique_constraint',
                        'unique(magento_sku)',
                        "Magento Product SKU must be unique")]

    @api.onchange('magento_sku')
    def onchange_magento_sku(self):
        _id = self._origin.id
        prod_to_update = self.env['magento.configurable.product'].search([('odoo_prod_category','=',_id)])
        prod_to_update.write({'magento_sku': self.magento_sku})

    @api.onchange('do_not_create_in_magento', 'magento_assigned_attr')
    def onchange_magento_data(self):
        _id = self._origin.id
        prod_to_update = self.env['magento.configurable.product'].search([('odoo_prod_category', '=', _id)])
        prod_to_update.write({'update_date': self.write_date})