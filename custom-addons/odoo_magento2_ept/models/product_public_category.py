from odoo import fields, models, api, _
from datetime import datetime
from odoo.exceptions import UserError
from .api_request import req

class ProductPublicCategory(models.Model):
    _inherit = "product.public.category"

    # magento_assigned_attr = fields.Many2many('product.attribute', string="Configurable Attribute(s)",
    #                                     help='Attribute(s) assigned as configurable for config.product in Magento')
    # magento_sku = fields.Char(string='Conf.Product SKU', help='Configurable Product SKU to be used in Magento')
    is_magento_config = fields.Boolean(string='Is Magento Config.Product',
                                       help='Selected if current category is Configurable Product in Magento')
    top_level_parent = fields.Char(string="The Top Parent", compute='_compute_top_level_parent', store=True)
    magento_prod_categ = fields.One2many('magento.product.category', 'product_public_categ', string="Magento categories",
                                         context={'active_test': False})

    @api.depends('name', 'parent_id', 'parent_id.top_level_parent')
    def _compute_top_level_parent(self):
        for category in self:
            if category.parent_id:
                category.top_level_parent = category.parent_id.top_level_parent
            else:
                category.top_level_parent = category.name

    # _sql_constraints = [('_magento_product_name_unique_constraint',
    #                     'unique(magento_sku)',
    #                     "Magento Product SKU must be unique")]

    # @api.onchange('magento_sku')
    # def onchange_magento_sku(self):
    #     _id = self._origin.id
    #     prod_to_update = self.env['magento.configurable.product'].search([('odoo_prod_category','=',_id)])
    #     prod_to_update.write({'magento_sku': self.magento_sku})
    #
    # @api.onchange('do_not_create_in_magento', 'magento_assigned_attr')
    # def onchange_magento_data(self):
    #     _id = self._origin.id
    #     prod_to_update = self.env['magento.configurable.product'].search([('odoo_prod_category', '=', _id)])
    #     prod_to_update.write({'update_date': datetime.now()})

    @api.onchange('x_magento_no_create', 'x_magento_attr_ids', 'name')
    def onchange_magento_data(self):
        _id = self._origin.id
        prod_to_update = self.env['magento.configurable.product'].search([('odoo_prod_category', '=', _id)])
        if prod_to_update:
            prod_to_update.write({'update_date': datetime.now()})

    @api.onchange('is_magento_config')
    def onchange_magento_config_check(self):
        _id = self._origin.id
        domain = [('odoo_prod_category', '=', _id)]
        conf_prod = self.env['magento.configurable.product'].with_context(active_test=False).search(domain)
        # conf_prod = self.env['magento.configurable.product'].search(domain)
        if conf_prod:
            raise UserError("You're not able to uncheck it as there is already Configurable Product "
                            "created in Magento Layer")

    @api.onchange('parent_id')
    def onchange_parent(self):
        _id = self._origin.id
        related_product_categ_obj = self.env['magento.product.category']
        if _id:
            domain = [('product_public_categ', '=', _id)]
            related_product_categ = related_product_categ_obj.with_context(active_test=False).search(domain)
            if related_product_categ:
                raise UserError("You're not able to change the parent category as it was already exported to Magento Layer")

    @api.model
    def create(self, vals):
        result = super(ProductPublicCategory, self).create(vals)
        # loop on each product category in Magento Layer for parent record if any
        for categ in result.parent_id.magento_prod_categ:
            categ.active and self.create_new_category_in_magento_and_layer(result, categ.instance_id, categ)
        return result

    def unlink(self):
        reject_to_remove = []
        to_remove = []
        for categ in self:
            for mag_categ in categ.magento_prod_categ:
                reject_to_remove.append(categ.name) if mag_categ.active is True else to_remove.append(mag_categ)

        if reject_to_remove:
            raise UserError("It is not allowed to remove following categories "
                            "as they were already exported to Magento Layer: %s\n" % str(tuple(reject_to_remove)))
        if to_remove:
            for categ in to_remove:
                try:
                    url = '/V1/categories/%s' % categ.category_id
                    res = req(categ.instance_id, url, 'DELETE')
                except Exception as e:
                    res = False
                    # raise UserError(_("Error while removing '%s' Product Category in Magento." % categ.name))
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
            raise UserError(_("Error while creation '%s' Product Category in Magento." % new_product_categ.name))

        if magento_category.get("id"):
            ml_product_categ = self.env['magento.product.category'].create({
                'name': new_product_categ.name,
                'instance_id': magento_instance.id,
                'product_public_categ': new_product_categ.id,
                'category_id': magento_category.get('id'),
                'magento_parent_id': parent_categ.id
            })

            return ml_product_categ
