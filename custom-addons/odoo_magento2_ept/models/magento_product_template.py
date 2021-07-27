# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
"""
Describes fields and methods for Magento products templates
"""
import json
from odoo import models, fields, api

PRODUCT_TEMPLATE = 'product.template'
MAGENTO_PRODUCT = 'magento.product.product'
MAGENTO_WEBSITE = 'magento.website'
MAGENTO_PRODUCT_IMAGE = 'magento.product.image'
PRODUCT_PRODUCT = 'product.product'
PRODUCT_ATTRIBUTE = 'product.attribute'


class MagentoProductTemplate(models.Model):
    """
    Describes fields and methods for Magento products templates
    """
    _name = 'magento.product.template'
    _description = 'Magento Product Template'
    _rec_name = "magento_product_name"

    magento_instance_id = fields.Many2one(
        'magento.instance',
        'Instance',
        ondelete="cascade",
        help="This field relocates magento instance"
    )
    magento_product_template_id = fields.Char(
        string="Magento Product Id",
        help="Magento Product Id"
    )
    magento_product_name = fields.Char(
        string="Magento Product Name",
        help="Magento Product Name",
        translate=True
    )
    odoo_product_template_id = fields.Many2one(
        PRODUCT_TEMPLATE,
        string="Odoo Product Template",
        ondelete='restrict',
        required=True
    )
    magento_product_ids = fields.One2many(
        MAGENTO_PRODUCT,
        'magento_tmpl_id',
        string="Magento Products",
        help="Magento Products"
    )
    magento_website_ids = fields.Many2many(
        MAGENTO_WEBSITE,
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
    magento_sku = fields.Char(string="Magento Product SKU", help="Magento Product SKU")
    description = fields.Text(string="Product Description", help="Description", translate=True)
    short_description = fields.Text(
        string='Product Short Description',
        help='Short Description',
        translate=True
    )
    magento_product_image_ids = fields.One2many(
        MAGENTO_PRODUCT_IMAGE,
        'magento_tmpl_id',
        string="Magento Product Images",
        help="Magento Product Images"
    )
    magento_product_price = fields.Float(
        string="Magento Product Prices",
        help="Magento Product Price"
    )
    sync_product_with_magento = fields.Boolean(
        string='Sync Product with Magento',
        help="If Checked means, Product synced With Magento Product"
    )
    active_template = fields.Boolean('Odoo Template Active', related="odoo_product_template_id.active")
    active = fields.Boolean("Active", default=True)
    image_1920 = fields.Image(related="odoo_product_template_id.image_1920")
    total_magento_variants = fields.Integer(string="Total Variants", compute='_compute_total_magento_variant')
    list_price = fields.Float(
        'Sales Price', related='odoo_product_template_id.list_price', readonly=False,
        digits='Product Price')
    standard_price = fields.Float(
        'Cost', related='odoo_product_template_id.standard_price', readonly=False,
        digits='Product Price')
    attribute_line_ids = fields.One2many(related='odoo_product_template_id.attribute_line_ids')
    currency_id = fields.Many2one(related='odoo_product_template_id.currency_id')

    _sql_constraints = [('_magento_template_unique_constraint',
                         'unique(magento_sku,magento_instance_id,magento_product_template_id)',
                         "Magento Product Template must be unique")]

    @api.depends('magento_product_ids.magento_tmpl_id')
    def _compute_total_magento_variant(self):
        for template in self:
            # do not pollute variants to be prefetched when counting variants
            template.total_magento_variants = len(template.with_prefetch().magento_product_ids)

    def view_odoo_product_template(self):
        """
        This method id used to view odoo product template.
        :return: Action
        """
        if self.odoo_product_template_id:
            return {
                'name': 'Odoo Product',
                'type': 'ir.actions.act_window',
                'res_model': PRODUCT_TEMPLATE,
                'view_type': 'form',
                'view_mode': 'tree,form',
                'domain': [('id', '=', self.odoo_product_template_id.id)],
            }
        return True

    def create_or_update_configurable_product(
            self, item, magento_instance, log_book_id,
            error, magento_per_sku, order_data_queue_line_id, order_ref=False,
    ):
        """
        Create or Update product with product variants
        :param item: Product items received from magento
        :param magento_instance: Instance of Magento
        :param log_book_id: Common log book object
        :param error: if error, it will return True.
        :param magento_per_sku: Dictionary of Magento Product
        :param order_ref: order reference
        :param order_data_queue_line_id: queue line object
        :return: error log if any
        """
        magento_product_template = self.search([
            ('magento_sku', '=', item.get('sku')), ('magento_instance_id', '=', magento_instance.id)
        ])
        order_ref, queue_line = self.get_order_ref_and_queue_line(order_ref, item)
        if 'configurable_product_options_data' not in item.get('extension_attributes'):
            message = "Please check Apichange extention is installed in Magento store."
            log_book_id.write({
                'log_lines': [(0, 0, {
                    'message': message,
                    'order_ref': order_ref,
                    queue_line: order_data_queue_line_id
                })]
            })
            error = True
            return error
        if magento_product_template:
            odoo_template, log_book_id, error = magento_product_template.check_product_template_is_exist_or_not(
                magento_instance, item, log_book_id, error, order_ref, queue_line, order_data_queue_line_id
            )
            if odoo_template and not error:
                magento_product_template_values = self.prepare_magento_product_template_vals(
                    item, magento_instance, odoo_template)
                magento_product_template.write(magento_product_template_values)
        else:
            odoo_template_id, log_book_id, error = self.check_product_template_is_exist_or_not(
                magento_instance, item, log_book_id, error, order_ref, queue_line, order_data_queue_line_id
            )
            if odoo_template_id:
                magento_product_template = self.search([
                    ('odoo_product_template_id', '=', odoo_template_id.id),
                    ('magento_instance_id', '=', magento_instance.id)
                ])
                if not magento_product_template:
                    magento_product_template, error = self.create_magento_product_template(
                        magento_instance, item, odoo_template_id,
                        log_book_id, order_ref, queue_line, order_data_queue_line_id, error)
        if not error:
            error = self.set_variant_sku(
                magento_instance, item, magento_product_template, magento_per_sku,
                log_book_id, error, order_data_queue_line_id, queue_line, order_ref)
            odoo_template = magento_product_template.odoo_product_template_id
            odoo_template.write({'name': item.get('name')})
        return error

    @staticmethod
    def get_order_ref_and_queue_line(order_ref, item):
        """
        Get Order_ref and queue_line.
        :param order_ref: order ref
        :param item: item received from Magento
        :return: order_ref and queue_line
        """
        queue_line = 'magento_order_data_queue_line_id'
        if not order_ref:
            queue_line = 'import_product_queue_line_id'
            order_ref = item.get('id')
        return order_ref, queue_line

    def get_magento_websites_and_descriptions(self, magento_instance_id, item):
        """
        return magento_websites, description, and short_description from the product item response.
        :param magento_instance_id:
        :param item:
        :return: magento_websites
        :return: description
        :return: short_description
        """
        description = short_description = ''
        website_ids = item.get('extension_attributes').get('website_ids')
        magento_websites = self.env[MAGENTO_WEBSITE].search([
            ('magento_website_id', 'in', website_ids),
            ('magento_instance_id', '=', magento_instance_id)
        ])
        for attribute_code in item.get('custom_attributes'):
            if attribute_code.get('attribute_code') == 'description':
                description = attribute_code.get('value')
            if attribute_code.get('attribute_code') == 'short_description':
                short_description = attribute_code.get('value')
        return magento_websites, description, short_description

    def prepare_magento_product_template_vals(self, item, magento_instance, odoo_template):
        """
        Prepare vals for the magento product template
        :param item: product vals
        :param magento_instance: magento instance
        :param odoo_template: odoo template
        :return: vals
        """
        ir_config_parameter_obj = self.env["ir.config_parameter"]
        if not odoo_template:
            magento_websites, description, short_description = self.get_magento_websites_and_descriptions(
                magento_instance.id, item
            )
        else:
            website_ids = item.get('extension_attributes').get('website_ids')
            magento_websites = self.env[MAGENTO_WEBSITE].search([
                ('magento_website_id', 'in', website_ids),
                ('magento_instance_id', '=', magento_instance.id)
            ])
            description = odoo_template.description_sale
            short_description = odoo_template.description
        values = {
            'magento_product_template_id': item.get('id'),
            'magento_product_name': item.get('name'),
            'magento_instance_id': magento_instance.id,
            'magento_website_ids': [(6, 0, magento_websites.ids)],
            'magento_sku': item.get('sku'),
            'product_type': item.get('type_id'),
            'created_at': item.get('created_at'),
            'updated_at': item.get('updated_at'),
            'odoo_product_template_id': odoo_template.id if odoo_template else False,
            'sync_product_with_magento': True
        }
        if ir_config_parameter_obj.sudo().get_param("odoo_magento2_ept.set_magento_sales_description"):
            values.update({
                'description': description,
                'short_description': short_description,
            })
        return values

    def check_product_template_is_exist_or_not(
            self, magento_instance, item, log_book_id, error, order_ref, queue_line, order_data_queue_line_id
    ):
        """
        This method is used for checking odoo product template exist or not.
        :param magento_instance: Instance of Magento
        :param item: Product items received from magento
        :param log_book_id: common log book object
        :param error: True if error else False
        :param order_ref: Order reference
        :param queue_line: product or order queue line
        :param order_data_queue_line_id: queue line object
        :return: odoo_product, common product log and error
        """
        odoo_template_id = magento_sku = False
        configurable_product_options_data = item.get('extension_attributes').get('configurable_product_options_data')
        if item.get('extension_attributes').get('configurable_product_link_data'):
            for link in item.get('extension_attributes').get('configurable_product_link_data'):
                link = json.loads(link)
                magento_sku = link.get('simple_product_sku')
                if not magento_sku:
                    continue
                odoo_template_id = self.search_odoo_product_template_exists(magento_sku, item)
                if odoo_template_id and len(odoo_template_id.attribute_line_ids) > 0 and \
                        len(odoo_template_id.attribute_line_ids) != len(configurable_product_options_data):
                    # Magento side product attribute and odoo product attribute total both are different
                    # Create log and set error as True
                    # Make queue as Failed
                    message = '%s having mismatch Attribute count' \
                              '\n%s product having %s attribute at magento side and %s Attribute at odoo side.' \
                              % (item.get('sku'), item.get('sku'),
                                 len(configurable_product_options_data),
                                 len(odoo_template_id.attribute_line_ids))
                    log_book_id.add_log_line(message, order_ref,
                                             order_data_queue_line_id, queue_line, item.get('sku'))
                    error = True
                    odoo_template_id = False
                    return odoo_template_id, log_book_id, error
                if odoo_template_id:
                    break
            odoo_template_id, error = self.create_missing_variant_of_existing_odoo_product_template(
                odoo_template_id, configurable_product_options_data, magento_instance,
                item, log_book_id, order_ref, order_data_queue_line_id, queue_line, error)
        if not error:
            odoo_template_id, error = self.create_odoo_prod_temp_based_on_configuration(
                odoo_template_id, magento_instance, item, magento_sku, log_book_id,
                order_ref, order_data_queue_line_id, queue_line, error)
        return odoo_template_id, log_book_id, error

    def search_odoo_product_template_exists(self, magento_sku, item):
        """
        Search Odoo product template exists or not.
        :param magento_sku: SKU received from Magento
        :param item: item received from Magento
        :return: odoo product template object or False
        """
        product_obj = self.env[PRODUCT_PRODUCT]
        magento_product_obj = self.env[MAGENTO_PRODUCT]
        magento_product_product = magento_product_obj.search([('magento_sku', '=', magento_sku)])
        if magento_product_product:
            existing_products = magento_product_product.odoo_product_id
        else:
            existing_products = product_obj.search([('default_code', '=', magento_sku)])
        if not existing_products:
            # not getting product.product record using SKU then search in magento.product.product.
            # product not exist in odoo variant but exist in magento variant layer
            magento_product_template = self.search([('magento_sku', '=', item.get('sku'))], limit=1)
            odoo_template_id = magento_product_template.odoo_product_template_id if \
                magento_product_template else False
        else:
            odoo_template_id = existing_products and existing_products[0].product_tmpl_id
        return odoo_template_id

    def create_missing_variant_of_existing_odoo_product_template(
            self, odoo_template_id, configurable_product_options_data, magento_instance,
            item, log_book_id, order_ref, order_data_queue_line_id, queue_line, error):
        if odoo_template_id and \
                len(odoo_template_id.attribute_line_ids) == 0 and \
                len(configurable_product_options_data) > 0:
            # Case 1: First Magento product is simple and import in odoo
            # result : There is not any variant for the imported product (In odoo layer)
            # Case 2 : Now add new variant in magento and
            # make that simple product as configurable and then import
            # result : Not create new product but add that variant in the odoo product.
            # (Which was simple before import product second time)
            if magento_instance.auto_create_product:
                attribute_line_vals = self.prepare_attribute_line_data(
                    item.get('extension_attributes').get('configurable_product_options_data')
                )
                odoo_template_id.update({'attribute_line_ids': attribute_line_vals})
                odoo_template_id._create_variant_ids()
                error = True
            else:
                message = 'In odoo : %s is simple product and Magento that product type is configurable' \
                          ' \nAnd your "Automatically Create Odoo Product If Not Found" ' \
                          ' setting is %s ' % (item.get('sku'), magento_instance.auto_create_product)
                log_book_id.add_log_line(message, order_ref, order_data_queue_line_id,
                                         queue_line, item.get('sku'))
        if odoo_template_id and \
                len(item.get('extension_attributes').get('configurable_product_link_data')) != \
                len(odoo_template_id.product_variant_ids) and \
                len(odoo_template_id.attribute_line_ids) == len(configurable_product_options_data):
            # product template exist in odoo
            # Product attribute of odoo and magento both are same
            # Product attribute value is different at odoo and magento side
            # add new value for the existing attribute in template
            if magento_instance.auto_create_product:
                self.add_new_variant_value(odoo_template_id, item)
            else:
                message = 'Relevant variant not found for %s product. ' \
                          ' \nAnd your "Automatically Create Odoo Product If Not Found" ' \
                          ' setting is %s ' % (item.get('sku'), magento_instance.auto_create_product)
                log_book_id.add_log_line(message, order_ref, order_data_queue_line_id,
                                         queue_line, item.get('sku'))
                error = True
        return odoo_template_id, error

    def create_odoo_prod_temp_based_on_configuration(
            self, odoo_template_id, magento_instance, item, magento_sku, log_book_id,
            order_ref, order_data_queue_line_id, queue_line, error):
        if (not odoo_template_id) and (not magento_instance.auto_create_product):
            message = 'Magento Product Template : %s or ' \
                      '\nAny relevant variants are not found with SKU : %s' \
                      '\nAnd your "Automatically Create Odoo Product If Not Found" setting is %s ' \
                      % (item.get('sku'), magento_sku, magento_instance.auto_create_product)
            log_book_id.add_log_line(message, order_ref, order_data_queue_line_id, queue_line, item.get('sku'))
            error = True
        elif (not odoo_template_id) and magento_instance.auto_create_product:
            odoo_template_id = self.create_odoo_product_template(item, magento_instance)
        return odoo_template_id, error

    def add_new_variant_value(self, odoo_template_id, item):
        """
        Add new value in the existing attribute. Create new variant product
        :param odoo_template_id: odoo template object
        :param item: Product Item
        :return:
        """
        if item.get('extension_attributes').get('configurable_product_options_data'):
            for option_data in item.get('extension_attributes').get('configurable_product_options_data'):
                option_data = json.loads(option_data)
                odoo_attribute, product_attribute_value_obj = self.find_odoo_attribute_and_values(
                    option_data, odoo_template_id)
                self.insert_product_attribute_values(odoo_attribute, option_data, product_attribute_value_obj)
            odoo_template_id._create_variant_ids()

    def insert_product_attribute_values(self, odoo_attribute, option_data, product_attribute_value_obj):
        if odoo_attribute and option_data.get('opt_values'):
            for opt_value in option_data.get('opt_values'):
                attrib_value = self.find_odoo_attribute_value_id(odoo_attribute, opt_value)
                if attrib_value and attrib_value.id not in product_attribute_value_obj.value_ids.ids:
                    product_attribute_value_obj.value_ids = [(4, attrib_value.id, False)]

    def find_odoo_attribute_and_values(self, option_data, odoo_template_id):
        product_attribute_obj = self.env[PRODUCT_ATTRIBUTE]
        odoo_attribute = product_attribute_obj.get_attribute(
            option_data.get('frontend_label'),
            create_variant='always',
            auto_create=True
        )
        product_attribute_value_obj = odoo_template_id.attribute_line_ids. \
            filtered(lambda x: x.attribute_id.id == odoo_attribute.id)
        return odoo_attribute, product_attribute_value_obj

    def create_odoo_product_template(self, item, magento_instance):
        """
        Create Odoo product template if not found
        :param item: Response received from magento
        :param magento_instance: Magento instance object
        :return: odoo_template
        """
        odoo_template = False
        ir_config_parameter_obj = self.env["ir.config_parameter"]
        product_template_obj = self.env[PRODUCT_TEMPLATE]
        extension_attributes = item.get('extension_attributes') or False
        if extension_attributes:
            attribute_line_vals = self.prepare_attribute_line_data(
                item.get('extension_attributes').get('configurable_product_options_data')
            )
            if attribute_line_vals:
                magento_websites, description, short_description = self.get_magento_websites_and_descriptions(
                    magento_instance.id, item
                )
                vals = {
                    'name': item.get('name'),
                    'type': 'product',
                    'attribute_line_ids': attribute_line_vals,
                    'sale_ok': True,
                    'purchase_ok': True,
                    'categ_id': magento_instance.import_product_category.id,
                    'invoice_policy': 'order'
                }
                if ir_config_parameter_obj.sudo().get_param("odoo_magento2_ept.set_magento_sales_description"):
                    vals.update({
                        'description': short_description,
                        'description_sale': description,
                    })
                # set the product category based on the instance setting
                odoo_template = product_template_obj.create(vals)
        return odoo_template

    def create_magento_product_template(
            self, magento_instance, item, odoo_template, log_book_id,
            order_ref, queue_line, order_data_queue_line_id, error):
        """
        This method is used for creating a product template in odoo.
        :param magento_instance: Instance of Magento
        :param item: Product Items received from Magento
        :param odoo_template: Odoo Product Template Object
        :param log_book_id: common log book object
        :param order_ref: Order reference/ product sku
        :param queue_line: magento order data queue line object
        :param order_data_queue_line_id: magento order data queue line id
        :param error: True if any error else False
        :return: magento_product_template,log_lines
        """
        website_ids = item.get('extension_attributes').get('website_ids')
        magento_websites = self.env[MAGENTO_WEBSITE].search(
            [('magento_instance_id', '=', magento_instance.id),
             ('magento_website_id', 'in', website_ids)], limit=1)
        magento_stores = magento_websites.store_view_ids
        template_vals = self.prepare_magento_product_template_vals(
            item, magento_instance, odoo_template
        )
        magento_product_template = self.create(template_vals)
        if magento_instance.allow_import_image_of_products:
            magento_media_url = False
            if magento_stores:
                magento_media_url = magento_stores[0].base_media_url
            if magento_media_url:
                full_img_url, error = self.create_or_update_product_images(
                    magento_instance, False, magento_product_template,
                    magento_media_url, item.get('media_gallery_entries'),
                    log_book_id, order_ref, queue_line, order_data_queue_line_id, error
                )
        self._cr.commit()
        return magento_product_template, error

    def set_variant_sku(
            self, magento_instance, item, magento_template,
            magento_per_sku, log_book_id, error, order_data_queue_line_id, queue_line, order_ref
    ):
        """
        Set different product variants of Product template.
        :param magento_instance: Instance of Magento
        :param item: Product Items received from Magento
        :param magento_template: Magento Template object
        :param magento_per_sku: Dictionary of Products
        :param log_book_id: Common log book object
        :param error: If error, It returns True
        :param order_data_queue_line_id: queue line object
        :param queue_line: magento order data queue line object
        :param order_ref: Order reference/ product sku
        :return: Logs if any
        """
        magento_product_obj = self.env[MAGENTO_PRODUCT]
        odoo_product_obj = self.env[PRODUCT_PRODUCT]
        odoo_product = False
        total_configured_variant_in_magento = len(
            item.get('extension_attributes').get('configurable_product_options')) \
            if item.get('extension_attributes').get('configurable_product_options') \
            else 0
        magento_prod_type = item if item.get('type_id') == 'configurable' else False
        variation_product_data, error = self.prepare_variation_product_data_dict(
            item, magento_instance, queue_line, error, log_book_id, order_data_queue_line_id)
        if variation_product_data:
            for variation_product in variation_product_data.get('items'):
                domain = []
                attribute_value_ids = self. \
                    get_attribute_value(variation_product.get('sku'),
                                        item.get('extension_attributes').get('configurable_product_link_data'))
                domain = self.prepare_attribute_domain(
                    attribute_value_ids, domain, magento_template, odoo_product,
                    variation_product.get('sku'), total_configured_variant_in_magento)

                if total_configured_variant_in_magento > 1:
                    self.write_product_product_sku(domain, magento_template.odoo_product_template_id.id,
                                                   odoo_product, variation_product.get('sku'))

                if domain:
                    domain.append(
                        ('product_tmpl_id', '=', magento_template.odoo_product_template_id.id)
                    )
                    odoo_product = odoo_product_obj.search(domain)
                if odoo_product:
                    odoo_product.write({'default_code': variation_product.get('sku')})
                self.map_magento_product_with_magento_template(magento_instance,
                                                               variation_product.get('sku'), magento_template)
                error = magento_product_obj.create_or_update_simple_product(
                    variation_product, magento_instance, log_book_id, error,
                    magento_per_sku, order_data_queue_line_id, magento_prod_tmpl=magento_template,
                    conf_product_item=magento_prod_type, order_ref=order_ref
                )  # pass conf_product_item parameter to set Magento Product Id and Magento Product SKU
                # while import product and product is already mapped before perform import operation
        return error

    def prepare_variation_product_data_dict(
            self, item, magento_instance, queue_line, error, log_book_id, order_data_queue_line_id):
        """
        Prepare Variation product data dictionary
        :param item: item received from Magento
        :param magento_instance: Magento instance object
        :param queue_line: sync import magento product data queue line object
        :param error: True if any error else False
        :param log_book_id: common log book object
        :param order_data_queue_line_id: sync import magento product data queue line id
        :return: dictionary of variant product
        """
        magento_product_obj = self.env[MAGENTO_PRODUCT]
        product_sku_array = []
        variation_product_data = {}
        update_product = True
        if queue_line == 'import_product_queue_line_id':
            update_product = self.env['sync.import.magento.product.queue.line'].browse(
                order_data_queue_line_id).do_not_update_existing_product
        if item.get('extension_attributes').get('configurable_product_links'):
            for product_link_data in item.get('extension_attributes').get('configurable_product_link_data'):
                product_link_data = json.loads(product_link_data)
                magento_product = magento_product_obj.sudo(). \
                    search([('magento_sku', '=', product_link_data.get('simple_product_sku')),
                            ('magento_instance_id', '=', magento_instance.id)])
                if (not magento_product) or (not magento_product.magento_product_id) or (
                        magento_product and not update_product):
                    # add this code for only append sku while product not exist in the magento product layer
                    # or product exist and not checked the "Do not update product?" checkbox.
                    # Product exist in magento layer. Because previously perform map operation.
                    # So in that case product ID not set, So we sent the request to get the product data.
                    product_sku_array.append({'sku': product_link_data.get('simple_product_sku')})
            if product_sku_array:
                variation_product_data, error = magento_product_obj. \
                    get_magento_product_by_sku(magento_instance,
                                               product_sku_array, queue_line,
                                               error, log_book_id,
                                               order_data_queue_line_id)
        return variation_product_data, error

    def prepare_attribute_domain(
            self, attribute_value_ids, domain, magento_template, odoo_product,
            sku, total_configured_variant_in_magento):
        """
        prepare the domain for the attribute
        :param attribute_value_ids:  value ids of the odoo attribute
        :param domain: domain
        :param magento_template: magento template object
        :param odoo_product: odoo product object
        :param sku: variation product sku
        :param total_configured_variant_in_magento: number of configured variant in magento (variant count)
        :return: domain
        """
        for attribute_value_id in attribute_value_ids:
            tpl = ('product_template_attribute_value_ids.product_attribute_value_id', '=', attribute_value_id)
            domain.append(tpl)
            if total_configured_variant_in_magento == 1:
                self.write_product_product_sku(domain, magento_template.odoo_product_template_id.id, odoo_product,
                                               sku)
                domain = []
        return domain

    def write_product_product_sku(self, domain, odoo_product_template_id, odoo_product, sku):
        """
        Write the sku in the odoo product product layer.
        :param domain: domain to find the odoo product
        :param odoo_product_template_id: odoo product template
        :param odoo_product: odoo product product
        :param sku: SKU
        :return:
        """
        odoo_product_obj = self.env[PRODUCT_PRODUCT]
        if domain:
            domain.append(
                ('product_tmpl_id', '=', odoo_product_template_id)
            )
            odoo_product = odoo_product_obj.search(domain)
        if odoo_product:
            odoo_product.write({'default_code': sku, 'invoice_policy': 'order'})

    def get_attribute_value(self, sku, configurable_product_link_data):
        """
        Get product attributes values by calling magento API.
        :param sku: SKU
        :param configurable_product_link_data: dictionary of child products
        :return: dictionary of attribute vals
        """
        product_attribute_obj = self.env[PRODUCT_ATTRIBUTE]
        attr_val_ids = []
        for link_data in configurable_product_link_data:
            link_data = json.loads(link_data)
            if link_data.get('simple_product_sku') == sku:
                for simple_product_data in link_data.get('simple_product_attribute'):
                    odoo_attribute = product_attribute_obj.get_attribute(
                        simple_product_data.get('label'),
                        create_variant='always',
                        auto_create=True
                    )
                    if odoo_attribute:
                        attrib_value = self.find_odoo_attribute_value_id(odoo_attribute,
                                                                         simple_product_data.get('value'))

                        attr_val_ids.append(attrib_value.id)
                break
        return attr_val_ids

    def find_odoo_attribute_value_id(self, odoo_attribute, attribute_value):
        """
        Find the value of the odoo attribute.
        :param odoo_attribute: product.attribute object
        :param attribute_value: value of the attribute
        :return: odoo attribute value
        """
        product_attribute_value_obj = self.env['product.attribute.value']
        attrib_value = product_attribute_value_obj.search([
            ('attribute_id', '=', odoo_attribute.id), ('name', '=', attribute_value)
        ], limit=1)
        if not attrib_value:
            attrib_value = product_attribute_value_obj.create({
                'attribute_id': odoo_attribute.id, 'name': attribute_value
            })
        return attrib_value

    def create_or_update_product_images(
            self, magento_instance, magento_product_id,
            magento_product_template_id, magento_media_url, media_gallery_response,
            log_book_id, order_ref, queue_line, order_data_queue_line_id, error
    ):
        """
        If product image not found, then create new product image other wise update it.
        :param magento_instance: Instance of Magento
        :param magento_product_id: Magento Product product Object
        :param magento_product_template_id: Magento Product Template Object
        :param magento_media_url: Magento Instance Media URL
        :param media_gallery_response: Product Images received from Magento
        :param log_book_id: common log book object
        :param order_ref: Order reference/ product sku
        :param queue_line: magento order data queue line object
        :param order_data_queue_line_id: magento order data queue line id
        :param error: True if any error else False
        """
        product_id = product_template_id = False
        if magento_product_id:
            product_id = magento_product_id.odoo_product_id
        if magento_product_template_id:
            product_template_id = magento_product_template_id.odoo_product_template_id
        for image_url in media_gallery_response:
            full_image_url = self.get_image_full_url(image_url, magento_media_url)
            prod_image = False
            try:
                prod_image = self.env['common.product.image.ept'].get_image_ept(full_image_url)
            except Exception:
                message = "%s \nCan't find image.\nPlease provide valid Image URL." % full_image_url
                log_book_id.add_log_line(message, order_ref, order_data_queue_line_id, queue_line,
                                         magento_product_template_id.magento_sku if magento_product_template_id else False)
                error = True
            if prod_image:
                magento_prod_image = self.get_and_set_product_images(
                    magento_product_id, magento_product_template_id, full_image_url,
                    image_url.get('types'), product_id, product_template_id, prod_image
                )
                if not magento_prod_image:
                    self.create_magento_product_image(
                        prod_image, magento_product_id, product_id, magento_product_template_id,
                        product_template_id, magento_instance, full_image_url, image_url)
                elif not magento_prod_image.odoo_image_id:
                    magento_prod_image.write({'odoo_image_id': magento_prod_image.id})
        return full_image_url, error

    @staticmethod
    def get_image_full_url(image_url, magento_media_url):
        full_image_url = ''
        file_url = image_url.get('file')
        if file_url:
            full_image_url = magento_media_url + 'catalog/product' + file_url
        return full_image_url

    def create_magento_product_image(
            self, prod_image, magento_product_id, product_id, magento_product_template_id,
            product_template_id, magento_instance, full_image_url, image_url):
        """

        :param prod_image: Base64 encoded image
        :param magento_product_id: Magento product product object
        :param product_id: product id
        :param magento_product_template_id: Magento product template object
        :param product_template_id: product template id
        :param magento_instance: Magento instance object
        :param full_image_url: Full image URL of product
        :param image_url: Image details received from Magento
        """
        common_prod_image = False
        if magento_product_id:
            common_prod_image = self.get_common_product_image(product_id, prod_image)
        elif magento_product_template_id:
            common_prod_image = self.get_common_product_image(product_template_id, prod_image)
        product_image_values = self.prepare_product_image_vals(
            magento_instance.id, product_id, product_template_id, full_image_url, prod_image,
            magento_product_id, magento_product_template_id, image_url.get('id')
        )
        if not common_prod_image:
            common_prod_image = self.env['common.product.image.ept'].create(product_image_values)
        else:
            common_prod_image.write({
                'magento_image_ids': product_image_values.get('magento_image_ids')})
        common_prod_image.magento_image_ids

    @staticmethod
    def get_common_product_image(product, product_image):
        """
        Search and get common product image.
        :param product: product/ product template object
        :param product_image: product image
        :return: common product image object
        """
        return product.ept_image_ids.filtered(lambda x: x.image == product_image)

    def get_and_set_product_images(
            self, magento_product_id, magento_product_template_id,
            full_image_url, image_type, product_id, product_template_id, prod_image
    ):
        """
        Set product/ product template main image and get magento product/ product template image.
        :param magento_product_id: Magento product product object
        :param magento_product_template_id: Magento product template object
        :param full_image_url: Full image url
        :param image_type: Image type
        :param product_id: Product product object
        :param product_template_id: Product template object
        :param prod_image: Product image
        :return: Magento product image object or False
        """
        magento_prod_image = False
        if magento_product_id:
            magento_prod_image = self.env[MAGENTO_PRODUCT_IMAGE].search([
                ('magento_product_id', '=', magento_product_id.id), ('url', '=', full_image_url)
            ])
            if image_type and 'image' in image_type:
                product_id.image_1920 = prod_image
        elif magento_product_template_id:
            magento_prod_image = self.env[MAGENTO_PRODUCT_IMAGE].search([
                ('magento_tmpl_id', '=', magento_product_template_id.id), ('url', '=', full_image_url)
            ])
            if image_type and 'image' in image_type:
                product_template_id.image_1920 = prod_image
        return magento_prod_image

    def prepare_product_image_vals(
            self, magento_instance_id, product_id, product_template_id, full_image_url,
            prod_image, magento_prod_id, magento_tmpl_id, image_id
    ):
        """
        Prepare dictionary for Product images
        :param magento_instance_id: Magento instance id
        :param product_id: Product product object
        :param product_template_id: Product template object
        :param full_image_url: Full image url
        :param prod_image: Product image
        :param magento_prod_id: Magento product id
        :param magento_tmpl_id: Magento product template id
        :param image_id: Image id
        :return: Dictionary for Product images
        """
        product_image_vals = {
            'product_id': product_id.id if product_id else False,
            'template_id': product_template_id.id if product_template_id else False,
            'url': full_image_url or '',
            'image': prod_image,
            'magento_image_ids': [(0, 0, {
                'magento_product_id': magento_prod_id.id if magento_prod_id else False,
                'magento_tmpl_id': magento_tmpl_id.id if magento_tmpl_id else False,
                'magento_image_id': image_id,
                'url': full_image_url or '',
                'image': prod_image,
                'magento_instance_id': magento_instance_id,
            })]
        }
        return product_image_vals

    def map_magento_product_with_magento_template(self, magento_instance, sku, magento_template):
        """
        This method is used to check magento product exist or not in odoo
        :param magento_instance: Instance of Magento
        :param sku: Magento Product SKU
        :param magento_template: Magento Product Template
        """
        magento_product_obj = self.env[MAGENTO_PRODUCT]
        magento_product = magento_product_obj.search([
            ('magento_sku', '=', sku),
            ('magento_instance_id', '=', magento_instance.id)
        ])
        if magento_product and magento_template and magento_product.magento_tmpl_id != magento_template \
                and magento_product.magento_tmpl_id.total_magento_variants > 1:
            # add last condition for while all simple product is in odoo layer.
            # all those is configurable's simple product in magento side
            # after map import that specific product
            # stop to overwride magento template in magento product.
            magento_product.magento_tmpl_id = magento_template.id

    def prepare_attribute_line_data(self, configurable_options):
        """
        This method is used to prepare attribute line  for set attribute line ids in template.
        :param configurable_options: Configurable product attributes options
        :return: Dictionary of Attribute values
        """
        attrib_line_vals = []
        attribute_line_ids_data = False
        if configurable_options:
            for option in configurable_options:
                attribute_data = json.loads(option)
                if attribute_data.get('frontend_label'):
                    odoo_attribute = self.env[PRODUCT_ATTRIBUTE].get_attribute(
                        attribute_data.get('frontend_label'),
                        create_variant='always',
                        auto_create=True
                    )
                    attr_val_ids = []
                    for option_values in attribute_data.get('opt_values'):
                        attrib_value = self.find_odoo_attribute_value_id(odoo_attribute,
                                                                         option_values)
                        attr_val_ids.append(attrib_value.id)
                    attribute_line_ids_data = (0, 0, {'attribute_id': odoo_attribute.id, 'value_ids': attr_val_ids})
                if attribute_line_ids_data:
                    attrib_line_vals.append(attribute_line_ids_data)
        return attrib_line_vals

    def open_variant_list(self):
        """
        This method used for smart button for view variant.
        @return: Action
        """
        form_view_id = self.env.ref('odoo_magento2_ept.view_magento_product_form').id
        tree_view = self.env.ref('odoo_magento2_ept.view_magento_product_tree').id
        action = {
            'name': 'Magento Product Variant',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'tree',
            'res_model': MAGENTO_PRODUCT,
            'views': [(tree_view, 'tree'), (form_view_id, 'form')],
            'view_id': tree_view,
            'target': 'current',
            'domain': [('id', 'in', self.magento_product_ids.ids)]
        }
        return action
