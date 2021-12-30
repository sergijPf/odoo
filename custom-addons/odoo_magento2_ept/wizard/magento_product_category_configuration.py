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

    magento_instance_id = fields.Many2one(
        'magento.instance',
        string='Magento Instance',
        default=_get_magento_instance,
        readonly=True
    )
    update_existed = fields.Boolean(string="To Update Existed")
    public_product_categ = fields.Many2one('product.public.category', string="Product's Root Category")

    def create_update_product_public_category_structure(self):
        url = '/V1/categories'
        magento_product_categ_obj = self.env['magento.product.category']
        domain = [('instance_id', '=', self.magento_instance_id.id)]

        try:
            magento_root_category = req(self.magento_instance_id, url)
        except Exception as error:
            raise UserError(_("Error while requesting Product Category" + str(error)))

        if self.update_existed:
            magento_categ = magento_product_categ_obj.with_context(active_test=False).search(domain)
            for categ in magento_categ:
                self.process_storeview_translations_export(self.magento_instance_id, categ.product_public_categ,
                                                           categ['category_id'])
        else:
            if magento_root_category.get("name") != self.public_product_categ.name:
                raise UserError("Root Product Category has to have the same name in Magento and Odoo.")
            if magento_root_category.get("children_data"):
                raise UserError("Root Product Category in Magento should not have any subcategories.")

            # remove existing records in Magento Layer related to current instance
            rec_to_remove = magento_product_categ_obj.with_context(active_test=False).search(domain)
            rec_to_remove and rec_to_remove.unlink()

            self.create_product_category_in_magento_and_layer(magento_product_categ_obj, self.public_product_categ,
                                                              self.magento_instance_id, magento_root_category.get("id"),
                                                              None)
        return {
            'effect': {
                'fadeout': 'slow',
                'message': "Product Categories were successfully created/updated in Magento and in Magento Layer!",
                'img_url': '/web/static/src/img/smile.svg',
                'type': 'rainbow_man',
            }
        }

    def create_product_category_in_magento_and_layer(self, product_categ_object, product_categ, magento_instance,
                                                    magento_categ_id, parent_categ):
        magento_category = {}
        # create category in Magento if not root category
        if parent_categ:
            data = {
                'category': {
                    'name': product_categ.name,
                    'parent_id': magento_categ_id,
                    'is_active': 'true',
                    'include_in_menu': 'true'
                }
            }
            try:
                url = '/V1/categories'
                magento_category = req(magento_instance, url, 'POST', data)
            except Exception as e:
                raise UserError(_("Error while creation '%s' Product Category in Magento." % product_categ.name) + str(e))

            if magento_category.get("id"):
                self.process_storeview_translations_export(magento_instance, product_categ, magento_category['id'])

        # create product category in Magento Layer
        if magento_category.get("id") or not parent_categ:
            magento_prod_categ = product_categ_object.create({
                # 'name': product_categ.name,
                'instance_id': magento_instance.id,
                'product_public_categ': product_categ.id,
                'category_id': magento_category.get('id') if parent_categ else magento_categ_id,
                'magento_parent_id': parent_categ.id if parent_categ else None
            })

            # add child ids and recursive call of current method
            if product_categ.child_id:
                for child in product_categ.child_id:
                    child_rec = self.create_product_category_in_magento_and_layer(
                        product_categ_object,
                        child,
                        magento_instance,
                        magento_category.get('id') if parent_categ else magento_categ_id,
                        magento_prod_categ
                    )
                    child_rec and magento_prod_categ.write({
                        'magento_child_ids': [(4, child_rec.id, 0)]
                    })
                return magento_prod_categ
        return None

    def process_storeview_translations_export(self, magento_instance, product_category, magento_category_id):
        magento_storeviews = [w.store_view_ids for w in magento_instance.magento_website_ids]
        for view in magento_storeviews:
            data = {
                "category": {
                    "name": product_category.with_context(lang=view.lang_id.code).name
                }
            }
            try:
                api_url = '/%s/V1/categories/%s' % (view.magento_storeview_code, magento_category_id)
                req(magento_instance, api_url, 'PUT', data)
            except Exception as e:
                raise UserError(_("Error while exporting '%s' Product Category's translation to %s storeview "
                                  "in Magento." % (product_category.name, view.magento_storeview_code) + str(e)))
