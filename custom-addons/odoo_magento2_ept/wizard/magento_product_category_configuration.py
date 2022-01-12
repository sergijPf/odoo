# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.

from odoo import models, fields, _
from odoo.exceptions import UserError
from ..models.api_request import req


class MagentoProductCategoryConfiguration(models.TransientModel):
    """
    Describes fields and methods for Magento Product Category Configuration
    """
    _name = "magento.product.category.configuration"
    _description = "Magento Product Category Configuration"

    def _get_magento_instance(self):
        return self.env.context.get('magento_instance_id', False)

    magento_instance_id = fields.Many2one('magento.instance', string='Magento Instance', default=_get_magento_instance,
                                          readonly=True)
    update_existed = fields.Boolean(string="To Update Existed")

    def create_update_product_public_category_structure(self):
        prod_publ_categ_obj = self.env['product.public.category']
        url = '/V1/categories'
        domain = [('parent_id', '=', False), ('no_create_in_magento', '=', False)]
        magento_product_categ_obj = self.env['magento.product.category']
        magento_categ_rec = magento_product_categ_obj.with_context(active_test=False).search([
            ('instance_id', '=', self.magento_instance_id.id)
        ])

        try:
            magento_root_category = req(self.magento_instance_id, url)
        except Exception as error:
            raise UserError(_("Error while requesting Product Category" + str(error)))

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
