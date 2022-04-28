# -*- coding: utf-8 -*-

from odoo import models, api


class ProductPricelistItem(models.Model):
    _inherit = "product.pricelist.item"

    @api.model
    def create(self, vals):
        res = super(ProductPricelistItem, self).create(vals)

        # check if related pricelist linked to any of Magento's websites and let update related products if true
        magento_instances = self.env['magento.instance'].search([])

        for instance in magento_instances:
            valid_for_magento = False
            if instance.catalog_price_scope == 'website':
                for website in instance.magento_website_ids:
                    if website.pricelist_id and website.pricelist_id.id == vals.get('pricelist_id'):
                        valid_for_magento = True

            if valid_for_magento:
                applied = vals.get('applied_on')

                if applied == '3_global' or applied == '2_product_category':
                    domain = [("magento_instance_id", "=", instance.id)]
                    if applied == '2_product_category':
                        domain.append(('inventory_category_id', '=', vals.get('categ_id')))

                    self.env['magento.product.product'].search(domain).write({"force_update": True})
                else:
                    if applied == '1_product':
                        product = self.env['product.product'].search([
                            ('product_tmpl_id', '=', vals.get('product_tmpl_id'))])
                    else:
                        # applied on '0_product_variant':
                        product = self.env['product.product'].browse(vals.get('product_id'))

                    product.magento_product_ids.filtered(
                        lambda x: x.magento_instance_id.id == instance.id).write({"force_update": True})

        return res

    def write(self, vals):
        # check if related pricelist linked to any of Magento's websites and let update related products if true
        applied_on_before = self.applied_on
        if applied_on_before == '2_product_category':
            scope = self.categ_id
        elif applied_on_before == '1_product':
            scope = self.product_tmpl_id
        elif applied_on_before == '0_product_variant':
            scope = self.product_id

        res = super(ProductPricelistItem, self).write(vals)

        magento_instances = self.env['magento.instance'].search([])
        for instance in magento_instances:
            valid_for_magento = False
            if instance.catalog_price_scope == 'website':
                for website in instance.magento_website_ids:
                    if website.pricelist_id.id == self.pricelist_id.id:
                        valid_for_magento = True

            if valid_for_magento:
                domain = [("magento_instance_id", "=", instance.id)]
                if applied_on_before != self.applied_on:
                    if applied_on_before > self.applied_on:
                        if applied_on_before == '2_product_category':
                            domain.append(('inventory_category_id', '=', scope.id))
                        elif applied_on_before == '1_product':
                            domain.append(('odoo_prod_template_id', '=', scope.id))
                    else:
                        if self.applied_on == '2_product_category':
                            domain.append(('inventory_category_id', '=', self.categ_id.id))
                        elif self.applied_on == '1_product':
                            domain.append(('odoo_prod_template_id', '=', self.product_tmpl_id.id))
                elif self.applied_on == '2_product_category':
                    domain.append(('inventory_category_id', '=', self.categ_id.id))
                elif self.applied_on == '1_product':
                    domain.append(('odoo_prod_template_id', '=', self.product_tmpl_id.id))
                elif self.applied_on == '0_product_variant':
                    domain.append(('magento_sku', '=', self.product_id.default_code))

                self.env['magento.product.product'].search(domain).write({"force_update": True})

        return res
