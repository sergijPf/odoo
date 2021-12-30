# -*- coding: utf-8 -*-

from odoo import fields, models, api, _
from odoo.exceptions import UserError
from .api_request import req

class ProductPublicCategory(models.Model):
    _inherit = "product.public.category"

    is_magento_config = fields.Boolean(string='Is Magento Config.Product',
                                       help='Selected if current category is Configurable Product in Magento') #remove
    top_level_parent = fields.Char(string="The Top Parent", compute='_compute_top_level_parent', store=True)
    magento_prod_categ = fields.One2many('magento.product.category', 'product_public_categ', string="Magento categories",
                                         context={'active_test': False})
    magento_conf_prod_ids = fields.One2many('magento.configurable.product', 'odoo_prod_template',
                                         string="Magento Configurable Products", context={'active_test': False}) #remove
    attribute_ids = fields.Many2many('config.product.attribute', string="Product's Page attributes",
                                     help="Descriptive attributes for Product page") #remove

    @api.depends('name', 'parent_id', 'parent_id.top_level_parent')
    def _compute_top_level_parent(self):
        for category in self:
            if category.parent_id:
                category.top_level_parent = category.parent_id.top_level_parent
            else:
                category.top_level_parent = category.name

    @api.onchange('parent_id')
    def onchange_parent(self):
        _id = self._origin.id
        curr_categ = self.browse(self._origin.id)
        if curr_categ and curr_categ.magento_prod_categ:
            raise UserError("You're not able to change the parent category as it was already exported to Magento.")

    def write(self, vals):
        res = super(ProductPublicCategory, self).write(vals)

        # check if product category needs to be created in Magento
        par_id = vals.get("parent_id")
        if res and par_id:
            par_rec = self.browse(par_id)
            if par_rec and par_rec.magento_prod_categ:
                categ_rec = self.browse(self._origin.id)
                # loop on each product category in Magento Layer for parent record if any
                for categ in par_rec.magento_prod_categ:
                    categ.active and self.create_new_category_in_magento_and_layer(categ_rec, categ.instance_id, categ)
        return res

    @api.model
    def create(self, vals):
        par_id = self.browse(vals.get("parent_id"))
        if par_id and par_id.magento_prod_categ:
            raise UserError("You're not allowed to create and link to this parent category as it was already added to Magento.\n"
                            "Please create category first, add translations and link to Parent category you'd like.")
        result = super(ProductPublicCategory, self).create(vals)
        return result

    def unlink(self):
        reject_to_remove = []
        to_remove = []

        for categ in self:
            for mag_categ in categ.magento_prod_categ:
                reject_to_remove.append(categ.name) if mag_categ.active else to_remove.append(mag_categ)

        if reject_to_remove:
            raise UserError("It is not allowed to remove following categories "
                            "as they were already exported to Magento Layer: %s\n" % str(tuple(reject_to_remove)))
        if to_remove:
            for categ in to_remove:
                try:
                    url = '/V1/categories/%s' % categ.category_id
                    res = req(categ.instance_id, url, 'DELETE')
                except Exception:
                    res = False
                if res is True:
                    categ.unlink()
        result = super(ProductPublicCategory, self).unlink()
        return result

    def create_new_category_in_magento_and_layer(self, new_product_categ, magento_instance, parent_categ):
        data = {
            'category': {
                'name': new_product_categ.name,
                'parent_id': parent_categ.category_id,
                'is_active': 'false',
                'include_in_menu': 'false'
            }
        }
        try:
            url = '/V1/categories'
            magento_category = req(magento_instance, url, 'POST', data)
        except Exception as e:
            raise UserError(_("Error while creating '%s' Product Category in Magento." % new_product_categ.name))

        if magento_category.get("id"):
            self.process_storeview_translations_export(magento_instance, new_product_categ, magento_category['id'])

            ml_product_categ = self.env['magento.product.category'].create({
                # 'name': new_product_categ.name,
                'instance_id': magento_instance.id,
                'product_public_categ': new_product_categ.id,
                'category_id': magento_category.get('id'),
                'magento_parent_id': parent_categ.id
            })
            return ml_product_categ

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
                                  "in Magento ." % (product_category.name, view.magento_storeview_code) + str(e)))
