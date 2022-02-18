# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
from odoo import models, fields, api
from odoo.exceptions import UserError


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_magento_config = fields.Boolean(string='Is Magento Config.Product',
                                       help='Selected if current product is Configurable Product in Magento')
    x_magento_no_create = fields.Boolean(string="Don't create in Magento", default=False,
                                         help="If checked the Configurable Product won't be created on Magento side")
    magento_conf_prod_ids = fields.One2many('magento.configurable.product', 'odoo_prod_template_id',
                                            string="Magento Configurable Products", context={'active_test': False})

    @api.onchange('is_magento_config')
    def onchange_magento_config_check(self):
        if self.magento_conf_prod_ids:
            raise UserError("You're not able to uncheck it as there are already Configurable Product(s) "
                            "created in Magento Layer")

    def write(self, vals):
        res = super(ProductTemplate, self).write(vals)

        if self.magento_conf_prod_ids and ('website_description' in vals or 'product_template_image_ids' in vals or
                                           'attribute_line_ids' in vals or 'x_magento_no_create' in vals or
                                           'public_categ_ids' in vals or 'categ_id' in vals ):
            self.magento_conf_prod_ids.force_update = True

        return res

    def unlink(self):
        reject_configs = []

        for prod in self:
            if prod.is_magento_config and prod.magento_conf_prod_ids:
                reject_configs.append({c.magento_instance_id.name: c.magento_sku for c in prod.magento_conf_prod_ids})

        if reject_configs:
            raise UserError("It's not allowed to delete these product(s) as they were already added to Magento Layer "
                            "as Configurable Products: %s\n" % (str(reject_configs)))

        result = super(ProductTemplate, self).unlink()
        return result


class ProductTemplateAttributeLine(models.Model):
    """Attributes available on product.template with their selected values in a m2m.
    Used as a configuration model to generate the appropriate product.template.attribute.value"""

    _inherit = "product.template.attribute.line"

    magento_config = fields.Boolean(string="Magento Config.Attribute", default=False)
    main_conf_attr = fields.Boolean(string="Main Config.Attribute.", default=False)
    is_ignored = fields.Boolean(related="attribute_id.is_ignored_in_magento")
    create_variant = fields.Selection(related="attribute_id.create_variant")
    is_magento_config_prod = fields.Boolean(related="product_tmpl_id.is_magento_config")
    x_magento_no_create = fields.Boolean(related="product_tmpl_id.x_magento_no_create")

    @api.onchange('magento_config')
    def onchange_magento_config_attribute(self):
        if not self.magento_config:
            self.main_conf_attr = False

    @api.onchange('main_conf_attr')
    def onchange_magento_main_config_attribute(self):
        if self.main_conf_attr and len(self.product_tmpl_id.attribute_line_ids.filtered(lambda x: x.main_conf_attr)) > 1:
            raise UserError("There is only one main configurable attribute allowed for Magento setup!")

    def write(self, vals):
        res = super(ProductTemplateAttributeLine, self).write(vals)

        if self.is_magento_config_prod and not self.is_ignored and len(self.value_ids) > 1 and not self.magento_config:
            self.magento_config = True

        if 'magento_config' in vals or 'main_conf_attr' in vals:
            if self.is_ignored:
                raise UserError ("Attribute with 'ignore for Magento' flag cannot be used as configurable!")
            else:
                self.product_tmpl_id.magento_conf_prod_ids.force_update = True

        return res