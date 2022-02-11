# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError


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
