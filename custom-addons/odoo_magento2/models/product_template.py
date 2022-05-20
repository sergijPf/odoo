# -*- coding: utf-8 -*-

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
        if self.is_magento_config and self.magento_conf_prod_ids:
            raise UserError("You're not able to uncheck it as there are already Configurable Product(s) "
                            "created in Magento Layer")
        elif not self.is_magento_config:
            self.attribute_line_ids.filtered(lambda a: a.magento_config).magento_config = False

    def write(self, vals):
        res = super(ProductTemplate, self).write(vals)

        if self.magento_conf_prod_ids:
            if 'detailed_type' in vals:
                raise UserError("Product type can't be changed for the products already exported to Magento layer")
            if ('description_sale' in vals or 'product_template_image_ids' in vals or 'attribute_line_ids' in vals or
                    'x_magento_no_create' in vals or 'public_categ_ids' in vals or 'categ_id' in vals or
                    'alternative_product_ids' in vals):
                self.magento_conf_prod_ids.force_update = True

        return res

    def unlink(self):
        rejected_configs = []

        for prod in self:
            if prod.is_magento_config and prod.magento_conf_prod_ids:
                rejected_configs.append({c.magento_instance_id.name: c.magento_sku for c in prod.magento_conf_prod_ids})

        if rejected_configs:
            raise UserError("It's not allowed to delete these product(s) as they were already added to Magento Layer "
                            "as Configurable Products: %s\n" % (str(rejected_configs)))

        return super(ProductTemplate, self).unlink()

    def make_configurable(self):
        for rec in self:
            rec.is_magento_config = True
            for attr in rec.attribute_line_ids:
                if not attr.is_ignored and len(attr.value_ids) > 1 and not attr.magento_config:
                    attr.magento_config = True
            if not rec.attribute_line_ids.filtered(lambda a: a.magento_config):
                print(rec.attribute_line_ids.filtered(lambda a: not a.is_ignored)[-1])
                rec.attribute_line_ids.filtered(lambda a: not a.is_ignored)[-1].magento_config = True

class ProductTemplateAttributeLine(models.Model):
    _inherit = "product.template.attribute.line"

    magento_config = fields.Boolean(string="Magento Conf.Attribute", default=False)
    main_conf_attr = fields.Boolean(string="Hover Attribute", help="Configurable Attribute to be visible while hovering a product",
                                    default=False)
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
            raise UserError("There is only one 'hover' configurable attribute allowed!")

    @api.model
    def create(self, vals):
        res = super(ProductTemplateAttributeLine, self).create(vals)

        if res.is_magento_config_prod and not res.is_ignored and len(res.value_ids) > 1 and not res.magento_config:
            res.magento_config = True

        return res

    def write(self, vals):
        res = super(ProductTemplateAttributeLine, self).write(vals)

        if self.is_magento_config_prod and not self.is_ignored and len(self.value_ids) > 1 and not self.magento_config:
            self.magento_config = True

        if 'magento_config' in vals or 'main_conf_attr' in vals:
            if self.is_ignored:
                raise UserError("Attribute with 'ignore for Magento' flag cannot be used as configurable!")
            else:
                self.product_tmpl_id.magento_conf_prod_ids.force_update = True

        return res


class ProductCategory(models.Model):
    _inherit = "product.category"

    x_attribute_ids = fields.Many2many('product.page.attribute', 'product_category_ids',
                                       string="Product Page attributes", help="Descriptive attributes for Product page")
    product_template_ids = fields.One2many('product.template', 'categ_id')

    def write(self, vals):
        res = super(ProductCategory, self).write(vals)

        if 'x_attribute_ids' in vals:
            self.product_template_ids.magento_conf_prod_ids.force_update = True

        return res
