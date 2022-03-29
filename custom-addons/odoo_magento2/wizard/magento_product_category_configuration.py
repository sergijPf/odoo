# -*- coding: utf-8 -*-

from odoo import models, fields, _
from odoo.exceptions import UserError
from ..python_library.api_request import req


class MagentoProductCategoryConfiguration(models.TransientModel):
    _name = "magento.product.category.configuration"
    _description = "Magento Product Category Configuration"

    def _default_get_magento_instance(self):
        return self.env.context.get('magento_instance_id', False)

    update_existed = fields.Boolean(string="To Update Existed only")
    magento_instance_id = fields.Many2one('magento.instance', string='Magento Instance', readonly=True,
                                          default=_default_get_magento_instance)

    def create_update_product_public_category_structure(self):
        prod_publ_categ_obj = self.env['product.public.category']
        magento_product_categ_obj = self.env['magento.product.category']
        domain = [('parent_id', '=', False), ('no_create_in_magento', '=', False)]
        magento_categ_rec = magento_product_categ_obj.with_context(active_test=False).search([
            ('instance_id', '=', self.magento_instance_id.id)
        ])

        try:
            url = '/V1/categories'
            magento_root_category = req(self.magento_instance_id, url)
        except Exception as error:
            raise UserError(_("Error getting Product Categories from Magento" + str(error)))

        if self.update_existed:
            for categ in magento_categ_rec:
                prod_publ_categ_obj.process_storeview_translations_export(
                    self.magento_instance_id, categ.product_public_categ_id, categ['magento_category']
                )
            domain.append(('magento_prod_categ_ids', '=', False))
        else:
            if magento_root_category.get("children_data"):
                raise UserError("Root Product Category in Magento should not have any subcategories.")
            magento_categ_rec and magento_categ_rec.unlink()

            for category in prod_publ_categ_obj.search(domain):
                prod_publ_categ_obj.create_product_category_in_magento_and_layer(
                    magento_product_categ_obj, category, self.magento_instance_id, magento_root_category.get("id"), None
                )

        return {
            'effect': {
                'fadeout': 'slow',
                'message': "Product Categories were successfully created/updated in Magento and in Magento Layer!",
                'img_url': '/web/static/src/img/smile.svg',
                'type': 'rainbow_man',
            }
        }
