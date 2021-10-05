# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
"""
Describes fields and methods for Magento configurable products
"""
import json
from datetime import datetime, timedelta
from odoo import fields, models, api, _
from odoo.exceptions import UserError
from .api_request import req

MAGENTO_DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'


class MagentoConfigurableProduct(models.Model):
    """
    Describes fields and methods for Magento products
    """
    _name = 'magento.configurable.product'
    _description = 'Magento Configurable Product'
    _rec_name = 'magento_product_name'

    magento_instance_id = fields.Many2one('magento.instance', 'Magento Instance',
                                          help="This field relocates magento instance")
    magento_sku = fields.Char(string="Magento Product SKU")
    magento_product_name = fields.Char(string="Magento Configurable Product Name", translate=True)
    magento_website_ids = fields.Many2many('magento.website', string='Magento Product Websites', readonly=False,
                                           domain="[('magento_instance_id','=',magento_instance_id)]")
    magento_status = fields.Selection([
        ('not_exported', 'not Exported'),
        ('in_process', 'In Process'),
        ('in_magento', 'In Magento'),
        ('no_need', 'Not needed'),
        ('log_error', 'Error to Export'),
        ('update_needed', 'Need to Update'),
        ('deleted', 'Deleted in Magento')
    ], string='Export Status', help='The status of Configurable Product Export to Magento ',
        default='not_exported')
    image_1920 = fields.Image(related="odoo_prod_category.ecommerce_category_id.image_1920")
    magento_product_id = fields.Char(string="Magento Product Id")
    active = fields.Boolean("Active", default=True)
    odoo_prod_category = fields.Many2one('product.category', string='Related Odoo Product Category')
    category_ids = fields.Many2many("magento.product.category", string="Product Categories", help="Magento Categories",
                                    domain="[('instance_id','=',magento_instance_id)]")
    magento_attr_set = fields.Char(string='Magento Product Attribute Set', help='Magento Attribute set',
                                   default="Default")
    do_not_create_flag = fields.Boolean(related="odoo_prod_category.do_not_create_in_magento",
                                        string="Don't create Product in Magento")
    mag_assign_attributes = fields.Many2many(related="odoo_prod_category.magento_assigned_attr",
                                             string="Configurable Attribute(s)")
    magento_export_date = fields.Datetime(string="Last Export Date",
                                          help="Configurable Product last Export Date to Magento")
    update_date = fields.Datetime(string="Configurable Product Update Date")

    _sql_constraints = [('_magento_conf_product_unique_constraint',
                         'unique(magento_sku,magento_instance_id)',
                         "Magento Configurable Product SKU must be unique within Magento instance")]

    @api.model
    def create(self, vals):
        product = super(MagentoConfigurableProduct, self).create(vals)
        product.update_date = product.create_date
        return product

    def delete_in_magento(self):
        """
        Delete Configurable Product in Magento, available in Magento Product Form view for products with Magento Product Id
        :return: None
        """
        self.ensure_one()
        try:
            api_url = '/V1/products/%s' % self.magento_sku
            response = req(self.magento_instance_id, api_url, 'DELETE')
        except Exception as err:
            raise UserError("Error while deleting product in Magento. " + str(err))
        if response is True:
            self.write({
                'magento_status': 'deleted',
                'magento_product_id': '',
                'magento_export_date': '',
                'update_date': '',
                'magento_website_ids': [(5, 0, 0)]
            })

    @api.onchange('magento_product_name', 'category_ids', 'magento_attr_set')
    def onchange_configurable_product(self):
        self.update_date = self.write_date