# -*- coding: utf-8 -*-

from odoo import fields, models, api
from odoo.exceptions import UserError


class ProductPublicCategory(models.Model):
    _inherit = "product.public.category"

    magento_prod_categ_ids = fields.One2many('magento.product.category', 'product_public_categ_id',
                                             string="Magento categories", context={'active_test': False})
    no_create_in_magento = fields.Boolean(string="Do not create Category in Magento", default=False)
    is_excluded_from_menu = fields.Boolean(string="Exclude from Magento Menu?", default=False)

    @api.onchange('parent_id', 'no_create_in_magento')
    def onchange_parent(self):
        curr_categ = self.browse(self._origin.id)
        if curr_categ and curr_categ.magento_prod_categ_ids:
            raise UserError("You're not able to change it as it was already exported to Magento.")

    @api.onchange('no_create_in_magento')
    def onchange_no_create(self):
        self.is_excluded_from_menu = False

    def write(self, vals):
        res = super(ProductPublicCategory, self).write(vals)

        # check if product category needs to be created in Magento
        parent_id = vals.get("parent_id")
        if res and parent_id:
            parent_rec = self.browse(parent_id)
            if parent_rec and parent_rec.magento_prod_categ_ids:
                public_categ_rec = self.browse(self._origin.id)

                for categ in parent_rec.magento_prod_categ_ids:
                    self.env['magento.product.category'].create_product_category_in_magento_and_layer(
                        public_categ_rec, categ.instance_id, categ.magento_category, categ
                    )
        return res

    @api.model
    def create(self, vals):
        if not vals.get('no_create_in_magento', True):
            par_id = self.browse(vals.get("parent_id"))
            if par_id and par_id.magento_prod_categ_ids:
                raise UserError("You're not allowed to create and link to this parent category as it was already "
                                "exported to Magento. Please create category first, add translations and link to "
                                "Parent category you'd like. Otherwise enable 'Do not create Category in Magento' flag")

        return super(ProductPublicCategory, self).create(vals)

    def unlink(self):
        reject_to_remove = []
        to_remove = []

        for categ in self:
            for ml_categ in categ.magento_prod_categ_ids:
                reject_to_remove.append(categ.name) if ml_categ.active else to_remove.append(ml_categ)

        if reject_to_remove:
            raise UserError(f"It is not allowed to remove following categories as they were already exported"
                            f" to Magento: {str(tuple(reject_to_remove))}. If you really need to remove it: please "
                            f"archive it in Magento Layer first and try once again.")
        if to_remove:
            for ml_categ in to_remove:
                if ml_categ.delete_category_in_magento(ml_categ.instance_id, ml_categ.magento_category):
                    ml_categ.unlink()

        return super(ProductPublicCategory, self).unlink()
