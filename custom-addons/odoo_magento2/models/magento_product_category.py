# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api
from odoo.exceptions import UserError
from ..python_library.api_request import req

_logger = logging.getLogger(__name__)

class MagentoProductCategory(models.Model):
    _name = "magento.product.category"
    _description = "Magento Product Categories"
    _rec_name = 'complete_category_name'

    instance_id = fields.Many2one('magento.instance', 'Magento Instance', ondelete="cascade")
    magento_category = fields.Char(string="Magento ID")
    magento_parent_id = fields.Many2one('magento.product.category', 'Parent Category', ondelete='cascade')
    magento_child_ids = fields.One2many(comodel_name='magento.product.category', inverse_name='magento_parent_id',
                                        string='Child Categories')
    complete_category_name = fields.Char("Full Category Name", help="Complete Category Path(Name)",
                                         compute="_compute_complete_name", recursive=True)
    active = fields.Boolean(string="Status", default=True)
    product_public_categ_id = fields.Many2one('product.public.category', string="Product Public Category")
    name = fields.Char("Name", related="product_public_categ_id.name")

    @api.depends('name', 'magento_parent_id.complete_category_name')
    def _compute_complete_name(self):
        for category in self:
            if category.magento_parent_id:
                category.complete_category_name = '%s / %s' % (category.magento_parent_id.complete_category_name,
                                                               category.name)
            else:
                category.complete_category_name = category.name

    @staticmethod
    def delete_category_in_magento(instance, categ_id):
        try:
            url = '/V1/categories/%s' % categ_id
            res = req(instance, url, 'DELETE')
        except Exception as e:
            _logger.warning(f'Failed to delete category id{categ_id} in Magento. The reason: {str(e)}')
            res = False

        return res

    def create_product_category_in_magento_and_layer(self, product_categ, instance, magento_categ_id, parent_categ):
        data = {
            'category': {
                'name': product_categ.name,
                'parent_id': magento_categ_id,
                'is_active': 'true',
                'include_in_menu': 'false' if product_categ.is_excluded_from_menu else 'true'
            }
        }

        try:
            url = '/V1/categories'
            magento_category = req(instance, url, 'POST', data)
        except Exception as e:
            raise UserError(("Error while creation '%s' Product Category in Magento." % product_categ.name) + str(e))

        if magento_category.get("id"):
            self.process_storeview_translations_export(instance, product_categ, magento_category['id'])

            ml_prod_categ = self.create({
                'instance_id': instance.id,
                'product_public_categ_id': product_categ.id,
                'magento_category': magento_category['id'],
                'magento_parent_id': parent_categ.id if parent_categ else None
            })

            # add child ids and recursive call of current method
            if product_categ.child_id:
                for child in product_categ.child_id:
                    if child.no_create_in_magento:
                        continue
                    child_rec = self.create_product_category_in_magento_and_layer(
                        child, instance,  magento_category.get('id'), ml_prod_categ
                    )
                    child_rec and ml_prod_categ.write({'magento_child_ids': [(4, child_rec.id, 0)]})

                return ml_prod_categ

        return None

    @staticmethod
    def process_storeview_translations_export(magento_instance, product_category, magento_category_id):
        magento_storeviews = [w.store_view_ids for w in magento_instance.magento_website_ids]

        for view in magento_storeviews:
            data = {
                "category": {
                    "name": product_category.with_context(lang=view.lang_id.code).name,
                    'include_in_menu': 'false' if product_category.is_excluded_from_menu else 'true'
                }
            }

            try:
                api_url = '/%s/V1/categories/%s' % (view.magento_storeview_code, magento_category_id)
                req(magento_instance, api_url, 'PUT', data)
            except Exception as e:
                raise UserError("Error while exporting '%s' Product Category's translation to %s storeview "
                                "in Magento." % (product_category.name, view.magento_storeview_code) + str(e))
