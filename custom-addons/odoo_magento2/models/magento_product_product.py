# -*- coding: utf-8 -*-

import pytz
from datetime import datetime, timedelta
from odoo import fields, models, api
from odoo.exceptions import UserError
from ..python_library.api_request import req

MAGENTO_DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'
IMG_SIZE = 'image_1024'


class MagentoProductProduct(models.Model):
    _name = 'magento.product.product'
    _description = 'Magento Product'
    _rec_name = 'x_magento_name'

    magento_instance_id = fields.Many2one('magento.instance', 'Magento Instance')
    magento_product_id = fields.Char(string="Magento Product Id")
    odoo_product_id = fields.Many2one('product.product', 'Odoo Product Variant', required=True, ondelete='restrict',
                                      copy=False)
    magento_website_ids = fields.Many2many('magento.website', string='Magento Product Websites', readonly=False,
                                           domain="[('magento_instance_id','=',magento_instance_id)]")
    magento_sku = fields.Char(string="Simple Product SKU")
    magento_product_name = fields.Char(string="Simple Product Name", related="odoo_product_id.name")
    active = fields.Boolean("Active", default=True)
    image_1920 = fields.Image(related="odoo_product_id.image_1920")
    thumbnail_image = fields.Image(string='Product Image')
    product_image_ids = fields.One2many(related="odoo_product_id.product_variant_image_ids")
    ptav_ids = fields.Many2many(related='odoo_product_id.product_template_attribute_value_ids')
    product_attribute_ids = fields.One2many('magento.product.attributes', 'magento_product_id',
                                            compute="_compute_product_attributes", store=True)
    currency_id = fields.Many2one(related='odoo_product_id.currency_id')
    odoo_prod_template_id = fields.Many2one(related='magento_conf_product_id.odoo_prod_template_id')
    company_id = fields.Many2one(related='odoo_product_id.company_id')
    uom_id = fields.Many2one(related='odoo_product_id.uom_id')
    magento_conf_product_id = fields.Many2one('magento.configurable.product', string='Magento Configurable Product')
    magento_conf_prod_sku = fields.Char('Config.Product SKU', related='magento_conf_product_id.magento_sku')
    prod_category_ids = fields.Many2many(related='magento_conf_product_id.category_ids')
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
    special_pricing_ids = fields.Many2many(comodel_name='magento.special.pricing',
                                           relation='simple_product_special_price_rel',
                                           column1='special_pricing_id', column2='simple_product_id',
                                           string='Magento Spec. Prices')
    price_ids = fields.Many2many(comodel_name='magento.special.pricing', relation='product_price_rel',
                                 column1='price_id', column2='product_id', string='Special Prices')
    base_prices = fields.Char(string="Base Prices:", help="Product base prices for each website",
                              compute="_compute_base_prices")
    error_log_ids = fields.One2many('magento.product.log.book', 'magento_product_id', string="Error Logs")

    _sql_constraints = [('_magento_product_unique_constraint',
                         'unique(magento_sku,magento_instance_id)',
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

    @api.depends('magento_instance_id.catalog_price_scope', 'magento_instance_id.magento_website_ids.pricelist_id')
    def _compute_base_prices(self):
        for rec in self:
            instance = rec.magento_instance_id
            base_price = ""

            if instance.catalog_price_scope == 'website':
                for website in instance.magento_website_ids:
                    if website.pricelist_id:
                        price = self.get_product_price_for_website(website, rec.odoo_product_id)
                        base_price += "" if not price else \
                            f"[{website.name} - {price}{website.pricelist_id.currency_id.name}]   "

            rec.base_prices = base_price

    def view_error_logs(self):
        domain = [('magento_instance_id', '=', self.magento_instance_id.id), ('magento_product_id', '=', self.id)]

        if self.error_log_ids:
            return {
                'name': 'Product export errors',
                'type': 'ir.actions.act_window',
                'res_model': 'magento.product.log.book',
                'view_type': 'form',
                'view_mode': 'tree,form',
                'domain': domain
            }

    def export_products_stock_to_magento(self, instance):
        stock_data = []
        instance_products = self.search([('magento_instance_id', '=', instance.id)])

        for product in instance_products:
            stock_data.append({'sku': product.magento_sku, 'qty': product.qty_avail, 'is_in_stock': 1})

        if stock_data:
            data = {'skuData': stock_data}
            return self.call_export_product_stock_api_and_log_result(instance, data)

    def call_export_product_stock_api_and_log_result(self, instance, data):
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
            response = req(instance, api_url, 'PUT', data)
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

    def export_product_prices_to_magento(self, instances):
        for instance in instances:
            res = []
            special_prices_obj = self.env['magento.special.pricing']

            base_prices, tier_prices, special_prices = self.prepare_product_prices_data_to_export(instance)

            if base_prices:
                api_url = "/all/V1/products/base-prices"
                res += special_prices_obj.call_export_product_price_api(instance, base_prices, api_url)

            if tier_prices:
                api_url = "/all/V1/products/tier-prices"
                res += special_prices_obj.call_export_product_price_api(instance, tier_prices, api_url)

            for store_code in special_prices:
                api_url = "/%s/V1/products/special-price" % store_code
                res += special_prices_obj.call_export_product_price_api(instance, special_prices[store_code], api_url)

            if tier_prices or special_prices:
                special_prices_obj.search([('magento_instance_id', '=', instance.id)]).export_status = 'exported'

            if res:
                special_prices_obj.log_price_errors(instance, res, 'Mass export of prices')
                return True

    def prepare_product_prices_data_to_export(self, instance):
        base_prices = []
        tier_prices = []
        special_prices = {}
        date_format = MAGENTO_DATETIME_FORMAT
        products_range = self.search([('magento_instance_id', '=', instance.id), ('magento_status', '=', 'in_magento')])

        for website in instance.magento_website_ids:
            pricelist = website.pricelist_id
            storeview_id = website.store_view_ids[0].magento_storeview_id
            store_code = website.store_view_ids[0].magento_storeview_code or 'all'

            if pricelist and (pricelist.currency_id.id == website.magento_base_currency.id) and storeview_id:
                for product in products_range:
                    product_price = self.get_product_price_for_website(website, product.odoo_product_id)

                    if product_price:
                        base_prices.append({
                            "price": product_price,
                            "store_id": storeview_id,
                            "sku": product.magento_sku
                        })

                    for price in product.price_ids.filtered(lambda x: not x.is_special_price):
                        tier_prices.append({
                            "sku": product.magento_sku,
                            "price": price.fixed_price if price.price_type == "fixed" else price.percent_price,
                            "price_type": price.price_type,  # fixed/discount
                            "website_id": price.website_id.magento_website_id if price.website_id else 0,
                            "customer_group": price.customer_group_id.group_name if price.customer_group_id else "ALL GROUPS",
                            "quantity": price.min_qty if price.min_qty else 1
                        })

                    for price in product.price_ids.filtered(lambda x: x.is_special_price):
                        item = {
                            "sku": product.magento_sku,
                            "price": price.fixed_price,
                            "store_id": storeview_id,
                            "price_from": datetime.strftime(price.price_from, date_format) if price.price_from else "",
                            "price_to": datetime.strftime(price.price_to, date_format) if price.price_to else ""
                        }

                        if special_prices.get(store_code):
                            special_prices[store_code].append(item)
                        else:
                            special_prices.update({store_code: [item]})

        return base_prices, tier_prices, special_prices

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

    def check_simple_products_need_to_be_exported(self, export_products, ml_simp_products, ml_conf_products):
        for prod in ml_simp_products:
            conf_sku = ml_simp_products[prod]['conf_sku']

            if conf_sku and ml_conf_products[conf_sku]['log_message']:
                text = "Configurable Product is not ok. Please check it first. "
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

                        if export_prod.error_log_ids:
                            export_prod.error_log_ids.sudo().unlink()

                    else:
                        ml_simp_products[prod]['magento_status'] = 'need_to_link'
                elif ml_simp_products[prod]['magento_status'] == 'in_magento':
                    ml_simp_products[prod]['magento_status'] = 'update_needed'
            elif ml_simp_products[prod]['magento_status'] not in ['log_error', 'in_process']:
                ml_simp_products[prod]['magento_status'] = 'update_needed'

    def process_simple_products_create_or_update(self, instance, odoo_simp_prod, ml_simp_products, attr_sets,
                                                 ml_conf_products, async_export, method):
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
                    self.assign_attr_to_config_product_in_magento(
                        instance, simple_product, attr_sets, ml_conf_products, ml_simp_products
                    )
                    if not ml_simp_products[prod_sku]['log_message']:
                        self.link_simple_to_config_product_in_magento(
                            instance, simple_product, ml_conf_products, ml_simp_products
                        )
        else:
            if self.export_simple_products_in_bulk(instance, odoo_simp_prod, ml_simp_products, attr_sets, method) is False:
                return

            if self.assign_attr_to_config_products_in_magento_in_bulk(
                    instance, odoo_simp_prod, ml_conf_products, ml_simp_products, attr_sets
            ) is False:
                return

            self.link_simple_to_config_products_in_bulk(instance, odoo_simp_prod,  ml_simp_products)

    def check_simple_products_for_errors_before_export(self, instance, odoo_simp_products, ml_simp_products,
                                                       ml_conf_products, attribute_sets):
        for prod in odoo_simp_products:
            prod_sku = prod.magento_sku
            conf_sku = prod.magento_conf_prod_sku
            prod_attr_set = prod.magento_conf_product_id.magento_attr_set
            avail_attributes = attribute_sets[prod_attr_set]['attributes']
            prod_attrs = {a.x_attribute_name: a.x_attribute_value for a in prod.product_attribute_ids}

            if ml_conf_products[conf_sku]['log_message']:
                text = "Configurable product is not ok. Please check it first. "
                ml_simp_products[prod_sku]['log_message'] += text
                continue

            if not len(prod_attrs) and not ml_simp_products[prod_sku]['do_not_export_conf']:
                text = "Product - %s has no attributes. " % prod_sku
                ml_simp_products[prod_sku]['log_message'] += text
                continue

            for attr in prod_attrs:
                mag_attr = avail_attributes.get(self.to_upper(attr))
                if not mag_attr:
                    text = "Attribute - %s has to be created on Magento side and attached " \
                           "to Attribute Set. " % attr
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
                text = "The Product with such sku is already in Magento. (And it's type isn't Simple Product). "
                ml_simp_products[prod_sku]['log_message'] += text
                continue

            if not ml_simp_products[prod_sku]['do_not_export_conf']:
                # check if product has configurable attributes defined in configurable product
                simp_prod_attr = prod.product_attribute_ids
                missed_attrs = ml_conf_products[conf_sku]['config_attr'].difference({
                    self.to_upper(a.x_attribute_name) for a in simp_prod_attr
                })
                if missed_attrs:
                    text = "Simple product is missing attribute(s): '%s' defined as configurable. " % missed_attrs
                    ml_simp_products[prod_sku]['log_message'] += text
                    continue

                check_values = self.check_product_attribute_values_combination_already_exist(
                    ml_conf_products, conf_sku, simp_prod_attr, avail_attributes, ml_simp_products, prod_sku
                )
                if check_values:
                    text = "The same configurable Set of Attribute Values was found in " \
                           "Product - %s. " % check_values
                    ml_simp_products[prod_sku]['log_message'] += text
                    continue

    def map_product_attributes_with_magento_attr(self, product_attributes, available_attributes):
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

    def assign_attr_to_config_product_in_magento(self, magento_instance, product, attr_sets, ml_conf_products,
                                                 ml_simp_products):
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
                        except Exception as err:
                            text = ("Error while unlinking Assign Attribute of %s Config.Product " \
                                   "in Magento. " % config_product_sku) + str(err)
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
                        except Exception as err:
                            txt = ("Error while assigning product attribute option to %s Config.Product in Magento. "
                                   % config_product_sku) + str(err)
                            ml_simp_products[product.magento_sku]['log_message'] += txt
                        # update conf.product dict with new conf.product option
                        ml_conf_products[config_product_sku]['magento_conf_prod_options'].append({
                            'id': "",
                            "attribute_id": attr["attribute_id"],
                            "label": attr_name
                        })

    @staticmethod
    def link_simple_to_config_product_in_magento(magento_instance, product, ml_conf_products, ml_simp_products):
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
        except Exception as err:
            text = ("Error while linking %s to %s Configurable Product in Magento.\n " %
                    (simple_product_sku, config_product_sku)) + str(err)
            ml_simp_products[simple_product_sku]['log_message'] += text

    def export_single_simple_product_to_magento(self, instance, product, ml_simp_products, attr_sets, method):
        prod_attr_set = product.magento_conf_product_id.magento_attr_set
        available_attributes = attr_sets[prod_attr_set]['attributes']
        prod_attr_list = [(self.to_upper(a.x_attribute_name), self.to_upper(a.x_attribute_value)) for a in
                          product.product_attribute_ids]
        custom_attributes = self.map_product_attributes_with_magento_attr(prod_attr_list, available_attributes)

        data = {
            "product": {
                "name": product.x_magento_name,
                "attribute_set_id":  attr_sets[prod_attr_set]['id'],
                "status": 1, # Enabled(1) / Disabled(0)
                "visibility": 3, # Search
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
                "qty": product.qty_avail,
                "is_in_stock": "true"
            })

        try:
            api_url = '/all/V1/products' if method == 'POST' else '/all/V1/products/%s' % product.magento_sku
            response = req(instance, api_url, method, data)
        except Exception as err:
            text = ("Error while new Simple Product creation in Magento: " if method == 'POST' else
                    "Error while Simple Product update in Magento: ") + str(err)
            ml_simp_products[product.magento_sku]['log_message'] += text
            return {}

        if response.get("sku"):
            ml_simp_products[product.magento_sku]['export_date_to_magento'] = response.get("updated_at")

            if ml_simp_products[product.magento_sku]['do_not_export_conf']:
                ml_simp_products[product.magento_sku]['magento_status'] = 'in_magento'
            else:
                ml_simp_products[product.magento_sku]['magento_status'] = 'need_to_link'

            if method == "POST":
                product.magento_conf_product_id.link_product_with_websites_in_magento(
                    instance, ml_simp_products, product.magento_sku, response
                )

            product.process_storeview_data_export(instance, product, ml_simp_products, product.magento_sku, data)

            product.process_images_export(instance, ml_simp_products)

            return response
        return {}

    def process_storeview_data_export(self, instance, product, ml_products, prod_sku, data):
        product_price = 0
        text = ''

        if instance.catalog_price_scope == 'global':
            text += "Catalog Price Scope has to changed to 'website' in Magento. "

        else:
            for website in instance.magento_website_ids:
                storeview_code = website.store_view_ids[0].magento_storeview_code
                lang_code = website.store_view_ids[0].lang_id.code
                data["product"]["name"] = product.with_context(lang=lang_code).odoo_product_id.name + ' ' + \
                                          ' '.join(product.product_attribute_ids.mapped('x_attribute_value'))

                if website.pricelist_id:
                    if website.magento_base_currency.id != website.pricelist_id.currency_id.id:
                        text += "Pricelist '%s' currency is different than Magento base currency " \
                                "for '%s' website.\n" % (website.pricelist_id.name, website.name)
                        break
                    product_price = self.get_product_price_for_website(website, product.odoo_product_id)
                else:
                    text += "There are no pricelist defined for '%s' website.\n" % website.name

                if product_price:
                    data["product"]["price"] = product_price
                    data["product"]["status"] = 1
                else:
                    data["product"]["price"] = data["product"]["status"] = 0
                    text += "There are no or '0' price defined for product in '%s' website price-list. " % website.name

                try:
                    api_url = '/%s/V1/products/%s' % (storeview_code, prod_sku)
                    req(instance, api_url, 'PUT', data)
                except Exception as e:
                    text = ("Error while exporting product data to '%s' store view. " % storeview_code) + str(e)
                    break

        if text:
            ml_products[prod_sku]['log_message'] += text
            ml_products[prod_sku]['force_update'] = True

    def process_images_export(self, instance, ml_simp_products):
        # process images export to magento
        if ml_simp_products[self.magento_sku].get('media_gallery', []):
            self.magento_conf_product_id.remove_product_images_from_magento(
                instance, ml_simp_products, self.magento_sku
            )
        if len(self.product_image_ids):
            prod_media = {
                self.magento_sku: [
                    (img.id, img.name, getattr(img, IMG_SIZE), img.image_role)
                    for img in self.product_image_ids if img
                ]
            }
            self.magento_conf_product_id.export_media_to_magento(
                instance, prod_media, ml_simp_products, 'product.image'
            )
        # export product's thumbnail Image
        # if product.odoo_product_id.image_256:
        #     thumb_image = {
        #         product.magento_sku: [(product.odoo_product_id.product_tmpl_id.id, '', product.odoo_product_id.image_256)]
        #     }
        #     product.magento_conf_product_id.export_media_to_magento(
        #         instance, thumb_image, ml_simp_products, 'product.template', True
        #     )

    def export_simple_products_in_bulk(self, instance, odoo_products, ml_simp_products, attr_sets, method='POST'):
        data = []
        prod_media = {}
        # thumb_images = {}
        product_websites = []
        remove_images = []
        conf_prod_obj = self.env['magento.configurable.product']

        for prod in odoo_products:
            if ml_simp_products[prod.magento_sku]['magento_status'] != 'need_to_link':
                prod_attr_set = prod.magento_conf_product_id.magento_attr_set
                prod_attr_list = [(self.to_upper(a.x_attribute_name), self.to_upper(a.x_attribute_value)) for a in
                                  prod.product_attribute_ids]
                custom_attributes = self.map_product_attributes_with_magento_attr(
                    prod_attr_list, attr_sets[prod_attr_set]['attributes']
                )

                data.append({
                    "product": {
                        "sku": prod.magento_sku,
                        # "name": prod.magento_product_name,
                        "name": prod.x_magento_name,
                        "attribute_set_id": attr_sets[prod_attr_set]['id'],
                        "status": 1, # Enabled(1) / Disabled(0)
                        "visibility": 3, # Search
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
            response = req(instance, api_url, method, data)
        except Exception as err:
            text = ("Error while asynchronously Simple Products %s in Magento: " % (
                'creation' if method == 'POST' else "update")) + str(err)
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
                for site in instance.magento_website_ids:
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
            res = conf_prod_obj.link_product_with_websites_in_magento_in_bulk(
                instance, product_websites, [s.magento_sku for s in odoo_products], ml_simp_products
            )
            if not res.get('errors', True):
                log_id = self.bulk_log_ids.create({
                    'bulk_uuid': res.get("bulk_uuid"),
                    'topic': 'Website info export'
                })
                odoo_products.write({'bulk_log_ids': [(4, log_id.id)]})

        self.process_simple_prod_storeview_data_export_in_bulk(instance, odoo_products, data, ml_simp_products)

        if remove_images:
            self.remove_product_images_from_magento_in_bulk(instance, remove_images, ml_simp_products)
        if prod_media:
            conf_prod_obj.export_media_to_magento_in_bulk(instance, prod_media, ml_simp_products, 'product.image')
        # if thumb_images:
        #     conf_prod_obj.export_media_to_magento_in_bulk(instance, thumb_images, ml_simp_products,
        #                                                   'product.template', True)

    def process_simple_prod_storeview_data_export_in_bulk(self, instance, odoo_products, data, ml_products):
        if instance.catalog_price_scope == 'global':
            text = "Catalog Price Scope has to be 'website' in Magento for '%s' instance. " % instance.name
            for product in data:
                ml_products[product['sku']]['log_message'] += text
            return

        for website in instance.magento_website_ids:
            data_lst = []
            storeview_code = website.store_view_ids[0].magento_storeview_code
            lang_code = website.store_view_ids[0].lang_id.code

            for prod in data:
                product_price = 0
                sku = prod['product']['sku']
                product = odoo_products.search([('magento_sku', '=', sku), ('magento_instance_id', '=', instance.id)])
                new_prod = {
                    'product': {
                        'name': product.with_context(lang=lang_code).odoo_product_id.name + ' ' +
                                ' '.join(product.product_attribute_ids.mapped('x_attribute_value')),
                        'sku': sku,
                        "status": 1,
                        'price': 0,
                        'custom_attributes': prod['product']["custom_attributes"].copy()
                    }
                }

                if not website.pricelist_id:
                    text = "There are no price-list defined for '%s' website.\n" % website.name
                    ml_products[sku]['log_message'] += text
                else:
                    if website.magento_base_currency.id != website.pricelist_id.currency_id.id:
                        text = "Price-list '%s' currency is different than Magento base currency " \
                                "for '%s' website.\n" % (website.pricelist_id.name, website.name)
                        ml_products[sku]['log_message'] += text
                        break

                    product_price = self.get_product_price_for_website(website, product.odoo_product_id)

                if product_price:
                    new_prod["product"]["price"] = product_price
                else:
                    new_prod["product"]["price"] = new_prod["product"]["status"] = 0
                    if not ml_products[sku]['log_message']:
                        text = "There are no or '0' price defined for product in '%s' website's price-list. " % website.name
                        ml_products[sku]['log_message'] += text

                data_lst.append(new_prod)

            try:
                api_url = '/%s/async/bulk/V1/products' % storeview_code
                res = req(instance, api_url, 'PUT', data_lst)
            except Exception as e:
                for product in data:
                    text = ("Error while exporting products data to '%s' store view. " % storeview_code) + str(e)
                    ml_products[product['product']['sku']]['log_message'] += text
                break

            if not res.get('errors', True):
                log_id = self.bulk_log_ids.create({
                    'bulk_uuid': res.get("bulk_uuid"),
                    'topic': 'Storeview-%s info export' % storeview_code
                })
                prod_list = [p['product']['sku'] for p in data]
                odoo_products.filtered(
                    lambda x: x.magento_sku in prod_list and x.magento_instance_id == instance
                ).write({'bulk_log_ids': [(4, log_id.id)]})

    @staticmethod
    def remove_product_images_from_magento_in_bulk(magento_instance, remove_images, ml_products):
        try:
            api_url = '/all/async/bulk/V1/products/bySku/media/byEntryId'
            req(magento_instance, api_url, 'DELETE', remove_images)
        except Exception as err:
            text = "Error while async Product Images remove from Magento. " + str(err)
            for sku in {img["sku"] for img in remove_images}:
                ml_products[sku]['force_update'] = True
                ml_products[sku]['log_message'] += text

    def assign_attr_to_config_products_in_magento_in_bulk(self, magento_instance, odoo_products, config_prod_conf_attr,
                                                          ml_simp_products, available_attributes):
        data = []

        for prod in odoo_products:
            prod_dict = ml_simp_products[prod.magento_sku]
            if prod_dict['log_message'] or prod_dict['do_not_export_conf']:
                continue

            mag_attr_set = prod.magento_conf_product_id.magento_attr_set
            mag_avail_attrs = available_attributes[mag_attr_set]['attributes']
            conf_sku = prod.magento_conf_prod_sku

            for prod_attr in prod.product_attribute_ids:
                attr_name = self.to_upper(prod_attr.x_attribute_name)
                if attr_name in config_prod_conf_attr.get(conf_sku, {}).get('config_attr', {}):
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
            except Exception as e:
                text = "Error while async assign product attributes to Configurable Product in Magento. " + str(e)
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
        data = []

        for prod in odoo_products:
            prod_dict = ml_simp_products[prod.magento_sku]
            if prod_dict['log_message'] or prod_dict['do_not_export_conf']:
                continue
            data.append({
                "childSku": prod.magento_sku,
                "sku": prod.magento_conf_prod_sku
            })

        if data:
            try:
                api_url = '/async/bulk/V1/configurable-products/bySku/child'
                res = req(magento_instance, api_url, 'POST', data)
            except Exception as e:
                res = {}
                text = "Error while asynchronously linking Simple to Configurable Product in Magento. " + str(e)
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

    def get_product_price_for_website(self, website, product):
        price_and_rule = website.pricelist_id.get_product_price_rule(product, 1.0, False)

        return 0 if price_and_rule[1] is False else price_and_rule[0]


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

    def save_error_messages_to_log_book(self, simp_log_message, conf_log_message):
        self.ensure_one()
        vals = {
            'magento_log_message': simp_log_message,
            'magento_log_message_conf': conf_log_message
        }

        if self.error_log_ids:
            self.error_log_ids.write(vals)
        else:
            vals.update({'magento_product_id': self.id})
            self.error_log_ids.create(vals)

    def export_adv_product_prices(self, instances):
        prices_log_obj = self.env['magento.prices.log.book']
        is_error = False
        tz = pytz.timezone('Europe/Warsaw')
        batch_code = datetime.now(tz).strftime("%Y-%b-%d %H:%M:%S")

        for instance in instances:
            data = {"prices": []}
            magento_storeviews = [(w, w.store_view_ids) for w in instance.magento_website_ids]
            self.clean_old_log_records(instance, prices_log_obj)

            if instance.catalog_price_scope == 'website':
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
