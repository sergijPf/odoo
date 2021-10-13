from odoo import fields, models, api
from datetime import datetime

class ProductPublicCategory(models.Model):
    _inherit = "product.public.category"

    # magento_assigned_attr = fields.Many2many('product.attribute', string="Configurable Attribute(s)",
    #                                     help='Attribute(s) assigned as configurable for config.product in Magento')
    # magento_sku = fields.Char(string='Conf.Product SKU', help='Configurable Product SKU to be used in Magento')
    is_magento_config = fields.Boolean(string='Is Magento Config.Product',
                                       help='Selected if current category is Configurable Product in Magento')
    # do_not_create_in_magento = fields.Boolean(string="Do not create in Magento", default=False,
    #                                           help="If checked the Configurable Product won't be created on Magento side")

    # _sql_constraints = [('_magento_product_name_unique_constraint',
    #                     'unique(magento_sku)',
    #                     "Magento Product SKU must be unique")]

    # @api.onchange('magento_sku')
    # def onchange_magento_sku(self):
    #     _id = self._origin.id
    #     prod_to_update = self.env['magento.configurable.product'].search([('odoo_prod_category','=',_id)])
    #     prod_to_update.write({'magento_sku': self.magento_sku})
    #
    # @api.onchange('do_not_create_in_magento', 'magento_assigned_attr')
    # def onchange_magento_data(self):
    #     _id = self._origin.id
    #     prod_to_update = self.env['magento.configurable.product'].search([('odoo_prod_category', '=', _id)])
    #     prod_to_update.write({'update_date': datetime.now()})

    @api.onchange('x_magento_no_create', 'x_magento_attr_ids')
    def onchange_magento_data(self):
        _id = self._origin.id
        prod_to_update = self.env['magento.configurable.product'].search([('odoo_prod_category', '=', _id)])
        if prod_to_update:
            prod_to_update.write({'update_date': datetime.now()})