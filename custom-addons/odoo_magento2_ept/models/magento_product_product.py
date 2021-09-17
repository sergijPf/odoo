# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
"""
Describes fields and methods for Magento products
"""
import json
from datetime import datetime, timedelta
from odoo import fields, models, _
from odoo.exceptions import UserError
from .api_request import req, create_search_criteria
from ..python_library.php import Php


MAGENTO_DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'
PRODUCT_PRODUCT = 'product.product'
STOCK_INVENTORY = 'stock.inventory'
COMMON_LOG_LINES_EPT = 'common.log.lines.ept'
MAGENTO_PRODUCT_TEMPLATE = 'magento.product.template'
MAGENTO_PRODUCT_PRODUCT = 'magento.product.product'


class MagentoProductProduct(models.Model):
    """
    Describes fields and methods for Magento products
    """
    _name = MAGENTO_PRODUCT_PRODUCT
    _description = 'Magento Product'
    _rec_name = 'magento_product_name'

    magento_instance_id = fields.Many2one(
        'magento.instance',
        'Instance',
        help="This field relocates magento instance"
    )
    magento_product_id = fields.Char(string="Magento Product", help="Magento Product Id")
    magento_product_name = fields.Char(
        string="Magento Product Name",
        help="Magento Product Name",
        translate=True
    )
    magento_tmpl_id = fields.Many2one(
        MAGENTO_PRODUCT_TEMPLATE,
        string="Magento Product template",
        help="Magento Product template",
        ondelete="cascade"
    )
    odoo_product_id = fields.Many2one(
        PRODUCT_PRODUCT,
        string='Odoo Product',
        required=True,
        ondelete='restrict',
        copy=False
    )
    magento_website_ids = fields.Many2many(
        'magento.website',
        string='Magento Websites',
        readonly=False,
        domain="[('magento_instance_id','=',magento_instance_id)]",
        help='Magento Websites'
    )
    product_type = fields.Selection([
        ('simple', 'Simple Product'),
        ('configurable', 'Configurable Product'),
        ('virtual', 'Virtual Product'),
        ('downloadable', 'Downloadable Product'),
        ('group', 'Group Product'),
        ('bundle', 'Bundle Product'),
    ], string='Magento Product Type', help='Magento Product Type', default='simple')
    created_at = fields.Date(
        string='Product Created At',
        help="Date when product created into Magento"
    )
    updated_at = fields.Date(
        string='Product Updated At',
        help="Date when product updated into Magento"
    )

    magento_sku = fields.Char(string="Magento Product SKU", help="Magento Product SKU")
    description = fields.Text(string="Product Description", help="Description", translate=True)
    short_description = fields.Text(
        string='Product Short Description',
        help='Short Description',
        translate=True
    )
    magento_product_image_ids = fields.One2many(
        'magento.product.image',
        'magento_product_id',
        string="Magento Product Images",
        help="Magento Product Images"
    )
    sync_product_with_magento = fields.Boolean(
        string='Sync Product with Magento',
        help="If Checked means, Product synced With Magento Product"
    )
    active_product = fields.Boolean('Odoo Product Active', related="odoo_product_id.active")
    active = fields.Boolean("Active", default=True)
    image_1920 = fields.Image(related="odoo_product_id.image_1920")
    product_template_attribute_value_ids = fields.Many2many(
        related='odoo_product_id.product_template_attribute_value_ids')
    qty_available = fields.Float(related='odoo_product_id.qty_available')
    lst_price = fields.Float(related='odoo_product_id.lst_price')
    standard_price = fields.Float(related='odoo_product_id.standard_price')
    currency_id = fields.Many2one(related='odoo_product_id.currency_id')
    valuation = fields.Selection(related='odoo_product_id.product_tmpl_id.valuation')
    cost_method = fields.Selection(related='odoo_product_id.product_tmpl_id.cost_method')
    company_id = fields.Many2one(related='odoo_product_id.company_id')
    uom_id = fields.Many2one(related='odoo_product_id.uom_id')
    uom_po_id = fields.Many2one(related='odoo_product_id.uom_po_id')
    total_magento_variants = fields.Integer(related='magento_tmpl_id.total_magento_variants')

    #added by SPf
    prod_categ_name = fields.Char(string='Magento Product Category', related='odoo_product_id.categ_id.magento_name',
                                  store=True)
    odoo_prod_categ = fields.Many2one(string='Odoo Product Category', related='odoo_product_id.categ_id')
    magento_prod_categ = fields.Many2one(string='Magento Product Category (Configurable Product)',
                                         related='odoo_product_id.categ_id', store=True)
    x_magento_name = fields.Char(string='Name for Magento', related='odoo_product_id.x_magento_name')
    magento_export_date = fields.Datetime(string="Last Export Date", copy=False)
    magento_export_date_conf = fields.Datetime(string="Configurable Product last Export Date")
    magento_status = fields.Selection([
        ('not_exported', 'not Exported'),
        ('in_process', 'In Process'),
        ('in_magento', 'In Magento'),
        ('need_to_link', 'Need to be Linked'),
        ('log_error', 'Error to Export'),
        ('update_needed', 'Need to Update'),
        ('deleted', 'Deleted in Magento')
    ], string='Export Status', help='The status of Product Export to Magento ',
        default='not_exported')

    _sql_constraints = [('_magento_product_unique_constraint',
                         'unique(magento_sku,magento_instance_id,magento_product_id)',
                         "Magento Product must be unique")]

    def unlink(self):
        unlink_magento_products = self.env[MAGENTO_PRODUCT_PRODUCT]
        unlink_magento_templates = self.env[MAGENTO_PRODUCT_TEMPLATE]
        for magento_product in self:
            # Check if the product is last product of this template...
            if not unlink_magento_templates or (unlink_magento_templates and unlink_magento_templates != magento_product.magento_tmpl_id):
                unlink_magento_templates |= magento_product.magento_tmpl_id
            unlink_magento_products |= magento_product
        res = super(MagentoProductProduct, unlink_magento_products).unlink()
        # delete templates after calling super, as deleting template could lead to deleting
        # products due to ondelete='cascade'
        if not unlink_magento_templates.magento_product_ids:
            unlink_magento_templates.unlink()
        self.clear_caches()
        return res

    def toggle_active(self):
        """ Archiving related magento.product.template if there is not any more active magento.product.product
        (and vice versa, unarchiving the related magento product template if there is now an active magento.product.product) """
        result = super().toggle_active()
        # We deactivate product templates which are active with no active variants.
        tmpl_to_deactivate = self.filtered(lambda product: (product.magento_tmpl_id.active
                                                            and not product.magento_tmpl_id.magento_product_ids)).mapped('magento_tmpl_id')
        # We activate product templates which are inactive with active variants.
        tmpl_to_activate = self.filtered(lambda product: (not product.magento_tmpl_id.active
                                                          and product.magento_tmpl_id.magento_product_ids)).mapped('magento_tmpl_id')
        (tmpl_to_deactivate + tmpl_to_activate).toggle_active()
        return result

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

    def create_product_inventory(self, instance):
        """
        This method is used to import product stock from magento,
        when Multi inventory sources is not available.
        It will create a product inventory.
        :param instance: Instance of Magento
        :return: True
        """
        stock_to_import = []
        stock_inventory = self.env[STOCK_INVENTORY]
        log_book_id = False
        if instance.is_import_product_stock:
            import_stock_location = instance.import_stock_warehouse
            location = import_stock_location and import_stock_location.lot_stock_id
            if location:
                model_id = self.env[COMMON_LOG_LINES_EPT].get_model_id(STOCK_INVENTORY)
                log_book_id = self.env["common.log.book.ept"].create({
                    'type': 'import',
                    'module': 'magento_ept',
                    'model_id': model_id,
                    'magento_instance_id': instance.id
                })
                stock_to_import = self.get_product_stock(stock_to_import, instance, location, log_book_id)
                if stock_to_import:
                    stock_inventory.create_stock_inventory_ept(stock_to_import, location, True)
                if not log_book_id.log_lines:
                    log_book_id.sudo().unlink()
                    log_book_id = False
            else:
                raise UserError(_("Please Choose Import product stock for %s location", import_stock_location.name))
        return log_book_id

    def get_product_stock(self, stock_to_import, instance, location, log_book_id):
        """
        Call stockItems API call and make dictionary
        :param stock_to_import: dictionary for import stock
        :param instance: Magento Instance object
        :param location: stock warehouse object
        :param log_book_id: common log book object
        :return: dictionary for import stock
        """
        consumable_products = []
        try:
            api_url = '/V1/stockItems/lowStock?scopeId=0&qty=10000000000&pageSize=100000'
            response = req(instance, api_url)
        except Exception:
            log_book_id.write({
                'log_lines': [(0, 0, {
                    'message': "Request is not satisfied please check API connection"
                })]
            })

        if response.get('items'):
            for inventory in response.get('items'):
                magento_prod = self.search([
                    ('magento_product_id', '=', inventory.get('product_id')),
                    ('magento_instance_id', '=', instance.id),
                    ('magento_website_ids', '!=', False)
                ], limit=1)
                qty = inventory.get('qty')
                if magento_prod and qty > 0.0:
                    if magento_prod.odoo_product_id.type != 'product':
                        consumable_products.append(magento_prod.odoo_product_id.default_code)
                    else:
                        stock_to_import.append({
                            'product_id': magento_prod.odoo_product_id,
                            'product_qty': qty,
                            'location_id': location
                        })
            self.create_import_product_process_log(consumable_products, log_book_id)
        return stock_to_import

    def create_product_multi_inventory(self, instance, magento_locations):
        """
        This method is used to import product stock from magento,
        when Multi inventory sources is available.
        It will create a product inventory.
        :param instance: Instance of Magento
        :param magento_locations: Magento products object
        :return: True
        """
        stock_inventory = self.env[STOCK_INVENTORY]
        if instance.is_import_product_stock:
            consumable_products = []
            model_id = self.env[COMMON_LOG_LINES_EPT].get_model_id(STOCK_INVENTORY)
            log_book_id = self.env["common.log.book.ept"].create({
                'type': 'import',
                'module': 'magento_ept',
                'model_id': model_id,
                'magento_instance_id': instance.id
            })
            for magento_location in magento_locations:
                stock_to_import = []
                location = magento_location.import_stock_warehouse and \
                           magento_location.import_stock_warehouse.lot_stock_id
                if location:
                    search_criteria = create_search_criteria({'source_code': magento_location.magento_location_code})
                    query_string = Php.http_build_query(search_criteria)
                    try:
                        api_url = '/V1/inventory/source-items?%s' % query_string
                        response = req(instance, api_url)
                    except Exception as error:
                        log_book_id.write({
                            'log_lines': [(0, 0, {
                                'message': _("Error while requesting products" + str(error))
                            })]
                        })
                    stock_to_import, consumable_products = self.prepare_import_product_stock_dictionary(
                        response, instance, consumable_products, stock_to_import, location)
                    stock_inventory.create_stock_inventory_ept(stock_to_import, location, True)
                else:
                    raise UserError(_("Please Choose Import product stock location for %s") % magento_location.name)
            self.create_import_product_process_log(consumable_products, log_book_id)
        return True

    def prepare_import_product_stock_dictionary(
            self, response, instance, consumable_products, stock_to_import, location):
        """
        Prepare dictionary for import product stock from response.
        :param response: response received from Magento
        :param instance: Magento Instance object
        :param consumable_products: Dictionary of consumable products
        :param stock_to_import: Dictionary for import product stock
        :param location: warehouse in which stock will be imported
        :return: stock_to_import, consumable_products
        """
        if response and response.get('items'):
            for inventory in response.get('items'):
                magento_prod = self.search([
                    ('magento_sku', '=', inventory.get('sku')), ('magento_instance_id', '=', instance.id),
                    ('magento_website_ids', '!=', False)
                ], limit=1)
                if magento_prod:
                    stock_to_import, consumable_products = self.prepare_import_stock_dict(
                        inventory, magento_prod, consumable_products, stock_to_import, location)
        return stock_to_import, consumable_products

    @staticmethod
    def prepare_import_stock_dict(inventory, magento_prod, consumable_products, stock_to_import, location):
        """
        Prepare import stock dictionary
        :param inventory: response received from Magento
        :param magento_prod: Magento product product object
        :param consumable_products: Dictionary of consumable products
        :param stock_to_import: Dictionary for import product stock
        :param location: warehouse in which stock will be imported
        :return: stock_to_import, consumable_products
        """
        qty = inventory.get('quantity') or False
        if qty and qty > 0.0:
            if magento_prod.odoo_product_id.type != 'product':
                consumable_products.append(magento_prod.odoo_product_id.default_code)
            else:
                stock_to_import.append({
                    'product_id': magento_prod.odoo_product_id,
                    'product_qty': qty,
                    'location_id': location
                })
        return stock_to_import, consumable_products

    @staticmethod
    def create_import_product_process_log(consumable_products, log_book_id):
        """
        Generate process log for import product stock with consumable product.
        :param consumable_products: dictionary of consumable products
        :param log_book_id: common log book object
        """
        if consumable_products:
            message = "The following products have not been imported due to " \
                      "product type is other than 'Storable.'\n %s" % str(list(set(consumable_products)))
            log_book_id.write({
                'log_lines': [(0, 0, {
                    'message': message
                })]
            })

    @staticmethod
    def create_export_product_process_log(consumable_products, log_book_id):
        """
        Generate process log for export product stock with consumable product.
        :param consumable_products: dictionary of consumable products
        :param log_book_id: common log book object
        """
        if consumable_products:
            message = "The following products have not been exported due to " \
                      "product type is other than 'Storable.'\n %s" % str(list(set(consumable_products)))
            log_book_id.write({
                'log_lines': [(0, 0, {
                    'message': message
                })]
            })

    def export_multiple_product_stock_to_magento(self, instance):
        """
        This method is used to export multiple product stock from odoo to magento.
        :param instance: Instance of Magento
        :return:
        """
        stock_data = []
        consumable_products = []
        model_id = self.env[COMMON_LOG_LINES_EPT].get_model_id(MAGENTO_PRODUCT_PRODUCT)
        job = self.env['common.log.book.ept'].create({
            'name': 'Export Product Stock', 'type': 'export', 'module': 'magento_ept',
            'model_id': model_id, 'res_id': self.id, 'magento_instance_id': instance.id})
        export_product_stock = self.get_export_product_stock(instance, instance.warehouse_ids)
        if export_product_stock:
            for product_id, stock in export_product_stock.items():
                exp_product = self.search([
                    ('odoo_product_id', '=', product_id), ('magento_instance_id', '=', instance.id)], limit=1)
                if exp_product and stock >= 0.0:
                    if exp_product.odoo_product_id.type != 'product':
                        consumable_products.append(exp_product.odoo_product_id.default_code)
                    else:
                        product_stock_dict = {'sku': exp_product.magento_sku, 'qty': stock, 'is_in_stock': 1}
                        stock_data.append(product_stock_dict)
        self.create_export_product_process_log(consumable_products, job)
        if stock_data:
            data = {'skuData': stock_data}
            api_url = "/V1/product/updatestock"
            job = self.call_export_product_stock_api(instance, api_url, data, job, 'PUT')
        if not job.log_lines:
            job.sudo().unlink()

    def export_product_stock_to_multiple_locations(self, instance, magento_locations):
        """
        This method is used to export product stock to magento,
        when Multi inventory sources is available.
        It will create a product inventory.
        :param instance: Instance of Magento
        :param magento_locations: Magento products object
        :return: True
        """
        stock_data = []
        consumable_products = []
        model_id = self.env[COMMON_LOG_LINES_EPT].get_model_id(MAGENTO_PRODUCT_PRODUCT)
        job = self.env['common.log.book.ept'].create({
            'name': 'Export Product Stock', 'type': 'export', 'module': 'magento_ept',
            'model_id': model_id, 'res_id': self.id, 'magento_instance_id': instance.id})
        for magento_location in magento_locations:
            export_stock_locations = magento_location.mapped('export_stock_warehouse_ids')
            if export_stock_locations and export_stock_locations.ids:
                export_product_stock = self.get_export_product_stock(instance, export_stock_locations)
                if export_product_stock:
                    for product_id, stock in export_product_stock.items():
                        stock_data = self.prepare_export_product_stock_dict(
                            product_id, instance, stock, consumable_products, stock_data, magento_location)
            else:
                raise UserError(_("Please Choose Export product stock location for %s", magento_location.name))
        self.create_export_product_process_log(consumable_products, job)
        if stock_data:
            data = {'sourceItems': stock_data}
            api_url = "/V1/inventory/source-items"
            job = self.call_export_product_stock_api(instance, api_url, data, job, 'POST')
        if not job.log_lines:
            job.sudo().unlink()
        return True

    def prepare_export_product_stock_dict(
            self, product_id, instance, stock, consumable_products, stock_data, magento_location):
        """
        Prepare Export Product Stock Dictionary
        :param product_id: Odoo product id
        :param instance: Magneto instance
        :param stock: stock of product
        :param consumable_products: dictionary for consumable products
        :param stock_data: dictionary for export product stock
        :param magento_location: magento inventory location object
        :return: dictionary for export product stock
        """
        exp_product = self.search([
            ('odoo_product_id', '=', product_id), ('magento_instance_id', '=', instance.id)
        ], limit=1)
        if exp_product and stock >= 0.0:
            if exp_product.odoo_product_id.type != 'product':
                consumable_products.append(exp_product.odoo_product_id.default_code)
            else:
                stock_data.append({'sku': exp_product.magento_sku,
                                   'source_code': magento_location.magento_location_code,
                                   'quantity': stock, 'status': 1})
        return stock_data

    def get_export_product_stock(self, instance, export_stock_locations):
        """
        Get export product stock dictionary with stock.
        :param instance: Magento instance object
        :param export_stock_locations: Stock location object
        :return: Export product stock dictionary.
        """
        product_product_obj = self.env[PRODUCT_PRODUCT]
        instance_export_date = instance.last_update_stock_time
        if not instance_export_date:
            instance_export_date = datetime.today() - timedelta(days=365)
        product_ids = product_product_obj.get_products_based_on_movement_date_ept(
            instance_export_date, instance.company_id
        )
        export_product_stock = self.get_magento_product_stock_ept(
            instance, product_ids, product_product_obj, export_stock_locations)
        return export_product_stock

    @staticmethod
    def call_export_product_stock_api(instance, api_url, data, job, method_type):
        """
        Call export product stock API for single or multi tracking inventory.
        :param instance: Magento instance object
        :param api_url: API Call URL
        :param data: Dictionary to be passed.
        :param job: Common log book object
        :param method_type: Api Request Method type (PUT/POST)
        :return: common log book object
        """
        try:
            responses = req(instance, api_url, method_type, data)
        except Exception as error:
            raise UserError(_("Error while Export product stock " + str(error)))
        if responses:
            for response in responses:
                if isinstance(response, dict):
                    message = response.get('message')
                else:
                    message = responses.get(response)
                job.write({'log_lines': [(0, 0, {'message': message})]})
        return job

    @staticmethod
    def get_magento_product_stock_ept(instance, product_ids, prod_obj, warehouse):
        """
        This Method relocates check type of stock.
        :param instance: This arguments relocates instance of amazon.
        :param product_ids: This arguments product listing id of odoo.
        :param prod_obj: This argument relocates product object of common connector.
        :param warehouse:This arguments relocates warehouse of amazon.
        :return: This Method return product listing stock.
        """
        product_listing_stock = False
        if product_ids:
            if instance.magento_stock_field == 'free_qty':
                product_listing_stock = prod_obj.get_free_qty_ept(warehouse, product_ids)
            elif instance.magento_stock_field == 'virtual_available':
                product_listing_stock = prod_obj.get_forecasted_qty_ept(warehouse, product_ids)
        return product_listing_stock

    #added by SPf
    def process_products_export_to_magento(self, single=False):
        """
        The main method to process Products Export to Magento. The Product's Categories are treated as Configurable
        Products and regular Odoo Products as Simple Products in Magento.
        """
        # Abbreviation used below:
        # ml - magento_layer with products in Odoo
        # mi - magento_instance
        # prod - product
        # attr - attribute
        # conf - configurable(in Magento) aka category_name(Odoo)
        # simp - simple
        status_check = self.env.context.get("status_check", False)
        if single:
            export_products = single
            single = True
        else:
            active_product_ids = self._context.get("active_ids", [])
            export_products = self.env["magento.product.product"].browse(active_product_ids)

        # create dict with "configurable_product_name: [list_of_related_simple_product_ids]" for each magento instance
        # to implement pagination with specified threshold
        products_dict = {d.magento_instance_id: {} for d in export_products}
        for mi in products_dict:
            products = export_products.filtered(lambda p: p.magento_instance_id.id == mi.id)
            products_dict[mi].update({
                c.prod_categ_name: [s.id for s in products if s.prod_categ_name == c.prod_categ_name] for c in products
            })

        for mi in products_dict:
            # implement pagination for large datasets
            threshold = 300
            selection = []
            category_list = list(products_dict[mi].keys())
            for categ in category_list:
                selection += products_dict[mi][categ]
                if categ != category_list[-1] and len(selection) < threshold:
                    continue
                else:
                    export_products = self.env["magento.product.product"].browse(selection)
                    selection = []

                    # create dictionaries which collect meta-data for selected configurable and simple products
                    ml_conf_products_dict, ml_simp_products_dict = self.create_products_metadata_dict(
                        export_products.filtered(lambda p: p.magento_instance_id.id == mi.id),
                        single
                    )

                    # get selected products from Magento if any
                    magento_conf_products = self.get_products_from_magento(mi, ml_conf_products_dict)
                    magento_simp_products = self.get_products_from_magento(mi, ml_simp_products_dict)

                    # update conf/simp dictionaries with Magento data
                    for prod in magento_conf_products:
                        self.update_conf_product_dict_with_magento_data(prod, ml_conf_products_dict)
                    del magento_conf_products
                    for prod in magento_simp_products:
                        self.update_simp_product_dict_with_magento_data(prod, ml_simp_products_dict)
                    del magento_simp_products

                    # create attribute-sets dict and get their id/attribute(options) data from Magento
                    attr_sets = self.create_attribute_sets_dict(mi, ml_conf_products_dict)

                    # check product's export statuses
                    self.check_config_products_to_export(ml_conf_products_dict, attr_sets)
                    self.check_simple_products_to_export(mi.id, mi.magento_website_ids, ml_simp_products_dict,
                                                         ml_conf_products_dict)

                    if status_check:
                        self.save_magento_products_info_to_database(mi.id, mi.magento_website_ids, ml_simp_products_dict,
                                                                    ml_conf_products_dict, True)
                    else:
                        # filter selected Odoo Products and their Configurable Products to be exported to Magento
                        conf_prod_to_export = {
                            k: v for k, v in ml_conf_products_dict.items() if v['to_export'] and not v['log_message']
                        }
                        simp_prod_to_export = export_products.filtered(
                            lambda prd: prd.magento_instance_id.id == mi.id and
                                         prd.magento_sku in ml_simp_products_dict and
                                         ml_simp_products_dict[prd.magento_sku]['to_export'] is True and
                                         not ml_simp_products_dict[prd.magento_sku]['log_message']
                        )

                        self.process_config_products_create_or_update(mi, conf_prod_to_export, ml_conf_products_dict,
                                                                      attr_sets, single)
                        # check if product attributes of all selected simple products exist in Magento
                        # log error when product has no attributes and create new attribute options(swatch) if needed
                        self.check_product_attributes_exist_in_magento(mi, simp_prod_to_export, attr_sets,
                                                                       ml_simp_products_dict)
                        self.process_simple_products_create_or_update(mi, simp_prod_to_export, ml_simp_products_dict,
                                                                      attr_sets, ml_conf_products_dict, single)
                        # save data with export dates, magento statuses and log_messages to Db
                        self.save_magento_products_info_to_database(mi.id, mi.magento_website_ids, ml_simp_products_dict,
                                                                    ml_conf_products_dict, False)

    def create_products_metadata_dict(self, export_products, single):
        """
        Create dictionary which contains metadata for selected Configurable(Odoo categories) and Simple Products
        :param export_products: Magento Layer Odoo Product to be exported
        :param single: Odoo product in case of process export directly (Odoo-Magento)
        :return: Configurable and Simple products dictionary
        """
        products_dict_c = {}
        products_dict_c.update({
            c.prod_categ_name: {
                'name': c.magento_prod_categ.name,
                'attribute_set': c.magento_prod_categ.magento_attr_set,
                'config_attr': {a.name for a in c.magento_prod_categ.magento_assigned_attr},
                'children': [],
                'log_message': '',
                'export_date_to_magento': c.magento_export_date_conf,
                'latest_update_date': c.magento_prod_categ.write_date,
                'to_export': True
            } for c in export_products if c.prod_categ_name
        })

        products_dict_s = {}
        text = "Product Category is missing 'Magento Product Name' field . \n"
        if single and export_products.magento_status == 'deleted':
            export_products.write({'magento_status': 'not_exported'})
        products_dict_s.update({
            s.magento_sku: {
                'category_name': s.prod_categ_name,
                'log_message': '' if s.prod_categ_name else text,
                'export_date_to_magento': s.magento_export_date,
                'latest_update_date': max(s.odoo_product_id.write_date, s.odoo_product_id.product_tmpl_id.write_date),
                'conf_attributes': self.get_product_conf_attributes_dict(s),
                'magento_status': s.magento_status,
                'to_export': True
            } for s in export_products if s.magento_status != 'deleted'
        })

        return products_dict_c, products_dict_s

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
        ml_conf_products_dict[magento_prod.get('sku')].update({
            'magento_type_id': magento_prod.get('type_id'),
            'magento_attr_set_id': magento_prod.get("attribute_set_id"),
            'magento_conf_prod_options': attr_opt,
            'children': children,
            'magento_configurable_product_link_data': self.convert_to_dict(link_data),
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
        ml_simp_products_dict[magento_prod.get("sku")].update({
            'magento_type_id': magento_prod.get('type_id'),
            'magento_prod_id': magento_prod.get("id"),
            'magento_update_date': magento_prod.get("updated_at"),
            'magento_website_ids': website_ids
        })

    def check_config_products_to_export(self, ml_conf_products_dict, attr_sets):
        """
        Check if Configurable Product Export to Magento needed
        :param ml_conf_products_dict: Dictionary contains metadata for selected Configurable Products (Odoo categories)
        :param attr_sets: Attribute set dictionary with unique data for selected products
        :return: None
        """
        for prod in ml_conf_products_dict:
            if ml_conf_products_dict[prod]['log_message']:
                ml_conf_products_dict[prod]['to_export'] = False
                continue

            # apply compatible date format to compare dates
            exp_date_c = self.format_to_magento_date(ml_conf_products_dict[prod]['export_date_to_magento'])
            upd_date_c = self.format_to_magento_date(ml_conf_products_dict[prod]['latest_update_date'])
            mag_date_c = ml_conf_products_dict[prod].get('magento_update_date', '')
            mag_date_c = mag_date_c if mag_date_c else ''

            if not exp_date_c:
                continue
            if exp_date_c > upd_date_c:
                if mag_date_c >= exp_date_c:
                    # check if assign attributes and attribute-set are the same in Magento and Odoo
                    if ml_conf_products_dict[prod]['magento_type_id'] == 'configurable':
                        attr_set_name = ml_conf_products_dict[prod]['attribute_set']
                        mag_attr_set_id = ml_conf_products_dict[prod]['magento_attr_set_id']
                        if mag_attr_set_id == attr_sets[attr_set_name]['id']:
                            if ml_conf_products_dict[prod]['attribute_set']:
                                mag_attr_options = ml_conf_products_dict[prod]['magento_conf_prod_options']
                                check_assign_attr = self.check_config_product_assign_attributes(
                                    mag_attr_options,
                                    attr_sets[attr_set_name]['attributes'], ml_conf_products_dict[prod]['config_attr']
                                )
                                if check_assign_attr:
                                    ml_conf_products_dict[prod]['to_export'] = False

    def check_simple_products_to_export(self, instance_id, magento_websites, ml_simp_products, ml_conf_products):
        """
        Check if Simple Product Export to Magento needed
        :param instance_id: Magento Instance ID
        :param magento_websites: Magento available websites related to current instance
        :param ml_simp_products: Dictionary contains metadata for selected Simple Products (Odoo products)
        :param ml_conf_products: Dictionary contains metadata for selected Configurable Products (Odoo categories)
        :return: None
        """
        remove_items = []
        for prod in ml_simp_products:
            categ_name = ml_simp_products[prod]['category_name']
            if ml_simp_products[prod]['log_message'] or ml_conf_products[categ_name]['log_message']:
                ml_simp_products[prod]['to_export'] = False
                if categ_name and ml_conf_products[categ_name]['log_message']:
                    text = "Configurable Product - %s for the current simple product is not ok. " \
                           "Please check it first.\n" % categ_name
                    ml_simp_products[prod]['log_message'] += text
                continue

            # apply compatible date format to compare dates
            exp_date_s = self.format_to_magento_date(ml_simp_products[prod]['export_date_to_magento'])
            upd_date_s = self.format_to_magento_date(ml_simp_products[prod]['latest_update_date'])
            upd_date_c = self.format_to_magento_date(ml_conf_products[categ_name]['latest_update_date'])
            mag_date_s = ml_simp_products[prod].get('magento_update_date', '')
            mag_date_s = mag_date_s if mag_date_s else ''

            if not exp_date_s:
                continue
            if exp_date_s > upd_date_s and exp_date_s > upd_date_c:
                if mag_date_s >= exp_date_s:
                    if not ml_conf_products[categ_name]['to_export']:
                        if ml_simp_products[prod]['magento_prod_id'] in ml_conf_products[categ_name]['children']:
                            ml_simp_products[prod]['to_export'] = False
                            values = {}
                            domain = [('magento_instance_id', '=', instance_id), ('magento_sku', '=', prod)]
                            magento_product = self.env['magento.product.product'].search(domain)
                            website_ids = ml_simp_products[prod].get('magento_website_ids', [])

                            if ml_simp_products[prod]['magento_status'] != 'in_magento':
                                values.update({'magento_status': 'in_magento'})
                            if {str(p.id) for p in magento_product.magento_website_ids} != set(website_ids):
                                ids = [w.id for w in magento_websites if str(w.magento_website_id) in website_ids]
                                values.update({'magento_website_ids': [(6, 0, ids)]})
                            if values:
                                magento_product.write(values)

                            # delete error messages if any
                            log_book = self.env['magento.product.log.book'].search(
                                [('magento_product_id', '=', magento_product.id)])
                            if log_book:
                                log_book.write({'magento_log_message': '', 'magento_log_message_conf': ''})

                            # will be removed from ml_simp_products
                            remove_items.append(prod)
                        else:
                            ml_simp_products[prod]['magento_status'] = 'need_to_link'
                    elif ml_simp_products[prod]['magento_status'] == 'in_magento':
                        ml_simp_products[prod]['magento_status'] = 'update_needed'
                else:
                    if ml_simp_products[prod]['magento_status'] not in ['log_error', 'in_process']:
                        ml_simp_products[prod]['magento_status'] = 'update_needed'
            else:
                if ml_simp_products[prod]['magento_status'] != 'log_error':
                    ml_simp_products[prod]['magento_status'] = 'update_needed'

        # remove products from ml_simp_products_dict which are already in Magento and have no need to be updated
        if remove_items:
            for prod in remove_items:
                del ml_simp_products[prod]

    def process_config_products_create_or_update(self, instance, conf_prod_to_export, ml_conf_products_dict, attr_sets, single):
        # if there are some config.products to export
        for prod in conf_prod_to_export:
            # check if attribute_set_id and assign_attributes are defined in configurable product
            mag_attr_set = conf_prod_to_export[prod]['attribute_set']
            prod_attr_set_id = attr_sets[mag_attr_set]['id']
            prod_conf_attr = conf_prod_to_export[prod]['config_attr']

            if not prod_attr_set_id:
                text = "Missed 'Magento Product Attribute Set' for %s configurable product.\n" % prod
                ml_conf_products_dict[prod]['log_message'] += text
                continue

            if not prod_conf_attr:
                text = "Missed 'Configurable Attribute(s)' for %s configurable product.\n" % prod
                ml_conf_products_dict[prod]['log_message'] += text
                continue

            # check if configurable attributes of all selected products exist in Magento
            # logs error when attribute doesn't exist in Magento
            available_attributes = [self.to_upper(a['default_label']) for a in attr_sets[mag_attr_set]['attributes']]
            conf_prod_attr = [self.to_upper(c) for c in prod_conf_attr if c]
            if not self.check_product_attr_are_in_attributes_list(available_attributes, conf_prod_attr):
                text = "Some of configurable attributes of %s Product doesn't exist in Magento. " \
                       "It has to be created at first on Magento side.\n" % prod
                ml_conf_products_dict[prod]['log_message'] += text
                continue

            # check & update (PUT) every single conf.product if it exists in Magento and there are no errors
            if ml_conf_products_dict[prod].get('magento_update_date', ''):
                if not ml_conf_products_dict[prod]['magento_type_id'] == 'configurable':
                    text = "Product with the following sku - \"%s\" already exists in Magento. " \
                        "And it's type is not Configurable.\n" % prod
                    ml_conf_products_dict[prod]['log_message'] += text

                # check if assign attributes are the same in Magento and Odoo
                mag_attr_options = ml_conf_products_dict[prod]['magento_conf_prod_options']
                check_assign_attr = self.check_config_product_assign_attributes(mag_attr_options,
                                                                                attr_sets[mag_attr_set]['attributes'],
                                                                                prod_conf_attr)
                conf_prod = self.update_single_conf_product_in_magento(instance, prod, prod_attr_set_id,
                                                                       ml_conf_products_dict,
                                                                       check_assign_attr)
                # update magento data in ml_conf_products_dict, later will be used while linking with simple prod
                if conf_prod:
                    self.update_conf_product_dict_with_magento_data(conf_prod, ml_conf_products_dict)
        # create (POST) new configurable products to Magento
        # if single - with regular API, else - via async request (RabbitMQ)
        new_conf_prod = {k: v for k, v in ml_conf_products_dict.items() if
                         not ml_conf_products_dict[k].get('magento_update_date', '') and
                         not ml_conf_products_dict[k]['log_message']}
        if not new_conf_prod:
            return
        if single:
            res = self.export_single_conf_product_to_magento(instance, new_conf_prod, ml_conf_products_dict, attr_sets)
            if res:
                self.update_conf_product_dict_with_magento_data(res, ml_conf_products_dict)
        else:
            self.export_new_conf_products_to_magento_in_bulk(instance, new_conf_prod, ml_conf_products_dict, attr_sets)

    def process_simple_products_create_or_update(self, instance, simp_prod_to_export, ml_simp_products_dict, attr_sets,
                                                 ml_conf_products_dict, single):
        self.check_simple_products_for_errors_before_export(simp_prod_to_export, ml_simp_products_dict,
                                                            ml_conf_products_dict, attr_sets)
        # process simple products update (async) in Magento
        update_simple_prod = {}
        for s in ml_simp_products_dict:
            if ml_simp_products_dict[s].get('magento_update_date', '') and not ml_simp_products_dict[s]['log_message']:
                update_simple_prod.update({s: ml_simp_products_dict[s]})

        if update_simple_prod:
            if single:
                prod_attr_set = simp_prod_to_export.magento_prod_categ.magento_attr_set
                available_attributes = attr_sets[prod_attr_set]['attributes']
                # to skip this step if only linking with parent needs to be done
                if ml_simp_products_dict[simp_prod_to_export.magento_sku]['magento_status'] != 'need_to_link':
                    res = self.export_single_simple_product_to_magento(instance, simp_prod_to_export,
                                                                       ml_simp_products_dict, available_attributes,
                                                                       attr_sets[prod_attr_set]['id'], 'PUT')
                    if res:
                        self.update_simp_product_dict_with_magento_data(res, ml_simp_products_dict)
                    else:
                        return

                self.assign_attr_to_config_product(instance, simp_prod_to_export, available_attributes,
                                                   ml_conf_products_dict, ml_simp_products_dict)
                if not ml_simp_products_dict[simp_prod_to_export.magento_sku]['log_message']:
                    self.link_simple_to_config_product_in_magento(instance, simp_prod_to_export, ml_conf_products_dict,
                                                                  ml_simp_products_dict)
            else:
                self.process_simple_products_export_in_bulk(instance, simp_prod_to_export, update_simple_prod,
                                                            ml_conf_products_dict, ml_simp_products_dict, attr_sets, 'PUT')

        # process new simple products creation in Magento, assign attributes to config.products and link them
        new_simple_prod = {}
        for s in ml_simp_products_dict:
            if not ml_simp_products_dict[s].get('magento_update_date') and not ml_simp_products_dict[s]['log_message']:
                new_simple_prod.update({s: ml_simp_products_dict[s]})

        if new_simple_prod:
            if single:
                prod_attr_set = simp_prod_to_export.magento_prod_categ.magento_attr_set
                available_attributes = attr_sets[prod_attr_set]['attributes']
                res = self.export_single_simple_product_to_magento(instance, simp_prod_to_export, ml_simp_products_dict,
                                                                   available_attributes, attr_sets[prod_attr_set]['id'],
                                                                   'POST')
                if res:
                    self.update_simp_product_dict_with_magento_data(res, ml_simp_products_dict)
                    self.assign_attr_to_config_product(instance, simp_prod_to_export, available_attributes,
                                                       ml_conf_products_dict, ml_simp_products_dict)
                    if not ml_simp_products_dict[simp_prod_to_export.magento_sku]['log_message']:
                        self.link_simple_to_config_product_in_magento(instance, simp_prod_to_export,
                                                                      ml_conf_products_dict, ml_simp_products_dict)
            else:
                self.process_simple_products_export_in_bulk(instance, simp_prod_to_export, new_simple_prod,
                                                            ml_conf_products_dict, ml_simp_products_dict, attr_sets, 'POST')

    def check_simple_products_for_errors_before_export(self, simp_prod_to_export, ml_simp_products_dict,
                                                       ml_conf_products_dict, attr_sets):
        for prod in simp_prod_to_export:
            categ_name = prod.prod_categ_name
            # check if any log_messages for current product or it's configurable
            if ml_simp_products_dict[prod.magento_sku]['log_message']:
                continue
            elif ml_conf_products_dict[categ_name]['log_message']:
                text = "Configurable product for the current simple product is not ok. Please check it first.\n"
                ml_simp_products_dict[prod.magento_sku]['log_message'] += text
                continue

            # check if product has assign attributes defined in it's configurable product
            simp_prod_attr = prod.odoo_product_id.product_template_attribute_value_ids.product_attribute_value_id
            check_assign_attr = self.check_product_attr_are_in_attributes_list(
                [a.attribute_id.name for a in simp_prod_attr], ml_conf_products_dict[categ_name]['config_attr'])
            if not check_assign_attr:
                text = 'Simple product - %s is missing attribute(s) defined as configurable in ' \
                       'Product Category table.\n' % prod.magento_sku
                ml_simp_products_dict[prod.magento_sku]['log_message'] += text
                continue

            prod_attr_set = prod.magento_prod_categ.magento_attr_set
            available_attributes = attr_sets[prod_attr_set]['attributes']

            # check if configurable product already contains such set of "Attribute: Value" pair.
            # Return False if not - will be unable to link it further
            check_attr_values = self.check_products_set_of_attribute_values(ml_conf_products_dict, categ_name,
                                                                            simp_prod_attr, available_attributes,
                                                                            ml_simp_products_dict, prod.magento_sku)
            if check_attr_values:
                text = "The same configurable Set of Attribute Values was found in " \
                       "Product - %s.\n" % check_attr_values
                ml_simp_products_dict[prod.magento_sku]['log_message'] += text
                continue

            # the code below relates only to Simple Products to be updated in Magento
            if ml_simp_products_dict[prod.magento_sku].get('magento_update_date') and \
                    ml_simp_products_dict[prod.magento_sku]['magento_type_id'] != 'simple':
                text = "The Product with such sku is already in Magento. (And it's type isn't Simple Product.)\n"
                ml_simp_products_dict[prod.magento_sku]['log_message'] += text

    def update_single_conf_product_in_magento(self, magento_instance, magento_sku, attribute_set_id, ml_conf_products,
                                              check_assign_attr):
        """
        Export(update) configurable product to Magento
        :param magento_instance: Instance of Magento
        :param magento_sku: Magento Product sku
        :param attribute_set_id: ID of Product's attribute set defined in Magento
        :param ml_conf_products: Dictionary contains metadata for selected Configurable Products (Odoo categories)
        :param check_assign_attr: Assign attributes are the same in Odoo and Magento (Boolean)
        :return: Updated Configurable Product Dictionary from Magento or empty Dictionary if error
        """
        data = {
            "product": {
                "name": magento_sku.upper(),
                "type_id": "configurable",
                "attribute_set_id": attribute_set_id
            }
        }

        # if not True - will unlink all related simple products linked to current configurable
        if not check_assign_attr:
            data['product'].update({"extension_attributes": {"configurable_product_links": []}})

        try:
            api_url = '/all/V1/products/%s' % magento_sku
            response = req(magento_instance, api_url, 'PUT', data)
        except Exception:
            text = "Error while config.product update in Magento.\n"
            ml_conf_products[magento_sku]['log_message'] += text
            return {}

        if response.get("sku"):
            ml_conf_products[magento_sku]['export_date_to_magento'] = response.get("updated_at")
            return response
        else:
            return {}

    def check_product_attributes_exist_in_magento(self, magento_instance, odoo_products, available_attributes,
                                                  ml_product_dict):
        """
        Check if Product's Attributes exist in Magento.
        :param magento_instance: Instance of Magento
        :param odoo_products: Selected Odoo Products to be exported
        :param available_attributes: Dictionary with defined Attributes and their values in Magento
        :param ml_product_dict: Dictionary contains metadata for selected Simple Products (Odoo products)
        :return: None
        """
        for prod in odoo_products:
            prod_attr = prod.odoo_product_id.product_template_attribute_value_ids.product_attribute_value_id
            if not len(prod_attr):
                text = "Product - %s has no attributes.\n" % prod.magento_sku
                ml_product_dict[prod.magento_sku]['log_message'] += text
                continue

            prod_attr_set = prod.magento_prod_categ.magento_attr_set
            avail_attr_list = available_attributes[prod_attr_set]['attributes']
            prod_attr_list = [(a.attribute_id.name, a.name) for a in prod_attr]

            # add Product Life Phase attribute (aka x_status)
            if prod.odoo_product_id.x_status:
                prod_attr_list.append(("PRODUCTLIFEPHASE", self.to_upper(prod.odoo_product_id.x_status)))

            # logs if any of attributes are missed in Magento and creates new attr.option in Magento if needed
            for attr in prod_attr_list:
                at = next((a for a in avail_attr_list if a and
                           self.to_upper(attr[0]) == self.to_upper(a.get('default_label'))), {})
                if not at:
                    text = "Attribute - %s has to be created on Magento side and attached " \
                           "to related Attribute Set.\n" % attr[0]
                    ml_product_dict[prod.magento_sku]['log_message'] += text
                else:
                    if self.to_upper(attr[1]) not in [self.to_upper(i.get('label')) for i in at['options']]:
                        _id, err = self.create_new_attribute_option_in_magento(magento_instance, at['attribute_code'],
                                                                               attr[1])
                        if err:
                            ml_product_dict[prod.magento_sku]['log_message'] += err
                        else:
                            for a in available_attributes[prod_attr_set]['attributes']:
                                if a['attribute_id'] == at['attribute_id']:
                                    a['options'].append({
                                        'label': attr[1].upper(),
                                        'value': _id
                                    })
                                    break

    def create_new_attribute_option_in_magento(self, magento_instance, attribute_code, attribute_option):
        """
        Creates new option(swatch) for defined attribute in Magento
        :param magento_instance: Instance of Magento
        :param attribute_code: The Code of Attribute defined in Magento
        :param attribute_option: Dictionary with defined Attributes and their values in Magento
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
        magento_storeviews = self.env["magento.storeview"].search([('magento_instance_id', '=', magento_instance.id),
                                                                   ('active', '=', True)])
        # get store_views from Magento to update store_labels field, if error - store_label remains [] (admin only)
        if magento_storeviews:
            store_labels = []
            for view in magento_storeviews:
                store_labels.append({"store_id": view.magento_storeview_id, "label": str(attribute_option).upper()})
            data['option'].update({"store_labels": store_labels})

        # create new attribute option(swatch)
        try:
            api_url = '/V1/products/attributes/%s/options' % attribute_code
            res = req(magento_instance, api_url, 'POST', data)
            try:
                _id = int(res[3:])
            except Exception:
                raise
        except Exception:
            return 0, "Error while new Product Attribute Option(Swatch) creation for %s Attribute.\n" % attribute_code
        return _id, ""

    def export_single_simple_product_to_magento(self, magento_instance, product, ml_simp_products, available_attributes,
                                                attribute_set_id, method):
        """
        Export(update) Simple Product to Magento
        :param magento_instance: Instance of Magento
        :param product: Odoo Product object
        :param ml_simp_products: Dictionary contains metadata for selected Simple Products (Odoo products)
        :param available_attributes: Dictionary with defined Attributes and their values in Magento
        :param attribute_set_id: ID of Product's attribute set defined in Magento
        :param method: http method (POST or PUT)
        :return: {} or Updated product
        """
        prod_attr_list = [(self.to_upper(a.attribute_id.name), self.to_upper(a.name)) for a in
                          product.odoo_product_id.product_template_attribute_value_ids.product_attribute_value_id]
        # add Product Life Phase attribute (aka x_status)
        if product.odoo_product_id.x_status:
            prod_attr_list.append(("PRODUCTLIFEPHASE", self.to_upper(product.odoo_product_id.x_status)))
        custom_attributes = self.map_product_attributes_from_magento(prod_attr_list, available_attributes)
        data = {
            "product": {
                "name": product.magento_product_name,
                # product.x_magento_name if product.x_magento_name else product.magento_product_name,
                "attribute_set_id": attribute_set_id,
                "price": product.lst_price,
                "status": 1,
                "visibility": 4,
                "type_id": "simple",
                "weight": product.odoo_product_id.weight,
                "media_gallery_entries": [],
                "custom_attributes": custom_attributes
            }
        }

        if method == 'POST':
            data["product"].update({
                "sku": product.magento_sku,
                "extension_attributes": {
                    "stock_item": {
                        "qty": product.qty_available or 0,
                        "is_in_stock": "true"
                    }
                }
            })

        try:
            api_url = '/V1/products' if method == 'POST' else '/all/V1/products/%s' % product.magento_sku
            response = req(magento_instance, api_url, method, data)
        except Exception:
            text = "Error while new Simple Product creation in Magento.\n" if method == 'POST' else \
                "Error while Simple Product update in Magento.\n"
            ml_simp_products[product.magento_sku]['log_message'] += text
            return {}

        if response.get("sku"):
            ml_simp_products[product.magento_sku]['export_date_to_magento'] = response.get("updated_at")
            ml_simp_products[product.magento_sku]['magento_status'] = 'need_to_link'
            if method == "POST":
                data = {"productWebsiteLink": {"sku": product.magento_sku}}
                website_ids = []
                for site in magento_instance.magento_website_ids:
                    data["productWebsiteLink"].update({"website_id": site.magento_website_id})
                    try:
                        api_url = '/V1/products/%s/websites' % product.magento_sku
                        res = req(magento_instance, api_url, method, data)
                        if res:
                            website_ids.append(site.magento_website_id)
                    except Exception:
                        text = "Error while adding website to product in Magento"
                        ml_simp_products[product.magento_sku]['log_message'] += text
                if website_ids:
                    response.get('extension_attributes',{'extension_attributes': {}}).update({'website_ids': website_ids})

            # export product images to Magento
            if len(product.odoo_product_id.product_template_image_ids):
                prod_media = (product.magento_sku, product.odoo_product_id.product_template_image_ids)
                self.export_media_to_magento(magento_instance, prod_media, ml_simp_products)

            return response
        return {}

    def map_product_attributes_from_magento(self, product_attributes, available_attributes):
        """
        Map Simple Product attributes from Odoo with exact attributes defined in Magneto.
        :param product_attributes: Odoo Product's attributes
        :param available_attributes: Dictionary with defined Attributes and their values in Magento
        :return: Magento format Attributes list
        """
        custom_attributes = []
        # update custom_attributes field with relevant data from Magento
        for attr in product_attributes:
            for avl_attr in available_attributes:
                if attr[0] == self.to_upper(avl_attr['default_label']):
                    for o in avl_attr['options']:
                        if attr[1] == self.to_upper(o['label']):
                            custom_attributes.append({
                                "attribute_code": avl_attr['attribute_code'],
                                "value": o['value']
                            })
                            break

        return custom_attributes

    def check_config_product_assign_attributes(self, mag_attr_options, available_attributes, conf_prod_assigned_attr):
        """
        Check if config.product "assign" attributes are the same in Magento and Odoo
        :param mag_attr_options: Product Attributes defined as configurable in Magento
        :param available_attributes: Dictionary with defined Attributes and their values in Magento
        :param conf_prod_assigned_attr: Product Attributes defined as configurable in Odoo
        :return: Boolean, True if the same, False if not
        """
        prod_attr_magento = {self.get_attr_name_by_id(available_attributes, attr.get("attribute_id")) for attr in
                             mag_attr_options if attr}
        prod_attr_odoo = {self.to_upper(attr) for attr in conf_prod_assigned_attr if attr}
        if prod_attr_odoo == prod_attr_magento:
            return True
        return False

    def assign_attr_to_config_product(self, magento_instance, product, available_attributes, ml_conf_products,
                                      ml_simp_products):
        """
        Assigns attributes to configurable product in Magento, in order to link it further
        :param magento_instance: Instance of Magento
        :param product: Odoo Product object
        :param available_attributes: Dictionary with defined Attributes and their values in Magento
        :param ml_conf_products: Dictionary contains metadata for selected Configurable Products (Odoo categories)
        :param ml_simp_products: Dictionary contains metadata for selected Simple Products (Odoo products)
        :return: None
        """
        config_product_sku = product.prod_categ_name
        product_attributes = product.odoo_product_id.product_template_attribute_value_ids.product_attribute_value_id
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
                self.get_attr_name_by_id(available_attributes, attr.get("attribute_id")): (
                    attr.get('id'), attr.get('attribute_id')) for attr in attr_options if attr
            }
            prod_attr_odoo = {self.to_upper(attr) for attr in conf_prod_assigned_attr if attr}

            if prod_attr_odoo != set(prod_attr_magento.keys()):
                # unlink attributes in Magento
                for attr in prod_attr_magento:
                    res = False
                    if attr not in prod_attr_odoo:
                        try:
                            api_url = '/V1/configurable-products/%s/options/%s' % (config_product_sku,
                                                                                   prod_attr_magento[attr][0])
                            res = req(magento_instance, api_url, 'DELETE')
                        except Exception:
                            text = "Error while unlinking Assign Attribute of %s Config.Product " \
                                   "in Magento. \n" % config_product_sku
                            ml_simp_products[product.magento_sku]['log_message'] += text
                    if res is True:
                        attr_options = list(
                            filter(lambda i: str(i.get('attribute_id')) != str(prod_attr_magento[attr][1]),
                                   attr_options))
                ml_conf_products[config_product_sku]['magento_conf_prod_options'] = attr_options

        # assign new options to config.product with relevant info from Magento
        for attr_val in product_attributes:
            prod_attr_name = attr_val.attribute_id.name
            if prod_attr_name in conf_prod_assigned_attr:
                if self.to_upper(prod_attr_name) not in set(prod_attr_magento.keys()):
                    # valid for new "assign" attributes for config.product to be created in Magento
                    attr = next((a for a in available_attributes if a and
                                 self.to_upper(prod_attr_name) == self.to_upper(a.get('default_label'))), {})
                    if attr:
                        for o in attr['options']:
                            if self.to_upper(attr_val.name) == self.to_upper(o['label']):
                                data['option'].update(
                                    {
                                        "attribute_id": attr["attribute_id"],
                                        "label": attr["default_label"],
                                        "values": [{"value_index": o["value"]}]
                                    }
                                )
                                try:
                                    api_url = '/V1/configurable-products/%s/options' % config_product_sku
                                    req(magento_instance, api_url, 'POST', data)
                                except Exception:
                                    txt = "Error while assigning product attribute option to %s Config.Product " \
                                          "in Magento. \n" % config_product_sku
                                    ml_simp_products[product.magento_sku]['log_message'] += txt

                                ml_conf_products[config_product_sku]['magento_conf_prod_options'].append({
                                    'id': "",
                                    "attribute_id": attr["attribute_id"],
                                    "label": attr["default_label"]
                                })
                                break

    def link_simple_to_config_product_in_magento(self, magento_instance, product, ml_conf_products, ml_simp_products):
        """
        Link simple product to configurable product in Magento
        :param magento_instance: Instance of Magento
        :param product: Odoo Product object
        :param ml_conf_products: Dictionary contains metadata for selected Configurable Products (Odoo categories)
        :param ml_simp_products: Dictionary contains metadata for selected Simple Products (Odoo products)
        :return: None
        """
        config_product_sku = product.prod_categ_name
        simple_product_sku = product.magento_sku
        config_product_children = ml_conf_products[config_product_sku]['children']

        # if already linked, skip
        if ml_simp_products[simple_product_sku]['magento_prod_id'] in config_product_children:
            ml_simp_products[simple_product_sku]['magento_status'] = 'in_magento'
            ml_simp_products[simple_product_sku]['log_message'] = ''
            ml_conf_products[config_product_sku]['log_message'] = ''
            return

        data = {
            "childSku": simple_product_sku
        }
        try:
            api_url = '/V1/configurable-products/%s/child' % config_product_sku
            res = req(magento_instance, api_url, 'POST', data)
            if res:
                ml_simp_products[product.magento_sku]['magento_status'] = 'in_magento'
        except Exception:
            text = "Error while linking %s to %s Configurable Product in Magento." % (simple_product_sku,
                                                                                      config_product_sku)
            ml_simp_products[simple_product_sku]['log_message'] += text

    def get_available_attributes_from_magento(self, magento_instance, attribute_set_name, ml_conf_products_dict,
                                              attr_sets):
        """
        Get available attributes and their related options(swatches) from Magento
        :param magento_instance: Instance of Magento
        :param attribute_set_name: Attribute Set Name defined in Odoo Product's Category
        :param ml_conf_products_dict: Dictionary contains metadata for selected Configurable Products (Odoo categories)
        :param attr_sets: Attribute set dictionary with unique data for selected products
        :return: Available in Magento Attributes list and their options
        """
        attribute_set_id = attr_sets[attribute_set_name]['id']
        if attribute_set_id:
            available_attributes = []
            try:
                api_url = '/V1/products/attribute-sets/%s/attributes' % attribute_set_id
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
                            'default_label': attr.get('default_frontend_label'),
                            'options': attr.get('options')
                        })
                return available_attributes

        for prod in ml_conf_products_dict:
            set_name = ml_conf_products_dict[prod]['attribute_set']
            if set_name == attribute_set_name:
                text = "Error while getting attributes for - %s attribute set from Magento.\n" % set_name
                ml_conf_products_dict[prod]['log_message'] += text
        return []

    def get_attribute_set_id_by_name(self, magento_instance, attribute_set_name, ml_conf_prod_dict,
                                     magento_entity_id=4):
        """
        Get Attribute ID from Magento by name defined in Odoo
        :param magento_instance: Instance of Magento
        :param attribute_set_name: Attribute Set Name defined in Odoo Product's Category
        :param ml_conf_prod_dict: Dictionary contains metadata for selected Configurable Products (Odoo categories)
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
        else:
            for prod in ml_conf_prod_dict:
                if attribute_set_name == ml_conf_prod_dict[prod]['attribute_set']:
                    text = "Error while getting attribute set id for - %s from Magento.\n" % attribute_set_name
                    ml_conf_prod_dict[prod]['log_message'] += text
            return False

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

    def get_attr_name_by_id(self, available_attributes, attr_id):
        """
        Get Attribute Name by it's Id
        :param available_attributes: List with available in Magento Product Attributes
        :param attr_id: Attribute's Id
        :return: Attribute's Name or None
        """
        for attr in available_attributes:
            if str(attr.get('attribute_id')) == str(attr_id):
                return self.to_upper(attr.get('default_label'))

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
                              '[filters][0][condition_type]=in&searchCriteria[filterGroups][0][filters][0][value]=%s' %\
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

        for k, v in new_conf_products.items():
            data.append({
                "product": {
                    "sku": k,
                    "name": k.upper(),
                    "attribute_set_id": attr_sets[v['attribute_set']]['id'],
                    "status": 1,  # Enabled
                    "visibility": 4,  # Catalog, Search
                    "type_id": "configurable",
                    "custom_attributes": []
                }
            })

        try:
            api_url = '/async/bulk/V1/products'
            response = req(magento_instance, api_url, 'POST', data)
        except Exception:
            for k in new_conf_products.keys():
                text = "Error while new Configurable Products creation in Magento.\n"
                ml_conf_products[k]['log_message'] += text
            return

        if not response.get('errors'):
            product_websites = []
            prod_media = {}
            for prod in new_conf_products.keys():
                ml_conf_products[prod]['export_date_to_magento'] = datetime.now()
                # prepare websites export
                for site in magento_instance.magento_website_ids:
                    product_websites.append({
                        "productWebsiteLink": {
                            "sku": prod,
                            "website_id": site.magento_website_id
                        },
                        "sku": prod
                    })
                # prepare imaged export
                domain = [('name', '=', ml_conf_products[prod]['name'])]
                eComm_categ = self.env['product.public.category'].search(domain)
                for categ in eComm_categ:
                    if len(categ.x_category_image_ids):
                        if prod_media.get(prod):
                            prod_media[prod] += categ.x_category_image_ids
                        else:
                            prod_media.update({prod: categ.x_category_image_ids})
            # process website export
            if product_websites:
                try:
                    api_url = '/async/bulk/V1/products/bySku/websites'
                    req(magento_instance, api_url, 'POST', product_websites)
                except Exception:
                    text = "Error while adding websites to product in Magento"
                    for prod in new_conf_products.keys():
                        ml_conf_products[prod]['log_message'] += text
            # process images export
            if prod_media:
                self.export_media_to_magento_in_bulk(magento_instance, prod_media, ml_conf_products)

    def export_single_conf_product_to_magento(self, magento_instance, new_conf_product, ml_conf_products, attr_sets):
        """
        Export(POST) to Magento new Configurable Product
        :param magento_instance: Instance of Magento
        :param new_conf_product: New Configurable Product to be exported
        :param ml_conf_products: Dictionary contains metadata for selected Configurable Products (Odoo categories)
        :param attr_sets: Attribute set dictionary with unique data for selected products
        :return: Magento Product or empty dict
        """
        data = {}
        prod_sku = list(new_conf_product.keys())[0]

        data.update({
            "product": {
                "sku": prod_sku,
                "name": prod_sku.upper(),
                "attribute_set_id": attr_sets[new_conf_product[prod_sku]['attribute_set']]['id'],
                "status": 1,  # Enabled
                "visibility": 4,  # Catalog, Search
                "type_id": "configurable",
                "custom_attributes": []
            }
        })

        try:
            api_url = '/V1/products'
            response = req(magento_instance, api_url, 'POST', data)
        except Exception:
            text = "Error while new Configurable Product creation in Magento.\n"
            ml_conf_products[prod_sku]['log_message'] += text
            return {}

        if response.get('sku'):
            ml_conf_products[prod_sku]['export_date_to_magento'] = response.get("updated_at")

            data = {"productWebsiteLink": {"sku": prod_sku}}
            for site in magento_instance.magento_website_ids:
                data["productWebsiteLink"].update({"website_id": site.magento_website_id})
                try:
                    api_url = '/V1/products/%s/websites' % prod_sku
                    req(magento_instance, api_url, 'POST', data)
                except Exception:
                    text = "Error while adding website to product in Magento"
                    ml_conf_products[prod_sku]['log_message'] += text

            # export product images to Magento
            domain = [('name', '=', new_conf_product[prod_sku]['name'])]
            eComm_categ = self.env['product.public.category'].search(domain)
            for categ in eComm_categ:
                if len(categ.x_category_image_ids):
                    prod_media = (prod_sku, categ.x_category_image_ids)
                    self.export_media_to_magento(magento_instance, prod_media, ml_conf_products)
            return response
        return {}

    def process_simple_products_export_in_bulk(self, instance, simp_prod_to_export, update_simple_prod,
                                               ml_conf_products_dict, ml_simp_products_dict, attr_sets, method):
        res = self.export_simple_products_in_bulk(instance, simp_prod_to_export, update_simple_prod,
                                                  ml_simp_products_dict, attr_sets, method)
        if res is False:
            return

        res = self.assign_attr_to_config_products_in_bulk(instance, simp_prod_to_export, update_simple_prod,
                                                          ml_conf_products_dict, ml_simp_products_dict, attr_sets)
        if res is False:
            return

        self.link_simple_to_config_products_in_bulk(instance, simp_prod_to_export, update_simple_prod,
                                                    ml_simp_products_dict)

    def export_simple_products_in_bulk(self, magento_instance, odoo_products, new_simple_prod, ml_simp_products,
                                       attr_sets, method='POST'):
        """
        Export(POST) to Magento new Simple Products in bulk (asynchronously)
        :param magento_instance: Instance of Magento
        :param odoo_products: Odoo Product objects
        :param new_simple_prod: List of new Simple Products to be exported
        :param ml_simp_products: Dictionary contains metadata for selected Simple Products (Odoo products)
        :param attr_sets: Attribute set dictionary with unique data for selected products
        :param method: Http request method (POST/PUT)
        :return: None or False
        """
        data = []
        prod_media = {}
        product_websites = []
        new_products_sku = new_simple_prod.keys()

        for prod in odoo_products:
            # map Odoo product attributes as in Magento
            if prod.magento_sku in new_products_sku:
                prod_attr_list = [(self.to_upper(a.attribute_id.name), self.to_upper(a.name)) for a in
                                  prod.odoo_product_id.product_template_attribute_value_ids.product_attribute_value_id]
                # add Product Life Phase attribute (aka x_status)
                if prod.odoo_product_id.x_status:
                    prod_attr_list.append(("PRODUCTLIFEPHASE", self.to_upper(prod.odoo_product_id.x_status)))

                custom_attributes = self.map_product_attributes_from_magento(
                    prod_attr_list,
                    attr_sets[prod.magento_prod_categ.magento_attr_set]['attributes']
                )
                attr_set_id = attr_sets[prod.magento_prod_categ.magento_attr_set]['id']
                data.append({
                    "product": {
                        "sku": prod.magento_sku,
                        "name": prod.magento_product_name,
                        # prod.x_magento_name if prod.x_magento_name else prod.magento_product_name,
                        "attribute_set_id": attr_set_id,
                        "price": prod.lst_price,
                        "status": 1,  # Enabled
                        "visibility": 4,  # Catalog, Search
                        "type_id": "simple",
                        "weight": prod.odoo_product_id.weight,
                        "extension_attributes": {
                            "stock_item": {
                                "qty": prod.qty_available or 0,
                                "is_in_stock": "true"
                            }
                        },
                        "custom_attributes": custom_attributes
                    }
                })

        if data:
            try:
                api_url = '/async/bulk/V1/products'
                response = req(magento_instance, api_url, method, data)
            except Exception:
                text = "Error while asynchronously new Simple Products creation in Magento.\n" if method == 'POST' else \
                    "Error while asynchronously Simple Products update in Magento.\n"
                for prod in odoo_products:
                    if prod.magento_sku in new_products_sku:
                        ml_simp_products[prod.magento_sku]['log_message'] += text
                return False

            if not response.get('errors'):
                for prod in odoo_products:
                    if prod.magento_sku in new_products_sku:
                        ml_simp_products[prod.magento_sku]['export_date_to_magento'] = datetime.now()
                        ml_simp_products[prod.magento_sku]['magento_status'] = 'in_process'

                    # update product_media dict if product has images
                    if len(prod.odoo_product_id.product_template_image_ids):
                        prod_media.update({prod.magento_sku: prod.odoo_product_id.product_template_image_ids})

                    # update product_websites dict
                    if method == "POST":
                        # add websites to product in Magento
                        for site in magento_instance.magento_website_ids:
                            product_websites.append({
                                "productWebsiteLink": {
                                    "sku": prod.magento_sku,
                                    "website_id": site.magento_website_id
                                },
                                "sku": prod.magento_sku
                            })

                if prod_media:
                    self.export_media_to_magento_in_bulk(magento_instance, prod_media, ml_simp_products)

                if product_websites:
                    try:
                        api_url = '/async/bulk/V1/products/bySku/websites'
                        req(magento_instance, api_url, method, product_websites)
                    except Exception:
                        text = "Error while adding websites to product in Magento"
                        for prod in odoo_products:
                            ml_simp_products[prod.magento_sku]['log_message'] += text
            else:
                return False

    def export_media_to_magento_in_bulk(self, magento_instance, products_media, ml_simp_products):
        """
        Export(POST) to Magento Product's Images in bulk (asynchronously)
        :param magento_instance: Instance of Magento
        :param products_media: Dictionary with Product Images added in Odoo
        :param ml_simp_products: Dictionary contains metadata for selected Simple Products (Odoo products)
        :return: None
        """
        images = []

        for prod_sku in products_media:
            for img in products_media[prod_sku]:
                attachment = self.env['ir.attachment'].sudo().search([
                    ('res_field', '=', 'image_256'),
                    ('res_model', '=', 'product.image'),
                    ('res_id', '=', img.id)
                ])
                images.append({
                    "entry": {
                        "media_type": "image",
                        "content": {
                            "base64EncodedData": img.image_256.decode('utf-8'),
                            "type": attachment.mimetype,
                            "name": attachment.mimetype.replace("/", ".")
                        }
                    },
                    "sku": prod_sku
                })

        try:
            api_url = '/async/bulk/V1/products/bySku/media'
            req(magento_instance, api_url, 'POST', images)
        except Exception:
            text = "Error while Simple Product Images export to Magento.\n"
            for prod_sku in products_media:
                ml_simp_products[prod_sku]['log_message'] += text

    def export_media_to_magento(self, magento_instance, products_media, ml_products):
        """
        Export(POST) to Magento Product's Images
        :param magento_instance: Instance of Magento
        :param products_media: Dictionary with Product Images added in Odoo
        :param ml_products: Dictionary contains metadata for selected Simple Products (Odoo products)
        :return: None
        """
        images = {}
        prod_sku = products_media[0]
        for img in products_media[1]:
            attachment = self.env['ir.attachment'].sudo().search([
                ('res_field', '=', 'image_256'),
                ('res_model', '=', 'product.image'),
                ('res_id', '=', img.id)
            ])
            images.update({
                "entry": {
                    "media_type": "image",
                    "content": {
                        "base64EncodedData": img.image_256.decode('utf-8'),
                        "type": attachment.mimetype,
                        "name": attachment.mimetype.replace("/", ".")
                    }
                }
            })

            try:
                api_url = '/V1/products/%s/media' % prod_sku
                req(magento_instance, api_url, 'POST', images)
            except Exception:
                text = "Error while Product Images export to Magento.\n"
                ml_products[prod_sku]['log_message'] += text

    def assign_attr_to_config_products_in_bulk(self, magento_instance, odoo_products, new_simple_products,
                                               config_prod_assigned_attr, ml_simp_products, available_attributes):
        """
        Assigns Attributes to Configurable Products in bulk (asynchronously)
        :param magento_instance: Instance of Magento
        :param odoo_products: Odoo Product records
        :param new_simple_products: List of new Simple Products to be exported
        :param config_prod_assigned_attr: Configurable Product Assigned Attributes
        :param ml_simp_products: Dictionary contains metadata for selected Simple Products (Odoo products)
        :param available_attributes: Dictionary with defined Attributes and their values in Magento
        :return: None or False
        """
        data = []
        new_products_sku = new_simple_products.keys()

        # assign new options to config.product with relevant info from Magento
        for simple_prod in odoo_products:
            if ml_simp_products[simple_prod.magento_sku]['log_message']:
                continue
            if simple_prod.magento_sku in new_products_sku:
                simp_prod_attrs = \
                    simple_prod.odoo_product_id.product_template_attribute_value_ids.product_attribute_value_id
                for attr_val in simp_prod_attrs:
                    attr_name = attr_val.attribute_id.name
                    categ_name = simple_prod.prod_categ_name
                    mag_attr_set = simple_prod.magento_prod_categ.magento_attr_set
                    if attr_name in config_prod_assigned_attr.get(categ_name)['config_attr']:
                        mag_avail_attrs = available_attributes.get(mag_attr_set).get('attributes')
                        for attr in mag_avail_attrs:
                            if self.to_upper(attr_name) == self.to_upper(attr['default_label']):
                                for o in attr['options']:
                                    if self.to_upper(attr_val.name) == self.to_upper(o['label']):
                                        data.append({
                                            'option': {
                                                "attribute_id": attr["attribute_id"],
                                                "label": attr["default_label"],
                                                "is_use_default": "false",
                                                "values": [{"value_index": o["value"]}]
                                            },
                                            'sku': categ_name
                                        })
        if data:
            try:
                api_url = '/async/bulk/V1/configurable-products/bySku/options'
                response = req(magento_instance, api_url, 'POST', data)
            except Exception:
                text = "Error while asynchronously assign product attributes to Config.Product in Magento.\n"
                for prod in odoo_products:
                    if prod.magento_sku in new_products_sku:
                        ml_simp_products[prod.magento_sku]['log_message'] += text
                return False

            if response.get('errors', {}):
                return False

    def link_simple_to_config_products_in_bulk(self, magento_instance, odoo_products, new_simple_products,
                                               ml_simp_products):
        """
        Link Simple Product to Configurable Product in Magento in bulk (asynchronously)
        :param magento_instance: Instance of Magento
        :param odoo_products: Odoo Product objects
        :param new_simple_products: List of new Simple Products to be exported
        :param ml_simp_products: Dictionary contains metadata for selected Simple Products (Odoo products)
        :return: None
        """
        data = []

        for simple_prod in odoo_products:
            if ml_simp_products[simple_prod.magento_sku]['log_message']:
                continue
            if simple_prod.magento_sku in new_simple_products:
                data.append({
                    "childSku": simple_prod.magento_sku,
                    "sku": simple_prod.prod_categ_name
                })

        if data:
            try:
                api_url = '/async/bulk/V1/configurable-products/bySku/child'
                req(magento_instance, api_url, 'POST', data)
            except Exception:
                text = "Error while asynchronously linking Simple to Configurable Product in Magento.\n"
                for prod in odoo_products:
                    if prod.magento_sku in new_simple_products:
                        ml_simp_products[prod.magento_sku]['log_message'] += text

    def check_products_set_of_attribute_values(self, ml_conf_products, categ_name, simp_prod_attr,
                                               available_attributes, ml_simple_prod, magento_sku):
        """
        Check Product's "Attribute: Value" pair for duplication
        :param ml_conf_products: Dictionary contains metadata for selected Configurable Products (Odoo categories)
        :param categ_name: Category Name of Product
        :param simp_prod_attr: Simple Product Attributes defined in Odoo
        :param available_attributes: Dictionary with defined Attributes and their values in Magento
        :param ml_simple_prod: Dictionary contains metadata for selected Simple Products (Odoo products)
        :param magento_sku: Product sku
        :return: Product sku in case of duplication or False
        """
        magento_conf_prod_links = ml_conf_products[categ_name].get('magento_configurable_product_link_data', {})
        conf_prod_attributes = ml_conf_products[categ_name]['config_attr']

        simp_attr_val = {}
        # create dict of {simple_product_sku: {attribute: values}} with config.attributes only
        for prod_attr in simp_prod_attr:
            prod_attr_name = prod_attr.attribute_id.name
            if prod_attr_name in conf_prod_attributes:
                for avail_attr in available_attributes:
                    if avail_attr.get('default_label') and \
                            self.to_upper(avail_attr.get('default_label')) == self.to_upper(prod_attr_name):
                        for opt in avail_attr.get('options'):
                            if opt.get('label') and self.to_upper(opt.get('label')) == self.to_upper(prod_attr.name):
                                simp_attr_val.update({
                                    self.to_upper(avail_attr.get('default_label')): self.to_upper(opt.get('label'))
                                })
                                break

        # check if simple product's "attribute: value" is already linked to configurable product in Magento
        for prod in magento_conf_prod_links:
            if magento_conf_prod_links[prod] == simp_attr_val and prod != magento_sku:
                return prod

        # check if simple product's "attribute: value" is within exported products
        for prod in ml_simple_prod:
            if ml_simple_prod[prod]['category_name'] == categ_name and prod != magento_sku and \
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
        for attrs in odoo_product.odoo_product_id.product_template_attribute_value_ids.product_attribute_value_id:
            if attrs.attribute_id.name in [a.name for a in odoo_product.magento_prod_categ.magento_assigned_attr]:
                attr_dict.update({self.to_upper(attrs.attribute_id.name): self.to_upper(attrs.name)})
        return attr_dict

    def save_magento_products_info_to_database(self, instance_id, magento_websites, ml_simp_products, ml_conf_products,
                                               status_check):
        """
        Save Products' export_dates, websites, magento_statuses and log_messages to database
        :param instance_id: Magento Instance ID
        :param magento_websites: Magento available websites related to current instance
        :param ml_simp_products: Dictionary contains metadata for selected Simple Products (Odoo products)
        :param ml_conf_products: Dictionary contains metadata for selected Configurable Products (Odoo categories)
        :param status_check: Check if method runs as status check (Binary)
        :return: None
        """
        magento_products = self.env['magento.product.product'].filtered(
            lambda prod: prod.magento_instance_id == instance_id)

        for s_prod in ml_simp_products:
            if ml_simp_products[s_prod]['log_message']:
                ml_simp_products[s_prod]['magento_status'] = 'log_error'
            values = {'magento_status': ml_simp_products[s_prod]['magento_status']}
            magento_product = magento_products.search([('magento_sku', '=', s_prod)])
            categ_name = ml_simp_products[s_prod].get('category_name')
            website_ids = ml_simp_products[s_prod].get('magento_website_ids', [])

            if website_ids and {str(p.id) for p in magento_product.magento_website_ids} != set(website_ids):
                ids = [w.id for w in magento_websites if str(w.magento_website_id) in website_ids]
                values.update({'magento_website_ids': [(6, 0, ids)]})

            if not status_check and ml_simp_products[s_prod]['to_export']:
                values.update({'magento_export_date': ml_simp_products[s_prod]['export_date_to_magento']})
                # update config.product export date for all related products if needed
                if ml_conf_products.get(categ_name, {}).get('to_export'):
                    products = magento_products.search([('prod_categ_name', '=', categ_name)])
                    vals = ({
                        'magento_export_date_conf': ml_conf_products.get(categ_name, {}).get('export_date_to_magento')
                    })
                    products.write(vals)
                    ml_conf_products[categ_name]['to_export'] = False

            magento_product.write(values)

            if not status_check and ml_simp_products[s_prod]['log_message']:
                self.save_error_message_to_log_book(ml_simp_products[s_prod]['log_message'],
                                                    ml_conf_products.get(categ_name, {}).get('log_message', ''),
                                                    magento_product)

    def save_error_message_to_log_book(self, simp_log_message, conf_log_message, magento_product):
        vals = {
            'magento_log_message': simp_log_message,
            'magento_log_message_conf': conf_log_message
        }
        log_book = self.env['magento.product.log.book'].search([('magento_product_id', '=', magento_product.id)])
        if not len(log_book):
            vals.update({'magento_product_id': magento_product.id})
            log_book.create(vals)
        else:
            log_book.write(vals)

    def create_attribute_sets_dict(self, magento_instance, ml_conf_products_dict):
        """
        Create Attribute-Sets dictionary for selected Products with Attribute ID and Attributes available in Magento
        :param magento_instance: Magento Instance
        :param ml_conf_products_dict: Dictionary contains metadata for selected Configurable Products (Odoo categories)
        :return: Attribute sets dictionary
        """
        attr_sets = {}
        attr_sets.update({
            ml_conf_products_dict[s]['attribute_set']: {} for s in
            ml_conf_products_dict.keys() if ml_conf_products_dict[s]['attribute_set']
        })
        for a_set in attr_sets:
            attr_sets[a_set].update({
                'id': self.get_attribute_set_id_by_name(magento_instance, a_set, ml_conf_products_dict)
            })
            attr_sets[a_set].update({
                'attributes': self.get_available_attributes_from_magento(magento_instance, a_set, ml_conf_products_dict,
                                                                         attr_sets)
            })
        return attr_sets

    def process_manually(self):
        """
        Process Product's Export (create/update) with regular Magento API process (without RabbitMQ)
        :return: None
        """
        self.ensure_one()
        self.process_products_export_to_magento(self)

    def delete_in_magento(self):
        self.ensure_one()
        try:
            api_url = '/V1/products/%s' % self.magento_sku
            response = req(self.magento_instance_id, api_url, 'DELETE')
        except Exception as err:
            raise UserError("Error while deleting product in Magento. " + str(err))
        if response is True:
            self.write({'magento_status': 'deleted'})

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