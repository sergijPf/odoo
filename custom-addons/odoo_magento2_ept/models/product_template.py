# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
from odoo import models, fields, api
from odoo.exceptions import UserError


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_magento_config = fields.Boolean(string='Is Magento Config.Product',
                                       help='Selected if current product is Configurable Product in Magento')
    # x_magento_attr_ids = fields.Many2many('product.attribute', string="Configurable Attribute(s)",
    #                                       help='Attribute(s) assigned as configurable for config.product in Magento')
    x_magento_no_create = fields.Boolean(string="Don't create in Magento", default=False,
                                         help="If checked the Configurable Product won't be created on Magento side")
    # x_magento_attr_set = fields.Char(string='Attribute Set', help='Magento Product Attribute Set',
    #                                  default="Default")
    # main_conf_attr_id = fields.Many2one('product.attribute', string="MAIN CONFIG. ATTRIBUTE",
    #                                     help='Main Magento Configurable Attribute')
    magento_conf_prod_ids = fields.One2many('magento.configurable.product', 'odoo_prod_template',
                                        string="Magento Configurable Products", context={'active_test': False})

    @api.onchange('is_magento_config')
    def onchange_magento_config_check(self):
        if self.magento_conf_prod_ids:
            raise UserError("You're not able to uncheck it as there are already Configurable Product(s) "
                            "created in Magento Layer")

    def write(self, vals):
        res = super(ProductTemplate, self).write(vals)

        if self.magento_conf_prod_ids and ('website_description' in vals or 'product_template_image_ids' in vals or\
                'x_magento_no_create' in vals or 'public_categ_ids' in vals):
            self.magento_conf_prod_ids.force_update = True

        return res

    def unlink(self):
        reject_configs = []

        for prod in self:
            if prod.is_magento_config and prod.magento_conf_prod_ids:
                reject_configs.append([c.magento_sku for c in prod.magento_conf_prod_ids])

        if reject_configs:
            raise UserError("It's not allowed to delete these products as they were already added to Magento Layer "
                            "as Configurable Products: %s\n" % (str(tuple(reject_configs))))

        result = super(ProductTemplate, self).unlink()
        return result