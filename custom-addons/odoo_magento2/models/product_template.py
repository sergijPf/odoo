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
        for rec in self:
            if rec.is_magento_config and rec.magento_conf_prod_ids:
                raise UserError("You're not able to uncheck it as there are already Configurable Product(s) "
                                "created in Magento Layer")
            elif not rec.is_magento_config:
                config_attrs = rec.attribute_line_ids.filtered(lambda a: a.magento_config)
                if config_attrs:
                    config_attrs.magento_config = config_attrs.main_conf_attr = False

    def write(self, vals):
        res = super(ProductTemplate, self).write(vals)

        if self.magento_conf_prod_ids:
            if 'detailed_type' in vals:
                raise UserError("Product type can't be changed for the products already exported to Magento layer")

            if ('website_description' in vals or 'name' in vals or 'x_magento_no_create' in vals or
                    'public_categ_ids' in vals or 'categ_id' in vals):
                self.magento_conf_prod_ids.force_update = True
            elif 'attribute_line_ids' in vals:
                self.magento_conf_prod_ids.force_update = True
                self.magento_conf_prod_ids.simple_product_ids.force_update = True
            elif 'product_template_image_ids' in vals:
                self.magento_conf_prod_ids.force_image_update = True
            elif 'image_1920' in vals:
                self.magento_conf_prod_ids.force_image_update = True
                self.magento_conf_prod_ids.simple_product_ids.force_image_update = True

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
            valid_lines = rec.attribute_line_ids.filtered(lambda a: not a.is_ignored)

            for attr_line in valid_lines:
                attr_line.magento_config = False
                attr_line.main_conf_attr = False
                if len(attr_line.value_ids) > 1:
                    attr_line.magento_config = True
                    if attr_line.attribute_id.name in ['color', 'collection']:
                        if not valid_lines.filtered(lambda a: a.main_conf_attr):
                            attr_line.main_conf_attr = True

            # if product has only one Variant (contains only lines with one attribute value)
            if not valid_lines.filtered(lambda a: a.magento_config):
                color_line = valid_lines.filtered(lambda line: line.attribute_id.name == 'color')
                collection_line = valid_lines.filtered(lambda line: line.attribute_id.name == 'collection')
                config_attr_line = (color_line and color_line[0]) or (collection_line and collection_line[0]) or\
                                   (valid_lines and valid_lines[-1])
                if config_attr_line:
                    config_attr_line.magento_config = True

class ProductTemplateAttributeLine(models.Model):
    _inherit = "product.template.attribute.line"

    magento_config = fields.Boolean(string="Magento Conf.Attribute", default=False)
    main_conf_attr = fields.Boolean(
        string="Hover Attribute",
        help="Configurable Attribute to be visible while hovering a product",
        default=False
    )
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
