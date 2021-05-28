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


class MagentoProductProduct(models.Model):
    """
    Describes fields and methods for Magento products
    """
    _name = 'magento.product.product'
    _inherits = {'product.product': 'odoo_product_id'}
    _description = 'Magento Product'

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
        'magento.product.template',
        string="Magento Product template",
        help="Magento Product template",
        ondelete="cascade"
    )
    odoo_product_id = fields.Many2one(
        'product.product',
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
    created_at = fields.Date(
        string='Product Created At',
        help="Date when product created into Magento"
    )
    updated_at = fields.Date(
        string='Product Updated At',
        help="Date when product updated into Magento"
    )
    product_type = fields.Selection([
        ('simple', 'Simple Product'),
        ('configurable', 'Configurable Product'),
        ('virtual', 'Virtual Product'),
        ('downloadable', 'Downloadable Product'),
        ('group', 'Group Product'),
        ('bundle', 'Bundle Product'),
    ], string='Magento Product Type', help='Magento Product Type', default='simple')

    no_stock_sync = fields.Boolean(
        string='No Stock Synchronization',
        help="Check this to exclude the product "
             "from stock synchronizations.",
    )
    export_stock_type = fields.Selection([
        ('fixed', 'Export Fixed Qty'),
        ('actual', 'Export Actual Stock')
    ], string="Export Product Stock Type", default='actual')
    export_fix_value = fields.Float(
        string="Fixed Stock Quantity",
        help="Fixed Stock Quantity"
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

    _sql_constraints = [('_magento_product_unique_constraint',
                         'unique(magento_sku,magento_instance_id,magento_product_id)',
                         "Magento Product must be unique")]

    def unlink(self):
        unlink_magento_products = self.env['magento.product.product']
        unlink_magento_templates = self.env['magento.product.template']
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

    def view_odoo_product(self):
        """
        This method id used to view odoo product.
        :return: Action
        """
        if self.odoo_product_id:
            vals = {
                'name': 'Odoo Product',
                'type': 'ir.actions.act_window',
                'res_model': 'product.product',
                'view_type': 'form',
                'view_mode': 'tree,form',
                'domain': [('id', '=', self.odoo_product_id.id)],
            }
            return vals

    def create_magento_product_in_odoo(
            self,
            magento_instance,
            items,
            magento_per_sku,
            product_count,
            product_total_queue,
            log_book_id
    ):
        """
        Create magento product if it is not available in Odoo
        :param magento_instance: Instance of Magento
        :param items: Product items received from Magento
        :param magento_per_sku: Dictionary product sku
        :param product_count: Incremental count of Product
        :param product_total_queue: Total of Product data queue lines
        :param log_book_id: Common log book object
        :return: Dictionary of magento_per_sku and product_count
        """
        magento_product_template_obj = self.env['magento.product.template']
        for item in items:
            error = False
            product_response = json.loads(item.product_data)
            magento_sku = product_response.get('sku')
            if not magento_per_sku or (
                    magento_per_sku and (magento_instance.id not in magento_per_sku.keys() or (
                        magento_instance.id in magento_per_sku.keys() and
                        magento_sku not in magento_per_sku[magento_instance.id].keys()))):
                if product_response.get('type_id') == 'simple':
                    # Create or update simple Product Process
                    error = self.create_or_update_simple_product(
                        product_response, magento_instance, log_book_id,
                        error, magento_per_sku, item.id, do_not_update = item.do_not_update_existing_product
                    )
                elif product_response.get('type_id') == 'configurable':
                    # Create or update configurable Product Process
                    error = magento_product_template_obj.create_or_update_configurable_product(
                        product_response, magento_instance, log_book_id,
                        error, magento_per_sku, item.id,
                    )
                else:
                    log_line_vals = {
                        'log_lines': [(0, 0, {
                            'message': 'Product Type %s Is Not Supported' % product_response.get('type_id'),
                            'order_ref': product_response.get('id'),
                            'import_product_queue_line_id': item.id
                        })]
                    }
                    log_book_id.write(log_line_vals)
                    error = True
            product_count += 1
            product_total_queue -= 1
            if product_count > 10 or (0 < product_count <= 10 and product_total_queue == 0):
                self._cr.commit()
                product_count = 1
                item.sync_import_magento_product_queue_id.is_process_queue = True
            item.write({'state': 'failed' if error else 'done', 'processed_at': datetime.now()})
        return magento_per_sku, product_count, product_total_queue

    def create_or_update_simple_product(
            self, item, instance, log_book_id, error,
            magento_per_sku, order_data_queue_line_id, order_ref=False, magento_prod_tmpl=False,
            conf_product_item=False, do_not_update = False
    ):
        """
        Create or Update Magento And Odoo Product
        :param item: Item received from Magento
        :param instance: Instance of Magento
        :param log_book_id: Common log book object
        :param error: If any error, returns True
        :param magento_per_sku: Dictionary of Magento Products
        :param order_data_queue_line_id: Order data queue object
        :param order_ref: Order Reference
        :param magento_prod_tmpl: Magento product template object
        :return:
        """
        magento_sku = item.get('sku')
        magento_product = self.env['magento.product.product'].search([
            ('magento_sku', '=', magento_sku), ('magento_instance_id', '=', instance.id)
        ])
        queue_line = 'import_product_queue_line_id' if not order_ref else 'magento_order_data_queue_line_id'
        order_ref = item.get('id') if not order_ref else order_ref
        website_ids = item.get('extension_attributes').get('website_ids')
        magento_websites = instance.magento_website_ids.filtered(lambda x: x.magento_website_id in str(website_ids))
        if magento_product and not magento_product.odoo_product_id:
            error = self.map_odoo_product_with_magento_product(
                instance, magento_product, item, log_book_id, order_ref, queue_line, order_data_queue_line_id, error
            )
        elif not magento_product:
            odoo_product, error = self.create_odoo_product(
                magento_sku, item, instance.auto_create_product, log_book_id,
                order_ref, queue_line, order_data_queue_line_id, error
            )
            if odoo_product:
                if not magento_prod_tmpl:
                    magento_prod_tmpl, error = self.create_magento_product_template(
                        odoo_product, instance, item, magento_websites,
                        log_book_id, order_ref, queue_line, order_data_queue_line_id, error
                    )
                magento_product, error = self.create_magento_product_product(
                    odoo_product, instance, magento_websites, item, magento_prod_tmpl.id,
                    log_book_id, order_ref, queue_line, order_data_queue_line_id, error
                )
        if magento_product:
            self.update_magento_product(item, magento_websites, instance, magento_product)
            # below code for set magento sku and magento product id while import
            # the product and product was already mapped before perform the import operation
            template_vals = {}
            if not magento_prod_tmpl and (
                    (not magento_product.magento_tmpl_id.magento_product_template_id or
                     not magento_product.magento_tmpl_id.magento_sku)
                    or
                    (magento_product.magento_tmpl_id and
                     magento_product.odoo_product_id.product_tmpl_id)
            ):
                # case 1 (configurable product): map product first.
                # So magento product id and created and updated date not set in the template
                # now while import that same configurable product then update that template and
                # set magento product ID and other value
                # Case 2 : During the time of the map product if not set the magento SKU
                # then set the magento sku as well
                # Case 3 : While import product first time and then change the product data from the magento
                # then update that data in magento layer product template as well
                itm = conf_product_item if conf_product_item else item
                if itm.get('sku') == magento_product.magento_tmpl_id.magento_sku:
                    # While configurable product's simple product update
                    # at that time template name and type was changed,
                    # So this condition added
                    template_vals = magento_product.magento_tmpl_id.prepare_magento_product_template_vals(
                        itm, instance, magento_product.odoo_product_id.product_tmpl_id)
                    template_vals.pop('name') # not change the product name,
                    # because it's change the odoo product/template name as well
            if template_vals or not magento_product.magento_tmpl_id.magento_sku:
                # Add "or" condition for below case
                # case : first map the product and then import that specific product,
                # So set the magento template id and sku
                template_vals.update({
                    'magento_product_template_id': conf_product_item.get('id') if conf_product_item else item.get('id'),
                    'magento_sku': conf_product_item.get('sku') if conf_product_item else item.get('sku'),
                    'product_type': 'configurable' if conf_product_item else 'simple',
                    'sync_product_with_magento': True
                })
                magento_product.magento_tmpl_id.write(template_vals)
        price = item.get('price') or 0.0
        if magento_product and not do_not_update:
            self.manage_price_scope(instance, price, magento_product, item)
        if magento_per_sku and instance.id in magento_per_sku.keys():
            magento_per_sku[instance.id][magento_sku] = magento_sku
        else:
            magento_per_sku.update({instance.id: {magento_sku: magento_sku}})
        return error

    def manage_price_scope(self, instance, price, magento_product, item):
        """
        :param instance: Magento Instance
        :param magento_product: magento Product
        :param price: Price of the magento product
        :return:
        """
        # Case : Price Scope = Global
        # ===========================================
        # add this for update price in the price-list
        # if the product and it's price is exist in configured price-list then update
        # else create new line in price-list with that simple product and price
        # Case : Price Scope = Website
        # ===========================================
        # If price scope is "website" then add product price in the configured -
        # price-list. [Path : Magento Instance > Magento Websites > price-list]
        # if bool object for the price update is checked then only price -
        # update if the product was exist in that price-list
        # If the bool obj of the update price not checked any product not exist
        # in the price-list then also the price will be added to the configured price-list
        # Add/Update Price Based on the magento Default Price
        self.create_pricelist_item(instance, price, magento_product, item)

    def create_pricelist_item(self, magento_instance, price, product, item):
        """
        Added product into price list.
        :param magento_instance: Instance of Magento
        :param price: Product Price
        :param product: Magento Product object
        :return: product pricelist item object
        """
        pricelist_item_obj = self.env['product.pricelist.item']
        if magento_instance.catalog_price_scope == 'global':
            pricelist_id = magento_instance.pricelist_id.id
            pricelist_item = pricelist_item_obj.search([
                ('pricelist_id', '=', pricelist_id),
                ('product_id', '=', product.odoo_product_id.id)
            ])
            self.create_or_update_price(pricelist_id, product, price, pricelist_item)
        else:
            if item.get('extension_attributes').get('website_wise_product_price_data'):
                for website_product_price in item.get('extension_attributes').get('website_wise_product_price_data'):
                    website_product_price = json.loads(website_product_price)
                    magento_website = self.env['magento.website'].\
                        search([('magento_website_id', '=', website_product_price.get('website_id'))], limit=1)
                    if magento_website:
                        pricelist_ids = magento_website.pricelist_ids
                        price = website_product_price.get('product_price')
                        default_store_currency = website_product_price.get('default_store_currency')
                        currency_obj = self.env['res.currency']
                        currency_id = currency_obj.search([
                            ('name', '=', default_store_currency),
                            '|', ('active', '=', False),
                            ('active', '=', True)
                        ], limit=1)
                        website_pricelist = pricelist_ids.filtered(lambda x: x.currency_id.id == currency_id.id)
                        if website_pricelist:
                            pricelist_items = pricelist_item_obj.\
                                search([('pricelist_id', '=', website_pricelist.id),
                                        ('product_id', '=', product.odoo_product_id.id)])
                            self.create_or_update_price(website_pricelist.id,
                                                        product,
                                                        price, pricelist_items)

    def create_or_update_price(self, pricelist_id, product, price, pricelist_item):
        pricelist_item_obj = self.env['product.pricelist.item']
        if pricelist_item:
            pricelist_item.write({'fixed_price': price})
        else:
            pricelist_item_obj.create({
                'pricelist_id': pricelist_id,
                'applied_on': '0_product_variant',
                'product_id': product.odoo_product_id.id,
                'product_tmpl_id': product.odoo_product_id.product_tmpl_id.id,
                'compute_price': 'fixed',
                'min_quantity': 1,
                'fixed_price': price
            })

    @staticmethod
    def get_website_wise_product_price(web_id, item):
        """
        return product price per website
        :param web_id: magento website ID
        :param item: product data
        :return: product price
        """
        for website_product_price in item.get('extension_attributes').get('website_wise_product_price_data'):
            website_product_price = json.loads(website_product_price)
            if int(website_product_price.get('website_id')) == web_id:
                return website_product_price.get('product_price'), website_product_price.get('default_store_currency')
        return True


    def update_magento_product(self, item, magento_websites, instance, magento_product):
        """
        magento product found, then prepare the new magento product vals and write it
        :param item: product item API response
        :param magento_websites: website data
        :param instance:  magento instance
        :param magento_product: magento product object
        :return:
        """
        values = self.prepare_magento_product_vals(item, magento_websites, instance.id)
        values.update({
            'magento_product_id': item.get('id'),
            'magento_tmpl_id': magento_product.magento_tmpl_id.id,
            'odoo_product_id': magento_product.odoo_product_id.id,
            'sync_product_with_magento': True
        })
        # Below code is for all the configurable's simple product is only simple product in odoo
        # not map all this odoo simple with configurable's simple product
        # and import configurable product, so set all the simple product's id and sync as true in magento.product.template
        magento_product_tmpl = self.env['magento.product.template'].search(
            [('magento_product_template_id', '=', False), ('sync_product_with_magento', '=', False),
             ('magento_sku', '=', magento_product.magento_sku)])
        if magento_product_tmpl:
            magento_product_tmpl.write({
                'magento_product_template_id': item.get('id'),
                'sync_product_with_magento': True
            })
        magento_product.write(values)


    def map_odoo_product_with_magento_product(
            self, instance, magento_product, item, log_book_id, order_ref, queue_line, order_data_queue_line_id, error
    ):
        """
        Map Odoo Product with existing Magneto Product in Layer
        :param instance: Magento Instance Object
        :param magento_product: Magento product product object
        :param item: Response received from Magento
        :param log_book_id: Common log book object
        :param order_ref: Order reference
        :param queue_line: product or order queue line
        :param order_data_queue_line_id: data queue line object
        :param error: True if error else False
        :return: Log book id, error
        """
        magento_sku = item.get('sku')
        odo_product = magento_product.odoo_product_id.filtered(lambda x: x.default_code == magento_sku)
        #odo_product = self.env['product.product'].search([('default_code', '=', magento_sku)])
        if not odo_product:
            odoo_product, error = self.create_odoo_product(
                magento_sku, item, instance.auto_create_product, log_book_id,
                order_ref, queue_line, order_data_queue_line_id, error
            )
            if odoo_product:
                magento_product.write({'odoo_product_id': [(0, 0, [odoo_product])]})
        return error

    def create_magento_product_template(self, odoo_product, instance_id, item, magento_websites,
                                        log_book_id, order_ref, queue_line, order_data_queue_line_id, error):
        """
        Create Magento Product Template if not found
        :param odoo_product: Product product object
        :param instance_id: Magento Instance OBJ
        :param item: Item received from Magento
        :param magento_websites: Magento Website Object
        :return: Magento Product Template Object
        """
        magento_prod_tmpl_obj = self.env['magento.product.template']
        magento_prod_tmpl = magento_prod_tmpl_obj.search([
            ('odoo_product_template_id', '=', odoo_product.product_tmpl_id.id),
            ('magento_instance_id', '=', instance_id.id)
        ])
        if not magento_prod_tmpl:
            value = self.prepare_magento_product_vals(item, magento_websites, instance_id.id)
            value.update({
                'magento_product_template_id': item.get('id'),
                'odoo_product_template_id': odoo_product.product_tmpl_id.id,
                'sync_product_with_magento': True
            })
            magento_prod_tmpl = magento_prod_tmpl_obj.create(value)
            if instance_id.allow_import_image_of_products:
                magento_media_url = False
                magento_stores = magento_websites.store_view_ids
                if magento_stores:
                    magento_media_url = magento_stores[0].base_media_url
                if magento_media_url:
                    full_img_url, error = magento_prod_tmpl_obj.create_or_update_product_images(
                        instance_id, False, magento_prod_tmpl,
                        magento_media_url, item.get('media_gallery_entries'),
                        log_book_id, order_ref, queue_line, order_data_queue_line_id, error
                    )
            self._cr.commit()
        return magento_prod_tmpl, error

    def create_magento_product_product(self, odoo_product, instance, magento_websites, item, magento_prod_tmpl_id,
                                       log_book_id, order_ref, queue_line, order_data_queue_line_id, error):
        """
        Create Magento Product if not found
        :param odoo_product: Odoo Product Object
        :param instance: Magento Instance Object
        :param magento_websites: Magento Website Object
        :param item: Item received from Magento
        :param magento_prod_tmpl_id:  Magento Product Template Id
        :return:
        """
        magento_prod_tmpl_obj = self.env['magento.product.template']
        magento_product_product_obj = self.env['magento.product.product']
        magento_product = magento_product_product_obj.search([
            ('odoo_product_id', '=', odoo_product.id),
            ('magento_instance_id', '=', instance.id)
        ])
        if not magento_product and odoo_product.default_code == item.get('sku'):
            values = self.prepare_magento_product_vals(item, magento_websites, instance.id)
            values.update({
                'magento_product_id': item.get('id'),
                'magento_tmpl_id': magento_prod_tmpl_id,
                'odoo_product_id': odoo_product.id,
                'sync_product_with_magento': True
            })
            magento_product = magento_product_product_obj.create(values)
            if instance.allow_import_image_of_products:
                magento_media_url = False
                magento_stores = magento_websites.store_view_ids
                if magento_stores:
                    magento_media_url = magento_stores[0].base_media_url
                if magento_media_url:
                    full_img_url, error = magento_prod_tmpl_obj.create_or_update_product_images(
                        instance, magento_product, False,
                        magento_media_url, item.get('media_gallery_entries'),
                        log_book_id, order_ref, queue_line, order_data_queue_line_id, error
                    )
            self._cr.commit()
        return magento_product, error

    def prepare_magento_product_vals(self, item, magento_websites, instance_id):
        """
        Prepare vals for Magento product and template
        :param item: Item received from Magento
        :param magento_websites: Magento Website Object
        :param instance_id: Magento Instance Id
        :return: Return dictionary of values
        """
        description = short_description = ''
        for attribute_code in item.get('custom_attributes'):
            if attribute_code.get('attribute_code') == 'description':
                description = attribute_code.get('value')
            if attribute_code.get('attribute_code') == 'description_sale':
                short_description = attribute_code.get('value')
        magento_product_vals = {
            'magento_product_name': item.get('name'),
            #'name': item.get('name'), # comment line,
            # Reason : While existing configurable pro's simple product update
            # at that time update that name as odoo product template name
            'magento_instance_id': instance_id,
            'magento_website_ids': [(6, 0, magento_websites.ids)],
            'magento_sku': item.get('sku'),
            'product_type': item.get('type_id'),
            'created_at': item.get('created_at'),
            'updated_at': item.get('updated_at'),
            'description': description,
            'description_sale' : short_description,
        }
        return magento_product_vals

    def create_odoo_product(
            self, magento_sku, prod, auto_create_product, log_book_id,
            order_ref, queue_line, order_data_queue_line_id, error
    ):
        """
        Checks and create product in Odoo.
        :param magento_sku: Magento Product SKU
        :param prod: Product items received from Magento
        :param auto_create_product: If checked , Product will be created if not found
        :param log_book_id: Common log book object
        :param order_ref: order reference
        :param queue_line: product or order queue line
        :param order_data_queue_line_id: queue line object
        :param error: True if error else False
        :return: Product Product Object
        """
        product_product_obj = self.env['product.product']
        odoo_product = product_product_obj.search([('default_code', '=', magento_sku)],  limit=1)
        if not odoo_product and auto_create_product:
            vals = {
                'name': prod.get('name'),
                'default_code': magento_sku,
                'type': 'product',
                'purchase_ok': True,
                'sale_ok': True,
                'invoice_policy': 'order'
            }
            odoo_product = product_product_obj.create(vals)
        elif not odoo_product and not auto_create_product:
            # Product not found in odoo layer
            # Auto create setting is off for this instance
            message = 'Odoo Product Not found for SKU : %s' \
                      '\nAnd your "Automatically Create Odoo Product If Not Found" ' \
                      'setting is %s'\
                      % (magento_sku, auto_create_product)
            log_book_id.add_log_line(message, order_ref, order_data_queue_line_id, queue_line, magento_sku)
            error = True
        return odoo_product, error

    def get_magento_product_by_id(self, magento_instance, magento_id, product_ids=None):
        """
        This method is used to call API for getting product data from magento.
        :param magento_instance: Instance of Magento
        :param magento_id: Magento Product Id
        :param product_ids: Dictionary of product get from magento
        :return: product sku or product response
        """
        if product_ids is None:
            product_ids = []
        if product_ids:
            products = []
            prod_response = []
            i = 1
            for product_id in product_ids:
                products.append(product_id)
                if i % 25 == 0 or i == len(product_ids):
                    filters = {}
                    filters.setdefault('entity_id', {})
                    filters['entity_id']['in'] = products
                    filters = create_search_criteria(filters)
                    que_str = Php.http_build_query(filters)
                    api_url = "/V1/products?%s" % que_str
                    try:
                        response = req(magento_instance, api_url)
                        prod_response.extend(response.get('items'))
                        products = []
                    except:
                        raise UserError(_("Error while requesting product"))
                i += 1
            final_prod_response, error = self.get_magento_product_by_sku(magento_instance, prod_response)
            return final_prod_response
        magento_product = self.env['magento.product.product'].search([
            ('magento_product_id', '=', magento_id), ('magento_instance_id', '=', magento_instance.id)
        ])
        sku = magento_product and magento_product.magento_sku
        if not sku:
            sku = self.get_magento_product_by_entity_id(magento_id, magento_instance)
        return sku

    def get_magento_product_by_entity_id(self, magento_id, magento_instance):
        """
        This method is used to call API for getting product data from magento.
        :param magento_id: Magento product id
        :param magento_instance: Magento instance
        :return: Magento product sku
        """
        filters = {'entity_id': magento_id}
        filters = create_search_criteria(filters)
        query_str = Php.http_build_query(filters)
        api_url = "/V1/products?%s" % (query_str)
        try:
            response = req(magento_instance, api_url)
        except:
            raise UserError(_("Error while requesting product"))
        return response.get('items')[0].get('sku')

    def get_magento_product_by_sku(self, magento_instance, prod_response, queue_line,
                                   log_book_id=False, order_data_queue_line_id=False):
        """
        This method is used to call API for getting product data from magento.
        :param magento_instance: Instance of Magento
        :param prod_response: Dictionary of product sku get from magento
        :return:
        """
        final_prod_res = {}
        result_list = []
        log_error = False
        for prod_res in prod_response:
            try:
                sku = Php.quote_sku(prod_res.get('sku'))
                api_url = '/V1/products/%s' % format(sku)
                response = req(magento_instance, api_url)
                result_list.append(response)
            except Exception as error:
                if log_book_id:
                    # Before process queue, delete some configurable's simple product.
                    # So mark that queue as Failed state and add log line
                    message = 'Magento Product not found with SKU %s' %  prod_res.get('sku')
                    log_book_id.add_log_line(message, False,
                                             order_data_queue_line_id,
                                             queue_line,
                                             prod_res.get('sku'))
                    log_error = True
        final_prod_res.update({'items':result_list})
        return final_prod_res, log_error

    def create_or_update_product_in_magento(
            self, order_responses, magento_instance, magento_per_sku, order_ref, order_data_queue_line_id, log_book_id
    ):
        """
        Create or update product when import orders from Magento.
        :param order_responses: Order Response received from Magento
        :param magento_instance: Instance of Magento
        :param magento_per_sku: Dictionary of Magento Product
        :param order_ref: Order reference
        :param order_data_queue_line_id: Order data queue line id
        :return: common log book object and skip order
        """
        magento_product_template_obj = self.env['magento.product.template']
        skip_order = False
        for order_response in order_responses:
            # Check the ordered product is already exist in the magento product product layer or not.
            # If product is already exist then no need to again send the API call.
            # Used existing product.
            magento_product_obj = self.env['magento.product.product'].search(
                [('magento_instance_id', '=', magento_instance.id), '|',
                 ('magento_product_id', '=', order_response.get('product_id')),
                 ('magento_sku', '=', order_response.get('sku'))],
                limit=1)
            if not magento_product_obj:
                product_obj = self.env['product.product'].search([('default_code', '=', order_response.get('sku'))])
                if product_obj:
                    continue
                try:
                    # every time send the product API call by using product id.
                    # To stop the product API call by using SKU because at that time
                    # wrong product id set in the magento product template and also
                    # create only single simple product which was ordered (Configurable product)
                    # Using this code if only single simple product ordered then also if main
                    # configurable product not found then create that main configurable product with all the variants.
                    filter = {'entity_id': order_response.get('product_id')}
                    search_criteria = create_search_criteria(filter)
                    query_string = Php.http_build_query(search_criteria)
                    api_url = '/V1/products?%s' % query_string
                    response = req(magento_instance, api_url).get('items')[0]
                except:
                    #Add below code for while order processing and product
                    # not found for the particular queue line then add log line and skip that queue line.
                    skip_order = True
                    message = _("Error While Requesting Product SKU %s") % order_response.get('sku')
                    log_book_id.add_log_line(message, order_ref,
                                             order_data_queue_line_id, "magento_order_data_queue_line_id",
                                             order_response.get('sku'))
                    continue
                magento_sku = response.get('sku')
                if not magento_per_sku or (
                        magento_per_sku and (magento_instance.id not in magento_per_sku.keys() or (
                        magento_instance.id in magento_per_sku.keys() and
                        magento_sku not in magento_per_sku[magento_instance.id].keys()))):
                    # Check product is simple type then sku of the order
                    # response and magento sku both are same.
                    # If ordered product is simple product and also have custom option.
                    # Then Ordered product sku and magento sku not same.
                    # So in that case need to check ordered product id and response product ID.
                    if order_response.get('product_type') == 'simple' and (
                            order_response.get('product_id') == response.get('id')
                            or order_response.get('sku') == magento_sku):
                        # Simple Product Process
                        skip_order = self.create_or_update_simple_product(response,
                                                                          magento_instance,
                                                                          log_book_id,
                                                                          skip_order,
                                                                          magento_per_sku,
                                                                          order_data_queue_line_id,
                                                                          order_ref)
                    # Check product type is configurable then in the ordered response we get simple product SKU and
                    # in the magento SKU we get main Configurable product sku. So Both are not same.
                    elif order_response.get('product_type') == 'configurable' \
                            and order_response.get('sku') != magento_sku:
                        # Configurable Product Process
                        skip_order = magento_product_template_obj.create_or_update_configurable_product(
                            response,
                            magento_instance,
                            log_book_id,
                            skip_order,
                            magento_per_sku,
                            order_data_queue_line_id,
                            order_ref
                        )
                    else:
                        skip_order = True
                        message = "Order %s skipped due to %s product type is not supported" % (
                            order_ref, response.get('type_id'))
                        log_book_id.add_log_line(message, order_ref,
                                                 order_data_queue_line_id, "magento_order_data_queue_line_id",
                                                 order_response.get('sku'))
                        break
        return skip_order

    def create_product_inventory(self, instance):
        """
        This method is used to import product stock from magento,
        when Multi inventory sources is not available.
        It will create a product inventory.
        :param instance: Instance of Magento
        :return: True
        """
        stock_to_import = []
        stock_inventory = self.env['stock.inventory']
        log_book_id = False
        if instance.is_import_product_stock:
            import_stock_location = instance.import_stock_warehouse
            location = import_stock_location and import_stock_location.lot_stock_id
            if location:
                model_id = self.env['common.log.lines.ept'].get_model_id('stock.inventory')
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
        magento_product_obj = self.env['magento.product.product']
        try:
            api_url = '/V1/stockItems/lowStock?scopeId=0&qty=10000000000&pageSize=100000'
            response = req(instance, api_url)
        except Exception as exc:
            log_book_id.write({
                'log_lines': [(0, 0, {
                    'message': "Request is not satisfied please check API connection"
                })]
            })

        if response.get('items'):
            for inventory in response.get('items'):
                magento_prod = magento_product_obj.search([
                    ('magento_product_id', '=', inventory.get('product_id')),
                    ('magento_instance_id', '=', instance.id),
                    ('magento_website_ids', '!=', False)
                ])
                if magento_prod:
                    qty = inventory.get('qty') or False
                    if qty and qty > 0.0:
                        stock_to_import.append({
                            'product_id': magento_prod.odoo_product_id,
                            'product_qty': qty,
                            'location_id': location
                        })
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
        stock_inventory = self.env['stock.inventory']
        magento_product_obj = self.env['magento.product.product']
        if instance.is_import_product_stock:
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
                        raise UserError(_("Error while requesting products" + str(error)))
                    if response.get('items'):
                        for inventory in response.get('items'):
                            magento_prod = magento_product_obj.search([
                                ('magento_sku', '=', inventory.get('sku')), ('magento_instance_id', '=', instance.id),
                                ('magento_website_ids', '!=', False)
                            ])
                            if magento_prod:
                                qty = inventory.get('quantity') or False
                                if qty and qty > 0.0:
                                    stock_to_import.append({
                                        'product_id': magento_prod.odoo_product_id,
                                        'product_qty': qty,
                                        'location_id': location
                                    })
                    stock_inventory.create_stock_inventory_ept(stock_to_import, location, True)
                else:
                    raise UserError(_("Please Choose Import product stock location for %s") % magento_location.name)
        return True

    def export_multiple_product_stock_to_magento(self, instance):
        """
        This method is used to export multiple product stock from odoo to magento.
        :param instance: Instance of Magento
        :return:
        """
        magento_product_obj = self.env['magento.product.product']
        stock_data = []
        model_id = self.env['common.log.lines.ept'].get_model_id('magento.product.product')
        job = self.env['common.log.book.ept'].create({
            'name': 'Export Product Stock', 'type': 'export', 'module': 'magento_ept',
            'model_id': model_id, 'res_id': self.id, 'magento_instance_id': instance.id})
        export_product_stock = self.get_export_product_stock(instance, instance.warehouse_ids)
        if export_product_stock:
            for product_id, stock in export_product_stock.items():
                exp_product = magento_product_obj.search([
                    ('odoo_product_id', '=', product_id), ('magento_instance_id', '=', instance.id)])
                if exp_product and stock >= 0.0:
                    product_stock_dict = {'sku': exp_product.magento_sku, 'qty': stock, 'is_in_stock': 1}
                    stock_data.append(product_stock_dict)
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
        magento_product_obj = self.env['magento.product.product']
        stock_data = []
        model_id = self.env['common.log.lines.ept'].get_model_id('magento.product.product')
        job = self.env['common.log.book.ept'].create({
            'name': 'Export Product Stock', 'type': 'export', 'module': 'magento_ept',
            'model_id': model_id, 'res_id': self.id, 'magento_instance_id': instance.id})
        for magento_location in magento_locations:
            export_stock_locations = magento_location.mapped('export_stock_warehouse_ids')
            if export_stock_locations and export_stock_locations.ids:
                export_product_stock = self.get_export_product_stock(instance, export_stock_locations)
                if export_product_stock:
                    for product_id, stock in export_product_stock.items():
                        exp_product = magento_product_obj.search([
                            ('odoo_product_id', '=', product_id), ('magento_instance_id', '=', instance.id)
                        ])
                        if exp_product and stock >= 0.0:
                            stock_data.append({'sku': exp_product.magento_sku,
                                               'source_code': magento_location.magento_location_code,
                                               'quantity': stock, 'status': 1})
            else:
                raise UserError(_("Please Choose Export product stock location for %s", magento_location.name))
        if stock_data:
            data = {'sourceItems': stock_data}
            api_url = "/V1/inventory/source-items"
            job = self.call_export_product_stock_api(instance, api_url, data, job, 'POST')
        if not job.log_lines:
            job.sudo().unlink()
        return True

    def get_export_product_stock(self, instance, export_stock_locations):
        """
        Get export product stock dictionary with stock.
        :param instance: Magento instance object
        :param export_stock_locations: Stock location object
        :return: Export product stock dictionary.
        """
        product_product_obj = self.env['product.product']
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
                message = response.get('message')
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
