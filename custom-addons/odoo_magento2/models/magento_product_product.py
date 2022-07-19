# -*- coding: utf-8 -*-

import pytz, json
import logging

from datetime import datetime, timedelta
from odoo import fields, models, api
from odoo.exceptions import UserError
from ..python_library.api_request import req

MAGENTO_DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'
_logger = logging.getLogger(__name__)

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
    is_enabled = fields.Boolean(string="Is Enabled in Magento?", default=False)
    magento_product_name = fields.Char(string="Simple Product Name", related="odoo_product_id.name")
    active = fields.Boolean("Active", default=True)
    image_1920 = fields.Image(related="odoo_product_id.image_1920")
    product_image_ids = fields.One2many(related="odoo_product_id.product_variant_image_ids")
    ptav_ids = fields.Many2many(related='odoo_product_id.product_template_attribute_value_ids')
    product_attribute_ids = fields.Many2many('product.template.attribute.value', compute="_compute_product_attributes",
                                             store=True)
    currency_id = fields.Many2one(related='odoo_product_id.currency_id')
    company_id = fields.Many2one(related='odoo_product_id.company_id')
    uom_id = fields.Many2one(related='odoo_product_id.uom_id')
    magento_conf_product_id = fields.Many2one('magento.configurable.product', string='Magento Configurable Product')
    odoo_prod_template_id = fields.Many2one(related='magento_conf_product_id.odoo_prod_template_id')
    magento_conf_prod_sku = fields.Char('Config.Product SKU', related='magento_conf_product_id.magento_sku')
    prod_category_ids = fields.Many2many(related='magento_conf_product_id.category_ids')
    x_magento_name = fields.Char(string='Product Name for Magento', compute="_compute_simpl_product_name")
    magento_export_date = fields.Datetime(string="Last Export Date", help="Product Variant last Export Date to Magento",
                                          copy=False)
    magento_status = fields.Selection([
        ('not_exported', 'not Exported'),
        ('in_process', 'In Process'),
        ('need_to_link', 'Need to be Linked'),
        ('update_needed', 'Need to Update'),
        ('extra_info', 'Extra info needed'),
        ('in_magento', 'In Magento'),
        ('log_error', 'Error to Export'),
    ], string='Export Status', help='The status of Product Variant export to Magento ', default='not_exported')
    force_update = fields.Boolean(string="Force export", help="Force run of Simple Product Export", default=False)
    force_image_update = fields.Boolean(string="Force image export", default=False)
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
    is_marketing_prod = fields.Boolean(related="magento_conf_product_id.is_marketing_prod")
    cross_sell_product_ids = fields.Many2many(string="Cross-Sell Products",
                                              related="magento_conf_product_id.cross_sell_product_ids")
    error_log_ids = fields.One2many('magento.product.log.book', 'magento_product_id', string="Error Logs")
    issue = fields.Char('Issue with product', compute="_check_simple_product_has_issues")

    _sql_constraints = [('_magento_product_unique_constraint',
                         'unique(magento_sku,magento_instance_id)',
                         "Magento Product must be unique")]

    @api.depends('magento_product_name', 'product_attribute_ids.product_attribute_value_id')
    def _compute_simpl_product_name(self):
        for rec in self:
            rec.x_magento_name = rec.with_context(lang='en_US').magento_product_name + ' ' +\
                                 ' '.join(rec.product_attribute_ids.product_attribute_value_id.mapped('name'))

    @api.depends('ptav_ids', 'ptav_ids.product_attribute_value_id.attribute_id.is_ignored_in_magento')
    def _compute_product_attributes(self):
        for rec in self:
            rec.product_attribute_ids = rec.ptav_ids.filtered(
                lambda x: not x.product_attribute_value_id.attribute_id.is_ignored_in_magento
            )

    @api.depends('odoo_product_id', 'magento_instance_id.location_ids')
    def _compute_available_qty(self):
        sq_obj = self.env['stock.quant']
        for prod in self:
            locations = prod.magento_instance_id.location_ids
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

    @api.depends('magento_product_id', 'is_enabled', 'magento_website_ids')
    def _check_simple_product_has_issues(self):
        for prod in self:
            prod.issue = ''
            if prod.magento_product_id:
                if not prod.is_enabled:
                    prod.issue = "Disabled in Magento. "
                if not prod.magento_website_ids:
                    prod.issue += "No websites linked to product."

    def write(self, vals):
        if 'active' in vals:
            for rec in self:
                if rec.magento_product_id:
                    raise UserError("You're not able to archive product until it is in Magento. Please delete it first!")

        return super(MagentoProductProduct, self).write(vals)

    def unlink(self):
        to_reject = []
        [to_reject.append(prod.magento_sku) for prod in self if prod.magento_product_id]

        if to_reject:
            raise UserError("You can't remove these Product(s) until they are in Magento: %s" % str(to_reject))

        return super(MagentoProductProduct, self).unlink()

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
        products_range = self.search([('magento_instance_id', '=', instance.id), ('magento_product_id', 'not in', [False, ''])])

        for product in products_range:
            stock_data.append({'sku': product.magento_sku, 'qty': product.qty_avail, 'is_in_stock': 1})

        if stock_data:
            result = self.call_export_product_stock_api(instance, stock_data)
            return self.log_stock_export_result(instance, result)

    @staticmethod
    def call_export_product_stock_api(instance, stock_data):
        result = []
        api_url = "/V1/product/updatestock"
        count = (len(stock_data) // 20) + 1

        for c in range(count):
            response = []
            list_extract = stock_data[c * 20:20 * (c + 1)]  # Magento max allowed export of 20 items at once
            try:
                response = req(instance, api_url, 'PUT', {"skuData": list_extract})
            except Exception as error:
                for item in list_extract:
                    response.append({'message': (str(item['sku']) + str(error)), 'code': '999'})

            if type(response) is list:
                result += response
            else:
                for item in list_extract:
                    result.append({'message': (str(item['sku']) + str(response)), 'code': '999'})

        return result

    def log_stock_export_result(self, instance, result):
        is_error = False
        stock_log_book_lines = self.env['magento.stock.log.book.lines']
        tz = pytz.timezone('Europe/Warsaw')
        stock_log_book = self.env['magento.stock.log.book']

        self.clean_old_log_records(instance, stock_log_book)

        log_book_rec = stock_log_book.create({
            'magento_instance_id': instance.id,
            'batch': datetime.now(tz).strftime("%Y-%b-%d %H:%M:%S"),
            'result': 'Errors'
        })

        for res in result:
            item = res if type(res) is dict else {'message': str(res), 'code': '999'}

            if item.get('code', False) != '200':
                is_error = True
                stock_log_book_lines.create({
                    'stock_log_book_id': log_book_rec.id,
                    'log_message': item.get('message', 'Message is missed'),
                    'code': item.get('code', '000')
                })

        if is_error:
            return False
        else:
            log_book_rec.write({"result": "Successfully Exported"})
            return True

    def export_product_prices_to_magento(self, instances):
        errors = False

        for instance in instances:
            err_lst = []
            special_prices_obj = self.env['magento.special.pricing']

            base_prices, tier_prices, special_prices = self.prepare_product_prices_data_to_export(instance)

            if base_prices:
                api_url = "/all/V1/products/base-prices"
                err_lst += special_prices_obj.call_export_product_price_api(instance, base_prices, api_url)

            if tier_prices:
                api_url = "/all/V1/products/tier-prices"
                err_lst += special_prices_obj.call_export_product_price_api(instance, tier_prices, api_url)

            for store_code in special_prices:
                api_url = "/%s/V1/products/special-price" % store_code
                err_lst += special_prices_obj.call_export_product_price_api(instance, special_prices[store_code], api_url)

            if tier_prices or special_prices:
                special_prices_obj.search([('magento_instance_id', '=', instance.id)]).export_status = 'exported'

            if err_lst:
                special_prices_obj.log_price_errors(instance, err_lst, 'Mass Export')
                errors = True
            else:
                special_prices_obj.remove_log_errors(instance, 'Mass Export')

        if errors:
            return {
                'name': 'Product Prices Export Error Logs',
                'view_mode': 'tree,form',
                'res_model': 'magento.prices.log.book',
                'type': 'ir.actions.act_window'
            }

    def prepare_product_prices_data_to_export(self, instance):
        base_prices = []
        tier_prices = []
        special_prices = {}
        date_format = MAGENTO_DATETIME_FORMAT
        domain = [('magento_instance_id', '=', instance.id), ('magento_product_id', 'not in', [False, ''])]
        if self:
            domain.append(('id', 'in', self.ids))

        products_range = self.search(domain)

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
    def update_simple_product_dict_with_magento_data(magento_product, simp_products_dict):
        website_ids = magento_product.get("extension_attributes").get("website_ids")
        product_prices = magento_product.get("extension_attributes").get("website_wise_product_price_data", [])
        prices_list = [json.loads(price) for price in product_prices]

        simp_products_dict[str(magento_product.get("sku"))].update({
            'magento_type_id': magento_product.get('type_id'),
            'magento_prod_id': magento_product.get("id"),
            'is_magento_enabled': True if magento_product.get('status') == 1 else False,
            'magento_update_date': magento_product.get("updated_at"),
            'magento_website_ids': website_ids,
            'media_gallery': [i['id'] for i in magento_product.get("media_gallery_entries", []) if i],
            'product_prices': {p['website_id']: p.get('product_price', 0) for p in prices_list if p.get('website_id')},
            'product_links_cnt': len(magento_product.get("product_links", []))
        })

    def check_simple_products_for_errors_and_update_export_statuses(self, conf_prods_dict, simp_prods_dict, attr_sets,
                                                                    update_export_statuses):
        for prod in simp_prods_dict:
            export_prod = simp_prods_dict[prod]['simple_prod_rec']
            conf_sku = export_prod.magento_conf_prod_sku

            if conf_sku and conf_prods_dict[conf_sku]['log_message']:
                text = "Configurable Product is not ok. Please check it first. "
                simp_prods_dict[prod]['log_message'] += text
                continue

            if simp_prods_dict[prod]['log_message']:
                continue

            if export_prod.check_simple_product_attributes_for_errors(simp_prods_dict, conf_prods_dict, attr_sets):
                continue

            if simp_prods_dict[prod]['force_update'] or simp_prods_dict[prod]['force_image_update']:
                if simp_prods_dict[prod]['magento_status'] in ['in_magento', 'extra_info']:
                    simp_prods_dict[prod]['magento_status'] = 'update_needed'
                continue

            if simp_prods_dict[prod].get('magento_update_date', ''):
                if simp_prods_dict[prod]['magento_type_id'] == 'simple':
                    magento_prod_id = simp_prods_dict[prod]['magento_prod_id']
                    if export_prod.is_marketing_prod or magento_prod_id in conf_prods_dict[conf_sku]['children']:
                        # check if images count is the same in Odoo and Magento
                        prod_imgs = export_prod.product_image_ids
                        thumb_img = export_prod.image_1920
                        small_base_imgs = prod_imgs.filtered(lambda x: x.image_role in ['small_image', 'image'])
                        sb_imgs_cnt = 1 if thumb_img and len(small_base_imgs) < 2 else 0
                        magento_imgs = simp_prods_dict[prod].get('media_gallery', [])

                        if (len(prod_imgs) + (1 if thumb_img else 0) + sb_imgs_cnt) != len(magento_imgs):
                            simp_prods_dict[prod]['magento_status'] = 'update_needed'
                            simp_prods_dict[prod]['force_image_update'] = True
                            continue

                        if update_export_statuses:
                            # check prices
                            if not self.check_simple_product_prices(export_prod, simp_prods_dict[prod]):
                                continue

                        if simp_prods_dict[prod]['product_links_cnt'] != len(export_prod.cross_sell_product_ids):
                            simp_prods_dict[prod]['magento_status'] = 'extra_info'
                            continue

                        if simp_prods_dict[prod]['magento_status'] != 'extra_info':
                            simp_prods_dict[prod]['magento_status'] = 'in_magento'

                        simp_prods_dict[prod]['to_export'] = False

                        if export_prod.error_log_ids:
                            export_prod.error_log_ids.sudo().unlink()
                    else:
                        simp_prods_dict[prod]['magento_status'] = 'need_to_link'
                else:
                    text = "The Product with such sku is already in Magento. (And it's type isn't Simple Product). "
                    simp_prods_dict[prod]['log_message'] += text
            elif simp_prods_dict[prod]['magento_status'] in ['in_magento', 'extra_info']:
                simp_prods_dict[prod]['magento_status'] = 'update_needed'

    def check_simple_product_attributes_for_errors(self, simp_products_dict, conf_products_dict, attribute_sets):
        prod_sku = self.magento_sku
        conf_sku = self.magento_conf_prod_sku
        instance = self.magento_instance_id
        prod_attr_set = self.magento_conf_product_id.magento_attr_set
        avail_attributes = attribute_sets[prod_attr_set]['attributes']
        prod_attrs = {a.attribute_id.name: a.name for a in self.product_attribute_ids.product_attribute_value_id}

        if not prod_attrs and not self.is_marketing_prod:
            text = "Product - %s has no attributes. " % prod_sku
            simp_products_dict[prod_sku]['log_message'] += text
            return True

        for attr, attr_val in prod_attrs.items():
            magento_attr = avail_attributes.get(self.to_upper(attr))
            if magento_attr:
                if self.to_upper(attr_val) not in [self.to_upper(i.get('label')) for i in magento_attr['options']]:
                    attr_val_rec = self.ptav_ids.product_attribute_value_id.filtered(lambda x: x.name == attr_val)
                    val_id, err = self.magento_conf_product_id.create_new_attribute_option_in_magento(
                        instance, magento_attr['attribute_code'], attr_val_rec or attr_val
                    )
                    if err:
                        simp_products_dict[prod_sku]['log_message'] += err
                    else:
                        magento_attr['options'].append({'label': attr_val.upper(), 'value': val_id})

        if simp_products_dict[prod_sku]['log_message']:
            return True

        if not self.is_marketing_prod:
            # check if product has configurable attributes defined in configurable product
            simp_prod_attr = self.product_attribute_ids.product_attribute_value_id
            missed_attrs = conf_products_dict[conf_sku]['config_attr'].difference({
                self.to_upper(a.attribute_id.name) for a in simp_prod_attr
            })
            if missed_attrs:
                text = "Simple product is missing attribute(s): '%s' defined as configurable. " % missed_attrs
                simp_products_dict[prod_sku]['log_message'] += text
                return True

            check_values = self.check_product_attribute_values_combination_already_exist(
                conf_products_dict, simp_products_dict, conf_sku, simp_prod_attr, avail_attributes, prod_sku
            )
            if check_values:
                text = "The same configurable Set of Attribute Values was found in " \
                       "Product - %s. " % check_values
                simp_products_dict[prod_sku]['log_message'] += text
                return True

    def check_simple_product_prices(self, product, product_dict):
        for website in product.magento_instance_id.magento_website_ids:
            text = ''
            if website.pricelist_id:
                if website.magento_base_currency.id != website.pricelist_id.currency_id.id:
                    text = "Price list '%s' currency is different than Magento base currency " \
                            "for '%s' website. " % (website.pricelist_id.name, website.name)

                odoo_price = self.get_product_price_for_website(website, product.odoo_product_id)
                magento_price = product_dict['product_prices'].get(website.magento_website_id, 0)

                if odoo_price == 0:
                    text = "Product missed base price for '%s' website in Odoo. " % website.name
                elif float(magento_price) == 0 or odoo_price != magento_price:
                    product_dict['magento_status'] = 'extra_info'
                else:
                    product_dict['magento_status'] = 'in_magento'
            else:
                text = "There are no price list defined for '%s' website. " % website.name

            if text:
                product_dict['log_message'] += text

        return False if product_dict['log_message'] else True

    def process_simple_products_export(self, instance, attr_sets, conf_prods_dict, simp_prods_dict, async_export):
        for prod in simp_prods_dict:
            if not simp_prods_dict[prod]['log_message']:
                conf_sku = simp_prods_dict[prod]['simple_prod_rec'].magento_conf_prod_sku
                error = conf_prods_dict[conf_sku]['log_message']
                if error:
                    text = f'Configurable product got some error while export: {error}'
                    simp_prods_dict[prod]['log_message'] = text

        simple_products = self.filtered(
            lambda p: simp_prods_dict[p.magento_sku]['to_export'] and not simp_prods_dict[p.magento_sku]['log_message']
        )

        # process simple products update in Magento
        products_to_update = simple_products.filtered(
            lambda s: simp_prods_dict[s.magento_sku].get('magento_update_date')
        )
        products_to_update.process_simple_products_create_or_update_in_magento(
            instance, simp_prods_dict, attr_sets, conf_prods_dict, async_export, 'PUT'
        )

        # process new simple product creation in Magento
        products_to_create = simple_products - products_to_update
        products_to_create.process_simple_products_create_or_update_in_magento(
            instance, simp_prods_dict, attr_sets, conf_prods_dict, async_export, 'POST'
        )

    def process_simple_products_create_or_update_in_magento(self, instance, simp_prod_dict, attr_sets, conf_prod_dict,
                                                            async_export, method):
        if not self:
            return

        if not async_export:
            for simple_product in self:
                prod_sku = simple_product.magento_sku
                simple_product.bulk_log_ids = [(5, 0, 0)]

                if method == 'POST' or simp_prod_dict[prod_sku]['magento_status'] != 'need_to_link':
                    res = simple_product.export_single_simple_product_to_magento(
                        instance, simp_prod_dict, attr_sets, method
                    )
                    if res:
                        self.update_simple_product_dict_with_magento_data(res, simp_prod_dict)
                    else:
                        continue

                if not simple_product.is_marketing_prod:
                    simple_product.assign_conf_attributes_to_config_product_in_magento(
                        instance, attr_sets, conf_prod_dict, simp_prod_dict
                    )
                    if not simp_prod_dict[prod_sku]['log_message']:
                        simple_product.link_simple_to_config_product_in_magento(instance, conf_prod_dict, simp_prod_dict)
        else:
            if self.export_simple_products_in_bulk(instance, simp_prod_dict, attr_sets, method) is False:
                return

            if self.assign_attr_to_config_products_in_magento_in_bulk(instance, conf_prod_dict, simp_prod_dict, attr_sets) is False:
                return

            self.link_simple_to_config_products_in_bulk(instance, simp_prod_dict)

    def map_product_attributes_with_magento_attr(self, product_attributes, available_attributes):
        custom_attributes = []
        unique_attr = set([a[0] for a in product_attributes])

        for attr_name in unique_attr:
            value = ''
            mag_attr = available_attributes.get(attr_name)
            for val in [v[1] for v in product_attributes if v[0] == attr_name]:
                opt = next((o for o in mag_attr['options'] if o.get('label') and self.to_upper(o['label']) == val), {})
                if opt:
                    value = opt['value'] if not value else f"{value},{opt['value']}"

            if value:
                custom_attributes.append({
                    "attribute_code": mag_attr['attribute_code'],
                    "value": value
                })

        return custom_attributes

    def assign_conf_attributes_to_config_product_in_magento(self, instance, attr_sets, conf_products, simp_products):
        prod_attr_magento = {}
        conf_prod_sku = self.magento_conf_prod_sku
        available_attributes = attr_sets[self.magento_conf_product_id.magento_attr_set]['attributes']
        conf_prod_dict = conf_products[conf_prod_sku]
        simp_prod_dict = simp_products[self.magento_sku]
        prod_attr_odoo = conf_prod_dict['config_attr']
        attr_options = conf_prod_dict['magento_conf_prod_options']
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
                self.magento_conf_product_id.get_attribute_name_by_id(available_attributes, attr.get("attribute_id")): (
                    attr.get('id'), attr.get('attribute_id')) for attr in attr_options if attr
            }

            if prod_attr_odoo != set(prod_attr_magento.keys()):
                # unlink attribute in Magento if assign attribute is not within Odoo attributes
                for attr in prod_attr_magento:
                    if attr not in prod_attr_odoo:
                        res = self.call_unassign_conf_attribute_option(
                            instance, conf_prod_sku, prod_attr_magento[attr][0], simp_prod_dict
                        )
                        if res:     # update magento conf.product options list (remove unassigned option)
                            attr_options = list(
                                filter(lambda i: str(i.get('attribute_id')) != str(prod_attr_magento[attr][1]), attr_options)
                            )
                conf_prod_dict['magento_conf_prod_options'] = attr_options

        # assign new options to config.product with relevant info from Magento
        for pav in self.product_attribute_ids.product_attribute_value_id:
            attr_name = self.to_upper(pav.attribute_id.name)
            if attr_name in prod_attr_odoo and attr_name not in prod_attr_magento:
                attr = available_attributes.get(attr_name)
                if attr:
                    opt = next((o for o in attr['options'] if o.get('label') and
                                self.to_upper(o['label']) == self.to_upper(pav.name)), {})
                    if opt:
                        data['option'].update({
                            "attribute_id": attr["attribute_id"],
                            "label": attr_name,
                            "values": [{"value_index": opt["value"]}]
                        })
                        self.call_assign_new_conf_attribute_option(instance, conf_prod_sku, data, simp_prod_dict)

                        # update conf.product dict with new conf.product option
                        conf_prod_dict['magento_conf_prod_options'].append({
                            'id': "",
                            "attribute_id": attr["attribute_id"],
                            "label": attr_name
                        })

    def call_unassign_conf_attribute_option(self, instance, conf_sku, prod_attr, simp_product_dict):
        try:
            api_url = f'/V1/configurable-products/{conf_sku}/options/{prod_attr}'
            res = req(instance, api_url, 'DELETE')
        except Exception as err:
            text = (f"Error while unlinking {prod_attr} Attribute of {conf_sku} Config.Product in Magento: {str(err)}.")
            simp_product_dict['log_message'] += text
            res = False

        return res

    def call_assign_new_conf_attribute_option(self, instance, conf_sku, data, simp_prod_dict):
        try:
            api_url = f'/V1/configurable-products/{conf_sku}/options'
            req(instance, api_url, 'POST', data)
        except Exception as e:
            txt = f"Error while assigning product attribute option to {conf_sku} Config.Product in Magento: {str(e)}. "
            simp_prod_dict['log_message'] += txt

    def link_simple_to_config_product_in_magento(self, magento_instance, conf_prods_dict, simp_prods_dict):
        config_sku = self.magento_conf_prod_sku
        simple_sku = self.magento_sku
        simp_dict = simp_prods_dict[simple_sku]
        conf_dict = conf_prods_dict[config_sku]

        if simp_dict['magento_prod_id'] in conf_dict['children']:
            simp_dict['magento_status'] = 'extra_info'
            simp_dict['log_message'] = ''
            conf_dict['log_message'] = ''
            return

        self.call_linking_of_simple_and_configurable_products(magento_instance, config_sku, simple_sku, simp_dict)

    def call_linking_of_simple_and_configurable_products(self, instance, config_sku, simple_sku, simp_dict):
        data = {"childSku": simple_sku}

        try:
            api_url = f'/V1/configurable-products/{config_sku}/child'
            res = req(instance, api_url, 'POST', data)
            if res is True:
                simp_dict['magento_status'] = 'extra_info'
            elif res.get('message'):
                raise
        except Exception as err:
            text = (f"Error while linking {simple_sku} with {config_sku} Configurable Product in Magento: {str(err)}.")
            simp_dict['log_message'] += text

    def export_single_simple_product_to_magento(self, instance, simp_prods_dict, attr_sets, method):
        magento_sku = self.magento_sku
        simp_dict = simp_prods_dict[magento_sku]
        conf_prod = self.magento_conf_product_id

        data = self.prepare_simple_product_data(attr_sets, method)
        response = conf_prod.call_product_export_request(instance, data, magento_sku, simp_dict, method)

        if response.get("sku"):
            simp_dict['export_date_to_magento'] = response.get("updated_at")
            simp_dict['magento_status'] = 'extra_info' if conf_prod.is_marketing_prod else 'need_to_link'

            if method == "POST":
                conf_prod.link_product_with_websites_in_magento(magento_sku, instance, simp_prods_dict, response)

            self.process_storeview_data_export(instance, simp_prods_dict)
            conf_prod.process_images_export(instance, simp_prods_dict, self, True)

            return response
        return {}

    def prepare_simple_product_data(self, attr_sets, method, is_in_bulk=False):
        prod_attr_set = self.magento_conf_product_id.magento_attr_set
        available_attributes = attr_sets[prod_attr_set]['attributes']
        prod_attr_list = [(self.to_upper(a.attribute_id.name), self.to_upper(a.name)) for a in
                          self.product_attribute_ids.product_attribute_value_id]
        custom_attributes = self.map_product_attributes_with_magento_attr(prod_attr_list, available_attributes)

        data = {
            "product": {
                "name": self.x_magento_name,
                "attribute_set_id": attr_sets[prod_attr_set]['id'],
                "status": 2,  # 1-enabled / 2-disabled
                "visibility": 1 if self.is_marketing_prod else 3,  # 1-Not visible indiv., 3-Search
                "price": 0,
                "type_id": "simple",
                "weight": self.odoo_product_id.weight,
                "custom_attributes": custom_attributes,
                "extension_attributes": {
                    "stock_item": {"qty": self.qty_avail + 100, "is_in_stock": "true"} if method == 'POST' else {} # to remove +100
                }
            }
        }

        if method == 'POST' or is_in_bulk:
            data["product"].update({"sku": self.magento_sku})

        return data

    def process_storeview_data_export(self, instance, products_dict):
        prod_sku = self.magento_sku
        text = ''

        if instance.catalog_price_scope == 'global':
            text += "Catalog Price Scope has to changed to 'website' in Magento. "

        else:
            for website in instance.magento_website_ids:
                storeview_code = website.store_view_ids[0].magento_storeview_code
                lang_code = website.store_view_ids[0].lang_id.code
                data = {'product': {'name': '', "price": 0, "visibility": 1 if self.is_marketing_prod else 3}}
                data["product"]["name"] = self.with_context(lang=lang_code).odoo_product_id.name + ' ' + \
                                          ' '.join(self.product_attribute_ids.product_attribute_value_id.mapped('name'))

                try:
                    api_url = f'/{storeview_code}/V1/products/{prod_sku}'
                    req(instance, api_url, 'PUT', data)
                except Exception as e:
                    text = f"Error while exporting product data to '{storeview_code}' store view: {str(e)}."
                    break

        if text:
            products_dict[prod_sku]['log_message'] += text
            products_dict[prod_sku]['force_update'] = True

    def export_simple_products_in_bulk(self, instance, simp_prods_dict, attr_sets, method='POST'):
        data = []
        conf_prod_obj = self.env['magento.configurable.product']

        for prod in self:
            if simp_prods_dict[prod.magento_sku]['magento_status'] != 'need_to_link':
                data.append(prod.prepare_simple_product_data(attr_sets, method, True))

        if data:
            response = self.call_simple_products_export_in_bulk(instance, simp_prods_dict, data, method)
            datetime_stamp = datetime.now()

            if not response or response.get('errors'):
                return False

            log_id = self.bulk_log_ids.create({'bulk_uuid': response.get("bulk_uuid"), 'topic': 'Product Export'})
            extra_info_dict = {'prod_media': {}, 'remove_images': [], 'product_websites': []}

            for prod in self:
                sku = prod.magento_sku
                simp_prods_dict[sku]['export_date_to_magento'] = datetime_stamp
                simp_prods_dict[sku]['magento_status'] = 'in_process'
                prod.write({'bulk_log_ids': [(6, 0, [log_id.id])]})

                conf_prod_obj.prepare_images_and_websites_info(
                    instance, prod, simp_prods_dict[sku], extra_info_dict, method, True
                )

            if method == "POST" and extra_info_dict['product_websites']:
                res = conf_prod_obj.link_product_with_websites_in_magento_in_bulk(
                    instance, extra_info_dict['product_websites'], [s.magento_sku for s in self], simp_prods_dict, self
                )
                if res:
                    self.write({'bulk_log_ids': [(4, res.id)]})

            self.process_simple_prod_storeview_data_export_in_bulk(instance, data, simp_prods_dict)
            conf_prod_obj.process_images_export_in_bulk(instance, extra_info_dict, simp_prods_dict)

    def call_simple_products_export_in_bulk(self, instance, simp_prods_dict, data, method):
        response = {}

        try:
            api_url = '/all/async/bulk/V1/products'
            response = req(instance, api_url, method, data)
        except Exception as err:
            text = (f"Error while asynchronously Simple Products {'create' if method == 'POST' else 'update'} in "
                    f"Magento: {str(err)}")
            for prod in self:
                simp_prods_dict[prod.magento_sku]['log_message'] += text

        return response

    def process_simple_prod_storeview_data_export_in_bulk(self, instance, data, products_dict):
        if instance.catalog_price_scope == 'global':
            text = f"Catalog Price Scope has to be 'website' in Magento for '{instance.name}' instance. "
            for product in data:
                products_dict[product['sku']]['log_message'] += text
            return

        for website in instance.magento_website_ids:
            data_lst = []
            storeview_code = website.store_view_ids[0].magento_storeview_code
            lang_code = website.store_view_ids[0].lang_id.code

            for prod in data:
                sku = prod['product']['sku']
                product = self.filtered(lambda x: x.magento_sku == sku)
                prod_name = product.with_context(lang=lang_code).odoo_product_id.name + ' ' + \
                            ' '.join(product.product_attribute_ids.product_attribute_value_id.mapped('name'))
                new_prod = {
                    'product': {
                        'name': prod_name,
                        'sku': sku,
                        "visibility": 1 if product.is_marketing_prod else 3,
                        'price': 0
                    }
                }
                data_lst.append(new_prod)

            try:
                api_url = '/%s/async/bulk/V1/products' % storeview_code
                res = req(instance, api_url, 'PUT', data_lst)
            except Exception as e:
                for product in data:
                    text = f"Error while exporting product's info to {storeview_code} store view: {str(e)}"
                    products_dict[product['product']['sku']]['log_message'] += text
                break

            if not res.get('errors', True):
                self.log_bulk_export(res.get("bulk_uuid"), f'Storeview-{storeview_code} info export')

    def assign_attr_to_config_products_in_magento_in_bulk(self, magento_instance, conf_prod_dict, simp_prod_dict,
                                                          available_attributes):
        data = []

        for prod in self:
            prod_dict = simp_prod_dict[prod.magento_sku]
            if prod_dict['log_message'] or prod.is_marketing_prod:
                continue

            mag_attr_set = prod.magento_conf_product_id.magento_attr_set
            mag_avail_attrs = available_attributes[mag_attr_set]['attributes']
            conf_sku = prod.magento_conf_prod_sku

            for pav in prod.product_attribute_ids.product_attribute_value_id:
                attr_name = self.to_upper(pav.attribute_id.name)
                if attr_name in conf_prod_dict.get(conf_sku, {}).get('config_attr', {}):
                    attr = mag_avail_attrs.get(attr_name)
                    if attr:
                        opt = next((o for o in attr['options'] if o.get('label') and
                                    self.to_upper(o['label']) == self.to_upper(pav.name)), {})
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
                for prod in self:
                    simp_prod_dict[prod.magento_sku]['log_message'] += text
                return False

            if response.get('errors', {}):
                return False
            else:
                self.log_bulk_export(response.get("bulk_uuid"), 'Assign Product Attributes')

    def link_simple_to_config_products_in_bulk(self, magento_instance, simp_prods_dict):
        data = []

        for prod in self:
            if simp_prods_dict[prod.magento_sku]['log_message'] or prod.is_marketing_prod:
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
                for prod in self:
                    simp_prods_dict[prod.magento_sku]['log_message'] += text

            if res.get("errors"):
                return False
            else:
                self.log_bulk_export(res.get("bulk_uuid"), 'Link Simple to Configurable')

    def check_product_attribute_values_combination_already_exist(self, conf_products, simple_products, conf_sku,
                                                                 simp_prod_attr, available_attributes, simpl_sku):
        """
        Check Product's "Attribute: Value" pair for duplication
        :return: Product sku in case of duplication or False
        """
        # magento_conf_prod_links is dict with already assigned configurable {attribute: value} pair to conf.product
        magento_conf_prod_links = conf_products[conf_sku].get('magento_configurable_product_link_data', {})
        conf_prod_attributes = conf_products[conf_sku]['config_attr']
        simp_attr_val = {}

        for pav in simp_prod_attr:
            attr_name = self.to_upper(pav.attribute_id.name)
            if attr_name in conf_prod_attributes:
                attr = available_attributes.get(attr_name)
                if attr:
                    opt = next((o for o in attr['options'] if o.get('label') and
                                self.to_upper(o.get('label')) == self.to_upper(pav.name)), {})
                    if opt:
                        simp_attr_val.update({attr_name: self.to_upper(opt['label'])})

        for prod in magento_conf_prod_links:
            if magento_conf_prod_links[prod] == simp_attr_val and prod != simpl_sku:
                return prod

        siblings = [
            prod for prod in simple_products if simple_products[prod]['simple_prod_rec'].magento_conf_prod_sku == conf_sku
        ]
        for prod in siblings:
            conf_attrs_and_vals = simple_products[prod]['simple_prod_rec'].get_product_conf_attributes_dict()
            if prod != simpl_sku and conf_attrs_and_vals == simp_attr_val:
                return prod

        return False

    def get_product_conf_attributes_dict(self):
        """
        Extract each Simple Product's "Attribute: Value" pair (only configurable ones) to one single dict
        :return: generated dictionary
        """
        attr_dict = {}
        for pav in self.product_attribute_ids.product_attribute_value_id:
            if pav.attribute_id.name in [
                a.name for a in self.magento_conf_product_id.with_context(lang='en_US').x_magento_assign_attr_ids
            ]:
                attr_dict.update({self.to_upper(pav.attribute_id.name): self.to_upper(pav.name)})
        return attr_dict

    @staticmethod
    def get_product_price_for_website(website, product, qty=1):
        price_and_rule = website.pricelist_id.get_product_price_rule(product, qty, False)

        return 0 if price_and_rule[1] is False else price_and_rule[0]

    def delete_simple_product_in_magento(self):
        self.ensure_one()
        self.magento_conf_product_id.delete_product_in_magento(self)

    def save_magento_products_info_to_database(self, instance, conf_products, simp_products, is_status_update, is_cron):
        magento_websites = instance.magento_website_ids
        simpl_prods = self.env['magento.product.product']
        conf_prods = self.env['magento.configurable.product']

        for s_prod in simp_products:
            simp_prod_dict = simp_products[s_prod]
            simp_prod_rec = simp_prod_dict['simple_prod_rec']
            simpl_prods += simp_prod_rec
            conf_sku = simp_prod_rec.magento_conf_prod_sku
            conf_prod_dict = conf_products[conf_sku]

            if simp_prod_dict['log_message']:
                simp_prod_dict['magento_status'] = 'log_error'
                simp_prod_rec.save_error_messages_to_log_book(simp_prod_dict['log_message'], conf_prod_dict['log_message'])
            else:
                if simp_prod_rec.error_log_ids:
                    simp_prod_rec.error_log_ids.sudo().unlink()
                if simp_prod_dict['magento_status'] == 'log_error':
                    new_status = 'update_needed' if simp_prod_dict.get('magento_prod_id') else 'not_exported'
                    simp_prod_dict['magento_status'] = new_status

            if simp_prod_dict['magento_status'] != 'in_magento' and conf_prod_dict['magento_status'] == 'in_magento':
                if simp_prod_dict['magento_status'] == 'extra_info':
                    conf_prod_dict['magento_status'] = 'extra_info'
                else:
                    conf_prod_dict['magento_status'] = 'update_needed'

            values = self.prepare_data_to_save(simp_prod_dict, simp_prod_rec, magento_websites, is_status_update)
            simp_prod_rec.write(values)

        for c_prod in conf_products:
            conf_prod_dict = conf_products[c_prod]
            conf_product = conf_prod_dict['conf_prod_rec']
            conf_prods += conf_product

            if conf_prod_dict['log_message']:
                conf_prod_dict['magento_status'] = 'log_error'
            else:
                if conf_prod_dict['magento_status'] == 'log_error':
                    new_status = 'update_needed' if conf_prod_dict.get('magento_prod_id') else 'not_exported'
                    conf_prod_dict['magento_status'] = new_status

            values = self.prepare_data_to_save(conf_prod_dict, conf_product, magento_websites, is_status_update)
            conf_product.write(values)

        if not is_cron:
            failed = self.process_products_statuses_update_in_magento(instance, simpl_prods, simp_products)
            failed += self.process_products_statuses_update_in_magento(instance, conf_prods, conf_products)

            if failed:
                _logger.warning(f"Failed to Enable/Disable products with the following SKUs in Magento: {failed}")

    @staticmethod
    def prepare_data_to_save(product_dict, odoo_product, websites, is_status_update):
        values = {'magento_status': product_dict['magento_status']}
        mag_prod_websites = product_dict.get('magento_website_ids', [])
        odoo_websites = {str(p.magento_website_id) for p in odoo_product.magento_website_ids}

        mag_prod_id = product_dict.get('magento_prod_id')
        if mag_prod_id:
            if str(mag_prod_id) != odoo_product.magento_product_id:
                values.update({'magento_product_id': mag_prod_id})
        else:
            if odoo_product.magento_product_id:
                values.update({'magento_product_id': ''})
            if values['magento_status'] in ['in_magento', 'extra_info', 'need_to_link', 'update_needed']:
                values.update({
                    'magento_status': 'not_exported',
                    'magento_export_date': '',
                    'is_enabled': False,
                    'force_update': False,
                    'force_image_update': False,
                    'bulk_log_ids': [(5, 0, 0)]
                })

        if mag_prod_websites:
            if odoo_websites != set(mag_prod_websites):
                ids = [w.id for w in websites if str(w.magento_website_id) in mag_prod_websites]
                values.update({'magento_website_ids': [(6, 0, ids)]})
        elif odoo_websites:
            values.update({'magento_website_ids': [(5, 0, 0)]})

        if not is_status_update:
            if product_dict['magento_status'] != 'log_error':
                if product_dict['to_export']:
                    values.update({'magento_export_date': product_dict['export_date_to_magento']})

                if product_dict['force_update']:
                    product_dict['force_update'] = False
                    values.update({'force_update': False})

                if product_dict['force_image_update']:
                    product_dict['force_image_update'] = False
                    values.update({'force_image_update': False})

            # valid for products which have failed exporting storeviews/images info (after product are created in M2)
            if product_dict['force_update']:
                values.update({'force_update': True})
            if product_dict['force_update']:
                values.update({'force_update': True})

        return values

    def save_error_messages_to_log_book(self, simp_log_message, conf_log_message):
        vals = {
            'magento_log_message': simp_log_message,
            'magento_log_message_conf': conf_log_message
        }

        if self.error_log_ids:
            self.error_log_ids.write(vals)
        else:
            vals.update({'magento_product_id': self.id})
            self.error_log_ids.create(vals)

    def process_products_statuses_update_in_magento(self, instance, product_recs,  products_dict):
        to_disable, to_enable = self.prepare_enable_or_disable_products(instance, product_recs, products_dict)
        common_list = to_disable + to_enable
        failed = []

        if common_list:
            api_url = '/all/V1/products/status'
            count = (len(common_list) // 20) + 1

            for c in range(count):
                list_extract = common_list[c * 20:20 * (c + 1)]

                try:
                    response = req(instance, api_url, 'POST', {"products": list_extract})
                except Exception as e:
                    _logger.warning(f'Change product status in Magento fails: {e}')
                    failed += list({p['sku'] for p in list_extract})
                    response = []

                if response:
                    failed_params = []
                    for res in response:
                        if isinstance(res, dict) and res.get('parameters'):
                            failed_params += res.get('parameters')
                    failed += list({p['sku'] for p in list_extract if p['sku'] in failed_params})

            if failed:
                product_recs = product_recs.filtered(lambda x: x.magento_sku not in failed)

        disable_prods = product_recs.filtered(
            lambda x: x.magento_sku in [p['sku'] for p in to_disable] or
                      (x.is_enabled and not products_dict[x.magento_sku].get('is_magento_enabled'))
        )
        disable_prods.write({'is_enabled': False})

        (product_recs - disable_prods).filtered(
            lambda x: x.magento_sku in [p['sku'] for p in to_enable] or
                      (not x.is_enabled and products_dict[x.magento_sku].get('is_magento_enabled'))
        ).write({'is_enabled': True})

        return failed

    def prepare_enable_or_disable_products(self, instance, product_recs, product_dict):
        to_disable = []
        to_enable = []

        for prod in product_recs:
            sku = prod.magento_sku
            is_enabled = product_dict[sku].get('is_magento_enabled')

            if prod.magento_status == 'in_magento':
                if not is_enabled:
                    for view in instance.magento_website_ids.store_view_ids:
                        to_enable.append({"sku": sku, "status": 1, "store_id": view.magento_storeview_id})
            else:
                if is_enabled:
                    for view in instance.magento_website_ids.store_view_ids:
                        to_disable.append({"sku": sku, "status": 2, "store_id": view.magento_storeview_id})

        return to_disable, to_enable

    def log_bulk_export(self, bulk_uuid, topic):
        log_id = self.bulk_log_ids.create({
            'bulk_uuid': bulk_uuid,
            'topic': topic
        })

        self.write({'bulk_log_ids': [(4, log_id.id)]})

    def export_products_extra_info_to_magento(self):
        self.ensure_one()

        err_res = self.export_product_prices_to_magento(self.magento_instance_id)
        if not err_res:
            self.magento_conf_product_id.processing_products_export_to_magento(True)
        else:
            return err_res

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
    def to_upper(val):
        if val:
            return "".join(str(val).split()).upper()
        else:
            return val
