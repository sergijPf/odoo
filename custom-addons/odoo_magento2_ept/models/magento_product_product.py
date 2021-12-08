# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
"""
Describes fields and methods for Magento products
"""
import json
from datetime import datetime, timedelta
from odoo import fields, models, _, api
from odoo.exceptions import UserError
from .api_request import req, create_search_criteria
from ..python_library.php import Php

MAGENTO_DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'
PRODUCT_PRODUCT = 'product.product'
# STOCK_INVENTORY = 'stock.inventory'
# COMMON_LOG_LINES_EPT = 'common.log.lines.ept'
MAGENTO_PRODUCT_PRODUCT = 'magento.product.product'
MAX_SIZE_FOR_IMAGES = 2500000 # should be aligned with MYSQL - max_allowed_size (currently 4M), !!! NOTE 4M is converted size and constant value is before convertion
PRODUCTS_THRESHOLD = 200
IMG_SIZE = 'image_1024'


class MagentoProductProduct(models.Model):
    """
    Describes fields and methods for Magento products
    """
    _name = MAGENTO_PRODUCT_PRODUCT
    _description = 'Magento Product'
    _rec_name = 'magento_product_name'

    magento_instance_id = fields.Many2one('magento.instance','Magento Instance',
                                          help="This field relocates magento instance")
    magento_product_id = fields.Char(string="Magento Product Id")
    # magento_tmpl_id = fields.Many2one(
    #     MAGENTO_PRODUCT_TEMPLATE,
    #     string="Magento Layer Product Template",
    #     help="Product Template related to current Product Variant in Odoo",
    #     ondelete="cascade"
    # )
    odoo_product_id = fields.Many2one(PRODUCT_PRODUCT, 'Odoo Product Variant', required=True, ondelete='restrict', copy=False)
    magento_website_ids = fields.Many2many('magento.website', string='Magento Product Websites', readonly=False,
                                           domain="[('magento_instance_id','=',magento_instance_id)]")
    # product_type = fields.Selection([
    #     ('simple', 'Simple Product'),
    #     ('configurable', 'Configurable Product'),
    #     ('virtual', 'Virtual Product'),
    #     ('downloadable', 'Downloadable Product'),
    #     ('group', 'Group Product'),
    #     ('bundle', 'Bundle Product'),
    # ], string='Magento Product Type', help='Magento Product Type', default='simple')
    # created_at = fields.Date(
    #     string='Product Created At',
    #     help="Date when product created into Magento"
    # )
    # updated_at = fields.Date(
    #     string='Product Updated At',
    #     help="Date when product updated into Magento"
    # )
    # description = fields.Text(string="Product Description", help="Description", translate=True)
    # short_description = fields.Text(
    #     string='Product Short Description',
    #     help='Short Description',
    #     translate=True
    # )
    # magento_product_image_ids = fields.One2many(
    #     'magento.product.image',
    #     'magento_product_id',
    #     string="Magento Product Images",
    #     help="Magento Product Images"
    # )
    # sync_product_with_magento = fields.Boolean(
    #     string='Sync Product with Magento',
    #     help="If Checked means, Product synced With Magento Product"
    # )
    magento_sku = fields.Char(string="Magento Simple Product SKU")
    magento_product_name = fields.Char(string="Magento Simple Product Name", related="odoo_product_id.name")
    active_product = fields.Boolean('Odoo Product Active', related="odoo_product_id.active")
    active = fields.Boolean("Active", default=True)
    image_1920 = fields.Image(related="odoo_product_id.image_1920")
    product_template_attribute_value_ids = fields.Many2many(related='odoo_product_id.product_template_attribute_value_ids')
    # qty_available = fields.Float(related='odoo_product_id.qty_available')
    # lst_price = fields.Float(related='odoo_product_id.lst_price')
    # standard_price = fields.Float(related='odoo_product_id.standard_price')
    currency_id = fields.Many2one(related='odoo_product_id.currency_id')
    # valuation = fields.Selection(related='odoo_product_id.product_tmpl_id.valuation')
    # cost_method = fields.Selection(related='odoo_product_id.product_tmpl_id.cost_method')
    company_id = fields.Many2one(related='odoo_product_id.company_id')
    uom_id = fields.Many2one(related='odoo_product_id.uom_id')
    # total_magento_variants = fields.Integer(related='magento_tmpl_id.total_magento_variants')
    uom_po_id = fields.Many2one(related='odoo_product_id.uom_po_id')

    # added by SPf
    magento_conf_product = fields.Many2one('magento.configurable.product', string='Magento Configurable Product')
    magento_conf_prod_sku = fields.Char(string='Magento Config.Product SKU', related='magento_conf_product.magento_sku')
    inventory_category_id = fields.Many2one(string='Odoo product category', related='odoo_product_id.categ_id')
    x_magento_name = fields.Char(string='Product Name for Magento', related='odoo_product_id.x_magento_name')
    category_ids = fields.Many2many("magento.product.category", string="Product Categories",
                                    help="Magento Product Categories", domain="[('instance_id','=',magento_instance_id)]")
    magento_export_date = fields.Datetime(string="Last Export Date", help="Product Variant last Export Date to Magento",
                                          copy=False)
    magento_status = fields.Selection([
        ('not_exported', 'not Exported'),
        ('in_process', 'In Process'),
        ('in_magento', 'In Magento'),
        ('need_to_link', 'Need to be Linked'),
        ('log_error', 'Error to Export'),
        ('update_needed', 'Need to Update'),
        ('deleted', 'Deleted in Magento')
    ], string='Export Status',
        help='The status of Product Variant Export to Magento ', default='not_exported')
    # update_date = fields.Datetime(string="Simple Product Update Date")
    force_update = fields.Boolean(string="To force run Simple Product Export", default=False)

    _sql_constraints = [('_magento_product_unique_constraint',
                         'unique(magento_sku,magento_instance_id,magento_product_id)',
                         "Magento Product must be unique")]

    # @api.model
    # def create(self, vals):
    #     product = super(MagentoProductProduct, self).create(vals)
    #     product.update_date = product.create_date
    #     return product

    # def write(self, vals):
    #     if 'magento_product_name' in vals:
    #         vals.update({'update_date': datetime.now()})
    #     res = super(MagentoProductProduct, self).write(vals)
    #     return res

    def view_odoo_product(self):
        """
        This method id used to view odoo product.
        :return: Action
        """
        if self.odoo_product_id:
            vals = {
                'name': 'Odoo Product',
                'type': 'ir.actions.act_window',
                'res_model': PRODUCT_PRODUCT,
                'view_type': 'form',
                'view_mode': 'tree,form',
                'domain': [('id', '=', self.odoo_product_id.id)],
            }
            return vals

    # def unlink(self):
    #     unlink_magento_products = self.env[MAGENTO_PRODUCT_PRODUCT]
    #     unlink_magento_templates = self.env[MAGENTO_PRODUCT_TEMPLATE]
    #     for magento_product in self:
    #         # Check if the product is last product of this template...
    #         if not unlink_magento_templates or (
    #                 unlink_magento_templates and unlink_magento_templates != magento_product.magento_tmpl_id):
    #             unlink_magento_templates |= magento_product.magento_tmpl_id
    #         unlink_magento_products |= magento_product
    #     res = super(MagentoProductProduct, unlink_magento_products).unlink()
    #     # delete templates after calling super, as deleting template could lead to deleting
    #     # products due to ondelete='cascade'
    #     if not unlink_magento_templates.magento_product_ids:
    #         unlink_magento_templates.unlink()
    #     self.clear_caches()
    #     return res

    # def toggle_active(self):
    #     """ Archiving related magento.product.template if there is not any more active magento.product.product
    #     (and vice versa, unarchiving the related magento product template if there is now an active magento.product.product) """
    #     result = super().toggle_active()
    #     # We deactivate product templates which are active with no active variants.
    #     tmpl_to_deactivate = self.filtered(lambda product: (product.magento_tmpl_id.active
    #                                                         and not product.magento_tmpl_id.magento_product_ids)).mapped('magento_tmpl_id')
    #     # We activate product templates which are inactive with active variants.
    #     tmpl_to_activate = self.filtered(lambda product: (not product.magento_tmpl_id.active
    #                                                       and product.magento_tmpl_id.magento_product_ids)).mapped('magento_tmpl_id')
    #     (tmpl_to_deactivate + tmpl_to_activate).toggle_active()
    #     return result



    # def create_magento_product_in_odoo(
    #         self,
    #         magento_instance,
    #         items,
    #         magento_per_sku,
    #         product_count,
    #         product_total_queue,
    #         log_book_id
    # ):
    #     """
    #     Create magento product if it is not available in Odoo
    #     :param magento_instance: Instance of Magento
    #     :param items: Product items received from Magento
    #     :param magento_per_sku: Dictionary product sku
    #     :param product_count: Incremental count of Product
    #     :param product_total_queue: Total of Product data queue lines
    #     :param log_book_id: Common log book object
    #     :return: Dictionary of magento_per_sku and product_count
    #     """
    #     magento_product_template_obj = self.env[MAGENTO_PRODUCT_TEMPLATE]
    #     for item in items:
    #         error = False
    #         product_response = json.loads(item.product_data)
    #         magento_sku = product_response.get('sku')
    #         if not magento_per_sku or (
    #                 magento_per_sku and (magento_instance.id not in magento_per_sku.keys() or (
    #                     magento_instance.id in magento_per_sku.keys() and
    #                     magento_sku not in magento_per_sku[magento_instance.id].keys()))):
    #             if product_response.get('type_id') == 'simple':
    #                 # Create or update simple Product Process
    #                 error = self.create_or_update_simple_product(
    #                     product_response, magento_instance, log_book_id,
    #                     error, magento_per_sku, item.id, do_not_update=item.do_not_update_existing_product
    #                 )
    #             elif product_response.get('type_id') == 'configurable':
    #                 # Create or update configurable Product Process
    #                 error = magento_product_template_obj.create_or_update_configurable_product(
    #                     product_response, magento_instance, log_book_id,
    #                     error, magento_per_sku, item.id,
    #                 )
    #             else:
    #                 log_line_vals = {
    #                     'log_lines': [(0, 0, {
    #                         'message': 'Product Type %s Is Not Supported' % product_response.get('type_id'),
    #                         'order_ref': product_response.get('id'),
    #                         'import_product_queue_line_id': item.id
    #                     })]
    #                 }
    #                 log_book_id.write(log_line_vals)
    #                 error = True
    #         product_count += 1
    #         product_total_queue -= 1
    #         item, product_count = self.check_more_product_queue_exists(product_count, product_total_queue, item)
    #         item.write({'state': 'failed' if error else 'done', 'processed_at': datetime.now()})
    #     return magento_per_sku, product_count, product_total_queue

    # def check_more_product_queue_exists(self, product_count, product_total_queue, item):
    #     """
    #     Check more product queue items exists
    #     :param product_count: incremental count of product queue line
    #     :param product_total_queue: total product queue line
    #     :param item: item received from Magento
    #     :return: product_count, item
    #     """
    #     if product_count > 1 or (0 < product_count <= 1 and product_total_queue == 0):
    #         self._cr.commit()
    #         product_count = 1
    #         item.sync_import_magento_product_queue_id.is_process_queue = True
    #     return item, product_count

    # def create_or_update_simple_product(
    #         self, item, instance, log_book_id, error,
    #         magento_per_sku, order_data_queue_line_id, order_ref=False, magento_prod_tmpl=False,
    #         conf_product_item=False, do_not_update=False
    # ):
    #     """
    #     Create or Update Magento And Odoo Product
    #     :param item: Item received from Magento
    #     :param instance: Instance of Magento
    #     :param log_book_id: Common log book object
    #     :param error: If any error, returns True
    #     :param magento_per_sku: Dictionary of Magento Products
    #     :param order_data_queue_line_id: Order data queue object
    #     :param order_ref: Order Reference
    #     :param magento_prod_tmpl: Magento product template object
    #     :return:
    #     """
    #     magento_sku = item.get('sku')
    #     magento_product = self.search([
    #         ('magento_sku', '=', magento_sku), ('magento_instance_id', '=', instance.id)])
    #     queue_line = 'import_product_queue_line_id' if not order_ref else 'magento_order_data_queue_line_id'
    #     order_ref = item.get('id') if not order_ref else order_ref
    #     website_ids = item.get('extension_attributes').get('website_ids')
    #     magento_websites = instance.magento_website_ids.filtered(lambda x: x.magento_website_id in str(website_ids))
    #     if magento_product and not magento_product.odoo_product_id:
    #         error = self.map_odoo_product_with_magento_product(
    #             instance, magento_product, item, log_book_id, order_ref, queue_line, order_data_queue_line_id, error
    #         )
    #     elif not magento_product:
    #         odoo_product, error = self.create_odoo_product(
    #             magento_sku, item, instance, log_book_id,
    #             order_ref, queue_line, order_data_queue_line_id, error
    #         )
    #         if odoo_product:
    #             if not magento_prod_tmpl:
    #                 magento_prod_tmpl, error = self.create_magento_product_template(
    #                     odoo_product, instance, item, magento_websites,
    #                     log_book_id, order_ref, queue_line, order_data_queue_line_id, error
    #                 )
    #             magento_product, error = self.create_magento_product_product(
    #                 odoo_product, instance, magento_websites, item, magento_prod_tmpl.id,
    #                 log_book_id, order_ref, queue_line, order_data_queue_line_id, error
    #             )
    #     if magento_product:
    #         magento_product = self.update_magento_product_and_template(
    #             item, magento_websites, instance, magento_product, magento_prod_tmpl, conf_product_item)
    #     self.manage_price_scope(instance, magento_product, item, do_not_update)
    #     if magento_per_sku and instance.id in magento_per_sku.keys():
    #         magento_per_sku[instance.id][magento_sku] = magento_sku
    #     else:
    #         magento_per_sku.update({instance.id: {magento_sku: magento_sku}})
    #     return error

    # def update_magento_product_and_template(
    #         self, item, magento_websites, instance, magento_product, magento_prod_tmpl, conf_product_item):
    #     """
    #     Update Magento Product and product template details.
    #     :param item: Item received from Magento
    #     :param magento_websites: Magento website object
    #     :param instance: Magento instance object
    #     :param magento_product: Magento product object
    #     :param magento_prod_tmpl: Magento product template object or False
    #     :param conf_product_item: Child product items received from Magento
    #     :return: Magento product object
    #     """
    #     self.update_magento_product(item, magento_websites, instance, magento_product)
    #     # below code for set magento sku and magento product id while import
    #     # the product and product was already mapped before perform the import operation
    #     template_vals = {}
    #     if not magento_prod_tmpl and (
    #             (not magento_product.magento_tmpl_id.magento_product_template_id or
    #              not magento_product.magento_tmpl_id.magento_sku)
    #             or
    #             (magento_product.magento_tmpl_id and
    #              magento_product.odoo_product_id.product_tmpl_id)
    #     ):
    #         # case 1 (configurable product): map product first.
    #         # So magento product id and created and updated date not set in the template
    #         # now while import that same configurable product then update that template and
    #         # set magento product ID and other value
    #         # Case 2 : During the time of the map product if not set the magento SKU
    #         # then set the magento sku as well
    #         # Case 3 : While import product first time and then change the product data from the magento
    #         # then update that data in magento layer product template as well
    #         itm = conf_product_item if conf_product_item else item
    #         if itm.get('sku') == magento_product.magento_tmpl_id.magento_sku:
    #             # While configurable product's simple product update
    #             # at that time template name and type was changed,
    #             # So this condition added
    #             template_vals = magento_product.magento_tmpl_id.prepare_magento_product_template_vals(
    #                 itm, instance, magento_product.odoo_product_id.product_tmpl_id)
    #             template_vals.pop('magento_product_name')  # not change the product name,
    #             # because it's change the odoo product/template name as well
    #     if template_vals or not magento_product.magento_tmpl_id.magento_sku:
    #         # Add "or" condition for below case
    #         # case : first map the product and then import that specific product,
    #         # So set the magento template id and sku
    #         if conf_product_item:
    #             conf_product_item_id = conf_product_item.get('id')
    #             conf_product_item_sku = conf_product_item.get('sku')
    #             magento_product_type = 'configurable'
    #         else:
    #             conf_product_item_id = item.get('id')
    #             conf_product_item_sku = item.get('sku')
    #             magento_product_type = 'simple'
    #         template_vals.update({
    #             'magento_product_template_id': conf_product_item_id,
    #             'magento_sku': conf_product_item_sku,
    #             'product_type': magento_product_type,
    #             'sync_product_with_magento': True
    #         })
    #         magento_product.magento_tmpl_id.write(template_vals)
    #     return magento_product

    # def manage_price_scope(self, instance, magento_product, item, do_not_update):
    #     """
    #     :param instance: Magento Instance
    #     :param magento_product: magento Product
    #     :param item: Item received from Magento
    #     :param do_not_update: If True, it will update existing magento product.
    #     :return:
    #     """
    #     # Case : Price Scope = Global
    #     # ===========================================
    #     # add this for update price in the price-list
    #     # if the product and it's price is exist in configured price-list then update
    #     # else create new line in price-list with that simple product and price
    #     # Case : Price Scope = Website
    #     # ===========================================
    #     # If price scope is "website" then add product price in the configured -
    #     # price-list. [Path : Magento Instance > Magento Websites > price-list]
    #     # if bool object for the price update is checked then only price -
    #     # update if the product was exist in that price-list
    #     # If the bool obj of the update price not checked any product not exist
    #     # in the price-list then also the price will be added to the configured price-list
    #     # Add/Update Price Based on the magento Default Price
    #     price = item.get('price') or 0.0
    #     if magento_product and not do_not_update:
    #         self.create_pricelist_item(instance, price, magento_product, item)

    # def create_pricelist_item(self, magento_instance, price, product, item):
    #     """
    #     Added product into price list.
    #     :param magento_instance: Instance of Magento
    #     :param price: Product Price
    #     :param product: Magento Product object
    #     :return: product pricelist item object
    #     """
    #     pricelist_item_obj = self.env['product.pricelist.item']
    #     if magento_instance.catalog_price_scope == 'global':
    #         pricelist_id = magento_instance.pricelist_id.id
    #         pricelist_item = pricelist_item_obj.search([
    #             ('pricelist_id', '=', pricelist_id),
    #             ('product_id', '=', product.odoo_product_id.id)
    #         ])
    #         self.create_or_update_price(pricelist_id, product, price, pricelist_item)
    #     elif item.get('extension_attributes').get('website_wise_product_price_data'):
    #         for website_product_price in item.get('extension_attributes').get('website_wise_product_price_data'):
    #             website_product_price = json.loads(website_product_price)
    #             magento_website = self.env['magento.website'].\
    #                 search([('magento_website_id', '=', website_product_price.get('website_id'))], limit=1)
    #             if magento_website:
    #                 pricelist_ids = magento_website.pricelist_ids
    #                 price = website_product_price.get('product_price')
    #                 website_pricelist = self.get_website_price_list(website_product_price, pricelist_ids)
    #                 if website_pricelist:
    #                     pricelist_items = pricelist_item_obj.\
    #                         search([('pricelist_id', '=', website_pricelist.id),
    #                                 ('product_id', '=', product.odoo_product_id.id)])
    #                     self.create_or_update_price(website_pricelist.id,
    #                                                 product,
    #                                                 price, pricelist_items)

    # def get_website_price_list(self, website_product_price, pricelist_ids):
    #     """
    #     Get price list of products magento website vise.
    #     :param website_product_price: website wise product price
    #     :param pricelist_ids: product pricelist ids
    #     :return:
    #     """
    #     default_store_currency = website_product_price.get('default_store_currency')
    #     currency_obj = self.env['res.currency']
    #     currency_id = currency_obj.with_context(active_test=False). \
    #         search([('name', '=', default_store_currency)], limit=1)
    #     return pricelist_ids.filtered(lambda x: x.currency_id.id == currency_id.id)

    # def create_or_update_price(self, pricelist_id, product, price, pricelist_item):
    #     pricelist_item_obj = self.env['product.pricelist.item']
    #     if pricelist_item:
    #         pricelist_item.write({'fixed_price': price})
    #     else:
    #         pricelist_item_obj.create({
    #             'pricelist_id': pricelist_id,
    #             'applied_on': '0_product_variant',
    #             'product_id': product.odoo_product_id.id,
    #             'product_tmpl_id': product.odoo_product_id.product_tmpl_id.id,
    #             'compute_price': 'fixed',
    #             'min_quantity': 1,
    #             'fixed_price': price
    #         })

    # @staticmethod
    # def get_website_wise_product_price(web_id, item):
    #     """
    #     return product price per website
    #     :param web_id: magento website ID
    #     :param item: product data
    #     :return: product price
    #     """
    #     for website_product_price in item.get('extension_attributes').get('website_wise_product_price_data'):
    #         website_product_price = json.loads(website_product_price)
    #         if int(website_product_price.get('website_id')) == web_id:
    #             return website_product_price.get('product_price'), website_product_price.get('default_store_currency')
    #     return True

    # def update_magento_product(self, item, magento_websites, instance, magento_product):
    #     """
    #     magento product found, then prepare the new magento product vals and write it
    #     :param item: product item API response
    #     :param magento_websites: website data
    #     :param instance:  magento instance
    #     :param magento_product: magento product object
    #     :return:
    #     """
    #     values = self.prepare_magento_product_vals(item, magento_websites, instance.id)
    #     values.update({
    #         'magento_product_id': item.get('id'),
    #         'magento_tmpl_id': magento_product.magento_tmpl_id.id,
    #         'odoo_product_id': magento_product.odoo_product_id.id,
    #         'sync_product_with_magento': True
    #     })
    #     # Below code is for all the configurable's simple product is only simple product in odoo
    #     # not map all this odoo simple with configurable's simple product
    #     # and import configurable product, so set all the simple product's id and sync as true in magento.product.template
    #     magento_product_tmpl = self.env[MAGENTO_PRODUCT_TEMPLATE].search(
    #         [('magento_product_template_id', '=', False), ('sync_product_with_magento', '=', False),
    #          ('magento_sku', '=', magento_product.magento_sku)])
    #     if magento_product_tmpl:
    #         magento_product_tmpl.write({
    #             'magento_product_template_id': item.get('id'),
    #             'sync_product_with_magento': True
    #         })
    #     magento_product.write(values)

    # def map_odoo_product_with_magento_product(
    #         self, instance, magento_product, item, log_book_id, order_ref, queue_line, order_data_queue_line_id, error
    # ):
    #     """
    #     Map Odoo Product with existing Magneto Product in Layer
    #     :param instance: Magento Instance Object
    #     :param magento_product: Magento product product object
    #     :param item: Response received from Magento
    #     :param log_book_id: Common log book object
    #     :param order_ref: Order reference
    #     :param queue_line: product or order queue line
    #     :param order_data_queue_line_id: data queue line object
    #     :param error: True if error else False
    #     :return: Log book id, error
    #     """
    #     magento_sku = item.get('sku')
    #     odo_product = magento_product.odoo_product_id.filtered(lambda x: x.default_code == magento_sku)
    #     if not odo_product:
    #         odoo_product, error = self.create_odoo_product(
    #             magento_sku, item, instance, log_book_id,
    #             order_ref, queue_line, order_data_queue_line_id, error
    #         )
    #         if odoo_product:
    #             magento_product.write({'odoo_product_id': [(0, 0, [odoo_product])]})
    #     return error

    # def create_magento_product_template(self, odoo_product, instance_id, item, magento_websites,
    #                                     log_book_id, order_ref, queue_line, order_data_queue_line_id, error):
    #     """
    #     Create Magento Product Template if not found
    #     :param odoo_product: Product product object
    #     :param instance_id: Magento Instance OBJ
    #     :param item: Item received from Magento
    #     :param magento_websites: Magento Website Object
    #     :return: Magento Product Template Object
    #     """
    #     magento_prod_tmpl_obj = self.env[MAGENTO_PRODUCT_TEMPLATE]
    #     magento_prod_tmpl = magento_prod_tmpl_obj.search([
    #         ('odoo_product_template_id', '=', odoo_product.product_tmpl_id.id),
    #         ('magento_instance_id', '=', instance_id.id)
    #     ])
    #     if not magento_prod_tmpl:
    #         value = self.prepare_magento_product_vals(item, magento_websites, instance_id.id)
    #         value.update({
    #             'magento_product_template_id': item.get('id'),
    #             'odoo_product_template_id': odoo_product.product_tmpl_id.id,
    #             'sync_product_with_magento': True
    #         })
    #         magento_attribute_set = self.env['magento.attribute.set'].search(
    #             [('instance_id', '=', instance_id.id), ('attribute_set_id', '=', item.get('attribute_set_id'))])
    #         if magento_attribute_set:
    #             value.update({'attribute_set_id': magento_attribute_set.id})
    #         magento_tax_class = ''
    #         for attribute_code in item.get('custom_attributes'):
    #             if attribute_code.get('attribute_code') == 'tax_class_id':
    #                 magento_tax = self.env['magento.tax.class'].search([
    #                     ('magento_instance_id', '=', instance_id.id),
    #                     ('magento_tax_class_id', '=', attribute_code.get('value'))])
    #                 magento_tax_class = magento_tax.id
    #         if magento_tax_class:
    #             value.update({'magento_tax_class': magento_tax_class})
    #         magento_categories_dict = []
    #         if 'category_links' in item.get('extension_attributes'):
    #             for attribute_code in item.get('extension_attributes').get('category_links'):
    #                 magento_categories_dict.append(attribute_code.get('category_id'))
    #             if magento_categories_dict:
    #                 magento_categories = self.env['magento.product.category'].search([
    #                     ('instance_id', '=', instance_id.id),
    #                     ('category_id', 'in', magento_categories_dict)])
    #                 value.update({'category_ids': [(6, 0, magento_categories.ids)]})
    #         magento_prod_tmpl = magento_prod_tmpl_obj.create(value)
    #         if instance_id.allow_import_image_of_products and item.get('type_id') == "configurable":
    #             magento_media_url = False
    #             magento_stores = magento_websites.store_view_ids
    #             if magento_stores:
    #                 magento_media_url = magento_stores[0].base_media_url
    #             if magento_media_url:
    #                 full_img_url, error = magento_prod_tmpl_obj.create_or_update_product_images(
    #                     instance_id, False, magento_prod_tmpl,
    #                     magento_media_url, item.get('media_gallery_entries'),
    #                     log_book_id, order_ref, queue_line, order_data_queue_line_id, error
    #                 )
    #         self._cr.commit()
    #     return magento_prod_tmpl, error

    # def create_magento_product_product(self, odoo_product, instance, magento_websites, item, magento_prod_tmpl_id,
    #                                    log_book_id, order_ref, queue_line, order_data_queue_line_id, error):
    #     """
    #     Create Magento Product if not found
    #     :param odoo_product: Odoo Product Object
    #     :param instance: Magento Instance Object
    #     :param magento_websites: Magento Website Object
    #     :param item: Item received from Magento
    #     :param magento_prod_tmpl_id:  Magento Product Template Id
    #     :return:
    #     """
    #     magento_prod_tmpl_obj = self.env[MAGENTO_PRODUCT_TEMPLATE]
    #     magento_product = self.search([
    #         ('odoo_product_id', '=', odoo_product.id),
    #         ('magento_instance_id', '=', instance.id)])
    #     if not magento_product and odoo_product.default_code == item.get('sku'):
    #         values = self.prepare_magento_product_vals(item, magento_websites, instance.id)
    #         values.update({
    #             'magento_product_id': item.get('id'),
    #             'magento_tmpl_id': magento_prod_tmpl_id,
    #             'odoo_product_id': odoo_product.id,
    #             'sync_product_with_magento': True
    #         })
    #         magento_product = self.create(values)
    #         if instance.allow_import_image_of_products:
    #             magento_media_url = False
    #             magento_stores = magento_websites.store_view_ids
    #             if magento_stores:
    #                 magento_media_url = magento_stores[0].base_media_url
    #             if magento_media_url:
    #                 full_img_url, error = magento_prod_tmpl_obj.create_or_update_product_images(
    #                     instance, magento_product, False,
    #                     magento_media_url, item.get('media_gallery_entries'),
    #                     log_book_id, order_ref, queue_line, order_data_queue_line_id, error
    #                 )
    #         self._cr.commit()
    #     return magento_product, error

    # def prepare_magento_product_vals(self, item, magento_websites, instance_id):
    #     """
    #     Prepare vals for Magento product and template
    #     :param item: Item received from Magento
    #     :param magento_websites: Magento Website Object
    #     :param instance_id: Magento Instance Id
    #     :return: Return dictionary of values
    #     """
    #     ir_config_parameter_obj = self.env["ir.config_parameter"]
    #     description = short_description = ''
    #     for attribute_code in item.get('custom_attributes'):
    #         if attribute_code.get('attribute_code') == 'description':
    #             description = attribute_code.get('value')
    #         if attribute_code.get('attribute_code') == 'short_description':
    #             short_description = attribute_code.get('value')
    #     magento_product_vals = {
    #         'magento_product_name': item.get('name'),
    #         'magento_instance_id': instance_id,
    #         'magento_website_ids': [(6, 0, magento_websites.ids)],
    #         'magento_sku': item.get('sku'),
    #         'product_type': item.get('type_id'),
    #         'created_at': item.get('created_at'),
    #         'updated_at': item.get('updated_at'),
    #     }
    #     if ir_config_parameter_obj.sudo().get_param("odoo_magento2_ept.set_magento_sales_description"):
    #         magento_product_vals.update({
    #             'description': description,
    #             'short_description': short_description,
    #         })
    #     return magento_product_vals

    # def create_odoo_product(
    #         self, magento_sku, prod, instance, log_book_id,
    #         order_ref, queue_line, order_data_queue_line_id, error
    # ):
    #     """
    #     Checks and create product in Odoo.
    #     :param magento_sku: Magento Product SKU
    #     :param prod: Product items received from Magento
    #     :param instance: Magento Instance Object
    #     :param log_book_id: Common log book object
    #     :param order_ref: order reference
    #     :param queue_line: product or order queue line
    #     :param order_data_queue_line_id: queue line object
    #     :param error: True if error else False
    #     :return: Product Product Object
    #     """
    #     ir_config_parameter_obj = self.env["ir.config_parameter"]
    #     auto_create_product = instance.auto_create_product
    #     product_product_obj = self.env[PRODUCT_PRODUCT]
    #     magento_product_template_obj = self.env[MAGENTO_PRODUCT_TEMPLATE]
    #     odoo_product = product_product_obj.search([('default_code', '=', magento_sku)], limit=1)
    #     if not odoo_product and auto_create_product:
    #         magento_websites, description, short_description = magento_product_template_obj.get_magento_websites_and_descriptions(
    #             instance.id, prod)
    #         vals = {
    #             'name': prod.get('name'),
    #             'default_code': magento_sku,
    #             'type': 'product',
    #             'purchase_ok': True,
    #             'sale_ok': True,
    #             'invoice_policy': 'order'
    #         }
    #         if ir_config_parameter_obj.sudo().get_param("odoo_magento2_ept.set_magento_sales_description"):
    #             vals.update({
    #                 'description': short_description,
    #                 'description_sale': description,
    #             })
    #         odoo_product = product_product_obj.create(vals)
    #     elif not odoo_product and not auto_create_product:
    #         # Product not found in odoo layer
    #         # Auto create setting is off for this instance
    #         message = 'Odoo Product Not found for SKU : %s' \
    #                   '\nAnd your "Automatically Create Odoo Product If Not Found" ' \
    #                   'setting is %s'\
    #                   % (magento_sku, auto_create_product)
    #         log_book_id.add_log_line(message, order_ref, order_data_queue_line_id, queue_line, magento_sku)
    #         error = True
    #     return odoo_product, error

    # def get_magento_product_by_sku(self, magento_instance, prod_response, queue_line, error,
    #                                log_book_id, order_data_queue_line_id):
    #     """
    #     This method is used to call API for getting product data from magento.
    #     :param magento_instance: Instance of Magento
    #     :param prod_response: Dictionary of product sku get from magento
    #     :param queue_line: Sync import magento product queue line object
    #     :param error: True if any error else False
    #     :param log_book_id: common log book object
    #     :param order_data_queue_line_id: Sync import magento product queue line id
    #     :return:
    #     """
    #     final_prod_res = {}
    #     result_list = []
    #     for prod_res in prod_response:
    #         try:
    #             sku = Php.quote_sku(prod_res.get('sku'))
    #             api_url = '/V1/products/%s' % format(sku)
    #             response = req(magento_instance, api_url)
    #             result_list.append(response)
    #         except Exception:
    #             if log_book_id:
    #                 # Before process queue, delete some configurable's simple product.
    #                 # So mark that queue as Failed state and add log line
    #                 message = 'Magento Product not found with SKU %s' % prod_res.get('sku')
    #                 log_book_id.add_log_line(message, False,
    #                                          order_data_queue_line_id,
    #                                          queue_line,
    #                                          prod_res.get('sku'))
    #                 error = True
    #     final_prod_res.update({'items': result_list})
    #     return final_prod_res, error

    # def create_or_update_product_in_magento(
    #         self, order_responses, magento_instance, magento_per_sku, order_ref, order_data_queue_line_id, log_book_id
    # ):
    #     """
    #     Create or update product when import orders from Magento.
    #     :param order_responses: Order Response received from Magento
    #     :param magento_instance: Instance of Magento
    #     :param magento_per_sku: Dictionary of Magento Product
    #     :param order_ref: Order reference
    #     :param order_data_queue_line_id: Order data queue line id
    #     :return: common log book object and skip order
    #     """
    #     skip_order = False
    #     for order_response in order_responses:
    #
    #         # Check the ordered product is already exist in the magento product product layer or not.
    #         # If product is already exist then no need to again send the API call.
    #         # Used existing product.
    #         magento_product_obj = self.search(
    #             [('magento_instance_id', '=', magento_instance.id), '|',
    #              ('magento_product_id', '=', order_response.get('product_id')),
    #              ('magento_sku', '=', order_response.get('sku'))],
    #             limit=1)
    #         product_obj = self.env[PRODUCT_PRODUCT].search([('default_code', '=', order_response.get('sku'))])
    #         if not magento_product_obj and not product_obj:
    #             if order_response.get('product_type') not in ['simple', 'configurable']:
    #                 skip_order = True
    #                 message = "Order %s skipped due to %s product type is not supported" % (
    #                     order_ref, order_response.get('product_type'))
    #                 log_book_id.add_log_line(message, order_ref,
    #                                          order_data_queue_line_id, "magento_order_data_queue_line_id",
    #                                          order_response.get('sku'))
    #                 break
    #             try:
    #                 # every time send the product API call by using product id.
    #                 # To stop the product API call by using SKU because at that time
    #                 # wrong product id set in the magento product template and also
    #                 # create only single simple product which was ordered (Configurable product)
    #                 # Using this code if only single simple product ordered then also if main
    #                 # configurable product not found then create that main configurable product with all the variants.
    #                 product_filter = {'entity_id': order_response.get('product_id')}
    #                 search_criteria = create_search_criteria(product_filter)
    #                 query_string = Php.http_build_query(search_criteria)
    #                 api_url = '/V1/products?%s' % query_string
    #                 response = req(magento_instance, api_url).get('items')[0]
    #             except Exception:
    #                 #Add below code for while order processing and product
    #                 # not found for the particular queue line then add log line and skip that queue line.
    #                 skip_order = True
    #                 message = _("Error While Requesting Product SKU %s") % order_response.get('sku')
    #                 log_book_id.add_log_line(message, order_ref,
    #                                          order_data_queue_line_id, "magento_order_data_queue_line_id",
    #                                          order_response.get('sku'))
    #                 continue
    #             magento_sku = response.get('sku')
    #             skip_order = self.create_or_update_magento_product(
    #                 order_response, response, magento_sku, magento_instance, log_book_id,
    #                 skip_order, magento_per_sku, order_data_queue_line_id, order_ref)
    #     return skip_order

    # def create_or_update_magento_product(
    #         self, order_response, response, magento_sku, magento_instance, log_book_id,
    #         skip_order, magento_per_sku, order_data_queue_line_id, order_ref):
    #     magento_product_template_obj = self.env[MAGENTO_PRODUCT_TEMPLATE]
    #     if not magento_per_sku or (
    #             magento_per_sku and (magento_instance.id not in magento_per_sku.keys() or (
    #             magento_instance.id in magento_per_sku.keys() and
    #             magento_sku not in magento_per_sku[magento_instance.id].keys()))):
    #         # Check product is simple type then sku of the order
    #         # response and magento sku both are same.
    #         # If ordered product is simple product and also have custom option.
    #         # Then Ordered product sku and magento sku not same.
    #         # So in that case need to check ordered product id and response product ID.
    #         if order_response.get('product_type') == 'simple' and (
    #                 order_response.get('product_id') == response.get('id')
    #                 or order_response.get('sku') == magento_sku):
    #             # Simple Product Process
    #             skip_order = self.create_or_update_simple_product(response,
    #                                                               magento_instance,
    #                                                               log_book_id,
    #                                                               skip_order,
    #                                                               magento_per_sku,
    #                                                               order_data_queue_line_id,
    #                                                               order_ref)
    #         # Check product type is configurable then in the ordered response we get simple product SKU and
    #         # in the magento SKU we get main Configurable product sku. So Both are not same.
    #         elif order_response.get('product_type') == 'configurable' \
    #                 and order_response.get('sku') != magento_sku:
    #             # Configurable Product Process
    #             skip_order = magento_product_template_obj.create_or_update_configurable_product(
    #                 response, magento_instance, log_book_id, skip_order,
    #                 magento_per_sku, order_data_queue_line_id, order_ref)
    #     return skip_order

    # def create_product_inventory(self, instance):
    #     """
    #     This method is used to import product stock from magento,
    #     when Multi inventory sources is not available.
    #     It will create a product inventory.
    #     :param instance: Instance of Magento
    #     :return: True
    #     """
    #     stock_to_import = []
    #     stock_inventory = self.env[STOCK_INVENTORY]
    #     log_book_id = False
    #     if instance.is_import_product_stock:
    #         import_stock_location = instance.import_stock_warehouse
    #         location = import_stock_location and import_stock_location.lot_stock_id
    #         if location:
    #             model_id = self.env[COMMON_LOG_LINES_EPT].get_model_id(STOCK_INVENTORY)
    #             log_book_id = self.env["common.log.book.ept"].create({
    #                 'type': 'import',
    #                 'module': 'magento_ept',
    #                 'model_id': model_id,
    #                 'magento_instance_id': instance.id
    #             })
    #             stock_to_import = self.get_product_stock(stock_to_import, instance, location, log_book_id)
    #             if stock_to_import:
    #                 stock_inventory.create_stock_inventory_ept(stock_to_import, location, True)
    #             if not log_book_id.log_lines:
    #                 log_book_id.sudo().unlink()
    #                 log_book_id = False
    #         else:
    #             raise UserError(_("Please Choose Import product stock for %s location", import_stock_location.name))
    #     return log_book_id

    # def get_product_stock(self, stock_to_import, instance, location, log_book_id):
    #     """
    #     Call stockItems API call and make dictionary
    #     :param stock_to_import: dictionary for import stock
    #     :param instance: Magento Instance object
    #     :param location: stock warehouse object
    #     :param log_book_id: common log book object
    #     :return: dictionary for import stock
    #     """
    #     consumable_products = []
    #     response = {}
    #     try:
    #         api_url = '/V1/stockItems/lowStock?scopeId=0&qty=10000000000&pageSize=100000'
    #         response = req(instance, api_url)
    #     except Exception:
    #         log_book_id.write({
    #             'log_lines': [(0, 0, {
    #                 'message': "Request is not satisfied please check API connection"
    #             })]
    #         })
    #
    #     if response.get('items'):
    #         for inventory in response.get('items'):
    #             magento_prod = self.search([
    #                 ('magento_product_id', '=', inventory.get('product_id')),
    #                 ('magento_instance_id', '=', instance.id),
    #                 ('magento_website_ids', '!=', False)
    #             ], limit=1)
    #             qty = inventory.get('qty')
    #             if magento_prod and qty > 0.0:
    #                 if magento_prod.odoo_product_id.type != 'product':
    #                     consumable_products.append(magento_prod.odoo_product_id.default_code)
    #                 else:
    #                     stock_to_import.append({
    #                         'product_id': magento_prod.odoo_product_id,
    #                         'product_qty': qty,
    #                         'location_id': location
    #                     })
    #         self.create_import_product_process_log(consumable_products, log_book_id)
    #     return stock_to_import

    # def create_product_multi_inventory(self, instance, magento_locations):
    #     """
    #     This method is used to import product stock from magento,
    #     when Multi inventory sources is available.
    #     It will create a product inventory.
    #     :param instance: Instance of Magento
    #     :param magento_locations: Magento products object
    #     :return: True
    #     """
    #     stock_inventory = self.env[STOCK_INVENTORY]
    #     if instance.is_import_product_stock:
    #         consumable_products = []
    #         model_id = self.env[COMMON_LOG_LINES_EPT].get_model_id(STOCK_INVENTORY)
    #         log_book_id = self.env["common.log.book.ept"].create({
    #             'type': 'import',
    #             'module': 'magento_ept',
    #             'model_id': model_id,
    #             'magento_instance_id': instance.id
    #         })
    #         for magento_location in magento_locations:
    #             stock_to_import = []
    #             location = magento_location.import_stock_warehouse and magento_location.import_stock_warehouse.lot_stock_id
    #             if location:
    #                 search_criteria = create_search_criteria({'source_code': magento_location.magento_location_code})
    #                 query_string = Php.http_build_query(search_criteria)
    #                 response = {}
    #                 try:
    #                     api_url = '/V1/inventory/source-items?%s' % query_string
    #                     response = req(instance, api_url)
    #                 except Exception as error:
    #                     log_book_id.write({
    #                         'log_lines': [(0, 0, {
    #                             'message': _("Error while requesting products" + str(error))
    #                         })]
    #                     })
    #                 stock_to_import, consumable_products = self.prepare_import_product_stock_dictionary(
    #                     response, instance, consumable_products, stock_to_import, location)
    #                 stock_inventory.create_stock_inventory_ept(stock_to_import, location, True)
    #             else:
    #                 raise UserError(_("Please Choose Import product stock location for %s") % magento_location.name)
    #         self.create_import_product_process_log(consumable_products, log_book_id)
    #     return True

    # def prepare_import_product_stock_dictionary(
    #         self, response, instance, consumable_products, stock_to_import, location):
    #     """
    #     Prepare dictionary for import product stock from response.
    #     :param response: response received from Magento
    #     :param instance: Magento Instance object
    #     :param consumable_products: Dictionary of consumable products
    #     :param stock_to_import: Dictionary for import product stock
    #     :param location: warehouse in which stock will be imported
    #     :return: stock_to_import, consumable_products
    #     """
    #     if response and response.get('items'):
    #         for inventory in response.get('items'):
    #             magento_prod = self.search([
    #                 ('magento_sku', '=', inventory.get('sku')), ('magento_instance_id', '=', instance.id),
    #                 ('magento_website_ids', '!=', False)
    #             ], limit=1)
    #             if magento_prod:
    #                 stock_to_import, consumable_products = self.prepare_import_stock_dict(
    #                     inventory, magento_prod, consumable_products, stock_to_import, location)
    #     return stock_to_import, consumable_products

    # @staticmethod
    # def prepare_import_stock_dict(inventory, magento_prod, consumable_products, stock_to_import, location):
    #     """
    #     Prepare import stock dictionary
    #     :param inventory: response received from Magento
    #     :param magento_prod: Magento product product object
    #     :param consumable_products: Dictionary of consumable products
    #     :param stock_to_import: Dictionary for import product stock
    #     :param location: warehouse in which stock will be imported
    #     :return: stock_to_import, consumable_products
    #     """
    #     qty = inventory.get('quantity') or False
    #     if qty and qty > 0.0:
    #         if magento_prod.odoo_product_id.type != 'product':
    #             consumable_products.append(magento_prod.odoo_product_id.default_code)
    #         else:
    #             stock_to_import.append({
    #                 'product_id': magento_prod.odoo_product_id,
    #                 'product_qty': qty,
    #                 'location_id': location
    #             })
    #     return stock_to_import, consumable_products

    # @staticmethod
    # def create_import_product_process_log(consumable_products, log_book_id):
    #     """
    #     Generate process log for import product stock with consumable product.
    #     :param consumable_products: dictionary of consumable products
    #     :param log_book_id: common log book object
    #     """
    #     if consumable_products:
    #         message = "The following products have not been imported due to " \
    #                   "product type is other than 'Storable.'\n %s" % str(list(set(consumable_products)))
    #         log_book_id.write({
    #             'log_lines': [(0, 0, {
    #                 'message': message
    #             })]
    #         })

    # @staticmethod
    # def create_export_product_process_log(consumable_products, log_book_id):
    #     """
    #     Generate process log for export product stock with consumable product.
    #     :param consumable_products: dictionary of consumable products
    #     :param log_book_id: common log book object
    #     """
    #     if consumable_products:
    #         message = "The following products have not been exported due to " \
    #                   "product type is other than 'Storable.'\n %s" % str(list(set(consumable_products)))
    #         log_book_id.write({
    #             'log_lines': [(0, 0, {
    #                 'message': message
    #             })]
    #         })

    def export_products_stock_to_magento(self, instance):
        """
        This method is used to export multiple product stock from odoo to magento
        :param instance: Instance of Magento
        :return:
        """
        stock_data = []
        # consumable_products = []
        # model_id = self.env[COMMON_LOG_LINES_EPT].get_model_id(MAGENTO_PRODUCT_PRODUCT)
        # job = self.env['common.log.book.ept'].create({
        #     'name': 'Export Product Stock', 'type': 'export', 'module': 'magento_ept',
        #     'model_id': model_id, 'res_id': self.id, 'magento_instance_id': instance.id})
        # export_product_stock = self.get_export_product_stock(instance, instance.warehouse_ids)
        export_product_stock = self.get_export_product_stock(instance, instance.location_ids)
        if export_product_stock:
            for product_id, stock in export_product_stock.items():
                exp_product = self.search([('odoo_product_id', '=', product_id),
                                           ('magento_instance_id', '=', instance.id)], limit=1)
                if exp_product and stock >= 0.0:
                    if exp_product.odoo_product_id.type == 'product':
                    #     consumable_products.append(exp_product.odoo_product_id.default_code)
                    # else:
                        product_stock_dict = {'sku': exp_product.magento_sku, 'qty': stock, 'is_in_stock': 1}
                        stock_data.append(product_stock_dict)
        # self.create_export_product_process_log(consumable_products, '')
        if stock_data:
            data = {'skuData': stock_data}
            api_url = "/V1/product/updatestock"
            self.call_export_product_stock_api(instance, api_url, data, 'PUT')

    def export_product_stock_to_multiple_locations(self, instance, magento_locations):
        """
        This method is used to export product stock to magento, when Multi inventory sources is available.
        It will create a product inventory
        :param instance: Instance of Magento
        :param magento_locations: Magento products object
        :return: True
        """
        stock_data = []
        # consumable_products = []
        # model_id = self.env[COMMON_LOG_LINES_EPT].get_model_id(MAGENTO_PRODUCT_PRODUCT)
        # job = self.env['common.log.book.ept'].create({
        #     'name': 'Export Product Stock', 'type': 'export', 'module': 'magento_ept',
        #     'model_id': model_id, 'res_id': self.id, 'magento_instance_id': instance.id})
        for magento_location in magento_locations:
            export_stock_locations = magento_location.mapped('export_stock_warehouse_ids')
            if export_stock_locations and export_stock_locations.ids:
                export_product_stock = self.get_export_product_stock(instance, export_stock_locations)
                if export_product_stock:
                    for product_id, stock in export_product_stock.items():
                        stock_data = self.prepare_export_product_stock_dict(
                            product_id, instance, stock, stock_data, magento_location)
            else:
                raise UserError(_("Please Choose Export product stock location for %s", magento_location.name))
        # self.create_export_product_process_log(consumable_products, '')
        if stock_data:
            data = {'sourceItems': stock_data}
            api_url = "/V1/inventory/source-items"
            self.call_export_product_stock_api(instance, api_url, data, 'POST')

    def prepare_export_product_stock_dict(self, product_id, instance, stock, stock_data, magento_location):
        """
        Prepare Export Product Stock Dictionary
        :param product_id: Odoo product id
        :param instance: Magneto instance
        :param stock: stock of product
        :param stock_data: dictionary for export product stock
        :param magento_location: magento inventory location object
        :return: dictionary for export product stock
        """
        exp_product = self.search([
            ('odoo_product_id', '=', product_id), ('magento_instance_id', '=', instance.id)
        ], limit=1)
        if exp_product and stock >= 0.0:
            if exp_product.odoo_product_id.type == 'product':
            #     consumable_products.append(exp_product.odoo_product_id.default_code)
            # else:
                stock_data.append({
                    'sku': exp_product.magento_sku,
                    'source_code': magento_location.magento_location_code,
                    'quantity': stock,
                    'status': 1
                })
        return stock_data

    def get_export_product_stock(self, instance, export_stock_locations):
        """
        Get export product stock dictionary with stock
        :param instance: Magento instance object
        :param export_stock_locations: Stock location object
        :return: Export product stock dictionary.
        """
        product_product_obj = self.env[PRODUCT_PRODUCT]
        instance_export_date = instance.last_update_stock_time
        if not instance_export_date:
            instance_export_date = datetime.today() - timedelta(days=365)
        product_ids = product_product_obj.get_products_based_on_movement_date(instance_export_date,
                                                                              instance.company_id)
        export_product_stock = self.get_magento_product_stock(instance, product_ids, product_product_obj,
                                                              export_stock_locations)
        return export_product_stock

    # @staticmethod
    def call_export_product_stock_api(self, instance, api_url, data, method_type):
        """
        Call export product stock API for single or multi tracking inventory
        :param instance: Magento instance object
        :param api_url: API Call URL
        :param data: Dictionary to be passed
        :param method_type: Api Request Method type (PUT/POST)
        :return: common log book object
        """
        try:
            responses = req(instance, api_url, method_type, data)
        except Exception as error:
            raise UserError(_("Error while Export product stock " + str(error)))
        print(responses)
        if responses:
            stock_log_book = self.env['magento.stock.log.book'].search([('magento_instance_id', '=', instance.id)])
            # archive all previous records
            # if stock_log_book:
            #     stock_log_book.write({'active': False})

            for response in responses:
                if isinstance(response, dict):
                    message = response.get('message')
                else:
                    message = responses.get(response)
                # log error
                if response.get('code', False) != '200':
                    stock_log_book.create({'magento_instance_id': instance.id, 'log_message': message})

    @staticmethod
    def get_magento_product_stock(instance, product_ids, prod_obj, locations):
        """
        This Method relocates check type of stock
        :param instance: This arguments relocates instance of magento
        :param product_ids: This arguments product listing id of odoo
        :param prod_obj: This argument relocates product object of common connector
        :param locations:This arguments relocates warehouse of magento
        :return: This Method return product listing stock
        """
        product_listing_stock = False
        if product_ids:
            if instance.magento_stock_field == 'free_qty':
                product_listing_stock = prod_obj.get_free_qty(locations, product_ids)
            elif instance.magento_stock_field == 'virtual_available':
                product_listing_stock = prod_obj.get_forecasted_qty(locations, product_ids)
        return product_listing_stock

    # added by SPf
    def process_products_export_to_magento(self, single=0, status_check=False):
        """
        The main method to process Products Export to Magento. The Product's Public Categories are treated as
        Configurable Products and regular Odoo Products as Simple Products in Magento.
        :param single: Odoo product Id in case of direct export from Odoo to Magento2 (omitting RabbitMQ) or 0
        :param status_check: Check(Update) Product(s) Export Status only, won't export Products
        :return: None
        """
        active_product_ids = single if single else self._context.get("active_ids", [])
        export_products = self.env["magento.product.product"].browse(active_product_ids)

        # create dict with "config_product_name: (attr_set, [related_simple_product_ids], {product_config_attributes})"
        # for each magento instance to process export by product categories and specified quantity (threshold)
        products_dict = {d.magento_instance_id: {} for d in export_products}
        for mi in products_dict:
            products = export_products.filtered(lambda p: p.magento_instance_id.id == mi.id and p.active)
            products_dict[mi].update({
                c.magento_conf_prod_sku: (
                    c.magento_conf_product.magento_attr_set,
                    products.filtered(lambda s: s.magento_conf_prod_sku == c.magento_conf_prod_sku).mapped('id'),
                    [a.name for a in c.magento_conf_product.mag_assign_attributes]
                ) for c in products if c.magento_conf_prod_sku and c.magento_conf_product.odoo_prod_category
            })
        del export_products

        for mi in products_dict:
            # create Attribute-sets dict which contains id/attribute(options) info received from Magento
            prod_attibute_sets = {products_dict[mi][a][0] for a in products_dict[mi] if products_dict[mi][a][0]}
            attr_sets = self.create_attribute_sets_dict(mi, prod_attibute_sets)

            # check if config.product's attributes passed the rules
            conf_attributes = []
            for prod in products_dict[mi]:
                [conf_attributes.append(a) for a in products_dict[mi][prod][2]]
            conf_attributes = dict.fromkeys(conf_attributes, 0)
            self.check_configurable_attributes(mi, conf_attributes, attr_sets)

            # proceed with products export
            selection = []
            conf_products_list = list(products_dict[mi].keys())
            for conf_prod in conf_products_list:
                selection += products_dict[mi][conf_prod][1]
                if conf_prod != conf_products_list[-1] and len(selection) < PRODUCTS_THRESHOLD:
                    continue
                else:
                    # export_products = self.env["magento.product.product"].browse(selection)
                    export_products = self.browse(selection)
                    selection = []
                    # create dictionaries which collect meta-data for selected configurable and simple products
                    ml_conf_products_dict, ml_simp_products_dict = self.create_products_metadata_dict(
                        export_products, single, status_check
                    )
                    # get selected products from Magento(if any) and update meta-dict with Magento data
                    magento_conf_products = self.get_products_from_magento(mi, ml_conf_products_dict)
                    for prod in magento_conf_products:
                        self.update_conf_product_dict_with_magento_data(prod, ml_conf_products_dict)
                    del magento_conf_products
                    magento_simp_products = self.get_products_from_magento(mi, ml_simp_products_dict)
                    for prod in magento_simp_products:
                        self.update_simp_product_dict_with_magento_data(prod, ml_simp_products_dict)
                    del magento_simp_products

                    # check product's export statuses to define which product(s) need to be created/updated in Magento
                    self.check_config_products_to_export(ml_conf_products_dict, attr_sets)
                    self.check_simple_products_to_export(export_products, ml_simp_products_dict, ml_conf_products_dict)
                    if status_check:
                        self.save_magento_products_info_to_database(mi.magento_website_ids, ml_simp_products_dict,
                                                                    ml_conf_products_dict, export_products, True)
                    else:
                        # check if product attributes of all selected Configurable Products exist in Magento
                        # and create new attribute options(swatch) if needed
                        self.check_conf_product_attributes_and_options_exist_in_magento(ml_conf_products_dict,
                                                                                        attr_sets)
                        self.process_config_products_create_or_update(mi, ml_conf_products_dict, attr_sets, single)

                        # filter selected Odoo Product Variants to be exported to Magento
                        odoo_simp_prod = export_products.filtered(
                            lambda prd: prd.magento_sku in ml_simp_products_dict and
                                        ml_simp_products_dict[prd.magento_sku]['to_export'] is True and
                                        not ml_simp_products_dict[prd.magento_sku]['log_message']
                        )
                        # check if product attributes of all selected Simple Products exist in Magento
                        # log error when product has no attributes and create new attribute options(swatch) if needed
                        self.check_simp_product_attributes_and_options_exist_in_magento(mi, odoo_simp_prod, attr_sets,
                                                                                        ml_simp_products_dict)
                        self.check_simple_products_for_errors_before_export(odoo_simp_prod, ml_simp_products_dict,
                                                                            ml_conf_products_dict, attr_sets)
                        # process simple products update in Magento
                        products_to_update = []
                        for s in odoo_simp_prod:
                            if ml_simp_products_dict[s.magento_sku].get('magento_update_date', '') and \
                                    not ml_simp_products_dict[s.magento_sku]['log_message']:
                                products_to_update.append(s.magento_sku)
                        self.process_simple_products_create_or_update(
                            mi, products_to_update, odoo_simp_prod, ml_simp_products_dict, attr_sets,
                            ml_conf_products_dict, single, 'PUT'
                        )
                        # process new simple products creation in Magento, assign attributes to config.products and link them
                        products_to_create = []
                        for s in odoo_simp_prod:
                            if not ml_simp_products_dict[s.magento_sku].get('magento_update_date') and \
                                    not ml_simp_products_dict[s.magento_sku]['log_message']:
                                products_to_create.append(s.magento_sku)
                        self.process_simple_products_create_or_update(
                            mi, products_to_create, odoo_simp_prod, ml_simp_products_dict, attr_sets,
                            ml_conf_products_dict, single, 'POST'
                        )
                        # save data of export dates, magento statuses and log_messages to Db
                        self.save_magento_products_info_to_database(mi.magento_website_ids, ml_simp_products_dict,
                                                                    ml_conf_products_dict, export_products, False)

    def create_attribute_sets_dict(self, magento_instance, attribute_sets):
        """
        Create Attribute-Sets dictionary for selected Products with Attribute ID and Attributes available in Magento
        :param magento_instance: Magento Instance
        :param attribute_sets: Python set of Product's 'Attribute-sets' defined in Product Categories
        :return: Attribute sets dictionary
        """
        # create dict with Attribute-set(s) defined in Odoo's Product Categories (by default - 'Default' only)
        attr_sets = {}.fromkeys(attribute_sets, {})

        for a_set in attr_sets:
            attr_sets[a_set].update({
                'id': self.get_attribute_set_id_by_name(magento_instance, a_set)
            })
            attr_sets[a_set].update({
                'attributes': self.get_available_attributes_from_magento(magento_instance, a_set, attr_sets)
            })
        return attr_sets

    def get_attribute_set_id_by_name(self, magento_instance, attribute_set_name, magento_entity_id=4):
        """
        Get Attribute ID from Magento by name defined in Odoo
        :param magento_instance: Instance of Magento
        :param attribute_set_name: Attribute-Set Name defined in Odoo Product's Category
        :param magento_entity_id: Entity Id defined in Magento - Default is 4
        :return: ID of Attribute Set assigned in Magento
        """
        filters = {
            'attribute_set_name': attribute_set_name,
            'entity_type_id': magento_entity_id
        }
        search_criteria = create_search_criteria(filters)
        query_string = Php.http_build_query(search_criteria)
        api_url = '/V1/eav/attribute-sets/list?%s' % query_string
        try:
            response = req(magento_instance, api_url)
        except Exception:
            response = {}

        if response.get('items'):
            return response.get('items')[0].get('attribute_set_id')
        return False

    def get_available_attributes_from_magento(self, magento_instance, attribute_set_name, attr_sets):
        """
        Get available attributes and related options(swatches) from Magento
        :param magento_instance: Instance of Magento
        :param attribute_set_name: Attribute Set Name defined in Odoo Product's Category
        :param attr_sets: Attribute-Set dictionary with unique data for selected products
        :return: Available in Magento Attributes list and their options
        """
        attribute_set_id = attr_sets[attribute_set_name]['id']
        if attribute_set_id:
            available_attributes = []
            try:
                api_url = '/all/V1/products/attribute-sets/%s/attributes' % attribute_set_id
                response = req(magento_instance, api_url)
            except Exception:
                response = []

            # generate the list of available attributes and their options from Magento
            if response:
                for attr in response:
                    if attr.get('default_frontend_label'):
                        available_attributes.append({
                            "attribute_id": attr.get("attribute_id"),
                            "attribute_code": attr.get('attribute_code'),
                            'default_label': self.to_upper(attr.get('default_frontend_label')),
                            'options': attr.get('options'),
                            'can_be_configurable': True if attr.get('is_user_defined') else False
                        })
                return available_attributes
        return []

    def check_configurable_attributes(self, magento_instance, conf_attributes, attr_sets):

        avail_attributes = []
        for at_set in attr_sets:
            avail_attributes += attr_sets[at_set]['attributes']

        # find attribute_id in Magento available attributes (if not found = 0)
        conf_attributes = {k: self.get_attribute_id_by_name(avail_attributes, k) for k, v in conf_attributes.items()}

        # request each config.attribute from Magento separately
        for _id in conf_attributes.values():
            if _id:
                api_url = '/all/V1/products/attributes/%s' % _id
                try:
                    response = req(magento_instance, api_url)
                except Exception:
                    response = {}

                # check attribute scope (must be global)
                if response.get("scope") and response.get("scope") != 'global':
                    for at_set in attr_sets:
                        attr = next((a for a in attr_sets[at_set]['attributes'] if str(a['attribute_id']) == str(_id)), {})
                        attr['can_be_configurable'] = False

    def get_attribute_id_by_name(self, available_attributes, odoo_attribute):
        attr = next((a for a in available_attributes if self.to_upper(odoo_attribute) == a['default_label']), {})
        if attr:
            return attr.get('attribute_id')
        else:
            return 0

    def create_products_metadata_dict(self, export_products, single, status_check):
        """
        Create dictionary which contains metadata for selected Configurable(Odoo categories) and Simple Products
        :param export_products: Magento Layer's Odoo Product(s) to be exported
        :param single: In case of direct (Odoo-Magento) single product export - True, else - False
        :param status_check: If method runs in "check_status' mode
        :return: Configurable and Simple products dictionary
        """
        products_dict_conf = {
            c.magento_conf_prod_sku: {
                'conf_object': c.magento_conf_product,
                'config_attr': {a.name for a in c.magento_conf_product.odoo_prod_category.x_magento_attr_ids},
                'children': [],
                'magento_status': c.magento_conf_product.magento_status,
                'log_message': '',
                'force_update': c.magento_conf_product.force_update,
                'export_date_to_magento': c.magento_conf_product.magento_export_date,
                'to_export': False if c.magento_conf_product.odoo_prod_category.x_magento_no_create else True
            } for c in export_products
        }

        text = "Product Category is missing 'Magento Product SKU' field. \n"
        if single and not status_check and export_products.magento_status == 'deleted':
            export_products.write({'magento_status': 'not_exported'})
        products_dict_simp = {
            s.magento_sku: {
                'conf_sku': s.magento_conf_prod_sku,
                'log_message': '' if s.magento_conf_prod_sku else text,
                'export_date_to_magento': s.magento_export_date,
                # 'latest_update_date': max(s.odoo_product_id.write_date, s.odoo_product_id.product_tmpl_id.write_date, s.update_date),
                'latest_update_date': max(s.odoo_product_id.write_date, s.odoo_product_id.product_tmpl_id.write_date),
                'conf_attributes': self.get_product_conf_attributes_dict(s),
                'magento_status': s.magento_status,
                'do_not_export_conf': s.magento_conf_product.odoo_prod_category.x_magento_no_create,
                'product_categ': [],
                'force_update': s.force_update,
                'to_export': True
            } for s in export_products if s.magento_status != 'deleted'
        }

        return products_dict_conf, products_dict_simp

    def update_conf_product_dict_with_magento_data(self, magento_prod, ml_conf_products_dict):
        """
        Update Conf.Products 'Meta-dictionary' with data from Magento
        :param magento_prod: Product dict received from Magento
        :param ml_conf_products_dict: Dictionary contains metadata for selected Configurable Products (Odoo categories)
        :return: None
        """
        attr_opt = magento_prod.get("extension_attributes").get("configurable_product_options")
        children = magento_prod.get("extension_attributes").get("configurable_product_links")
        link_data = magento_prod.get("extension_attributes").get("configurable_product_link_data")
        website_ids = magento_prod.get("extension_attributes").get("website_ids")
        category_links = magento_prod.get("extension_attributes").get("category_links", [])
        ml_conf_products_dict[magento_prod.get('sku')].update({
            'magento_type_id': magento_prod.get('type_id'),
            'magento_prod_id': magento_prod.get("id"),
            'magento_attr_set_id': magento_prod.get("attribute_set_id"),
            'magento_conf_prod_options': attr_opt,
            'children': children,
            'magento_website_ids': website_ids,
            'category_links': [cat['category_id'] for cat in category_links],
            'magento_configurable_product_link_data': self.convert_to_dict(link_data),
            'media_gallery': [i['id'] for i in magento_prod.get("media_gallery_entries", []) if i],
            'magento_update_date': magento_prod.get("updated_at")
        })

    def update_simp_product_dict_with_magento_data(self, magento_prod, ml_simp_products_dict):
        """
        Update Simple Products 'Meta-dictionary' with data from Magento
        :param magento_prod: Product dict received from Magento
        :param ml_simp_products_dict: Dictionary contains metadata for selected Simple Products (Odoo products)
        :return: None
        """
        website_ids = magento_prod.get("extension_attributes").get("website_ids")
        category_links = magento_prod.get("extension_attributes").get("category_links", [])
        ml_simp_products_dict[magento_prod.get("sku")].update({
            'magento_type_id': magento_prod.get('type_id'),
            'magento_prod_id': magento_prod.get("id"),
            'magento_update_date': magento_prod.get("updated_at"),
            'magento_website_ids': website_ids,
            'category_links': [cat['category_id'] for cat in category_links],
            'media_gallery': [i['id'] for i in magento_prod.get("media_gallery_entries", []) if i]
        })

    def check_config_products_to_export(self, ml_conf_products, attr_sets):
        """
        Check if Configurable Product Export to Magento needed
        :param ml_conf_products: Dictionary contains metadata for selected Configurable Products (Odoo categories)
        :param attr_sets: Attribute-Set dictionary with available in Magento Attributes info for selected products
        :return: None
        """
        for prod in ml_conf_products:
            if ml_conf_products[prod]['log_message']:
                ml_conf_products[prod]['to_export'] = False
                continue
            conf_obj = ml_conf_products[prod]['conf_object']
            mag_attr_set = conf_obj.magento_attr_set

            if not mag_attr_set:
                text = "Missed 'Magento Product Attribute Set' field in Product Category. \n"
                ml_conf_products[prod]['log_message'] += text
                ml_conf_products[prod]['to_export'] = False
                continue

            prod_attr_set_id = attr_sets[mag_attr_set]['id']
            if not prod_attr_set_id:
                text = "Error while getting attribute set id for - %s from Magento. \n" % mag_attr_set
                ml_conf_products[prod]['log_message'] += text
                ml_conf_products[prod]['to_export'] = False
                continue

            avail_attributes = attr_sets[mag_attr_set]['attributes']
            if not avail_attributes:
                text = "Error while getting attributes for - %s Attribute-Set from Magento. \n" % mag_attr_set
                ml_conf_products[prod]['log_message'] += text
                ml_conf_products[prod]['to_export'] = False
                continue

            if conf_obj.odoo_prod_category.x_magento_no_create:
                ml_conf_products[prod]['magento_status'] = 'no_need'
                continue

            prod_conf_attr = ml_conf_products[prod]['config_attr']
            if not prod_conf_attr:
                text = "Missed 'Configurable Attribute(s)' for %s configurable product.\n" % prod
                ml_conf_products[prod]['log_message'] += text
                continue

            for attr in conf_obj.mag_assign_attributes:
                if attr.is_ignored_in_magento:
                    text = "The '%s' attribute cannot be used in Configurable Product.\n" % attr.name
                    ml_conf_products[prod]['log_message'] += text
                    continue

            # apply compatible date format to compare Product's dates
            exp_date = ml_conf_products[prod]['export_date_to_magento']
            export_date = self.format_to_magento_date(exp_date)
            # update_date = self.format_to_magento_date(conf_obj.update_date)
            magento_date = ml_conf_products[prod].get('magento_update_date', '')

            if not export_date or conf_obj.force_update:
                if ml_conf_products[prod]['magento_status'] == 'in_magento':
                    ml_conf_products[prod]['magento_status'] = 'update_needed'
                continue
        # if export_date > update_date:
            if magento_date and magento_date >= export_date:
                if ml_conf_products[prod]['magento_type_id'] == 'configurable':
                    # check if product images need to be updated
                    public_categ = conf_obj.odoo_prod_category
                    magento_images = ml_conf_products[prod].get('media_gallery', [])
                    if public_categ and (len(magento_images) != (len(public_categ.x_category_image_ids) +
                                                                 (1 if public_categ.image_256 else 0))):
                        ml_conf_products[prod]['magento_status'] = 'update_needed'
                        continue
                    # check if assign attribute(s) and attribute-set are the same in Magento and Odoo
                    if ml_conf_products[prod]['magento_attr_set_id'] == prod_attr_set_id:
                        mag_attr_options = ml_conf_products[prod]['magento_conf_prod_options']
                        check_assign_attr = self.check_config_product_assign_attributes_match(
                            mag_attr_options, prod_conf_attr, avail_attributes
                        )
                        if check_assign_attr:
                            ml_conf_products[prod]['to_export'] = False
                            ml_conf_products[prod]['magento_status'] = 'in_magento'
                            continue
                    if ml_conf_products[prod]['magento_status'] == 'in_magento':
                        ml_conf_products[prod]['magento_status'] = 'update_needed'
            elif ml_conf_products[prod]['magento_status'] not in ['log_error', 'in_process']:
                ml_conf_products[prod]['magento_status'] = 'update_needed'
        # elif ml_conf_products[prod]['magento_status'] != 'log_error':
        #     ml_conf_products[prod]['magento_status'] = 'update_needed'

    def check_simple_products_to_export(self, export_products, ml_simp_products, ml_conf_products):
        """
        Check if need to export Simple Products to Magento
        :param export_products: Magento Layer's Odoo product(s) to be exported
        :param ml_simp_products: Dictionary contains metadata for selected Simple Products (Odoo products)
        :param ml_conf_products: Dictionary contains metadata for selected Configurable Products (Odoo categories)
        :return: None
        """
        for prod in ml_simp_products:
            conf_sku = ml_simp_products[prod]['conf_sku']
            if ml_simp_products[prod]['log_message'] or ml_conf_products[conf_sku]['log_message']:
                ml_simp_products[prod]['to_export'] = False
                if conf_sku and ml_conf_products[conf_sku]['log_message']:
                    text = "Configurable Product is not ok. Please check it first.\n"
                    ml_simp_products[prod]['log_message'] += text
                continue

            # apply compatible date format to compare Product's dates
            export_date = self.format_to_magento_date(ml_simp_products[prod]['export_date_to_magento'])
            update_date_simp = self.format_to_magento_date(ml_simp_products[prod]['latest_update_date'])
            # update_date_conf = self.format_to_magento_date(ml_conf_products[categ_sku]['conf_object'].update_date)
            # update_date_conf = self.format_to_magento_date(ml_conf_products[conf_sku]['conf_object'].write_date)
            magento_date = ml_simp_products[prod].get('magento_update_date', '')

            if not export_date or ml_simp_products[prod]['force_update']:
                if ml_simp_products[prod]['magento_status'] == 'in_magento':
                    ml_simp_products[prod]['magento_status'] = 'update_needed'
                continue
            # if export_date > update_date_simp and export_date > update_date_conf:
            if export_date > update_date_simp:
                if magento_date and magento_date >= export_date:
                    if not ml_conf_products[conf_sku]['to_export']:
                        if ml_simp_products[prod]['do_not_export_conf'] or \
                                ml_simp_products[prod]['magento_prod_id'] in ml_conf_products[conf_sku]['children']:
                            export_prod = export_products.filtered(lambda p: p.magento_sku == prod)
                            # check if images count is the same in Odoo and Magento
                            if (len(export_prod.odoo_product_id.product_template_image_ids) +
                                (1 if export_prod.odoo_product_id.image_256 else 0)) !=\
                                    len(ml_simp_products[prod].get('media_gallery', [])):
                                ml_simp_products[prod]['magento_status'] = 'update_needed'
                                continue
                            if ml_simp_products[prod]['magento_status'] != 'in_magento':
                                ml_simp_products[prod]['magento_status'] = 'in_magento'

                            ml_simp_products[prod]['to_export'] = False
                            # delete error messages if any
                            log_book = self.env['magento.product.log.book'].search(
                                [('magento_product_id', '=', export_prod.id)])
                            if log_book:
                                log_book.write({'magento_log_message': '', 'magento_log_message_conf': ''})
                        else:
                            ml_simp_products[prod]['magento_status'] = 'need_to_link'
                    elif ml_simp_products[prod]['magento_status'] == 'in_magento':
                        ml_simp_products[prod]['magento_status'] = 'update_needed'
                elif ml_simp_products[prod]['magento_status'] not in ['log_error', 'in_process']:
                    ml_simp_products[prod]['magento_status'] = 'update_needed'
            elif ml_simp_products[prod]['magento_status'] != 'log_error':
                ml_simp_products[prod]['magento_status'] = 'update_needed'

    def process_config_products_create_or_update(self, instance, ml_conf_products, attr_sets, single):
        """
        Process Configurable Products (Odoo Product Categories) creation or update in Magento
        :param instance: Magento Instance
        :param ml_conf_products: Dictionary contains metadata for selected Configurable Products (Odoo categories)
        :param attr_sets: Attribute-Set dictionary with available in Magento Attributes info for selected products
        :param single: In case of direct (Odoo-Magento) single product export - True, else - False
        :return: None
        """
        new_conf_products = []
        for prod in ml_conf_products:
            if not ml_conf_products[prod]['to_export'] or ml_conf_products[prod]['log_message']:
                continue
            mag_attr_set = ml_conf_products[prod]['conf_object'].magento_attr_set
            prod_attr_set_id = attr_sets[mag_attr_set]['id']
            prod_attr_mag = attr_sets[mag_attr_set]['attributes']
            prod_conf_attr = ml_conf_products[prod]['config_attr']

            # check if Product's configurable attribute(s) exist in Magento, log error if attribute is missed in Magento
            available_attributes = [a['default_label'] for a in prod_attr_mag]
            conf_prod_attr = [self.to_upper(c) for c in prod_conf_attr if c]
            if not self.check_product_attr_are_in_attributes_list(available_attributes, conf_prod_attr):
                text = "Some of Configurable Product's attribute doesn't exist in Magento. " \
                       "It has to be created at first on Magento side.\n"
                ml_conf_products[prod]['log_message'] += text
                continue
            if not self.check_conf_attributes_can_be_configurable(conf_prod_attr, prod_attr_mag):
                text = "Some of Configurable Product's attribute can't be assigned as configurable in Magento. " \
                       "Make sure it has 'Global' scope and was created manually. "
                ml_conf_products[prod]['log_message'] += text
                continue

            # update (PUT) Conf.Product if it exists in Magento
            if ml_conf_products[prod].get('magento_update_date', ''):
                if ml_conf_products[prod]['magento_type_id'] != 'configurable':
                    text = "Product with the following sku - \"%s\" already exists in Magento. " \
                           "And it's type is not Configurable.\n" % prod
                    ml_conf_products[prod]['log_message'] += text
                # check if assign attributes are the same in Magento and Odoo
                mag_attr_options = ml_conf_products[prod]['magento_conf_prod_options']
                check_assign_attr = self.check_config_product_assign_attributes_match(
                    mag_attr_options, prod_conf_attr, attr_sets[mag_attr_set]['attributes']
                )
                conf_prod = self.export_single_conf_product_to_magento(
                    instance, prod, ml_conf_products, attr_sets, check_assign_attr, 'PUT'
                )
                # update magento data in ml_conf_products_dict, later will be used while linking with simple prod
                if conf_prod:
                    self.update_conf_product_dict_with_magento_data(conf_prod, ml_conf_products)
            else:
                new_conf_products.append(prod)

        # create (POST) new configurable products in Magento
        # if single - with regular API, else - via async request (RabbitMQ)
        if new_conf_products:
            if single:
                res = self.export_single_conf_product_to_magento(instance, new_conf_products[0], ml_conf_products,
                                                                 attr_sets)
                if res:
                    self.update_conf_product_dict_with_magento_data(res, ml_conf_products)
            else:
                self.export_new_conf_products_to_magento_in_bulk(instance, new_conf_products, ml_conf_products,
                                                                 attr_sets)

    def process_simple_products_create_or_update(self, instance, products_to_export, odoo_simp_prod, ml_simp_products,
                                                 attr_sets, ml_conf_products, single, method):
        """
        Process Simple Products (Odoo Products) creation or update in Magento
        :param instance: Magento Instance
        :param products_to_export: List of products to be exported
        :param odoo_simp_prod: Odoo Product Object(s)
        :param ml_simp_products: Dictionary contains metadata of Simple Products (Odoo Products)
        :param attr_sets: Attribute-Set dictionary with available in Magento Attributes info for selected products
        :param ml_conf_products: Dictionary contains metadata of Configurable Products (Odoo categories)
        :param single: In case of direct (Odoo-Magento) single product export - True, else - False
        :param method: Http method (POST/PUT)
        :return: None
        """
        if products_to_export:
            if single:
                prod_sku = odoo_simp_prod.magento_sku
                # to skip this step if only linking with parent needs to be done
                if method == 'POST' or ml_simp_products[prod_sku]['magento_status'] != 'need_to_link':
                    res = self.export_single_simple_product_to_magento(
                        instance, odoo_simp_prod, ml_simp_products, attr_sets, method
                    )
                    if res:
                        self.update_simp_product_dict_with_magento_data(res, ml_simp_products)
                    else:
                        return
                if not ml_simp_products[prod_sku]['do_not_export_conf']:
                    self.assign_attr_to_config_product(
                        instance, odoo_simp_prod, attr_sets, ml_conf_products, ml_simp_products
                    )
                    if not ml_simp_products[prod_sku]['log_message']:
                        self.link_simple_to_config_product_in_magento(
                            instance, odoo_simp_prod, ml_conf_products, ml_simp_products
                        )
            else:
                res = self.export_simple_products_in_bulk(
                    instance, products_to_export, odoo_simp_prod, ml_simp_products, attr_sets, method
                )
                if res is False:
                    return
                res = self.assign_attr_to_config_products_in_bulk(
                    instance, products_to_export, odoo_simp_prod, ml_conf_products, ml_simp_products, attr_sets
                )
                if res is False:
                    return
                self.link_simple_to_config_products_in_bulk(
                    instance, products_to_export, odoo_simp_prod,  ml_simp_products
                )

    def check_simple_products_for_errors_before_export(self, odoo_simp_products, ml_simp_products, ml_conf_products,
                                                       attribute_sets):
        """
        Check if Odoo Products to be exported have any errors
        :param odoo_simp_products: Odoo Products to be exported
        :param ml_simp_products: Dictionary contains metadata for Simple Products (Odoo products) to be exported
        :param ml_conf_products: Dictionary contains metadata for Configurable Products (Odoo Product Categories) to be exported
        :param attribute_sets: Dictionary with defined Attributes and their options in Magento
        :return: None
        """
        for prod in odoo_simp_products:
            conf_sku = prod.magento_conf_prod_sku
            prod_sku = prod.magento_sku
            # check if any log_messages for current product or it's configurable
            if ml_simp_products[prod_sku]['log_message']:
                continue
            elif ml_conf_products[conf_sku]['log_message']:
                text = "Configurable product is not ok. Please check it first.\n"
                ml_simp_products[prod_sku]['log_message'] += text
                continue

            if not ml_simp_products[prod_sku]['do_not_export_conf']:
                # check if product has assign attributes defined in it's configurable product
                simp_prod_attr = prod.product_template_attribute_value_ids.product_attribute_value_id
                check_assign_attr = self.check_product_attr_are_in_attributes_list(
                    [a.attribute_id.name for a in simp_prod_attr], ml_conf_products[conf_sku]['config_attr'])
                if not check_assign_attr:
                    text = "Simple product is missing attribute(s) defined as configurable. \n"
                    ml_simp_products[prod_sku]['log_message'] += text
                    continue

                prod_attr_set = prod.magento_conf_product.magento_attr_set
                available_attributes = attribute_sets[prod_attr_set]['attributes']
                # check if configurable product already contains such set of "Attribute: Value" pair.
                # Return False if not - will not be possible to link it in next steps
                check_attr_values = self.check_products_set_of_attribute_values(ml_conf_products, conf_sku,
                                                                                simp_prod_attr, available_attributes,
                                                                                ml_simp_products, prod_sku)
                if check_attr_values:
                    text = "The same configurable Set of Attribute Values was found in " \
                           "Product - %s.\n" % check_attr_values
                    ml_simp_products[prod_sku]['log_message'] += text
                    continue

            if ml_simp_products[prod_sku].get('magento_update_date') and \
                    ml_simp_products[prod_sku]['magento_type_id'] != 'simple':
                text = "The Product with such sku is already in Magento. (And it's type isn't Simple Product)/"
                ml_simp_products[prod_sku]['log_message'] += text

    def add_conf_product_attributes(self, conf_product, attr_sets, lang_code):
        custom_attributes = []
        available_attributes = attr_sets[conf_product.magento_attr_set]['attributes']
        prod_attributes = conf_product.odoo_prod_category.attribute_ids
        prod_attr_list = list(
            {(a.categ_group_id.name, a.categ_group_id.id) for a in prod_attributes if a.categ_group_id})
        # add product's attributes
        for prod_attr in prod_attr_list:
            attr = next((a for a in available_attributes if a['default_label'] and
                         self.to_upper(prod_attr[0]) == a['default_label']), {})
            if attr:
                custom_attributes.append({
                    "attribute_code": attr['attribute_code'],
                    "value": self.to_html_listitem(
                        prod_attributes.filtered(lambda x: x.categ_group_id.id == prod_attr[1]), lang_code)
                })
        # add Product's Website Description
        if conf_product.odoo_prod_category and conf_product.odoo_prod_category.website_description:
            custom_attributes.append({
                "attribute_code": 'description',
                "value": conf_product.with_context(lang=lang_code).odoo_prod_category.website_description
            })
        return custom_attributes

    def check_simp_product_attributes_and_options_exist_in_magento(self, magento_instance, odoo_products, attribute_sets,
                                                                   ml_product_dict):
        """
        Check if Product's Attributes exist in Magento.
        :param magento_instance: Instance of Magento
        :param odoo_products: Odoo Products to be exported
        :param attribute_sets: Dictionary with defined Attributes and their options in Magento
        :param ml_product_dict: Dictionary contains metadata for selected Simple Products (Odoo products)
        :return: None
        """
        for prod in odoo_products:
            prod_attributes = prod.product_template_attribute_value_ids.product_attribute_value_id
            if not len(prod_attributes) and not ml_product_dict[prod.magento_sku]['do_not_export_conf']:
                text = "Product - %s has no attributes.\n" % prod.magento_sku
                ml_product_dict[prod.magento_sku]['log_message'] += text
                continue
            prod_attr_set = prod.magento_conf_product.magento_attr_set
            available_attributes = attribute_sets[prod_attr_set]['attributes']
            prod_attr_list = [(a.attribute_id.name, a.name) for a in prod_attributes
                              if not a.attribute_id.is_ignored_in_magento]

            # add Product Life Phase attribute (aka x_status)
            if prod.odoo_product_id.x_status:
                prod_attr_list.append(("PRODUCTLIFEPHASE", self.to_upper(prod.odoo_product_id.x_status)))

            # logs if any of attributes are missed in Magento and creates new attr.option in Magento if needed
            for prod_attr in prod_attr_list:
                attr = next((a for a in available_attributes if a and self.to_upper(prod_attr[0]) == a['default_label']), {})
                if not attr:
                    text = "Attribute - %s has to be created on Magento side and attached " \
                           "to Attribute Set.\n" % prod_attr[0]
                    ml_product_dict[prod.magento_sku]['log_message'] += text
                else:
                    if self.to_upper(prod_attr[1]) not in [self.to_upper(i.get('label')) for i in attr['options']]:
                        _id, err = self.create_new_attribute_option_in_magento(magento_instance, attr['attribute_code'],
                                                                               prod_attr[1])
                        if err:
                            ml_product_dict[prod.magento_sku]['log_message'] += err
                        else:
                            attr['options'].append({'label': prod_attr[1].upper(), 'value': _id})

    def check_conf_product_attributes_and_options_exist_in_magento(self, ml_product_dict, attribute_sets):
        """
        Check if Product's Attributes exist in Magento.
        :param attribute_sets: Dictionary with defined Attributes and their options in Magento
        :param ml_product_dict: Dictionary contains metadata for selected Simple Products (Odoo products)
        :return: None
        """
        for prod in ml_product_dict:
            conf_prod = ml_product_dict[prod]['conf_object']
            prod_attr_set = conf_prod.magento_attr_set
            available_attributes = attribute_sets[prod_attr_set]['attributes']
            prod_attributes = conf_prod.odoo_prod_category.attribute_ids
            # create list of unique groups of product attributes to be used as attributes in magento
            prod_attr_list = list({a.categ_group_id.name for a in prod_attributes if a.categ_group_id})

            # logs if any of attributes are missed in Magento and creates new attr.option in Magento if needed
            for prod_attr in prod_attr_list:
                attr = next((a for a in available_attributes if a and self.to_upper(prod_attr) == a['default_label']), {})
                if not attr:
                    text = "Attribute - %s has to be created on Magento side and attached " \
                           "to Attribute Set.\n" % prod_attr
                    ml_product_dict[prod]['log_message'] += text

    def create_new_attribute_option_in_magento(self, magento_instance, attribute_code, attribute_option):
        """
        Creates new option(swatch) for defined attribute in Magento
        :param magento_instance: Instance of Magento
        :param attribute_code: The Code of Attribute defined in Magento
        :param attribute_option: The Attribute Value in Odoo
        :return: ID ID of created option
        """
        data = {
            "option": {
                "label": str(attribute_option).upper(),
                "sort_order": 0,
                "is_default": "false",
                "store_labels": []
            }
        }
        magento_storeviews = [w.store_view_ids for w in magento_instance.magento_website_ids]

        # get store_views from Magento to update store_labels field, if error - store_label remains [] (admin only)
        if magento_storeviews:
            store_labels = []
            # find Attribute Value translations if any
            avail_translations = self.env['ir.translation'].search([('name', '=', 'product.attribute.value,name'),
                                                                    ('src', '=', attribute_option)])
            for view in magento_storeviews:
                translated_label = ''
                if avail_translations:
                    for item in avail_translations:
                        if item.lang and (str(item.lang[:2]).upper()) == view.magento_storeview_code.upper():
                            translated_label = str(item.value if item.value else item.src).upper()
                            break
                store_labels.append({"store_id": view.magento_storeview_id, "label": translated_label})
            data['option'].update({"store_labels": store_labels})

        try:
            api_url = '/all/V1/products/attributes/%s/options' % attribute_code
            res = req(magento_instance, api_url, 'POST', data)
            try:
                _id = int(res[3:])
            except Exception:
                raise
        except Exception:
            return 0, "Error while new Product Attribute Option(Swatch) creation for %s Attribute.\n" % attribute_code
        return _id, ""

    def map_product_attributes_with_magento_attr(self, product_attributes, available_attributes):
        """
        Map Simple Product attributes from Odoo with exact attributes defined in Magneto.
        :param product_attributes: Odoo Product's attributes
        :param available_attributes: Dictionary with defined Attributes and their values in Magento
        :return: Magento format Attributes list
        """
        custom_attributes = []
        # update custom_attributes field with relevant data from Magento
        for prod_attr in product_attributes:
            attr = next((a for a in available_attributes if a['default_label'] and prod_attr[0] == a['default_label']), {})
            if attr:
                opt = next((o for o in attr['options'] if o.get('label') and self.to_upper(o['label']) == prod_attr[1]), {})
                if opt:
                    custom_attributes.append({
                        "attribute_code": attr['attribute_code'],
                        "value": opt['value']
                    })
        return custom_attributes

    def check_config_product_assign_attributes_match(self, mag_attr_options, conf_prod_assigned_attr, available_attributes):
        """
        Check if Config.Product (Product Category in Odoo) "assign" attributes are the same in Magento and Odoo
        :param mag_attr_options: Product Attributes defined as configurable in Magento
        :param available_attributes: Dictionary with available Attributes and their options in Magento
        :param conf_prod_assigned_attr: Product Attributes defined as configurable in Odoo
        :return: Boolean, True if the same, False if not
        """
        prod_attr_magento = {self.get_attribute_name_by_id(available_attributes, attr.get("attribute_id")) for attr in
                             mag_attr_options if attr}
        prod_attr_odoo = {self.to_upper(attr) for attr in conf_prod_assigned_attr if attr}
        if prod_attr_odoo == prod_attr_magento:
            return True
        return False

    def assign_attr_to_config_product(self, magento_instance, product, attr_sets, ml_conf_products, ml_simp_products):
        """
        Assigns attributes to configurable product in Magento, in order to link it with Simple Product
        :param magento_instance: Instance of Magento
        :param product: Odoo Product object
        :param available_attributes: Dictionary with defined Attributes and their values in Magento
        :param ml_conf_products: Dictionary contains metadata for selected Configurable Products (Odoo categories)
        :param ml_simp_products: Dictionary contains metadata for selected Simple Products (Odoo products)
        :return: None
        """
        prod_attr_set = product.magento_conf_product.magento_attr_set
        available_attributes = attr_sets[prod_attr_set]['attributes']
        config_product_sku = product.magento_conf_prod_sku
        product_attributes = product.product_template_attribute_value_ids.product_attribute_value_id
        conf_prod_assigned_attr = ml_conf_products[config_product_sku]['config_attr']
        data = {
            "option": {
                "attribute_id": "",
                "label": "",
                "position": 0,
                "is_use_default": "false",
                "values": []
            }
        }

        # check if config.product "assign" attributes are the same in magento and odoo
        attr_options = ml_conf_products[config_product_sku]['magento_conf_prod_options']
        prod_attr_magento = {}
        if attr_options:
            prod_attr_magento = {
                self.get_attribute_name_by_id(available_attributes, attr.get("attribute_id")): (
                    attr.get('id'), attr.get('attribute_id')) for attr in attr_options if attr
            }
            prod_attr_odoo = {self.to_upper(attr) for attr in conf_prod_assigned_attr if attr}

            if prod_attr_odoo != set(prod_attr_magento.keys()):
                # unlink attribute in Magento if assign attribute is not within Odoo attributes
                for attr in prod_attr_magento:
                    res = False
                    if attr not in prod_attr_odoo:
                        try:
                            api_url = '/V1/configurable-products/%s/options/%s' % (config_product_sku,
                                                                                   prod_attr_magento[attr][0])
                            res = req(magento_instance, api_url, 'DELETE')
                        except Exception:
                            text = "Error while unlinking Assign Attribute of %s Config.Product " \
                                   "in Magento.\n" % config_product_sku
                            ml_simp_products[product.magento_sku]['log_message'] += text
                    if res is True:
                        # update magento conf.product options list (without removed option)
                        attr_options = list(filter(lambda i: str(i.get('attribute_id')) != str(prod_attr_magento[attr][1]),
                                                   attr_options))
                ml_conf_products[config_product_sku]['magento_conf_prod_options'] = attr_options

        # assign new options to config.product with relevant info from Magento
        for attr_val in product_attributes:
            prod_attr_name = attr_val.attribute_id.name
            if prod_attr_name in conf_prod_assigned_attr:
                if self.to_upper(prod_attr_name) not in prod_attr_magento:
                    # valid for new "assign" attributes for config.product to be created in Magento
                    attr = next((a for a in available_attributes if a.get('default_label') and
                                 self.to_upper(prod_attr_name) == a['default_label']), {})
                    if attr:
                        opt = next((o for o in attr['options'] if o.get('label') and
                                    self.to_upper(o['label']) == self.to_upper(attr_val.name)), {})
                        if opt:
                            data['option'].update({
                                "attribute_id": attr["attribute_id"],
                                "label": attr["default_label"],
                                "values": [{"value_index": opt["value"]}]
                            })
                            try:
                                api_url = '/V1/configurable-products/%s/options' % config_product_sku
                                req(magento_instance, api_url, 'POST', data)
                            except Exception:
                                txt = "Error while assigning product attribute option to %s Config.Product " \
                                      "in Magento.\n " % config_product_sku
                                ml_simp_products[product.magento_sku]['log_message'] += txt
                            # update conf.product dict with new conf.product option
                            ml_conf_products[config_product_sku]['magento_conf_prod_options'].append({
                                'id': "",
                                "attribute_id": attr["attribute_id"],
                                "label": attr["default_label"]
                            })

    def link_simple_to_config_product_in_magento(self, magento_instance, product, ml_conf_products, ml_simp_products):
        """
        Link simple product to configurable product in Magento
        :param magento_instance: Instance of Magento
        :param product: Odoo Product object
        :param ml_conf_products: Dictionary contains metadata of Configurable Products (Odoo categories)
        :param ml_simp_products: Dictionary contains metadata of Simple Products (Odoo products)
        :return: None
        """
        config_product_sku = product.magento_conf_prod_sku
        simple_product_sku = product.magento_sku
        config_product_children = ml_conf_products[config_product_sku]['children']

        # if already linked, skip
        if ml_simp_products[simple_product_sku]['magento_prod_id'] in config_product_children:
            ml_simp_products[simple_product_sku]['magento_status'] = 'in_magento'
            ml_simp_products[simple_product_sku]['log_message'] = ''
            ml_conf_products[config_product_sku]['log_message'] = ''
            return

        data = {"childSku": simple_product_sku}
        try:
            api_url = '/V1/configurable-products/%s/child' % config_product_sku
            res = req(magento_instance, api_url, 'POST', data)
            if res is True:
                ml_simp_products[product.magento_sku]['magento_status'] = 'in_magento'
            elif res.get('message'):
                # if return error
                raise
        except Exception:
            text = "Error while linking %s to %s Configurable Product in Magento.\n " % (simple_product_sku, config_product_sku)
            ml_simp_products[simple_product_sku]['log_message'] += text

    def check_product_attr_are_in_attributes_list(self, attributes_list, prod_attrs):
        """
        Check if Attributes are in the list
        :param attributes_list: List with Product Attributes
        :param prod_attrs: Attributes assigned to Product
        :return: Boolean (True if in list, False if not)
        """
        if not prod_attrs:
            return False
        for attr in prod_attrs:
            if attr not in attributes_list:
                return False
        return True

    def check_conf_attributes_can_be_configurable(self, conf_prod_attributes, product_attributes_in_magento):
        for attr_name in conf_prod_attributes:
            attr = next((a for a in product_attributes_in_magento if str(a['default_label']) == attr_name), {})
            if not attr['can_be_configurable']:
                return False
        return True

    def get_attribute_name_by_id(self, available_attributes, attr_id):
        """
        Get Attribute Name by it's Id
        :param available_attributes: List with available in Magento Product Attributes
        :param attr_id: Attribute's Id
        :return: Attribute's Name or None
        """
        for attr in available_attributes:
            if str(attr.get('attribute_id')) == str(attr_id):
                return attr.get('default_label')

    def get_products_from_magento(self, magento_instance, ml_products_dict):
        """
        Get selected Products from Magento
        :param magento_instance: Instance of Magento
        :param ml_products_dict: Dictionary contains metadata for selected Simple/Configurable Products
        :return: List of Products from Magento
        """
        res = []
        step = 50
        cur_page = 0
        magento_sku_list = list(ml_products_dict)
        times = (len(magento_sku_list) // step) + (1 if len(magento_sku_list) % step else 0)
        for cnt in range(times):
            sku_list = ','.join(magento_sku_list[cur_page:step * (1 + cnt)])
            search_criteria = 'searchCriteria[filterGroups][0][filters][0][field]=sku&searchCriteria[filterGroups][0]' \
                              '[filters][0][condition_type]=in&searchCriteria[filterGroups][0][filters][0][value]=%s' % \
                              sku_list
            api_url = '/V1/products?%s' % search_criteria
            try:
                response = req(magento_instance, api_url)
            except Exception:
                for prod in magento_sku_list[cur_page:step * (1 + cnt)]:
                    text = "Error while requesting product from Magento.\n"
                    ml_products_dict[prod]['log_message'] += text
                cur_page += step
                continue

            res += (response.get('items', []))
            cur_page += step

        return res

    def export_new_conf_products_to_magento_in_bulk(self, magento_instance, new_conf_products, ml_conf_products, attr_sets):
        """
        Export(POST) to Magento new Configurable Products in bulk (asynchronously)
        :param magento_instance: Instance of Magento
        :param new_conf_products: List of new Configurable Products to be exported
        :param ml_conf_products: Dictionary contains metadata for selected Configurable Products (Odoo categories)
        :param attr_sets: Attribute set dictionary with unique data for selected products
        :return: None
        """
        data = []
        lang_code = self.env['res.lang']._lang_get(self.env.user.lang).code
        for prod in new_conf_products:
            conf_product = ml_conf_products[prod]['conf_object']
            # categ_list = [cat.category_id for cat in conf_product.category_ids]
            custom_attributes = self.add_conf_product_attributes(conf_product, attr_sets, lang_code)

            data.append({
                "product": {
                    "sku": prod,
                    "name": str(conf_product.magento_product_name).upper(),
                    "attribute_set_id": attr_sets[conf_product.magento_attr_set]['id'],
                    "status": 1,  # initially disabled
                    "visibility": 2,  # Catalog.
                    "type_id": "configurable",
                    "custom_attributes": custom_attributes,
                    "extension_attributes": {
                        # "category_links": [{"position": 0, "category_id": cat_id} for cat_id in categ_list]
                    }
                }
            })

        try:
            api_url = '/all/async/bulk/V1/products'
            response = req(magento_instance, api_url, 'POST', data)
        except Exception:
            for prod in new_conf_products:
                text = "Error while new Configurable Products creation in Magento. " \
                       "Please check if rabbitmq works properly.\n"
                ml_conf_products[prod]['log_message'] += text
            return
        # api = '/V1/bulk/%s/status' % response.get('bulk_uuid')
        if not response.get('errors'):
            product_websites = []
            prod_media = {}
            thumb_images = {}
            for prod in new_conf_products:
                conf_product = ml_conf_products[prod]['conf_object']
                ml_conf_products[prod]['export_date_to_magento'] = datetime.now()
                ml_conf_products[prod]['magento_status'] = 'in_process'

                # prepare websites export
                for site in magento_instance.magento_website_ids:
                    product_websites.append({
                        "productWebsiteLink": {
                            "sku": prod,
                            "website_id": site.magento_website_id
                        },
                        "sku": prod
                    })

                # prepare images export
                config_prod = conf_product.odoo_prod_category
                if config_prod:
                    # update product_media dict if product has images
                    if len(config_prod.x_category_image_ids):
                        prod_media.update({
                            prod: [(img.id, img.name, getattr(img, IMG_SIZE)) for img in config_prod.x_category_image_ids if img]
                        })
                    # update if product has thumbnail image
                    if config_prod.image_256:
                        thumb_images.update({prod: [(config_prod.id, '', config_prod.image_256)]})

            if product_websites:
                self.process_product_website_data_export_in_bulk(magento_instance, product_websites, new_conf_products,
                                                                 ml_conf_products)
            self.process_conf_prod_storeview_data_export_in_bulk(magento_instance, data, attr_sets, ml_conf_products)

            if prod_media:
                self.export_media_to_magento_in_bulk(magento_instance, prod_media, ml_conf_products, 'product.image')
            if thumb_images:
                self.export_media_to_magento_in_bulk(magento_instance, thumb_images, ml_conf_products,
                                                     'product.public.category', True)

    def export_single_conf_product_to_magento(self, magento_instance, prod_sku, ml_conf_products, attr_sets,
                                              check_assign_attr=True, method='POST'):
        """
        Export to Magento Single Configurable Product
        :param magento_instance: Instance of Magento
        :param prod_sku: New Configurable Product SKU to be exported
        :param ml_conf_products: Dictionary contains metadata for selected Configurable Products (Odoo categories)
        :param attr_sets: Attribute set dictionary with unique data for selected products
        :param check_assign_attr: Assign attributes are the same in Odoo and Magento (Boolean)
        :param method Http method (POST/PUT)
        :return: Magento Product or empty dict
        """
        conf_product = ml_conf_products[prod_sku]['conf_object']
        # categ_list = [cat.category_id for cat in conf_product.category_ids]
        lang_code = self.env['res.lang']._lang_get(self.env.user.lang).code
        custom_attributes = self.add_conf_product_attributes(conf_product, attr_sets, lang_code)

        data = {
            "product": {
                "name": str(conf_product.magento_product_name).upper(),
                "attribute_set_id": attr_sets[conf_product.magento_attr_set]['id'],
                "type_id": "configurable",
                "custom_attributes": custom_attributes,
                "extension_attributes": {
                    # "category_links": [{"position": 0, "category_id": cat_id} for cat_id in categ_list]
                }
            }
        }

        if method == 'POST':
            data['product'].update({
                "sku": prod_sku,
                "status": 1,  # Enabled
                "visibility": 2,  # Catalog
            })

        # here if not True - means assign attributes were changed and will unlink all related simple products
        if not check_assign_attr:
            data['product']["extension_attributes"].update({"configurable_product_links": []})

        try:
            api_url = '/all/V1/products' if method == "POST" else '/all/V1/products/%s' % prod_sku
            response = req(magento_instance, api_url, method, data)
        except Exception:
            text = "Error while Config.Product %s in Magento.\n" % ('update' if method == "PUT" else "creation")
            ml_conf_products[prod_sku]['log_message'] += text
            return {}

        if response.get('sku'):
            if method == "POST":
                self.process_product_websites_export(magento_instance, ml_conf_products, prod_sku, response)

            # export data related to each storeview(product name/description)
            self.process_storeview_data_export(magento_instance, conf_product, ml_conf_products, prod_sku, data,
                                               attr_sets, True)

            if conf_product.odoo_prod_category:
                trigger = False
                if method == "PUT":
                    magento_images = ml_conf_products[prod_sku].get('media_gallery', [])
                    export_date_to_magento = ml_conf_products[prod_sku]['export_date_to_magento']
                    export_date_to_magento = export_date_to_magento or datetime.min
                    if conf_product.odoo_prod_category.write_date > export_date_to_magento or \
                            len(magento_images) != (len(conf_product.odoo_prod_category.x_category_image_ids) +
                                                    (1 if conf_product.odoo_prod_category.image_256 else 0)):
                        trigger = True
                        if len(magento_images):
                            self.remove_product_images_from_magento(magento_instance, ml_conf_products, prod_sku)

                if method =="POST" or trigger:
                    self.process_images_export_to_magento(magento_instance, ml_conf_products, prod_sku)

            ml_conf_products[prod_sku]['export_date_to_magento'] = response.get("updated_at")
            ml_conf_products[prod_sku]['magento_status'] = 'in_magento'
            return response
        return {}

    def process_product_websites_export(self, magento_instance, ml_products, prod_sku, product, method="POST"):
        # add all available Websites to Product in case of initial export
        website_ids = []
        data = {"productWebsiteLink": {"sku": prod_sku}}
        for site in magento_instance.magento_website_ids:
            data["productWebsiteLink"].update({"website_id": site.magento_website_id})
            try:
                api_url = '/V1/products/%s/websites' % prod_sku
                res = req(magento_instance, api_url, method, data)
                if res is True:
                    website_ids.append(site.magento_website_id)
            except Exception:
                text = "Error while adding website to product in Magento.\n"
                ml_products[prod_sku]['log_message'] += text

        if website_ids:
            product.get('extension_attributes', {'extension_attributes': {}}).update(
                {'website_ids': website_ids})

    def process_storeview_data_export(self, magento_instance, product, ml_products, prod_sku, data, attr_sets, is_config):
        product_price = 0
        text = ''
        magento_storeviews = [(w, w.store_view_ids) for w in magento_instance.magento_website_ids]

        if not is_config and magento_instance.catalog_price_scope == 'global':
            if not len(magento_instance.pricelist_id):
                text += "There are no pricelist(s) defined for '%s' instance.\n" % magento_instance.name
            else:
                product_price = magento_instance.pricelist_id.get_product_price(product.odoo_product_id, 1.0, False)

        for view in magento_storeviews:
            lang_code = view[1].lang_id.code
            if is_config:
                data['product']['name'] = str(product.with_context(lang=lang_code).odoo_prod_category.name).upper()
                data['product']['custom_attributes'] = self.add_conf_product_attributes(product, attr_sets, lang_code)
            else:
                # valid for simple products only
                data["product"]["name"] = product.with_context(lang=lang_code).odoo_product_id.name

                # find description attribute to add translations for each storeview
                descr_attr = next(
                    (a for a in data["product"]["custom_attributes"] if a.get('attribute_code') == 'description'), {}
                )
                if descr_attr:
                    descr_attr["value"] = product.with_context(lang=lang_code).odoo_product_id.website_description

                # apply product prices for each website
                if magento_instance.catalog_price_scope == 'website':
                    if not len(view[0].pricelist_id):
                        text += "There are no pricelist defined for '%s' website.\n" % view[0].name
                    else:
                        if view[0].magento_base_currency.id != view[0].pricelist_id.currency_id.id:
                            text += "Pricelist '%s' currency is different than Magento base currency " \
                                    "for '%s' website.\n" % (view[0].pricelist_id.name, view[0].name)
                            break
                        price_and_rule = view[0].pricelist_id.get_product_price_rule(product.odoo_product_id, 1.0, False)
                        product_price = 0 if price_and_rule[1] is False else price_and_rule[0]

                if product_price:
                    data["product"]["price"] = product_price
                else:
                    data["product"]["price"] = data["product"]["status"] = 0
                    if not text:
                        text += "There are no or '0' price defined for product in '%s' " \
                                "website price-lists.\n" % (view[0].name)
            try:
                api_url = '/%s/V1/products/%s' % (view[1].magento_storeview_code, prod_sku)
                req(magento_instance, api_url, 'PUT', data)
            except Exception:
                text = "Error while exporting product's data to '%s' store view.\n" % view[1].magento_storeview_code
                break

        if text:
            ml_products[prod_sku]['log_message'] += text
            ml_products[prod_sku]['force_update'] = True

    def process_simple_prod_storeview_data_export_in_bulk(self, magento_instance, odoo_products, data, ml_products):
        magento_storeviews = [(w, w.store_view_ids) for w in magento_instance.magento_website_ids]

        if magento_instance.catalog_price_scope == 'global':
            if not len(magento_instance.pricelist_id):
                text = "There are no pricelist(s) defined for '%s' instance.\n" % magento_instance.name
                for product in data:
                    ml_products[product['sku']]['log_message'] += text
                return

        for view in magento_storeviews:
            data_lst = []
            lang_code = view[1].lang_id.code
            for prod in data:
                product_price = 0
                sku = prod['product']['sku']
                product = odoo_products.search([('magento_sku', '=', sku),
                                                ('magento_instance_id', '=', magento_instance.id)], limit=1)
                prod = {
                    'product': {
                        'name': product.with_context(lang=lang_code).odoo_product_id.name,
                        'sku': sku,
                        'price': 0,
                        'custom_attributes': prod['product']["custom_attributes"].copy()
                    }
                }
                # find description attribute to add translations for each storeview
                descr_attr = next(
                    (a for a in prod["product"]["custom_attributes"] if a.get('attribute_code') == 'description'), {}
                )
                if descr_attr:
                    descr_attr["value"] = product.with_context(lang=lang_code).odoo_product_id.website_description

                # product price
                if magento_instance.catalog_price_scope == 'global':
                    product_price = magento_instance.pricelist_id.get_product_price(product.odoo_product_id, 1.0, False)
                elif magento_instance.catalog_price_scope == 'website':
                    if not len(view[0].pricelist_id):
                        text = "There are no pricelist defined for '%s' website.\n" % view[0].name
                        ml_products[sku]['log_message'] += text
                    else:
                        if view[0].magento_base_currency.id != view[0].pricelist_id.currency_id.id:
                            text = "Pricelist '%s' currency is different than Magento base currency " \
                                    "for '%s' website.\n" % (view[0].pricelist_id.name, view[0].name)
                            ml_products[sku]['log_message'] += text
                            break
                        price_and_rule = view[0].pricelist_id.get_product_price_rule(product.odoo_product_id, 1.0, False)
                        product_price = 0 if price_and_rule[1] is False else price_and_rule[0]

                if product_price:
                    prod["product"]["price"] = product_price
                else:
                    prod["product"]["price"] = 0
                    prod["product"].update({"status": 0})
                    if not ml_products[sku]['log_message']:
                        text = "There are no or '0' price defined for product in '%s' " \
                                "website price-lists.\n" % (view[0].name)
                        ml_products[sku]['log_message'] += text

                data_lst.append(prod)

            try:
                api_url = '/%s/async/bulk/V1/products' % view[1].magento_storeview_code
                req(magento_instance, api_url, 'PUT', data_lst)
            except Exception:
                for product in data:
                    text = "Error while exporting products data to '%s' store view.\n" % view[1].magento_storeview_code
                    ml_products[product['product']['sku']]['log_message'] += text
                break

    def process_conf_prod_storeview_data_export_in_bulk(self, magento_instance, data, attr_sets, ml_conf_products):
        magento_storeviews = [(w, w.store_view_ids) for w in magento_instance.magento_website_ids]

        for view in magento_storeviews:
            data_lst = []
            lang_code = view[1].lang_id.code
            for product in data:
                sku = product['product']['sku']
                conf_prod = ml_conf_products[sku]['conf_object']
                prod = {
                    'product': {
                        'name': str(conf_prod.with_context(lang=lang_code).odoo_prod_category.name).upper(),
                        'sku': sku,
                        'custom_attributes': self.add_conf_product_attributes(conf_prod, attr_sets, lang_code)
                    }
                }
                data_lst.append(prod)

            try:
                api_url = '/%s/async/bulk/V1/products' % view[1].magento_storeview_code
                req(magento_instance, api_url, 'PUT', data_lst)
            except Exception:
                for product in data:
                    text = "Error while exporting products' data to '%s' store view.\n" % view[1].magento_storeview_code
                    ml_conf_products[product['product']['sku']]['log_message'] += text
                break

    def export_single_simple_product_to_magento(self, magento_instance, product, ml_simp_products, attr_sets, method):
        """
        Export(update) Simple Product to Magento
        :param magento_instance: Instance of Magento
        :param product: Odoo Product object
        :param ml_simp_products: Dictionary contains metadata for selected Simple Products (Odoo products)
        :param attr_sets: Dictionary with defined Attributes and their values in Magento
        :param method: http method (POST or PUT)
        :return: {} or Updated product
        """
        prod_attr_set = product.magento_conf_product.magento_attr_set
        available_attributes = attr_sets[prod_attr_set]['attributes']
        prod_attr_list = [(self.to_upper(a.attribute_id.name), self.to_upper(a.name)) for a in
                          product.product_template_attribute_value_ids.product_attribute_value_id
                          if not a.attribute_id.is_ignored_in_magento]
        # add Product Life Phase attribute (aka x_status)
        if product.odoo_product_id.x_status:
            prod_attr_list.append(("PRODUCTLIFEPHASE", self.to_upper(product.odoo_product_id.x_status)))

        custom_attributes = self.map_product_attributes_with_magento_attr(prod_attr_list, available_attributes)

        # add Product's Website Description
        if product.odoo_product_id.website_description:
            custom_attributes.append({
                "attribute_code": 'description',
                "value": product.odoo_product_id.website_description
            })

        # add product categories links
        if product.magento_conf_product.do_not_create_flag:
            categ_list = [(cat.magento_prod_categ.id, cat.magento_prod_categ.category_id) for cat in
                          product.odoo_product_id.public_categ_ids if cat and cat.magento_prod_categ and
                          cat.magento_prod_categ.instance_id.id == magento_instance.id]
        else:
            categ_list = [(cat.id, cat.category_id) for cat in product.magento_conf_product.category_ids]
        ml_simp_products[product.magento_sku]['product_categ'] = [c[0] for c in categ_list]

        # get product stock from specified locations, valid for initial(POST) export only
        stock_item =  {
            "qty": self.get_magento_product_stock(magento_instance, [product.odoo_product_id.id],
                                                  self.env[PRODUCT_PRODUCT],
                                                  magento_instance.location_ids).get(product.odoo_product_id.id),
            "is_in_stock": "true"
        } if method == 'POST' else {}

        data = {
            "product": {
                "name": product.magento_product_name,
                # product.x_magento_name if product.x_magento_name else product.magento_product_name,
                "attribute_set_id":  attr_sets[prod_attr_set]['id'],
                "price": 0,#product.lst_price,
                # "status": 0,#initially disabled
                "type_id": "simple",
                "weight": product.odoo_product_id.weight,
                "custom_attributes": custom_attributes,
                "extension_attributes": {
                    "stock_item": stock_item,
                    "category_links": [{"position": 0, "category_id": cat_id[1]} for cat_id in categ_list]
                }
            }
        }
        if method == 'POST':
            data["product"].update({"sku": product.magento_sku, "status": 1, "visibility": 4})

        try:
            api_url = '/all/V1/products' if method == 'POST' else '/all/V1/products/%s' % product.magento_sku
            response = req(magento_instance, api_url, method, data)
        except Exception:
            text = "Error while new Simple Product creation in Magento.\n" if method == 'POST' else \
                "Error while Simple Product update in Magento.\n"
            ml_simp_products[product.magento_sku]['log_message'] += text
            return {}

        if response.get("sku"):
            ml_simp_products[product.magento_sku]['export_date_to_magento'] = response.get("updated_at")
            if ml_simp_products[product.magento_sku]['do_not_export_conf']:
                ml_simp_products[product.magento_sku]['magento_status'] = 'in_magento'
            else:
                ml_simp_products[product.magento_sku]['magento_status'] = 'need_to_link'

            if method == "POST":
                self.process_product_websites_export(magento_instance, ml_simp_products, product.magento_sku, response)

            # export data related to each storeview (product name/description, price)
            self.process_storeview_data_export(magento_instance, product, ml_simp_products, product.magento_sku,
                                               data, attr_sets, False)
            ## process images export to magento
            # remove product images in magento if any
            if ml_simp_products[product.magento_sku].get('media_gallery', []):
                self.remove_product_images_from_magento(magento_instance, ml_simp_products, product.magento_sku)
            # export product's images to Magento
            if len(product.odoo_product_id.product_template_image_ids):
                prod_media = {
                    product.magento_sku: [
                        (img.id, img.name, getattr(img, IMG_SIZE)) for img in product.odoo_product_id.product_template_image_ids if img
                    ]
                }
                self.export_media_to_magento(magento_instance, prod_media, ml_simp_products, 'product.image')
            # export product's thumbnail Image
            if product.odoo_product_id.image_256:
                thumb_image = {
                    product.magento_sku: [(product.odoo_product_id.product_tmpl_id.id, '', product.odoo_product_id.image_256)]
                }
                self.export_media_to_magento(magento_instance, thumb_image, ml_simp_products, 'product.template', True)

            return response
        return {}

    def export_simple_products_in_bulk(self, magento_instance, export_prod_list, odoo_products, ml_simp_products,
                                       attr_sets, method='POST'):
        """
        Export(POST) to Magento new Simple Products in bulk (asynchronously)
        :param magento_instance: Instance of Magento
        :param export_prod_list: List of new Simple Products to be exported
        :param odoo_products: Odoo Product objects
        :param ml_simp_products: Dictionary contains metadata for selected Simple Products (Odoo products)
        :param attr_sets: Attribute set dictionary with unique data for selected products
        :param method: Http request method (POST/PUT)
        :return: None or False
        """
        data = []
        prod_media = {}
        thumb_images = {}
        product_websites = []
        remove_images = []
        # get product stock from specified locations, valid for initial(POST) export only
        prod_stock = self.get_magento_product_stock(
            magento_instance, [p.odoo_product_id.id for p in odoo_products], self.env[PRODUCT_PRODUCT],
            magento_instance.location_ids
        ) if method == 'POST' else {}

        for prod in odoo_products:
            if prod.magento_sku in export_prod_list and ml_simp_products[prod.magento_sku]['magento_status'] != 'need_to_link':
                prod_attr_list = [(self.to_upper(a.attribute_id.name), self.to_upper(a.name)) for a in
                                  prod.product_template_attribute_value_ids.product_attribute_value_id
                                  if not a.attribute_id.is_ignored_in_magento]
                # add Product Life Phase attribute (aka x_status)
                if prod.odoo_product_id.x_status:
                    prod_attr_list.append(("PRODUCTLIFEPHASE", self.to_upper(prod.odoo_product_id.x_status)))
                # Odoo attribute(s) mapping with attributes from Magento
                custom_attributes = self.map_product_attributes_with_magento_attr(
                    prod_attr_list, attr_sets[prod.magento_conf_product.magento_attr_set]['attributes']
                )
                # add Product's Website Description
                if prod.odoo_product_id.website_description:
                    custom_attributes.append({
                        "attribute_code": 'description',
                        "value": prod.odoo_product_id.website_description
                    })

                attr_set_id = attr_sets.get(prod.magento_conf_product.magento_attr_set, {}).get('id')
                # add product categories info
                if prod.magento_conf_product.do_not_create_flag:
                    categ_list = [(cat.magento_prod_categ.id, cat.magento_prod_categ.category_id) for cat in
                                  prod.odoo_product_id.public_categ_ids if cat and cat.magento_prod_categ and
                                  cat.magento_prod_categ.instance_id.id == magento_instance.id]
                else:
                    categ_list = [(cat.id, cat.category_id) for cat in prod.magento_conf_product.category_ids]
                ml_simp_products[prod.magento_sku]['product_categ'] = [c[0] for c in categ_list]

                p = {
                    "product": {
                        "sku": prod.magento_sku,
                        "name": prod.magento_product_name,
                        # prod.x_magento_name if prod.x_magento_name else prod.magento_product_name,
                        "attribute_set_id": attr_set_id,
                        "price": 0, #prod.lst_price,
                        "type_id": "simple",
                        "weight": prod.odoo_product_id.weight,
                        "extension_attributes": {
                            "stock_item": {"qty": prod_stock.get(prod.odoo_product_id.id) or 0,
                                           "is_in_stock": "true"} if method == 'POST' else {},
                            "category_links": [{"position": 0, "category_id": cat_id[1]} for cat_id in categ_list]
                        },
                        "custom_attributes": custom_attributes
                    }
                }
                if method == 'POST':
                    p["product"].update({"status": 1, "visibility": 4})
                data.append(p)

        if not data:
            return False
        try:
            api_url = '/all/async/bulk/V1/products'
            response = req(magento_instance, api_url, method, data)
        except Exception:
            text = "Error while asynchronously Simple Products %s in Magento.\n" % (
                'creation' if method == 'POST' else "update")
            for prod in export_prod_list:
                ml_simp_products[prod]['log_message'] += text
            return False

        if response.get('errors'):
            return False
        for prod in odoo_products:
            if prod.magento_sku in export_prod_list:
                img_update = False
                ml_simp_products[prod.magento_sku]['export_date_to_magento'] = datetime.now()
                ml_simp_products[prod.magento_sku]['magento_status'] = 'in_process'

                # prepare products dict with websites and images info to be exported
                if method == "POST":
                    # update product_website dict with avail.websites
                    for site in magento_instance.magento_website_ids:
                        product_websites.append({
                            "productWebsiteLink": {
                                "sku": prod.magento_sku,
                                "website_id": site.magento_website_id
                            },
                            "sku": prod.magento_sku
                        })
                elif method == "PUT" and (len(prod.odoo_product_id.product_template_image_ids) +
                                          (1 if prod.odoo_product_id.image_256 else 0)) != \
                        len(ml_simp_products[prod.magento_sku].get('media_gallery', [])):
                    for _id in ml_simp_products[prod.magento_sku]['media_gallery']:
                        remove_images.append({
                            "entryId": _id,
                            "sku": prod.magento_sku
                        })
                    img_update = True
                if method == 'POST' or img_update:
                    # update product_media dict if product has images
                    if len(prod.odoo_product_id.product_template_image_ids):
                        prod_media.update({
                            prod.magento_sku: [(img.id, img.name, getattr(img, IMG_SIZE)) for img in
                                               prod.odoo_product_id.product_template_image_ids if img]
                        })
                    # update if product has thumbnail image
                    if prod.odoo_product_id.image_256:
                        thumb_images.update({
                            prod.magento_sku: [(prod.odoo_product_id.product_tmpl_id.id, '', prod.odoo_product_id.image_256)]
                        })

        if method == "POST":
            if product_websites:
                self.process_product_website_data_export_in_bulk(magento_instance, product_websites,
                                                                 export_prod_list, ml_simp_products)

        self.process_simple_prod_storeview_data_export_in_bulk(magento_instance, odoo_products, data, ml_simp_products)

        if remove_images:
            self.remove_product_images_from_magento_in_bulk(magento_instance, remove_images, ml_simp_products)
        if prod_media:
            self.export_media_to_magento_in_bulk(magento_instance, prod_media, ml_simp_products, 'product.image')
        if thumb_images:
            self.export_media_to_magento_in_bulk(magento_instance, thumb_images, ml_simp_products,
                                                 'product.template', True)

    def process_product_website_data_export_in_bulk(self, magento_instance, product_websites, product_list, ml_products):
        try:
            api_url = '/async/bulk/V1/products/bySku/websites'
            req(magento_instance, api_url, 'POST', product_websites)
        except Exception:
            text = "Error while assigning website(s) to product in Magento"
            for prod_sku in product_list:
                ml_products[prod_sku]['log_message'] += text

    def export_media_to_magento_in_bulk(self, magento_instance, products_media, ml_simp_products, res_model,
                                        is_thumbnail=False):
        """
        Export(POST) to Magento Product's Images in bulk (asynchronously)
        :param magento_instance: Instance of Magento
        :param products_media: Dictionary with Product Images added in Odoo
        :param ml_simp_products: Dictionary contains metadata for selected Simple Products (Odoo products)
        :param res_model: Model to be referenced to find image in attachment model
        :param is_thumbnail: If Image has to be exported as thumbnail (Boolean)
        :return: None
        """

        files_size = 0
        images = []
        last_prod = list(products_media)[-1]

        def process(images):
            try:
                api_url = '/all/async/bulk/V1/products/bySku/media'
                req(magento_instance, api_url, 'POST', images)
            except Exception:
                text = "Error while Product (%s) Images export to Magento in bulk. \n" % str(
                    'Thumbnail' if is_thumbnail else 'Base')
                for sku in {img["sku"] for img in images}:
                    if not ml_simp_products[sku]['log_message']:
                        ml_simp_products[sku]['force_update'] = True
                        ml_simp_products[sku]['log_message'] += text
            return [], 0

        for prod_sku in products_media:
            for img in products_media[prod_sku]:
                if ml_simp_products[prod_sku]['log_message']:
                    continue
                attachment = self.env['ir.attachment'].sudo().search([
                    ('res_field', '=', 'image_256' if is_thumbnail else IMG_SIZE),
                    ('res_model', '=', res_model),
                    ('res_id', '=', img[0])
                ])
                if not len(attachment):
                    continue

                if files_size and files_size + attachment.file_size > MAX_SIZE_FOR_IMAGES:
                    images, files_size = process(images)

                images.append({
                    "entry": {
                        "media_type": "image",
                        "types": ["thumbnail"] if is_thumbnail else [],
                        "disabled": "true" if is_thumbnail else "false",
                        "label": img[1],
                        "content": {
                            "base64EncodedData": img[2].decode('utf-8'),
                            "type": attachment.mimetype,
                            "name": attachment.mimetype.replace("/", ".")
                        }
                    },
                    "sku": prod_sku
                })
                files_size += attachment.file_size

                # valid for the last image of last product
                if prod_sku == last_prod and img == products_media[prod_sku][-1]:
                    images, files_size = process(images)

    def process_images_export_to_magento(self, magento_instance, ml_conf_products, magento_sku):
        # product images (Base)
        public_categ = ml_conf_products[magento_sku]['conf_object'].odoo_prod_category
        if len(public_categ.x_category_image_ids):
            prod_media = {
                magento_sku: [(img.id, img.name, getattr(img, IMG_SIZE)) for img in public_categ.x_category_image_ids if img]
            }
            self.export_media_to_magento(magento_instance, prod_media, ml_conf_products, 'product.image')
        # product images (Thumbnail)
        if public_categ.image_256:
            thumb_image = {magento_sku: [(public_categ.id, '', public_categ.image_256)]}
            self.export_media_to_magento(magento_instance, thumb_image, ml_conf_products,
                                         'product.public.category', True)

    def export_media_to_magento(self, magento_instance, products_media, ml_products, res_model, is_thumbnail=False):
        """
        Export(POST) to Magento Product's Images
        :param magento_instance: Instance of Magento
        :param products_media: Dictionary with list of Product's Image tuples (img_id, img_name, img_bytecode)
        :param ml_products: Dictionary contains metadata for selected Conf/Simple Products
        :param res_model: Model to be referenced to find image in attachment model
        :param is_thumbnail: If Image has to be exported as thumbnail (Boolean)
        :return: None
        """
        images = {}
        prod_sku = list(products_media.keys())[0]
        for img in products_media[prod_sku]:
            attachment = self.env['ir.attachment'].sudo().search([
                ('res_field', '=', 'image_256' if is_thumbnail else IMG_SIZE),
                ('res_model', '=', res_model),
                ('res_id', '=', img[0])
            ])
            if not len(attachment):
                continue
            images.update({
                "entry": {
                    "media_type": "image",
                    "types": ["thumbnail"] if is_thumbnail else [],
                    "disabled": "true" if is_thumbnail else "false",
                    "label": img[1],
                    "content": {
                        "base64EncodedData": img[2].decode('utf-8'),
                        "type": attachment.mimetype,
                        "name": attachment.mimetype.replace("/", ".")
                    }
                }
            })
            try:
                api_url = '/all/V1/products/%s/media' % prod_sku
                req(magento_instance, api_url, 'POST', images)
            except Exception:
                ml_products[prod_sku]['force_update'] = True
                text = "Error while Product (%s) Images export to Magento.\n" % str('Thumbnail' if is_thumbnail else 'Base')
                ml_products[prod_sku]['log_message'] += text

    def remove_product_images_from_magento(self, magento_instance, ml_products, magento_sku):
        for _id in ml_products[magento_sku]['media_gallery']:
            try:
                api_url = '/all/V1/products/%s/media/%s' % (magento_sku, _id)
                req(magento_instance, api_url, 'DELETE')
            except Exception:
                ml_products[magento_sku]['force_update'] = True
                text = "Error while Product Images remove from Magento. \n"
                ml_products[magento_sku]['log_message'] += text

    def remove_product_images_from_magento_in_bulk(self, magento_instance, remove_images, ml_products):
        try:
            api_url = '/all/async/bulk/V1/products/bySku/media/byEntryId'
            req(magento_instance, api_url, 'DELETE', remove_images)
        except Exception:
            text = "Error while async Product Images remove from Magento. \n"
            for sku in {img["sku"] for img in remove_images}:
                ml_products[sku]['force_update'] = True
                ml_products[sku]['log_message'] += text

    def assign_attr_to_config_products_in_bulk(self, magento_instance, export_prod_list, odoo_products,
                                               config_prod_assigned_attr, ml_simp_products, available_attributes):
        """
        Assigns Attributes to Configurable Products in bulk (asynchronously)
        :param magento_instance: Instance of Magento
        :param export_prod_list: List of new Simple Products to be exported
        :param odoo_products: Odoo Product records
        :param config_prod_assigned_attr: Configurable Product Assigned Attributes
        :param ml_simp_products: Dictionary contains metadata for selected Simple Products (Odoo products)
        :param available_attributes: Dictionary with defined Attributes and their values in Magento
        :return: None or False
        """
        data = []

        # assign new options to config.product with relevant info from Magento
        for simple_prod in odoo_products:
            if simple_prod.magento_sku not in export_prod_list or \
                    ml_simp_products[simple_prod.magento_sku]['log_message'] or \
                    ml_simp_products[simple_prod.magento_sku]['do_not_export_conf']:
                continue

            simp_prod_attrs = simple_prod.product_template_attribute_value_ids.product_attribute_value_id
            mag_attr_set = simple_prod.magento_conf_product.magento_attr_set
            mag_avail_attrs = available_attributes.get(mag_attr_set).get('attributes')
            conf_sku = simple_prod.magento_conf_prod_sku

            for prod_attr in simp_prod_attrs:
                attr_name = prod_attr.attribute_id.name
                if attr_name in config_prod_assigned_attr.get(conf_sku).get('config_attr'):
                    attr = next((a for a in mag_avail_attrs if a.get('default_label') and
                                 self.to_upper(attr_name) == a['default_label']), {})
                    if attr:
                        opt = next((o for o in attr['options'] if o.get('label') and
                                    self.to_upper(o['label']) == self.to_upper(prod_attr.name)), {})
                        if opt:
                            data.append({
                                'option': {
                                    "attribute_id": attr["attribute_id"],
                                    "label": attr["default_label"],
                                    "is_use_default": "false",
                                    "values": [{"value_index": opt["value"]}]
                                },
                                'sku': conf_sku
                            })

        if data:
            try:
                api_url = '/async/bulk/V1/configurable-products/bySku/options'
                response = req(magento_instance, api_url, 'POST', data)
            except Exception:
                text = "Error while asynchronously assign product attributes to Configurable Product in Magento.\n"
                for prod in export_prod_list:
                    ml_simp_products[prod]['log_message'] += text
                return False

            if response.get('errors', {}):
                return False

    def link_simple_to_config_products_in_bulk(self, magento_instance, export_prod_list, odoo_products, ml_simp_products):
        """
        Link Simple Product to Configurable Product in Magento in bulk (asynchronously)
        :param magento_instance: Instance of Magento
        :param export_prod_list: List of new Simple Products to be exported
        :param odoo_products: Odoo Product objects
        :param ml_simp_products: Dictionary contains metadata for selected Simple Products (Odoo products)
        :return: None
        """
        data = []

        for simple_prod in odoo_products:
            if simple_prod.magento_sku not in export_prod_list or \
                    ml_simp_products[simple_prod.magento_sku]['log_message'] or \
                    ml_simp_products[simple_prod.magento_sku]['do_not_export_conf']:
                continue
            data.append({
                "childSku": simple_prod.magento_sku,
                "sku": simple_prod.magento_conf_prod_sku
            })

        if data:
            try:
                api_url = '/async/bulk/V1/configurable-products/bySku/child'
                req(magento_instance, api_url, 'POST', data)
            except Exception:
                text = "Error while asynchronously linking Simple to Configurable Product in Magento.\n"
                for prod in export_prod_list:
                    ml_simp_products[prod]['log_message'] += text

    def check_products_set_of_attribute_values(self, ml_conf_products, conf_sku, simp_prod_attr,
                                               available_attributes, ml_simple_prod, magento_sku):
        """
        Check Product's "Attribute: Value" pair for duplication
        :param ml_conf_products: Dictionary contains metadata for selected Configurable Products (Odoo categories)
        :param conf_sku: Product Category Name
        :param simp_prod_attr: Simple Product Attributes defined in Odoo
        :param available_attributes: Dictionary with defined Attributes and their values in Magento
        :param ml_simple_prod: Dictionary contains metadata for selected Simple Products (Odoo products)
        :param magento_sku: Product sku
        :return: Product sku in case of duplication or False
        """
        # magento_conf_prod_links - dict with already assigned configurable {attribute: value} pair to conf.product
        magento_conf_prod_links = ml_conf_products[conf_sku].get('magento_configurable_product_link_data', {})
        conf_prod_attributes = ml_conf_products[conf_sku]['config_attr']

        # create dict {simple_product_sku: {attribute: value,...}} with config.attributes only
        simp_attr_val = {}
        for prod_attr in simp_prod_attr:
            prod_attr_name = prod_attr.attribute_id.name
            if prod_attr_name in conf_prod_attributes:
                attr = next((a for a in available_attributes if a['default_label'] and
                             self.to_upper(prod_attr_name) == a['default_label']), {})
                if attr:
                    opt = next((o for o in attr['options'] if o.get('label') and
                                self.to_upper(o.get('label')) == self.to_upper(prod_attr.name)), {})
                    if opt:
                        simp_attr_val.update({attr['default_label']: self.to_upper(opt['label'])})

        # check if simple product's "attribute: value" is already linked to configurable product in Magento
        for prod in magento_conf_prod_links:
            if magento_conf_prod_links[prod] == simp_attr_val and prod != magento_sku:
                return prod

        # check if simple product's "attribute: value" is within exported products
        for prod in ml_simple_prod:
            if ml_simple_prod[prod]['conf_sku'] == conf_sku and prod != magento_sku and \
                    ml_simple_prod[prod]['conf_attributes'] == simp_attr_val:
                return prod

        return False

    def convert_to_dict(self, conf_prod_link_data):
        """
        Convert API result from json format to Python dict
        :param conf_prod_link_data: Json formatted data from Magento
        :return: Python dict
        """
        if not conf_prod_link_data:
            return {}

        link_data_dict = {}
        for prod in conf_prod_link_data:
            new_dict = json.loads(prod)
            opt_dict = {}
            for attr_opt in new_dict.get('simple_product_attribute'):
                opt_dict.update({self.to_upper(attr_opt.get('label')): self.to_upper(attr_opt.get('value'))})
            link_data_dict.update({new_dict['simple_product_sku']: opt_dict})
        return link_data_dict

    def get_product_conf_attributes_dict(self, odoo_product):
        """
        Extract each Simple Product's "Attribute: Value" pair (only configurable ones) to one single dict
        :param odoo_product: Odoo Product object
        :return: Dictionary with Product's "Attribute: Value" data
        """
        attr_dict = {}
        for attrs in odoo_product.product_template_attribute_value_ids.product_attribute_value_id:
            if attrs.attribute_id.name in [a.name for a in odoo_product.magento_conf_product.odoo_prod_category.x_magento_attr_ids]:
                attr_dict.update({self.to_upper(attrs.attribute_id.name): self.to_upper(attrs.name)})
        return attr_dict

    def save_magento_products_info_to_database(self, magento_websites, ml_simp_products, ml_conf_products,
                                               export_products, status_check):
        """
        Save Products' export_dates, websites, magento_statuses and log_messages to database
        :param magento_websites: Magento available websites related to current instance
        :param ml_simp_products: Dictionary contains metadata for selected Simple Products (Odoo products)
        :param ml_conf_products: Dictionary contains metadata for selected Configurable Products (Odoo categories)
        :param export_products: Magento Layer's Odoo Product to be exported
        :param status_check: Check if method runs as status check (Boolean)
        :return: None
        """
        for c_prod in ml_conf_products:
            odoo_product = ml_conf_products[c_prod]['conf_object']
            if ml_conf_products[c_prod]['log_message']:
                ml_conf_products[c_prod]['magento_status'] = 'log_error'

            values = self.prepare_data_before_save(ml_conf_products, c_prod, odoo_product, magento_websites,
                                                   status_check)
            odoo_product.write(values)

        for s_prod in ml_simp_products:
            export_product = export_products.filtered(lambda prod: prod.magento_sku == s_prod)
            conf_sku = ml_simp_products[s_prod].get('conf_sku')

            if ml_simp_products[s_prod]['log_message']:
                ml_simp_products[s_prod]['magento_status'] = 'log_error'
                self.save_error_message_to_log_book(
                    ml_simp_products[s_prod]['log_message'],
                    ml_conf_products.get(conf_sku, {}).get('log_message', ''),
                    export_product.id
                )

            values = self.prepare_data_before_save(ml_simp_products, s_prod, export_product, magento_websites,
                                                   status_check)
            export_product.write(values)

    def prepare_data_before_save(self, ml_products, prod_sku, odoo_product, websites, status_check):
        mag_prod_websites = ml_products[prod_sku].get('magento_website_ids', [])
        odoo_websites = {str(p.magento_website_id) for p in odoo_product.magento_website_ids}

        values = {'magento_status': ml_products[prod_sku]['magento_status']}

        # assign Magento product id to Product in Magento Layer
        mag_prod_id = ml_products[prod_sku].get('magento_prod_id')
        if mag_prod_id:
            if str(mag_prod_id) != odoo_product.magento_product_id:
                values.update({'magento_product_id': mag_prod_id})
        elif odoo_product.magento_product_id:
            values.update({'magento_product_id': ''})

        # check if Product's website(s) are the same in Odoo ML and Magento (M2 has priority)
        if mag_prod_websites:
            if odoo_websites != set(mag_prod_websites):
                ids = [w.id for w in websites if str(w.magento_website_id) in mag_prod_websites]
                values.update({'magento_website_ids': [(6, 0, ids)]})
        elif odoo_websites:
            values.update({'magento_website_ids': [(5, 0, 0)]})

        # add product categories to Simple Products
        if ml_products[prod_sku].get('product_categ'):
            values.update({'category_ids': [(6, 0, ml_products[prod_sku]['product_categ'])]})

        if not status_check:
            if ml_products[prod_sku]['to_export']:
                values.update({'magento_export_date': ml_products[prod_sku]['export_date_to_magento']})

            if ml_products[prod_sku]['force_update'] and ml_products[prod_sku]['magento_status'] != 'log_error':
                ml_products[prod_sku]['force_update'] = False
                values.update({'force_update': False})

        if ml_products[prod_sku]['force_update']:
            values.update({'force_update': True})

        return values

    def save_error_message_to_log_book(self, simp_log_message, conf_log_message, product_id):
        """
        Save Product's Error Message to Product's log book
        :param simp_log_message: Simple Product log message
        :param conf_log_message: Conf.Product log message
        :param product_id: Id of Odoo product in Magento Layer
        :return: None
        """
        vals = {
            'magento_log_message': simp_log_message,
            'magento_log_message_conf': conf_log_message
        }
        log_book = self.env['magento.product.log.book'].search([('magento_product_id', '=', product_id)])
        if not len(log_book):
            vals.update({'magento_product_id': product_id})
            log_book.create(vals)
        else:
            log_book.write(vals)

    def process_manually(self):
        """
        Process Product's Export (create/update) with regular Magento API process (without RabbitMQ)
        :return: None
        """
        self.ensure_one()
        self.process_products_export_to_magento(self.id)

    def status_check_of_export(self):
        """
        Check (Update) Product(s) Export Status
        """
        status_check = self.env.context.get("status_check", False)
        single = self.env.context.get("single", False)
        self.process_products_export_to_magento(self.id if single else 0, status_check)

    def delete_in_magento(self):
        """
        Delete Simple Product in Magento, available in Magento Product Form view for products with Magento Product Id
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
                'magento_website_ids': [(5, 0, 0)]
            })

    def to_html_listitem(self, attributes, lang_code):
        lst = '<ul>'
        for attr in attributes:
            if attr['attribute_value']:
               lst += "<li>" + attr.with_context(lang=lang_code)['attribute_value'] + "</li>"
        return lst + "</ul>"

    @staticmethod
    def to_upper(val):
        if val:
            return "".join(str(val).split()).upper()
        else:
            return val

    @staticmethod
    def format_to_magento_date(odoo_date):
        if odoo_date:
            return datetime.strftime(odoo_date, MAGENTO_DATETIME_FORMAT)
        else:
            return ""
