# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
"""
Describes fields and methods for Magento products
"""
import pytz
from datetime import datetime, timedelta
from odoo import fields, models, api, _
from odoo.exceptions import UserError
from .api_request import req

MAGENTO_DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'
PRODUCT_PRODUCT = 'product.product'
IMG_SIZE = 'image_1024'


class MagentoProductProduct(models.Model):
    """
    Describes fields and methods for Magento products
    """
    _name = 'magento.product.product'
    _description = 'Magento Product'
    _rec_name = 'magento_product_name'

    magento_instance_id = fields.Many2one('magento.instance','Magento Instance',
                                          help="This field relocates magento instance")
    magento_product_id = fields.Char(string="Magento Product Id")
    odoo_product_id = fields.Many2one(PRODUCT_PRODUCT, 'Odoo Product Variant', required=True, ondelete='restrict', copy=False)
    magento_website_ids = fields.Many2many('magento.website', string='Magento Product Websites', readonly=False,
                                           domain="[('magento_instance_id','=',magento_instance_id)]")
    magento_sku = fields.Char(string="Magento Simple Product SKU")
    magento_product_name = fields.Char(string="Magento Simple Product Name", related="odoo_product_id.name")
    active = fields.Boolean("Active", default=True)
    image_1920 = fields.Image(related="odoo_product_id.image_1920")
    thumbnail_image = fields.Image(string='Product Image')
    product_image_ids = fields.One2many(related="odoo_product_id.product_variant_image_ids")
    product_template_attribute_value_ids = fields.Many2many(related='odoo_product_id.product_template_attribute_value_ids')
    attribute_value_ids = fields.Many2many('product.template.attribute.value', compute="_compute_simpl_product_attributes")
    currency_id = fields.Many2one(related='odoo_product_id.currency_id')
    company_id = fields.Many2one(related='odoo_product_id.company_id')
    uom_id = fields.Many2one(related='odoo_product_id.uom_id')
    magento_conf_product_id = fields.Many2one('magento.configurable.product', string='Magento Configurable Product')
    magento_conf_prod_sku = fields.Char(string='Magento Config.Product SKU', related='magento_conf_product_id.magento_sku')
    inventory_category_id = fields.Many2one(string='Odoo product category', related='odoo_product_id.categ_id')
    x_magento_name = fields.Char(string='Product Name for Magento', compute="_compute_simpl_product_name")
    # category_ids = fields.Many2many("magento.product.category", string="Product Categories",
    #                                 help="Magento Product Categories", domain="[('instance_id','=',magento_instance_id)]")
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
    force_update = fields.Boolean(string="To force run Simple Product Export", default=False)
    bulk_log_ids = fields.Many2many('magento.async.bulk.logs', string="Async Bulk Logs")

    _sql_constraints = [('_magento_product_unique_constraint',
                         'unique(magento_sku,magento_instance_id,magento_product_id)',
                         "Magento Product must be unique")]

    @api.depends('product_template_attribute_value_ids', 'magento_conf_product_id')
    def _compute_simpl_product_attributes(self):
        for rec in self:
            rec.attribute_value_ids = rec.product_template_attribute_value_ids
            # avail_attrs = rec.magento_conf_product.odoo_prod_template_id.attribute_line_ids.filtered(
            #     lambda x: len(x.value_ids) > 1 and not x.attribute_id.is_ignored_in_magento).mapped('attribute_id').mapped('id')
            # rec.attribute_value_ids = rec.product_template_attribute_value_ids.filtered(
            #     lambda x: x.product_attribute_value_id.attribute_id.id in avail_attrs)

    @api.depends('magento_product_name', 'attribute_value_ids')
    def _compute_simpl_product_name(self):
        for rec in self:
            rec.x_magento_name = rec.magento_product_name + ' ' + ' '.join(rec.attribute_value_ids.product_attribute_value_id.mapped('name'))

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

    # product's stock export section
    def export_products_stock_to_magento(self, instance):
        """
        This method is used to export multiple product stock from odoo to magento
        :param instance: Instance of Magento
        :return:
        """
        stock_data = []
        export_product_stock = self.get_export_product_stock(instance, instance.location_ids)
        if export_product_stock:
            for product_id, stock in export_product_stock.items():
                exp_product = self.search([('odoo_product_id', '=', product_id),
                                           ('magento_instance_id', '=', instance.id)], limit=1)
                if exp_product and stock >= 0.0:
                    if exp_product.odoo_product_id.type == 'product':
                        product_stock_dict = {'sku': exp_product.magento_sku, 'qty': stock, 'is_in_stock': 1}
                        stock_data.append(product_stock_dict)
        if stock_data:
            data = {'skuData': stock_data}
            api_url = "/V1/product/updatestock"
            return self.call_export_product_stock_api(instance, api_url, data, 'PUT')

    def export_product_stock_to_multiple_locations(self, instance, magento_locations):
        """
        This method is used to export product stock to magento, when Multi inventory sources is available.
        It will create a product inventory
        :param instance: Instance of Magento
        :param magento_locations: Magento products object
        :return: True
        """
        stock_data = []
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
        if stock_data:
            data = {'sourceItems': stock_data}
            api_url = "/V1/inventory/source-items"
            return self.call_export_product_stock_api(instance, api_url, data, 'POST')

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

    def call_export_product_stock_api(self, instance, api_url, data, method_type):
        """
        Call export product stock API for single or multi tracking inventory
        :param instance: Magento instance object
        :param api_url: API Call URL
        :param data: Dictionary to be passed
        :param method_type: Api Request Method type (PUT/POST)
        :return:
        """
        stock_log_book_obj = self.env['magento.stock.log.book']
        is_error = False
        tz = pytz.timezone('Europe/Warsaw')
        batch_code = datetime.now(tz).strftime("%Y-%b-%d %H:%M:%S")
        self.clean_old_log_records(instance, stock_log_book_obj)

        try:
            responses = req(instance, api_url, method_type, data)
        except Exception as error:
            message = "Error while Export product stock " + str(error)
            stock_log_book_obj.create({
                'magento_instance_id': instance.id,
                'batch': batch_code,
                'log_message': message
            })
            return False

        if responses:
            for response in responses:
                if response.get('code', False) != '200':
                    is_error = True
                    stock_log_book_obj.create({
                        'magento_instance_id': instance.id,
                        'batch': batch_code,
                        'log_message': response.get('message', response)
                    })

        if is_error:
            return False
        else:
            stock_log_book_obj.create({
                'magento_instance_id': instance.id,
                'batch': batch_code,
                'log_message': "Successfully Exported"
            })
            return True

    @staticmethod
    def get_magento_product_stock(instance, product_ids, prod_obj, locations):
        """
        This Method relocates check type of stock
        :param instance: Magento instance
        :param product_ids: Id of products list
        :param prod_obj: Product object
        :param locations: Odoo locations related to Magento stock
        :return: This Method return product listing stock
        """
        product_listing_stock = False
        if product_ids:
            if instance.magento_stock_field == 'free_qty':
                product_listing_stock = prod_obj.get_free_qty(locations, product_ids)
            elif instance.magento_stock_field == 'virtual_available':
                product_listing_stock = prod_obj.get_forecasted_qty(locations, product_ids)
        return product_listing_stock

    @staticmethod
    def update_simp_product_dict_with_magento_data(magento_prod, ml_simp_products_dict):
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

    def check_simple_products_to_export(self, export_products, ml_simp_products, ml_conf_products):
        """
        Check if Simple Products export to Magento needed
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
            magento_date = ml_simp_products[prod].get('magento_update_date', '')

            if not export_date or ml_simp_products[prod]['force_update']:
                if ml_simp_products[prod]['magento_status'] == 'in_magento':
                    ml_simp_products[prod]['magento_status'] = 'update_needed'
                continue

            if export_date > update_date_simp:
                if magento_date and magento_date >= export_date:
                    if not ml_conf_products[conf_sku]['to_export']:
                        if ml_simp_products[prod]['do_not_export_conf'] or \
                                ml_simp_products[prod]['magento_prod_id'] in ml_conf_products[conf_sku]['children']:
                            export_prod = export_products.filtered(lambda p: p.magento_sku == prod)
                            # check if images count is the same in Odoo and Magento
                            # if (len(export_prod.odoo_product_id.product_variant_image_ids) +
                            #     (1 if export_prod.odoo_product_id.image_256 else 0)) !=\
                            #         len(ml_simp_products[prod].get('media_gallery', [])):
                            if (len(export_prod.product_image_ids)) != len(ml_simp_products[prod].get('media_gallery', [])):
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
                for simple_product in odoo_simp_prod:
                    prod_sku = simple_product.magento_sku
                    # to skip this step if only linking with parent needs to be done
                    if method == 'POST' or ml_simp_products[prod_sku]['magento_status'] != 'need_to_link':
                        res = self.export_single_simple_product_to_magento(
                            instance, simple_product, ml_simp_products, attr_sets, method
                        )
                        if res:
                            self.update_simp_product_dict_with_magento_data(res, ml_simp_products)
                        else:
                            continue
                    if not ml_simp_products[prod_sku]['do_not_export_conf']:
                        self.assign_attr_to_config_product(
                            instance, simple_product, attr_sets, ml_conf_products, ml_simp_products
                        )
                        if not ml_simp_products[prod_sku]['log_message']:
                            self.link_simple_to_config_product_in_magento(
                                instance, simple_product, ml_conf_products, ml_simp_products
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
                simp_prod_attr = prod.attribute_value_ids.product_attribute_value_id
                check_assign_attr = prod.magento_conf_product_id.check_product_attr_are_in_attributes_list(
                    [a.attribute_id.name for a in simp_prod_attr], ml_conf_products[conf_sku]['config_attr'])
                if not check_assign_attr:
                    text = "Simple product is missing attribute(s) defined as configurable. \n"
                    ml_simp_products[prod_sku]['log_message'] += text
                    continue

                prod_attr_set = prod.magento_conf_product_id.magento_attr_set
                available_attributes = attribute_sets[prod_attr_set]['attributes']
                # check if configurable product already contains such set of "Attribute: Value"
                # Return False if not (good result)
                check_attr_values = self.check_products_set_of_attribute_values(
                    ml_conf_products, conf_sku, simp_prod_attr, available_attributes, ml_simp_products, prod_sku
                )
                if check_attr_values:
                    text = "The same configurable Set of Attribute Values was found in " \
                           "Product - %s.\n" % check_attr_values
                    ml_simp_products[prod_sku]['log_message'] += text
                    continue

            if ml_simp_products[prod_sku].get('magento_update_date') and \
                    ml_simp_products[prod_sku]['magento_type_id'] != 'simple':
                text = "The Product with such sku is already in Magento. (And it's type isn't Simple Product)/"
                ml_simp_products[prod_sku]['log_message'] += text

    def check_simp_product_attributes_and_options_exist_in_magento(self, magento_instance, odoo_products, attribute_sets,
                                                                   ml_product_dict):
        """
        Check if Product's Attributes exist in Magento
        :param magento_instance: Instance of Magento
        :param odoo_products: Odoo Products to be exported
        :param attribute_sets: Dictionary with defined Attributes and their options in Magento
        :param ml_product_dict: Dictionary contains metadata for selected Simple Products (Odoo products)
        :return: None
        """
        for prod in odoo_products:
            prod_attributes = prod.attribute_value_ids.product_attribute_value_id
            if not len(prod_attributes) and not ml_product_dict[prod.magento_sku]['do_not_export_conf']:
                text = "Product - %s has no attributes.\n" % prod.magento_sku
                ml_product_dict[prod.magento_sku]['log_message'] += text
                continue
            prod_attr_set = prod.magento_conf_product_id.magento_attr_set
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
        prod_attr_set = product.magento_conf_product_id.magento_attr_set
        available_attributes = attr_sets[prod_attr_set]['attributes']
        config_product_sku = product.magento_conf_prod_sku
        product_attributes = product.attribute_value_ids.product_attribute_value_id
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
                product.magento_conf_product_id.get_attribute_name_by_id(available_attributes, attr.get("attribute_id")): (
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
                        'name': product.with_context(lang=lang_code).odoo_product_id.name + ' ' +\
                                          ' '.join(product.attribute_value_ids.product_attribute_value_id.mapped('name')),
                        'sku': sku,
                        'price': 0,
                        'custom_attributes': prod['product']["custom_attributes"].copy()
                    }
                }

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
                res = req(magento_instance, api_url, 'PUT', data_lst)
            except Exception:
                for product in data:
                    text = "Error while exporting products data to '%s' store view.\n" % view[1].magento_storeview_code
                    ml_products[product['product']['sku']]['log_message'] += text
                break

            if not res.get('errors', True):
                log_id = self.bulk_log_ids.create({
                    'bulk_uuid': res.get("bulk_uuid"),
                    'topic': 'Storeview-%s info export' % view[1].magento_storeview_code
                })
                prod_list = [p['product']['sku'] for p in data]
                odoo_products.filtered(
                    lambda x: x.magento_sku in prod_list and x.magento_instance_id == magento_instance
                ).write({'bulk_log_ids': [(4, log_id.id)]})

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
        prod_attr_set = product.magento_conf_product_id.magento_attr_set
        available_attributes = attr_sets[prod_attr_set]['attributes']
        prod_attr_list = [(self.to_upper(a.attribute_id.name), self.to_upper(a.name)) for a in
                          product.attribute_value_ids.product_attribute_value_id
                          if not a.attribute_id.is_ignored_in_magento]
        # add Product Life Phase attribute (aka x_status)
        if product.odoo_product_id.x_status:
            prod_attr_list.append(("PRODUCTLIFEPHASE", self.to_upper(product.odoo_product_id.x_status)))

        custom_attributes = self.map_product_attributes_with_magento_attr(prod_attr_list, available_attributes)

        # add Product's Website Description
        # if product.odoo_product_id.website_description:
        #     custom_attributes.append({
        #         "attribute_code": 'description',
        #         "value": product.odoo_product_id.website_description
        #     })

        # add product categories links
        # if product.magento_conf_product.do_not_create_flag:
        #     categ_list = [(cat.magento_prod_categ.id, cat.magento_prod_categ.category_id) for cat in
        #                   product.odoo_product_id.public_categ_ids if cat and cat.magento_prod_categ and
        #                   cat.magento_prod_categ.instance_id.id == magento_instance.id]
        # else:
        #     categ_list = [(cat.id, cat.category_id) for cat in product.magento_conf_product.category_ids]
        # ml_simp_products[product.magento_sku]['product_categ'] = [c[0] for c in categ_list]

        # get product stock from specified locations, valid for initial(POST) export only
        stock_item =  {
            "qty": self.get_magento_product_stock(magento_instance, [product.odoo_product_id.id],
                                                  self.env[PRODUCT_PRODUCT],
                                                  magento_instance.location_ids).get(product.odoo_product_id.id),
            "is_in_stock": "true"
        } if method == 'POST' else {}

        data = {
            "product": {
                "name": product.x_magento_name,
                # "name": product.magento_product_name,
                "attribute_set_id":  attr_sets[prod_attr_set]['id'],
                "status": 1,
                "visibility": 3,
                "price": 0,
                "type_id": "simple",
                "weight": product.odoo_product_id.weight,
                "custom_attributes": custom_attributes,
                "extension_attributes": {
                    "stock_item": stock_item,
                    # "category_links": [{"position": 0, "category_id": cat_id[1]} for cat_id in categ_list]
                }
            }
        }
        if method == 'POST':
            data["product"].update({"sku": product.magento_sku})

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
                product.magento_conf_product_id.process_product_websites_export(
                    magento_instance, ml_simp_products, product.magento_sku, response
                )

            # export data related to each storeview (product name/description, price)
            product.magento_conf_product_id.process_storeview_data_export(
                magento_instance, product, ml_simp_products, product.magento_sku, data, attr_sets, False
            )
            # process images export to magento
            if ml_simp_products[product.magento_sku].get('media_gallery', []):
                product.magento_conf_product_id.remove_product_images_from_magento(
                    magento_instance, ml_simp_products, product.magento_sku
                )

            if len(product.product_image_ids):
                prod_media = {
                    product.magento_sku: [
                        (img.id, img.name, getattr(img, IMG_SIZE), img.image_role) for img in product.product_image_ids if img
                    ]
                }
                product.magento_conf_product_id.export_media_to_magento(
                    magento_instance, prod_media, ml_simp_products, 'product.image'
                )
            # export product's thumbnail Image
            # if product.odoo_product_id.image_256:
            #     thumb_image = {
            #         product.magento_sku: [(product.odoo_product_id.product_tmpl_id.id, '', product.odoo_product_id.image_256)]
            #     }
            #     product.magento_conf_product_id.export_media_to_magento(
            #         magento_instance, thumb_image, ml_simp_products, 'product.template', True
            #     )

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
        # thumb_images = {}
        product_websites = []
        remove_images = []
        conf_prod_obj = self.env['magento.configurable.product']
        # get product stock from specified locations, valid for initial(POST) export only
        prod_stock = self.get_magento_product_stock(
            magento_instance, [p.odoo_product_id.id for p in odoo_products], self.env[PRODUCT_PRODUCT],
            magento_instance.location_ids
        ) if method == 'POST' else {}

        for prod in odoo_products:
            if prod.magento_sku in export_prod_list and ml_simp_products[prod.magento_sku]['magento_status'] != 'need_to_link':
                prod_attr_list = [(self.to_upper(a.attribute_id.name), self.to_upper(a.name)) for a in
                                  prod.attribute_value_ids.product_attribute_value_id
                                  if not a.attribute_id.is_ignored_in_magento]
                # add Product Life Phase attribute (aka x_status)
                if prod.odoo_product_id.x_status:
                    prod_attr_list.append(("PRODUCTLIFEPHASE", self.to_upper(prod.odoo_product_id.x_status)))

                custom_attributes = self.map_product_attributes_with_magento_attr(
                    prod_attr_list, attr_sets[prod.magento_conf_product_id.magento_attr_set]['attributes']
                )
                # add Product's Website Description
                # if prod.odoo_product_id.website_description:
                #     custom_attributes.append({
                #         "attribute_code": 'description',
                #         "value": prod.odoo_product_id.website_description
                #     })

                attr_set_id = attr_sets.get(prod.magento_conf_product_id.magento_attr_set, {}).get('id')
                # add product categories info
                # if prod.magento_conf_product.do_not_create_flag:
                #     categ_list = [(cat.magento_prod_categ.id, cat.magento_prod_categ.category_id) for cat in
                #                   prod.odoo_product_id.public_categ_ids if cat and cat.magento_prod_categ and
                #                   cat.magento_prod_categ.instance_id.id == magento_instance.id]
                # else:
                #     categ_list = [(cat.id, cat.category_id) for cat in prod.magento_conf_product.category_ids]
                # ml_simp_products[prod.magento_sku]['product_categ'] = [c[0] for c in categ_list]

                data.append({
                    "product": {
                        "sku": prod.magento_sku,
                        # "name": prod.magento_product_name,
                        "name": prod.x_magento_name,
                        "attribute_set_id": attr_set_id,
                        "status": 1,
                        "visibility": 3,
                        "price": 0,
                        "type_id": "simple",
                        "weight": prod.odoo_product_id.weight,
                        "extension_attributes": {
                            "stock_item": {"qty": prod_stock.get(prod.odoo_product_id.id) or 0,
                                           "is_in_stock": "true"} if method == 'POST' else {},
                            # "category_links": [{"position": 0, "category_id": cat_id[1]} for cat_id in categ_list]
                        },
                        "custom_attributes": custom_attributes
                    }
                })

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

        log_id = self.bulk_log_ids.create({
            'bulk_uuid': response.get("bulk_uuid"),
            'topic': 'Product Export'
        })
        for prod in odoo_products:
            if prod.magento_sku in export_prod_list:
                img_update = False
                ml_simp_products[prod.magento_sku]['export_date_to_magento'] = datetime.now()
                ml_simp_products[prod.magento_sku]['magento_status'] = 'in_process'
                prod.write({'bulk_log_ids': [(6, 0, [log_id.id])]})

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
                elif method == "PUT" and (len(prod.product_image_ids)) != len(ml_simp_products[prod.magento_sku].get('media_gallery', [])):
                # elif method == "PUT" and (len(prod.product_image_ids) +
                #                           (1 if prod.odoo_product_id.image_256 else 0)) != \
                #         len(ml_simp_products[prod.magento_sku].get('media_gallery', [])):
                    for _id in ml_simp_products[prod.magento_sku]['media_gallery']:
                        remove_images.append({
                            "entryId": _id,
                            "sku": prod.magento_sku
                        })
                    img_update = True
                if method == 'POST' or img_update:
                    if len(prod.product_image_ids):
                        prod_media.update({
                            prod.magento_sku: [(img.id, img.name, getattr(img, IMG_SIZE), img.image_role) for img in
                                               prod.product_image_ids if img]
                        })
                    # if prod.odoo_product_id.image_256:
                    #     thumb_images.update({
                    #         prod.magento_sku: [(prod.odoo_product_id.product_tmpl_id.id, '', prod.odoo_product_id.image_256)]
                    #     })

        if method == "POST" and product_websites:
            res = conf_prod_obj.process_product_website_data_export_in_bulk(
                magento_instance, product_websites, export_prod_list, ml_simp_products
            )
            if not res.get('errors', True):
                log_id = self.bulk_log_ids.create({
                    'bulk_uuid': res.get("bulk_uuid"),
                    'topic': 'Website info export'
                })
                odoo_products.filtered(lambda x: x.magento_sku in export_prod_list).write({
                    'bulk_log_ids': [(4, log_id.id)]
                })

        self.process_simple_prod_storeview_data_export_in_bulk(magento_instance, odoo_products, data, ml_simp_products)

        if remove_images:
            self.remove_product_images_from_magento_in_bulk(magento_instance, remove_images, ml_simp_products)
        if prod_media:
            conf_prod_obj.export_media_to_magento_in_bulk(magento_instance, prod_media, ml_simp_products, 'product.image')
        # if thumb_images:
        #     conf_prod_obj.export_media_to_magento_in_bulk(magento_instance, thumb_images, ml_simp_products,
        #                                                   'product.template', True)

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

            simp_prod_attrs = simple_prod.attribute_value_ids.product_attribute_value_id
            mag_attr_set = simple_prod.magento_conf_product_id.magento_attr_set
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
            else:
                log_id = self.bulk_log_ids.create({
                    'bulk_uuid': response.get("bulk_uuid"),
                    'topic': 'Assign Product Attributes'
                })
                for prod in odoo_products:
                    if prod.magento_sku in export_prod_list:
                        prod.write({'bulk_log_ids': [(4, log_id.id)]})

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
                res = req(magento_instance, api_url, 'POST', data)
            except Exception:
                res = {}
                text = "Error while asynchronously linking Simple to Configurable Product in Magento.\n"
                for prod in export_prod_list:
                    ml_simp_products[prod]['log_message'] += text
            
            if res.get("errors"):
                return False
            else:
                log_id = self.bulk_log_ids.create({
                    'bulk_uuid': res.get("bulk_uuid"),
                    'topic': 'Link Simple to Configurable'
                })
                for prod in odoo_products:
                    if prod.magento_sku in export_prod_list:
                        prod.write({'bulk_log_ids': [(4, log_id.id)]})

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

    def get_product_conf_attributes_dict(self):
        """
        Extract each Simple Product's "Attribute: Value" pair (only configurable ones) to one single dict
        :param odoo_product: Odoo Product object
        :return: Dictionary with Product's "Attribute: Value" data
        """
        attr_dict = {}
        for attrs in self.attribute_value_ids.product_attribute_value_id:
            if attrs.attribute_id.name in [a.name for a in self.magento_conf_product_id.x_magento_assign_attrs]:
                attr_dict.update({self.to_upper(attrs.attribute_id.name): self.to_upper(attrs.name)})
        return attr_dict

    def export_product_prices(self, instances):
        prices_log_obj = self.env['magento.prices.log.book']
        is_error = False
        tz = pytz.timezone('Europe/Warsaw')
        batch_code = datetime.now(tz).strftime("%Y-%b-%d %H:%M:%S")

        for instance in instances:
            data = {"prices": []}
            magento_storeviews = [(w, w.store_view_ids) for w in instance.magento_website_ids]
            self.clean_old_log_records(instance, prices_log_obj)

            if instance.catalog_price_scope == 'global':
                if not len(instance.pricelist_id):
                    raise UserError("There are no pricelist(s) defined for '%s' instance.\n" % instance.name)
                else:
                    for view in magento_storeviews:
                        for product in self.search([
                            ('magento_instance_id', '=', instance.id),
                            ('magento_status', 'in', ['in_magento', 'need_to_link', 'update_needed'])
                        ]):
                            product_price = instance.pricelist_id.get_product_price(product.odoo_product_id, 1.0, False)
                            if product_price:
                                data["prices"].append({
                                    "price": product_price,
                                    "store_id": view[1].magento_storeview_id,
                                    "sku": product.magento_sku
                                })
                            else:
                                is_error = True
                                text = "Product Price is not defined for %s instance and %s store view" % (
                                    instance.name, view[1].name)
                                self.create_price_export_log(instance, view[1], prices_log_obj, batch_code,
                                                             product.magento_sku, text)
            elif instance.catalog_price_scope == 'website':
                for view in magento_storeviews:
                    pricelist = view[0].pricelist_id
                    if not len(pricelist):
                        raise UserError("There are no pricelist defined for '%s' website.\n" % view[0].name)
                    else:
                        if view[0].magento_base_currency.id != pricelist.currency_id.id:
                            text = "Pricelist '%s' currency is different than Magento base currency " \
                                   "for '%s' website.\n" % (pricelist.name, view[0].name)
                            raise UserError(text)

                        for product in self.search([
                            ('magento_instance_id', '=', instance.id),
                            ('magento_status', 'in', ['in_magento', 'need_to_link', 'update_needed'])
                        ]):
                            price_and_rule = pricelist.get_product_price_rule(product.odoo_product_id, 1.0, False)
                            # check if public price applied (rule = False), and not specific one from website's pricelist
                            product_price = 0 if price_and_rule[1] is False else price_and_rule[0]
                            if product_price:
                                data["prices"].append({
                                    "price": product_price,
                                    "store_id": view[1].magento_storeview_id,
                                    "sku": product.magento_sku
                                })
                            else:
                                is_error = True
                                text = "Product Price is not defined for %s instance and %s store view" % (
                                    instance.name, view[1].name)
                                self.create_price_export_log(instance, view[1], prices_log_obj, batch_code,
                                                             product.magento_sku, text)

            # process export to magento
            if data["prices"]:
                try:
                    api_url = '/V1/products/base-prices'
                    res = req(instance, api_url, 'POST', data)
                    if res:
                        is_error = True
                        text = self.format_error_log(res)
                        self.create_price_export_log(instance, False, prices_log_obj, batch_code, "", text)
                except Exception:
                    text = "Error while exporting product prices to '%s' magento instance.\n" % instance.name
                    raise UserError(text)

            if not is_error:
                self.create_price_export_log(instance, False, prices_log_obj, batch_code, "", "Successfully Exported")

        return False if is_error else True

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

    @staticmethod
    def create_price_export_log(instance, view, prices_log_obj, batch_code, sku, text):
        prices_log_obj.create({
            "magento_instance_id": instance.id,
            "magento_storeview_id": view.id if view else False,
            "batch": batch_code,
            "magento_sku": sku,
            "log_message": text
        })

    @staticmethod
    def clean_old_log_records(instance, log_book_obj):
        # remove all records older than 30 days
        log_book_rec = log_book_obj.with_context(active_test=False).search([
            ('create_date', '<', datetime.today() - timedelta(days=30))
        ])
        if log_book_rec:
            log_book_rec.sudo().unlink()

        # archive all previous records older than 7 days
        log_book_rec = log_book_rec.search([
            ('magento_instance_id', '=', instance.id),
            ('create_date', '<', datetime.today() - timedelta(days=7))
        ])
        if log_book_rec:
            log_book_rec.write({'active': False})

    @staticmethod
    def format_error_log(result):
        text = ""
        for err in result:
            cnt = 0
            mess = str(err.get("message", ""))
            param = err.get("parameters", [])
            while (mess.find("%") >= 0):
                ind = mess.find("%")
                ind2 = mess.find(" ", ind) if mess.find(" ", ind) >= 0 else len(mess)
                mess = mess.replace(mess[ind:ind2], param[cnt] if len(param) > cnt else "")
                cnt += 1
            text += mess + "\n"
        return text

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
