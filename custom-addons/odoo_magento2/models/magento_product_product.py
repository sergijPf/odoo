# -*- coding: utf-8 -*-

import pytz
from datetime import datetime, timedelta
from odoo import fields, models, api
from odoo.exceptions import UserError
from ..python_library.api_request import req

MAGENTO_DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'
PRODUCT_PRODUCT = 'product.product'
IMG_SIZE = 'image_1024'


class MagentoProductProduct(models.Model):
    _name = 'magento.product.product'
    _description = 'Magento Product'
    _rec_name = 'magento_product_name'

    magento_instance_id = fields.Many2one('magento.instance', 'Magento Instance')
    magento_product_id = fields.Char(string="Magento Product Id")
    odoo_product_id = fields.Many2one(PRODUCT_PRODUCT, 'Odoo Product Variant', required=True, ondelete='restrict',
                                      copy=False)
    magento_website_ids = fields.Many2many('magento.website', string='Magento Product Websites', readonly=False,
                                           domain="[('magento_instance_id','=',magento_instance_id)]")
    magento_sku = fields.Char(string="Magento Simple Product SKU")
    magento_product_name = fields.Char(string="Magento Simple Product Name", related="odoo_product_id.name")
    active = fields.Boolean("Active", default=True)
    image_1920 = fields.Image(related="odoo_product_id.image_1920")
    thumbnail_image = fields.Image(string='Product Image')
    product_image_ids = fields.One2many(related="odoo_product_id.product_variant_image_ids")
    ptav_ids = fields.Many2many(related='odoo_product_id.product_template_attribute_value_ids')
    product_attribute_ids = fields.One2many('magento.product.attributes', 'magento_product_id',
                                            compute="_compute_product_attributes", store=True)
    currency_id = fields.Many2one(related='odoo_product_id.currency_id')
    company_id = fields.Many2one(related='odoo_product_id.company_id')
    uom_id = fields.Many2one(related='odoo_product_id.uom_id')
    magento_conf_product_id = fields.Many2one('magento.configurable.product', string='Magento Configurable Product')
    magento_conf_prod_sku = fields.Char('Magento Config.Product SKU', related='magento_conf_product_id.magento_sku')
    inventory_category_id = fields.Many2one(string='Odoo product category', related='odoo_product_id.categ_id')
    x_magento_name = fields.Char(string='Product Name for Magento', compute="_compute_simpl_product_name")
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
    ], string='Export Status', help='The status of Product Variant export to Magento ', default='not_exported')
    force_update = fields.Boolean(string="Force export", help="Force run of Simple Product Export", default=False)
    qty_avail = fields.Float(string="Qty on hand", help="Available quantity on specified Locations",
                             compute="_compute_available_qty")
    bulk_log_ids = fields.Many2many('magento.async.bulk.logs', string="Async Bulk Logs",
                                    help="Logs of async (via RabbitMQ) export of products to Magento")

    _sql_constraints = [('_magento_product_unique_constraint',
                         'unique(magento_sku,magento_instance_id,magento_product_id)',
                         "Magento Product must be unique")]

    @api.depends('magento_product_name', 'product_attribute_ids')
    def _compute_simpl_product_name(self):
        for rec in self:
            rec.x_magento_name = rec.with_context(lang='en_US').magento_product_name + ' ' +\
                                 ' '.join(rec.product_attribute_ids.mapped('x_attribute_value'))

    @api.depends('ptav_ids')
    def _compute_product_attributes(self):
        self.product_attribute_ids.sudo().unlink()
        for rec in self:
            for attr in rec.ptav_ids:
                attr_val = attr.with_context(lang='en_US').product_attribute_value_id
                if not attr_val.attribute_id.is_ignored_in_magento:
                    value = attr_val.name
                    if attr.attribute_line_id.magento_config and attr_val.attribute_id.name == "size_N":
                        sep = value.find('-')
                        if sep >= 0:
                            vals = value.split('-', 1)
                            value = vals[1].strip()

                            rec.product_attribute_ids.create({
                                'magento_product_id': rec.id,
                                'x_attribute_name': 'relative size',
                                'x_attribute_value': vals[0].strip()
                            })

                    rec.product_attribute_ids.create({
                        'magento_product_id': rec.id,
                        'x_attribute_name': attr_val.attribute_id.name,
                        'x_attribute_value': value
                    })

    @api.depends('odoo_product_id', 'magento_instance_id.location_ids')
    def _compute_available_qty(self):
        sq_obj = self.env['stock.quant']
        locations = self.magento_instance_id.location_ids
        for prod in self:
            qty = sum([sq_obj._get_available_quantity(prod.odoo_product_id, loc) for loc in locations])
            prod.qty_avail = qty if qty > 0.0 else 0

    def view_odoo_product(self):
        if self.odoo_product_id:
            return {
                'name': 'Odoo Product',
                'type': 'ir.actions.act_window',
                'res_model': PRODUCT_PRODUCT,
                'view_type': 'form',
                'view_mode': 'tree,form',
                'domain': [('id', '=', self.odoo_product_id.id)],
            }

    def export_products_stock_to_magento(self, instance):
        stock_data = []
        instance_products = self.search([('magento_instance_id', '=', instance.id)])

        for product in instance_products:
            stock_data.append({'sku': product.magento_sku, 'qty': product.qty_avail, 'is_in_stock': 1})

        if stock_data:
            data = {'skuData': stock_data}
            return self.call_export_product_stock_api_and_log_result(instance, data, 'PUT')

    def call_export_product_stock_api_and_log_result(self, instance, data, method_type):
        is_error = False
        stock_log_book_obj = self.env['magento.stock.log.book']
        tz = pytz.timezone('Europe/Warsaw')
        logbook_rec = {
            'magento_instance_id': instance.id,
            'batch': datetime.now(tz).strftime("%Y-%b-%d %H:%M:%S"),
            'log_message': ''
        }

        self.clean_old_log_records(instance, stock_log_book_obj)

        try:
            api_url = "/V1/product/updatestock"
            response = req(instance, api_url, method_type, data)
        except Exception as error:
            logbook_rec.update({"log_message": "Error while Export product stock " + str(error)})
            stock_log_book_obj.create(logbook_rec)
            return False

        if response:
            for resp in response:
                if resp.get('code', False) != '200':
                    is_error = True
                    logbook_rec.update({"log_message": resp.get('message', resp)})
                    stock_log_book_obj.create(logbook_rec)

        if is_error:
            return False
        else:
            logbook_rec.update({"log_message": "Successfully Exported"})
            stock_log_book_obj.create(logbook_rec)
            return True

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
    def update_simple_product_dict_with_magento_data(magento_product, ml_simp_products_dict):
        website_ids = magento_product.get("extension_attributes").get("website_ids")
        category_links = magento_product.get("extension_attributes").get("category_links", [])

        ml_simp_products_dict[magento_product.get("sku")].update({
            'magento_type_id': magento_product.get('type_id'),
            'magento_prod_id': magento_product.get("id"),
            'magento_update_date': magento_product.get("updated_at"),
            'magento_website_ids': website_ids,
            'category_links': [cat['category_id'] for cat in category_links],
            'media_gallery': [i['id'] for i in magento_product.get("media_gallery_entries", []) if i]
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

            if conf_sku and ml_conf_products[conf_sku]['log_message']:
                text = "Configurable Product is not ok. Please check it first. \n"
                ml_simp_products[prod]['log_message'] += text
                ml_simp_products[prod]['to_export'] = False
                continue

            if ml_simp_products[prod]['log_message']:
                ml_simp_products[prod]['to_export'] = False
                continue

            # apply compatible date format to compare Product's dates
            odoo_exp_date = ml_simp_products[prod]['export_date_to_magento']
            export_date = datetime.strftime(odoo_exp_date, MAGENTO_DATETIME_FORMAT) if odoo_exp_date else ""
            magento_date = ml_simp_products[prod].get('magento_update_date', '')

            if not export_date or ml_simp_products[prod]['force_update']:
                if ml_simp_products[prod]['magento_status'] == 'in_magento':
                    ml_simp_products[prod]['magento_status'] = 'update_needed'
                continue

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
                        domain = [('magento_product_id', '=', export_prod.id)]
                        self.env['magento.product.log.book'].search(domain).write({
                            'magento_log_message': '',
                            'magento_log_message_conf': ''
                        })
                    else:
                        ml_simp_products[prod]['magento_status'] = 'need_to_link'
                elif ml_simp_products[prod]['magento_status'] == 'in_magento':
                    ml_simp_products[prod]['magento_status'] = 'update_needed'
            elif ml_simp_products[prod]['magento_status'] not in ['log_error', 'in_process']:
                ml_simp_products[prod]['magento_status'] = 'update_needed'

    def process_simple_products_create_or_update(self, instance, odoo_simp_prod, ml_simp_products, attr_sets,
                                                 ml_conf_products, async_export, method):
        """
        Process Simple Products (Odoo Products) creation or update in Magento
        :param instance: Magento Instance
        :param odoo_simp_prod: Odoo Product Object(s)
        :param ml_simp_products: Dictionary contains metadata of Simple Products (Odoo Products)
        :param attr_sets: Attribute-Set dictionary with available in Magento Attributes info for selected products
        :param ml_conf_products: Dictionary contains metadata of Configurable Products (Odoo categories)
        :param async_export: if export will be done via RabbitMQ
        :param method: Http method (POST/PUT)
        :return: None
        """
        if not odoo_simp_prod:
            return

        if not async_export:
            for simple_product in odoo_simp_prod:
                prod_sku = simple_product.magento_sku
                simple_product.bulk_log_ids = [(5, 0, 0)]

                if method == 'POST' or ml_simp_products[prod_sku]['magento_status'] != 'need_to_link':
                    res = self.export_single_simple_product_to_magento(
                        instance, simple_product, ml_simp_products, attr_sets, method
                    )
                    if res:
                        self.update_simple_product_dict_with_magento_data(res, ml_simp_products)
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
            if self.export_simple_products_in_bulk(instance, odoo_simp_prod, ml_simp_products, attr_sets, method) is False:
                return

            if self.assign_attr_to_config_products_in_bulk(
                    instance, odoo_simp_prod, ml_conf_products, ml_simp_products, attr_sets
            ) is False:
                return

            self.link_simple_to_config_products_in_bulk(instance, odoo_simp_prod,  ml_simp_products)

    def check_simple_products_for_errors_before_export(self, instance, odoo_simp_products, ml_simp_products,
                                                       ml_conf_products, attribute_sets):
        """
        Check if Odoo Products to be exported have any errors
        :param instance: Magento Instance
        :param odoo_simp_products: Odoo Products to be exported
        :param ml_simp_products: Dictionary contains metadata for Simple Products (Odoo products) to be exported
        :param ml_conf_products: Dictionary contains metadata for Configurable Products (Odoo Product Categories) to be exported
        :param attribute_sets: Dictionary with defined Attributes and their options in Magento
        :return: None
        """
        for prod in odoo_simp_products:
            prod_sku = prod.magento_sku
            conf_sku = prod.magento_conf_prod_sku
            prod_attr_set = prod.magento_conf_product_id.magento_attr_set
            avail_attributes = attribute_sets[prod_attr_set]['attributes']
            prod_attrs = {a.x_attribute_name: a.x_attribute_value for a in prod.product_attribute_ids}

            if ml_conf_products[conf_sku]['log_message']:
                text = "Configurable product is not ok. Please check it first. \n"
                ml_simp_products[prod_sku]['log_message'] += text
                continue

            if not len(prod_attrs) and not ml_simp_products[prod_sku]['do_not_export_conf']:
                text = "Product - %s has no attributes.\n" % prod_sku
                ml_simp_products[prod_sku]['log_message'] += text
                continue

            for attr in prod_attrs:
                mag_attr = avail_attributes.get(self.to_upper(attr))
                if not mag_attr:
                    text = "Attribute - %s has to be created on Magento side and attached " \
                           "to Attribute Set.\n" % attr
                    ml_simp_products[prod_sku]['log_message'] += text
                else:
                    attr_val = prod_attrs[attr]
                    if self.to_upper(attr_val) not in [self.to_upper(i.get('label')) for i in mag_attr['options']]:
                        _id, err = prod.magento_conf_product_id.create_new_attribute_option_in_magento(
                            instance, mag_attr['attribute_code'], attr_val
                        )
                        if err:
                            ml_simp_products[prod_sku]['log_message'] += err
                        else:
                            mag_attr['options'].append({'label': attr_val.upper(), 'value': _id})

            if ml_simp_products[prod_sku]['log_message']:
                continue

            if ml_simp_products[prod_sku].get('magento_update_date') and \
                    ml_simp_products[prod_sku]['magento_type_id'] != 'simple':
                text = "The Product with such sku is already in Magento. (And it's type isn't Simple Product). \n"
                ml_simp_products[prod_sku]['log_message'] += text
                continue

            if not ml_simp_products[prod_sku]['do_not_export_conf']:
                # check if product has configurable attributes defined in configurable product
                simp_prod_attr = prod.product_attribute_ids
                missed_attrs = ml_conf_products[conf_sku]['config_attr'].difference({
                    self.to_upper(a.x_attribute_name) for a in simp_prod_attr
                })
                if missed_attrs:
                    text = "Simple product is missing attribute(s): '%s' defined as configurable. \n" % missed_attrs
                    ml_simp_products[prod_sku]['log_message'] += text
                    continue

                check_values = self.check_product_attribute_values_combination_already_exist(
                    ml_conf_products, conf_sku, simp_prod_attr, avail_attributes, ml_simp_products, prod_sku
                )
                if check_values:
                    text = "The same configurable Set of Attribute Values was found in " \
                           "Product - %s.\n" % check_values
                    ml_simp_products[prod_sku]['log_message'] += text
                    continue

    def map_product_attributes_with_magento_attr(self, product_attributes, available_attributes):
        """
        Map Simple Product attributes from Odoo with exact attributes defined in Magneto
        :param product_attributes: Odoo Product's attributes
        :param available_attributes: Dictionary with defined Attributes and their values in Magento
        :return: Magento format Attributes list
        """
        custom_attributes = []
        unique_attr = set([a[0] for a in product_attributes])

        for attr_name in unique_attr:
            value = ''
            attr = available_attributes.get(attr_name)
            for val in [v[1] for v in product_attributes if v[0] == attr_name]:
                opt = next((o for o in attr['options'] if o.get('label') and
                            self.to_upper(o['label']) == val), {})
                if opt:
                    value = opt['value'] if not value else value + ',' + opt['value']

            if value:
                custom_attributes.append({
                    "attribute_code": attr['attribute_code'],
                    "value": value
                })

        return custom_attributes

    def assign_attr_to_config_product(self, magento_instance, product, attr_sets, ml_conf_products, ml_simp_products):
        """
        Assigns attributes to configurable product in Magento, in order to link it with Simple Product
        :param magento_instance: Instance of Magento
        :param product: Odoo Product object
        :param attr_sets: Dictionary with defined Attributes and their values in Magento
        :param ml_conf_products: Dictionary contains metadata for selected Configurable Products
        :param ml_simp_products: Dictionary contains metadata for selected Simple Products
        :return: None
        """
        prod_attr_magento = {}
        prod_attr_set = product.magento_conf_product_id.magento_attr_set
        available_attributes = attr_sets[prod_attr_set]['attributes']
        config_product_sku = product.magento_conf_prod_sku
        prod_attr_odoo = ml_conf_products[config_product_sku]['config_attr']
        attr_options = ml_conf_products[config_product_sku]['magento_conf_prod_options']
        data = {
            "option": {
                "attribute_id": "",
                "label": "",
                "position": 0,
                "is_use_default": "false",
                "values": []
            }
        }

        # check if config.product "configurable" attributes are the same in magento and odoo
        if attr_options:
            prod_attr_magento = {
                product.magento_conf_product_id.get_attribute_name_by_id(available_attributes, attr.get("attribute_id")): (
                    attr.get('id'), attr.get('attribute_id')) for attr in attr_options if attr
            }

            if prod_attr_odoo != set(prod_attr_magento.keys()):
                # unlink attribute in Magento if assign attribute is not within Odoo attributes
                for at in prod_attr_magento:
                    res = False
                    if at not in prod_attr_odoo:
                        try:
                            api_url = '/V1/configurable-products/%s/options/%s' % (
                                config_product_sku, prod_attr_magento[at][0]
                            )
                            res = req(magento_instance, api_url, 'DELETE')
                        except Exception:
                            text = "Error while unlinking Assign Attribute of %s Config.Product " \
                                   "in Magento.\n" % config_product_sku
                            ml_simp_products[product.magento_sku]['log_message'] += text
                    if res is True:
                        # update magento conf.product options list (without removed option)
                        attr_options = list(
                            filter(lambda i: str(i.get('attribute_id')) != str(prod_attr_magento[at][1]), attr_options)
                        )
                ml_conf_products[config_product_sku]['magento_conf_prod_options'] = attr_options

        # assign new options to config.product with relevant info from Magento
        for attr_val in product.product_attribute_ids:
            attr_name = self.to_upper(attr_val.x_attribute_name)
            if attr_name in prod_attr_odoo and attr_name not in prod_attr_magento:
                # valid for new "configurable" attributes of config.product to be created in Magento
                attr = available_attributes.get(attr_name)
                if attr:
                    opt = next((o for o in attr['options'] if o.get('label') and
                                self.to_upper(o['label']) == self.to_upper(attr_val.x_attribute_value)), {})
                    if opt:
                        data['option'].update({
                            "attribute_id": attr["attribute_id"],
                            "label": attr_name,
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
                            "label": attr_name
                        })

    @staticmethod
    def link_simple_to_config_product_in_magento(magento_instance, product, ml_conf_products, ml_simp_products):
        """
        Link simple product to configurable product in Magento
        :param magento_instance: Instance of Magento
        :param product: Odoo Product object
        :param ml_conf_products: Dictionary contains metadata of Configurable Products
        :param ml_simp_products: Dictionary contains metadata of Simple Products
        :return: None
        """
        config_product_sku = product.magento_conf_prod_sku
        simple_product_sku = product.magento_sku
        config_product_children = ml_conf_products[config_product_sku]['children']

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
                raise
        except Exception:
            text = "Error while linking %s to %s Configurable Product in Magento.\n " % \
                   (simple_product_sku, config_product_sku)
            ml_simp_products[simple_product_sku]['log_message'] += text

    def export_single_simple_product_to_magento(self, magento_instance, product, ml_simp_products, attr_sets, method):
        prod_attr_set = product.magento_conf_product_id.magento_attr_set
        available_attributes = attr_sets[prod_attr_set]['attributes']
        prod_attr_list = [(self.to_upper(a.x_attribute_name), self.to_upper(a.x_attribute_value)) for a in
                          product.product_attribute_ids]
        custom_attributes = self.map_product_attributes_with_magento_attr(prod_attr_list, available_attributes)

        data = {
            "product": {
                "name": product.x_magento_name,
                "attribute_set_id":  attr_sets[prod_attr_set]['id'],
                "status": 1,
                "visibility": 3,
                "price": 0,
                "type_id": "simple",
                "weight": product.odoo_product_id.weight,
                "custom_attributes": custom_attributes,
                "extension_attributes": {
                    "stock_item": {}
                }
            }
        }

        if method == 'POST':
            data["product"].update({"sku": product.magento_sku})
            data["product"]["extension_attributes"]["stock_item"].update({
                "qty": self.qty_avail,
                "is_in_stock": "true"
            })

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
                product.magento_conf_product_id.process_products_website_info_export(
                    magento_instance, ml_simp_products, product.magento_sku, response
                )

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
                        (img.id, img.name, getattr(img, IMG_SIZE), img.image_role)
                        for img in product.product_image_ids if img
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

    def export_simple_products_in_bulk(self, magento_instance, odoo_products, ml_simp_products, attr_sets, method='POST'):
        data = []
        prod_media = {}
        # thumb_images = {}
        product_websites = []
        remove_images = []
        conf_prod_obj = self.env['magento.configurable.product']

        for prod in odoo_products:
            if ml_simp_products[prod.magento_sku]['magento_status'] != 'need_to_link':
                prod_attr_list = [(self.to_upper(a.x_attribute_name), self.to_upper(a.x_attribute_value)) for a in
                                  prod.product_attribute_ids]

                custom_attributes = self.map_product_attributes_with_magento_attr(
                    prod_attr_list, attr_sets[prod.magento_conf_product_id.magento_attr_set]['attributes']
                )
                attr_set_id = attr_sets[prod.magento_conf_product_id.magento_attr_set]['id']

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
                            "stock_item": {"qty": prod.qty_avail, "is_in_stock": "true"} if method == 'POST' else {}
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
            for prod in odoo_products:
                ml_simp_products[prod.magento_sku]['log_message'] += text
            return False

        if response.get('errors'):
            return False

        log_id = self.bulk_log_ids.create({
            'bulk_uuid': response.get("bulk_uuid"),
            'topic': 'Product Export'
        })

        for prod in odoo_products:
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
                magento_instance, product_websites, [s.magento_sku for s in odoo_products], ml_simp_products
            )
            if not res.get('errors', True):
                log_id = self.bulk_log_ids.create({
                    'bulk_uuid': res.get("bulk_uuid"),
                    'topic': 'Website info export'
                })
                odoo_products.write({'bulk_log_ids': [(4, log_id.id)]})

        self.process_simple_prod_storeview_data_export_in_bulk(magento_instance, odoo_products, data, ml_simp_products)

        if remove_images:
            self.remove_product_images_from_magento_in_bulk(magento_instance, remove_images, ml_simp_products)
        if prod_media:
            conf_prod_obj.export_media_to_magento_in_bulk(magento_instance, prod_media, ml_simp_products, 'product.image')
        # if thumb_images:
        #     conf_prod_obj.export_media_to_magento_in_bulk(magento_instance, thumb_images, ml_simp_products,
        #                                                   'product.template', True)

    @staticmethod
    def remove_product_images_from_magento_in_bulk(magento_instance, remove_images, ml_products):
        try:
            api_url = '/all/async/bulk/V1/products/bySku/media/byEntryId'
            req(magento_instance, api_url, 'DELETE', remove_images)
        except Exception:
            text = "Error while async Product Images remove from Magento. \n"
            for sku in {img["sku"] for img in remove_images}:
                ml_products[sku]['force_update'] = True
                ml_products[sku]['log_message'] += text

    def assign_attr_to_config_products_in_bulk(self, magento_instance, odoo_products, config_prod_assigned_attr,
                                               ml_simp_products, available_attributes):
        """
        Assigns Attributes to Configurable Products in bulk (asynchronously)
        :param magento_instance: Instance of Magento
        :param odoo_products: Odoo Product records
        :param config_prod_assigned_attr: Configurable Product Assigned Attributes
        :param ml_simp_products: Dictionary contains metadata for selected Simple Products (Odoo products)
        :param available_attributes: Dictionary with defined Attributes and their values in Magento
        :return: None or False
        """
        data = []

        # assign new options to config.product with relevant info from Magento
        for prod in odoo_products:
            if ml_simp_products[prod.magento_sku]['log_message'] or \
                    ml_simp_products[prod.magento_sku]['do_not_export_conf']:
                continue

            mag_attr_set = prod.magento_conf_product_id.magento_attr_set
            mag_avail_attrs = available_attributes[mag_attr_set]['attributes']
            conf_sku = prod.magento_conf_prod_sku

            for prod_attr in prod.product_attribute_ids:
                attr_name = self.to_upper(prod_attr.x_attribute_name)
                if attr_name in config_prod_assigned_attr.get(conf_sku, {}).get('config_attr', {}):
                    attr = mag_avail_attrs.get(attr_name)
                    if attr:
                        opt = next((o for o in attr['options'] if o.get('label') and
                                    self.to_upper(o['label']) == self.to_upper(prod_attr.x_attribute_value)), {})
                        if opt:
                            data.append({
                                'option': {
                                    "attribute_id": attr["attribute_id"],
                                    "label": attr_name,
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
                for prod in odoo_products:
                    ml_simp_products[prod.magento_sku]['log_message'] += text
                return False

            if response.get('errors', {}):
                return False
            else:
                log_id = self.bulk_log_ids.create({
                    'bulk_uuid': response.get("bulk_uuid"),
                    'topic': 'Assign Product Attributes'
                })
                odoo_products.write({'bulk_log_ids': [(4, log_id.id)]})

    def link_simple_to_config_products_in_bulk(self, magento_instance, odoo_products, ml_simp_products):
        """
        Link Simple Product to Configurable Product in Magento in bulk (asynchronously)
        :param magento_instance: Instance of Magento
        :param odoo_products: Odoo Product objects
        :param ml_simp_products: Dictionary contains metadata for selected Simple Products (Odoo products)
        :return: None
        """
        data = []

        for prod in odoo_products:
            if ml_simp_products[prod.magento_sku]['log_message'] or \
                    ml_simp_products[prod.magento_sku]['do_not_export_conf']:
                continue
            data.append({
                "childSku": prod.magento_sku,
                "sku": prod.magento_conf_prod_sku
            })

        if data:
            try:
                api_url = '/async/bulk/V1/configurable-products/bySku/child'
                res = req(magento_instance, api_url, 'POST', data)
            except Exception:
                res = {}
                text = "Error while asynchronously linking Simple to Configurable Product in Magento.\n"
                for prod in odoo_products:
                    ml_simp_products[prod.magento_sku]['log_message'] += text
            
            if res.get("errors"):
                return False
            else:
                log_id = self.bulk_log_ids.create({
                    'bulk_uuid': res.get("bulk_uuid"),
                    'topic': 'Link Simple to Configurable'
                })
                odoo_products.write({'bulk_log_ids': [(4, log_id.id)]})

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
                        'name': product.with_context(lang=lang_code).odoo_product_id.name + ' ' +
                                ' '.join(product.product_attribute_ids.mapped('x_attribute_value')),
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
                                "website price-lists.\n" % view[0].name
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

    def check_product_attribute_values_combination_already_exist(self, ml_conf_products, conf_sku, simp_prod_attr,
                                                                 available_attributes, ml_simple_prod, magento_sku):
        """
        Check Product's "Attribute: Value" pair for duplication
        :param ml_conf_products: Dictionary contains metadata for selected Configurable Products
        :param conf_sku: Config.Product Name
        :param simp_prod_attr: Simple Product Attributes defined in Odoo
        :param available_attributes: Dictionary with defined Attributes and their values in Magento
        :param ml_simple_prod: Dictionary contains metadata for selected Simple Products (Odoo products)
        :param magento_sku: Product sku
        :return: Product sku in case of duplication or False
        """
        # magento_conf_prod_links is dict with already assigned configurable {attribute: value} pair to conf.product
        magento_conf_prod_links = ml_conf_products[conf_sku].get('magento_configurable_product_link_data', {})
        conf_prod_attributes = ml_conf_products[conf_sku]['config_attr']

        simp_attr_val = {}
        for prod_attr in simp_prod_attr:
            pa_name = self.to_upper(prod_attr.x_attribute_name)
            if pa_name in conf_prod_attributes:
                attr = available_attributes.get(pa_name)
                if attr:
                    opt = next((o for o in attr['options'] if o.get('label') and
                                self.to_upper(o.get('label')) == self.to_upper(prod_attr.x_attribute_value)), {})
                    if opt:
                        simp_attr_val.update({pa_name: self.to_upper(opt['label'])})

        for prod in magento_conf_prod_links:
            if magento_conf_prod_links[prod] == simp_attr_val and prod != magento_sku:
                return prod

        for prod in ml_simple_prod:
            if ml_simple_prod[prod]['conf_sku'] == conf_sku and prod != magento_sku and \
                    ml_simple_prod[prod]['conf_attributes'] == simp_attr_val:
                return prod

        return False

    def get_product_conf_attributes_dict(self):
        """
        Extract each Simple Product's "Attribute: Value" pair (only configurable ones) to one single dict
        :return: generated dictionary
        """
        attr_dict = {}
        for attrs in self.product_attribute_ids:
            if attrs.x_attribute_name in [
                a.name for a in self.magento_conf_product_id.with_context(lang='en_US').x_magento_assign_attr_ids
            ]:
                attr_dict.update({self.to_upper(attrs.x_attribute_name): self.to_upper(attrs.x_attribute_value)})
        return attr_dict

    def delete_in_magento(self):
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
                'active': False,
                'magento_website_ids': [(5, 0, 0)]
            })

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
    def format_error_log(result):
        text = ""
        for err in result:
            cnt = 0
            mess = str(err.get("message", ""))
            param = err.get("parameters", [])
            while mess.find("%") >= 0:
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


class MagentoProductAttributes(models.Model):
    _name = 'magento.product.attributes'
    _description = 'Magento Product Attributes'
    _rec_name = 'x_attr_combined'

    magento_product_id = fields.Many2one('magento.product.product', 'Magento Product', ondelete='cascade')
    x_attr_combined = fields.Char(string="Attribute",  compute="_compute_full_attribute_name")
    x_attribute_name = fields.Char(string='Attribute Name')
    x_attribute_value = fields.Char(string='Attribute Value')

    @api.depends('x_attribute_name', 'x_attribute_value')
    def _compute_full_attribute_name(self):
        for rec in self:
            rec.x_attr_combined = str(rec.x_attribute_name) + ': ' + str(rec.x_attribute_value)
