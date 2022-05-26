# -*- coding: utf-8 -*-

from odoo import models, fields, _
from odoo.exceptions import UserError
from ..python_library.api_request import req


class MagentoProductCategoryConfiguration(models.TransientModel):
    _name = "magento.product.category.configuration"
    _description = "Magento Product Category Configuration"

    def _default_get_magento_instance(self):
        return self.env.context.get('magento_instance_id', False)

    is_update_existed = fields.Boolean(string="Update Existed only",
                                       help="To update categories already exported to Magento")
    magento_instance_id = fields.Many2one('magento.instance', string='Magento Instance', readonly=True,
                                          default=_default_get_magento_instance)

    def create_update_product_public_category_structure(self):
        prod_publ_categ_obj = self.env['product.public.category']
        domain = [('parent_id', '=', False), ('no_create_in_magento', '=', False)]
        ml_category_obj = self.env['magento.product.category']
        ml_category_recs = ml_category_obj.with_context(active_test=False).search([
            ('instance_id', '=', self.magento_instance_id.id)
        ])

        try:
            url = '/V1/categories'
            magento_root_category = req(self.magento_instance_id, url)
            if not magento_root_category and not isinstance(magento_root_category, dict):
                raise "Product Categories request has returned incompatible data."
        except Exception as error:
            raise UserError(_("Error getting Product Categories from Magento" + str(error)))

        roots_children = magento_root_category.get("children_data")

        if self.is_update_existed:
            if not roots_children:
                raise UserError("There is nothing to update on Magento side!")

            magento_categories_list = []
            self._get_all_magento_category_ids(roots_children.get('children_data', []), magento_categories_list)

            for categ in ml_category_recs:
                if categ.magento_category in magento_categories_list:
                    ml_category_obj.process_storeview_translations_export(
                        self.magento_instance_id, categ.product_public_categ_id, categ.magento_category
                    )
                else:
                    categ.active = False
        else:
            # remove existed
            if roots_children:
                for child in roots_children:
                    child_id = str(child.get("id"))
                    if child_id and ml_category_obj.delete_category_in_magento(self.magento_instance_id, child_id) is True:
                        ml_category = ml_category_obj.search([
                            ('magento_category', '=', child_id),
                            ('instance_id', '=', self.magento_instance_id.id)
                        ])
                        ml_category and ml_category.unlink()

            # create new categories
            for public_category in prod_publ_categ_obj.search(domain):
                ml_category_obj.create_product_category_in_magento_and_layer(
                    public_category, self.magento_instance_id, magento_root_category.get("id"), None
                )

        return {
            'effect': {
                'fadeout': 'slow',
                'message': "Product Categories were successfully created/updated in Magento and in Magento Layer!",
                'img_url': '/web/static/img/smile.svg',
                'type': 'rainbow_man',
            }
        }

    def _get_all_magento_category_ids(self, children, categories_list):
        for child in children:
            categories_list.append(str(child.get('id')))
            ch = child.get("children_data", [])
            if ch:
                self._get_all_magento_category_ids(ch, categories_list)
