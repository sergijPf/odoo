# -*- coding: utf-8 -*-

from odoo import fields, models, api, _
from odoo.exceptions import UserError
from .api_request import req

class ProductPublicCategory(models.Model):
    _inherit = "product.public.category"

    magento_prod_categ_ids = fields.One2many('magento.product.category', 'product_public_categ_id',
                                             string="Magento categories", context={'active_test': False})
    no_create_in_magento = fields.Boolean(string="Do not create Category in Magento", default=False)

    @api.onchange('parent_id')
    def onchange_parent(self):
        curr_categ = self.browse(self._origin.id)
        if curr_categ and curr_categ.magento_prod_categ_ids:
            raise UserError("You're not able to change the parent category as it was already exported to Magento.")

    @api.onchange('no_create_in_magento')
    def onchange_no_create_in_magento(self):
        curr_categ = self.browse(self._origin.id)
        if curr_categ and curr_categ.magento_prod_categ_ids:
            raise UserError("You're not able to change it as it was already exported to Magento.")

    def write(self, vals):
        res = super(ProductPublicCategory, self).write(vals)

        # check if product category needs to be created in Magento
        parent_id = vals.get("parent_id")
        if res and parent_id:
            parent_rec = self.browse(parent_id)
            if parent_rec and parent_rec.magento_prod_categ_ids:
                categ_rec = self.browse(self._origin.id)
                magento_product_categ_obj = self.env['magento.product.category']
                # loop on each product category in Magento Layer of parent record if any
                for categ in parent_rec.magento_prod_categ_ids:
                    self.create_product_category_in_magento_and_layer(
                        magento_product_categ_obj, categ_rec, categ.instance_id, categ.magento_category, categ)
        return res

    @api.model
    def create(self, vals):
        par_id = self.browse(vals.get("parent_id"))
        if par_id and par_id.magento_prod_categ_ids:
            raise UserError("You're not allowed to create and link to this parent category as it was already exported to Magento.\n"
                            "Please create category first, add translations and link to Parent category you'd like.")
        result = super(ProductPublicCategory, self).create(vals)
        return result

    def unlink(self):
        reject_to_remove = []
        to_remove = []

        for categ in self:
            for mag_categ in categ.magento_prod_categ_ids:
                reject_to_remove.append(categ.name) if mag_categ.active else to_remove.append(mag_categ)

        if reject_to_remove:
            raise UserError("It is not allowed to remove following categories "
                            "as they were already exported to Magento Layer: %s\n" % str(tuple(reject_to_remove)))
        if to_remove:
            for categ in to_remove:
                try:
                    url = '/V1/categories/%s' % categ.magento_category
                    res = req(categ.instance_id, url, 'DELETE')
                except Exception:
                    res = False
                if res is True:
                    categ.unlink()
        result = super(ProductPublicCategory, self).unlink()
        return result

    def create_product_category_in_magento_and_layer(self, product_categ_object, product_categ, magento_instance,
                                                     magento_categ_id, parent_categ):
        # create category on Magento side
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
            ml_prod_categ = product_categ_object.create({
                'instance_id': magento_instance.id,
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
                        product_categ_object, child, magento_instance,  magento_category.get('id'), ml_prod_categ
                    )
                    child_rec and ml_prod_categ.write({
                        'magento_child_ids': [(4, child_rec.id, 0)]
                    })
                return ml_prod_categ
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
