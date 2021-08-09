# -*- coding: utf-8 -*-

import json

from odoo import fields, models
from datetime import datetime
# from odoo.exceptions import UserError
from ...odoo_magento2_ept.models.api_request import req, create_search_criteria
from ...odoo_magento2_ept.python_library.php import Php

MAGENTO_DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'


class MagentoProductProduct(models.Model):
    """
    Extends Magento Products functionality with Export to Magento operation
    """
    _inherit = 'magento.product.product'

    prod_categ_name = fields.Char(string='Product Category Name', related='odoo_product_id.categ_id.name')
    # magento_log_book_rec = fields.Many2one('product_log_book',string="Magento Log Book records")
    magento_export_date = fields.Datetime(string="Last Export Date", copy=False)
    magento_export_date_conf = fields.Datetime(string="Configurable Product last Export Date", copy=False)
    magento_log_message = fields.Char(string="Product Error Messages")
    magento_log_message_conf = fields.Char(string="Product Category Error Messages")
    magento_status = fields.Selection([
        ('not_exported', 'not Exported'),
        ('in_process', 'In Process'),
        ('in_magento', 'In Magento'),
        ('need_to_link', 'Need to be Linked'),
        ('log_error', 'Error to Export'),
        ('update_needed', 'Need to Update')
    ], string='Magento Export Status', help='The status of Product Export to Magento ', default='not_exported')

    def process_products_export_to_magento(self, single=False):
        """
        The main method to process Products Export to Magento. The Product's Categories are treated as Configurable
        Products and regular Odoo Products as Simple Products in Magento.
        """
        if single:
            export_products = single
        else:
            active_product_ids = self._context.get("active_ids", [])
            export_products = self.env["magento.product.product"].browse(active_product_ids)

        # Abbreviation used below:
        # ml - magento_layer with products in Odoo
        # mi - magento_instance
        # prod - product
        # attr - attribute
        # conf - configurable(in Magento) aka category_name(Odoo)
        # simp - simple
        # mag - magento
        for mi in {i.magento_instance_id: {} for i in export_products}:
            # create dict which collects meta-data for unique selected configurable/simple products
            ml_conf_products_dict = self.create_conf_products_dict(mi.id, export_products)
            ml_simp_products_dict = self.create_simple_products_dict(mi.id, export_products)

            # get selected products from Magento if any
            magento_conf_products = self.get_products_from_magento(mi, ml_conf_products_dict)
            magento_simp_products = self.get_products_from_magento(mi, ml_simp_products_dict)

            # update conf/simp dictionaries with Magento data
            for prod in magento_conf_products:
                self.update_conf_product_dict_with_magento_data(prod, ml_conf_products_dict)
            for prod in magento_simp_products:
                self.update_simp_product_dict_with_magento_data(prod, ml_simp_products_dict)

            del magento_conf_products
            del magento_simp_products

            # create unique attribute-sets and get their id/attribute(options) data from Magento
            attr_sets = self.create_attribute_sets_dict(mi, ml_conf_products_dict)

            # check and update 'to_export' field of ml_dict for products which don't need to be exported
            self.check_config_products_to_export(ml_conf_products_dict, attr_sets)
            self.check_simple_products_to_export(mi.id, ml_simp_products_dict, ml_conf_products_dict)

            # filter selected Odoo Products and their Configurable Products to be exported to Magento
            conf_prod_to_export = {
                k: v for k, v in ml_conf_products_dict.items() if v['to_export'] and not v['log_message']
            }
            simp_prod_to_export = export_products.filtered(
                lambda prd: prd.magento_instance_id.id == mi.id and
                            prd.magento_sku in ml_simp_products_dict and
                            ml_simp_products_dict[prd.magento_sku]['to_export'] == True and
                            ml_simp_products_dict[prd.magento_sku]['log_message'] == ""
            )

            # if there are some config.products to export
            for prod in conf_prod_to_export:
                # check if attribute_set_id and assign_attributes are defined in configurable product
                mag_attr_set = conf_prod_to_export[prod]['attribute_set']
                prod_attr_set_id = attr_sets[mag_attr_set]['id']
                prod_conf_attr = ml_conf_products_dict[prod]['config_attr']
                if prod_attr_set_id and prod_conf_attr:
                    # check if configurable attributes of all selected products exist in Magento
                    # logs error when attribute doesn't exist in Magento
                    available_attributes = [self.to_upper(a['default_label']) for a in
                                            attr_sets[mag_attr_set]['attributes']]
                    conf_prod_attr = [self.to_upper(c) for c in prod_conf_attr if c]
                    if not self.check_product_attr_is_in_attributes_list(available_attributes, conf_prod_attr):
                        text = "Some of configurable attributes of %s Product doesn't exist in Magento. " \
                               "Attribute has to be created at first on Magento side.\n" % prod
                        ml_conf_products_dict[prod]['log_message'] += text

                    # check & update (PUT) every single conf.product if it exists in Magento and there are no errors
                    if ml_conf_products_dict[prod].get('magento_update_date', ''):
                        if ml_conf_products_dict[prod]['magento_type_id'] == 'configurable':
                            # check if assign attributes are the same in Magento and Odoo
                            mag_attr_options = ml_conf_products_dict[prod]['magento_conf_prod_options']
                            check_assign_attr = self.check_config_product_assign_attributes(
                                mag_attr_options,
                                attr_sets[mag_attr_set]['attributes'],
                                prod_conf_attr
                            )
                            conf_prod = self.update_single_conf_product_in_magento(mi, prod, prod_attr_set_id,
                                                                                   ml_conf_products_dict,
                                                                                   check_assign_attr)
                            # update magento data in ml_conf_products_dict,
                            # later will be used while linking with simple prod
                            if conf_prod:
                                self.update_conf_product_dict_with_magento_data(conf_prod, ml_conf_products_dict)
                        else:
                            ml_conf_products_dict[prod]['log_message'] += \
                                "Product with the following sku - \"%s\" already exists in Magento. " \
                                "And it's type is not Configurable.\n" % prod
                else:
                    if not prod_attr_set_id:
                        text = "Missed Magento Product Attribute Set for %s configurable product.\n" % prod
                        ml_conf_products_dict[prod]['log_message'] += text

                    if not prod_conf_attr:
                        text = "Missed Configurable Attribute(s) for %s configurable product.\n" % prod
                        ml_conf_products_dict[prod]['log_message'] += text

            # create (POST) a bulk of new configurable products to be exported to Magento
            new_conf_prod = {k: v for k, v in ml_conf_products_dict.items() if
                             not ml_conf_products_dict[k].get('magento_update_date', '') and
                             not ml_conf_products_dict[k]['log_message']}
            if not single and new_conf_prod:
                self.create_bulk_of_new_conf_products_in_magento(mi, new_conf_prod, ml_conf_products_dict, attr_sets)
            elif single:
                res = self.create_single_conf_product_in_magento(mi, new_conf_prod, ml_conf_products_dict, attr_sets)
                if res:
                    self.update_conf_product_dict_with_magento_data(res, ml_conf_products_dict)

            # check if product attributes of all selected simple products exist in Magento
            # logs error when product has no attributes and when needed - creates new attribute options(swatch)
            self.check_product_attributes_exist_in_magento(mi, simp_prod_to_export, attr_sets, ml_simp_products_dict)

            for prod in simp_prod_to_export:
                categ_name = prod.odoo_product_id.categ_id.name

                # check if any log_messages for current product or it's configurable
                if ml_simp_products_dict[prod.magento_sku]['log_message']:
                    continue
                elif ml_conf_products_dict[categ_name]['log_message']:
                    text = "Configurable product for the current simple product is not ok. Please check it first.\n"
                    ml_simp_products_dict[prod.magento_sku]['log_message'] += text
                    continue

                # check if product has assign attributes defined in it's configurable product
                simp_prod_attr = prod.odoo_product_id.product_template_attribute_value_ids.product_attribute_value_id
                check_assign_attr = self.check_product_attr_is_in_attributes_list(
                    [a.attribute_id.name for a in simp_prod_attr],
                    ml_conf_products_dict[categ_name]['config_attr']
                )
                if not check_assign_attr:
                    text = 'Simple product - %s is missing attribute(s) defined as configurable in ' \
                           'Product Category table.\n' % prod.magento_sku
                    ml_simp_products_dict[prod.magento_sku]['log_message'] += text
                    continue

                prod_attr_set = prod.odoo_product_id.categ_id.magento_attr_set
                available_attributes = attr_sets[prod_attr_set]['attributes']

                # check if configurable product already contains such set of "Attribute: Value" pair
                # if doesn't return False - will be unable to link it further
                check_attr_values = self.check_products_set_of_attribute_values(ml_conf_products_dict, categ_name,
                                                                                simp_prod_attr, available_attributes,
                                                                                ml_simp_products_dict, prod.magento_sku)
                if check_attr_values:
                    text = "The same configurable Set of Attribute Values was found in " \
                           "Product - %s.\n" % check_attr_values
                    ml_simp_products_dict[prod.magento_sku]['log_message'] += text
                    continue

                # the code below relates only to Simple Products to be updated in Magento
                if ml_simp_products_dict[prod.magento_sku].get('magento_update_date', ''):
                    if not ml_conf_products_dict[categ_name].get('magento_update_date', ''):
                        # log warning that newly created config.products via async-bulk request possibly are not created
                        # in Magento yet (at the moment of further code execution)
                        text = "The Configurable Product - %s related to current product is not in Magento yet. " \
                               "And they cannot be linked so far.\n" % categ_name
                        ml_simp_products_dict[prod.magento_sku]['log_message'] += text
                        continue

                    if ml_simp_products_dict[prod.magento_sku]['magento_type_id'] == 'simple':
                        print(ml_simp_products_dict)
                        # to skip this step if only linking with parent needs to be done
                        if ml_simp_products_dict[prod.magento_sku]['magento_status'] != 'need_to_link':
                            res = self.update_single_simple_product_in_magento(mi, prod, available_attributes,
                                                                               attr_sets[prod_attr_set]['id'],
                                                                               ml_simp_products_dict)
                            if ml_simp_products_dict[prod.magento_sku]['log_message']:
                                continue
                            else:
                                self.update_simp_product_dict_with_magento_data(res, ml_simp_products_dict)
                    else:
                        text = "The Product with such sku is already created in Magento. " \
                               "(And it's type isn't Simple Product.)\n"
                        ml_simp_products_dict[prod.magento_sku]['log_message'] += text
                        continue

                    self.assign_attr_to_config_product(mi, prod, available_attributes, ml_conf_products_dict,
                                                       ml_simp_products_dict)
                    if not ml_conf_products_dict[categ_name]['log_message']:
                        self.link_simple_to_config_product_in_magento(mi, prod,
                                                                      ml_conf_products_dict[categ_name]['children'],
                                                                      ml_simp_products_dict)

                    # check if simple product assigned to any other of selected config.product than
                    # current one and unlink it
                    for conf_prod in ml_conf_products_dict:
                        prod_id = ml_simp_products_dict[prod.magento_sku]['magento_prod_id']
                        if conf_prod != categ_name and prod_id in ml_conf_products_dict[conf_prod]['children']:
                            self.unlink_simple_and_config_prod(mi, prod.magento_sku, conf_prod)

            # process mass upload of simple products to Magento, assign attributes to config.products and link them
            new_simple_prod = {}
            for s in ml_simp_products_dict:
                if not ml_simp_products_dict[s].get('magento_update_date', '') and \
                        not ml_simp_products_dict[s]['log_message']:
                    new_simple_prod.update({s: ml_simp_products_dict[s]})
            if not single and new_simple_prod:
                self.create_new_bulk_of_simple_products_in_magento(mi, simp_prod_to_export, new_simple_prod,
                                                                   ml_simp_products_dict, attr_sets)
                self.assign_attr_to_config_products_in_bulk(mi, simp_prod_to_export, new_simple_prod,
                                                            ml_conf_products_dict, ml_simp_products_dict, attr_sets)
                self.link_simple_to_config_products_in_bulk(mi, simp_prod_to_export, new_simple_prod,
                                                            ml_simp_products_dict)

            if single:
                res = self.create_new_simple_product_in_magento(mi, simp_prod_to_export, new_simple_prod,
                                                                ml_simp_products_dict, attr_sets)
                if res:
                    self.update_simp_product_dict_with_magento_data(res, ml_simp_products_dict)
                    prod_attr_set = simp_prod_to_export.odoo_product_id.categ_id.magento_attr_set
                    available_attributes = attr_sets[prod_attr_set]['attributes']
                    self.assign_attr_to_config_product(mi, simp_prod_to_export, available_attributes,
                                                       ml_conf_products_dict, ml_simp_products_dict)
                    if not ml_conf_products_dict[simp_prod_to_export.odoo_product_id.categ_id.name]['log_message']:
                        self.link_simple_to_config_product_in_magento(
                            mi,
                            simp_prod_to_export,
                            ml_conf_products_dict[simp_prod_to_export.odoo_product_id.categ_id.name]['children'],
                            ml_simp_products_dict
                        )

            # save data with export dates, magento statuses and log_messages to Db
            self.save_magento_data_to_database(mi.id, ml_simp_products_dict, ml_conf_products_dict)

            # {print({k: v}) for k, v in ml_conf_products_dict.items() if ml_conf_products_dict[k]['log_message']}
            # {print({k: v}) for k, v in ml_simp_products_dict.items() if ml_simp_products_dict[k]['log_message']}

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

            if exp_date_c:
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
                                        attr_sets[attr_set_name]['attributes'],
                                        ml_conf_products_dict[prod]['config_attr']
                                    )
                                    if check_assign_attr:
                                        ml_conf_products_dict[prod]['to_export'] = False

    def check_simple_products_to_export(self, instance_id, ml_simp_products_dict, ml_conf_products_dict):
        """
        Check if Simple Product Export to Magento needed
        :param ml_simp_products_dict: Dictionary contains metadata for selected Simple Products (Odoo products)
        :param ml_conf_products_dict: Dictionary contains metadata for selected Configurable Products (Odoo categories)
        :return: None
        """
        remove_items = []
        for prod in ml_simp_products_dict:
            categ_name = ml_simp_products_dict[prod]['category_name']
            if ml_simp_products_dict[prod]['log_message'] or ml_conf_products_dict[categ_name]['log_message']:
                ml_simp_products_dict[prod]['to_export'] = False
                if ml_conf_products_dict[categ_name]['log_message']:
                    text = "Configurable Product - %s for the current simple product is not ok. " \
                           "Please check it first.\n" % categ_name
                    ml_simp_products_dict[prod]['log_message'] += text
                continue

            # apply compatible date format to compare dates
            exp_date_s = self.format_to_magento_date(ml_simp_products_dict[prod]['export_date_to_magento'])
            upd_date_s = self.format_to_magento_date(ml_simp_products_dict[prod]['latest_update_date'])
            upd_date_c = self.format_to_magento_date(ml_conf_products_dict[categ_name]['latest_update_date'])
            mag_date_s = ml_simp_products_dict[prod].get('magento_update_date', '')
            mag_date_s = mag_date_s if mag_date_s else ''

            if exp_date_s:
                if exp_date_s > upd_date_s and exp_date_s > upd_date_c:
                    if mag_date_s >= exp_date_s:
                        if not ml_conf_products_dict[categ_name]['to_export']:
                            if ml_simp_products_dict[prod]['magento_prod_id'] in \
                                ml_conf_products_dict[categ_name]['children']:
                                ml_simp_products_dict[prod]['to_export'] = False
                                # re-write to db if not "in_magento" status
                                if ml_simp_products_dict[prod]['magento_status'] != 'in_magento':
                                    magento_product = self.env['magento.product.product'].search([
                                        ('magento_sku', '=', prod), ('magento_instance_id', '=', instance_id)
                                    ])
                                    magento_product.write({
                                        'magento_status': "in_magento",
                                        'magento_log_message': "",
                                        'magento_log_message_conf': ""
                                    })
                                remove_items.append(prod)
                            else:
                                ml_simp_products_dict[prod]['magento_status'] = 'need_to_link'
                    else:
                        ml_simp_products_dict[prod]['magento_status'] = 'update_needed'
                else:
                    ml_simp_products_dict[prod]['magento_status'] = 'update_needed'

        # delete unneeded products from ml_simp_products_dict
        if remove_items:
            for prod in remove_items:
                del ml_simp_products_dict[prod]

    def process_manually(self):
        self.ensure_one()
        self.process_products_export_to_magento(self)

        # return {
        #     'effect': {
        #         'fadeout': 'slow',
        #         'message': "Process Completed Successfully!".format({}),
        #         'img_url': '/web/static/src/img/smile.svg',
        #         'type': 'rainbow_man',
        #     }
        # }

    def update_single_conf_product_in_magento(self, magento_instance, magento_sku, attribute_set_id, ml_conf_products,
                                              check_assign_attr):
        """
        Export(update) configurable product to Magento
        :param magento_instance: Instance of Magento
        :param magento_sku: Magento Product sku
        :param attribute_set_id: ID of Product's attribute set defined in Magento
        :param ml_conf_products: Dictionary contains metadata for selected Configurable Products (Odoo categories)
        :param check_assign_attr: Boolean - if assign attributes of Product were changed
        :return: Updated Configurable Product Dictionary from Magento or empty Dictionary if error
        """
        data = {
            "product": {
                "name": magento_sku.upper(),
                "type_id": "configurable",
                "attribute_set_id": attribute_set_id
            }
        }

        # will unlink all related simple products to configurable
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

        return response

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

            prod_attr_set = prod.odoo_product_id.categ_id.magento_attr_set
            avail_attr_list = available_attributes[prod_attr_set]['attributes']
            # logs if any of attributes are missed in Magento and creates new attr.option in Magento if needed
            for attr in prod_attr:
                attr_name = self.to_upper(attr.attribute_id.name)
                at = next((a for a in avail_attr_list if a and attr_name == self.to_upper(a.get('default_label'))), {})
                if not at:
                    text = "Attribute - %s has to be created at first on Magento side.\n" % attr.attribute_id.name
                    ml_product_dict[prod.magento_sku]['log_message'] += text
                else:
                    if self.to_upper(attr.name) not in [self.to_upper(i.get('label')) for i in at['options']]:
                        id, err = self.create_new_attribute_option_in_magento(magento_instance, at['attribute_code'],
                                                                              attr.name)
                        if err:
                            ml_product_dict[prod.magento_sku]['log_message'] += err
                        else:
                            for d in available_attributes[prod_attr_set]['attributes']:
                                if d['attribute_id'] == at['attribute_id']:
                                    d['options'].append({
                                        'label': attr.name.upper(),
                                        'value': id
                                    })
                                    break

    def create_new_attribute_option_in_magento(self, magento_instance, attribute_code, attribute_option):
        """
        Creates new option(swatch) for defined attribute in Magento
        :param magento_instance: Instance of Magento
        :param attribute_code: The Code of Attribute defined in Magento
        :param attribute_option: Dictionary with defined Attributes and their values in Magento
        :return: ID of created option
        """
        data = {
            "option": {
                "label": str(attribute_option).upper(),
                "sort_order": 0,
                "is_default": "false",
                "store_labels": []
            }
        }

        magento_storeviews = self.env["magento.storeview"].search([('magento_instance_id', '=', magento_instance.id)])

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
        except Exception:
            return 0, "Error while new Product Attribute Option(Swatch) creation for %s Attribute.\n" % attribute_code
        return res[3:], ""

    def update_single_simple_product_in_magento(self, magento_instance, product, available_attributes,
                                                attribute_set_id, ml_simp_products):
        """
        Export(update) Simple Product to Magento
        :param magento_instance: Instance of Magento
        :param product: Odoo Product object
        :param available_attributes: Dictionary with defined Attributes and their values in Magento
        :param attribute_set_id: ID of Product's attribute set defined in Magento
        :param ml_simp_products: Dictionary contains metadata for selected Simple Products (Odoo products)
        :return: {} or Updated product
        """
        product_attributes = product.odoo_product_id.product_template_attribute_value_ids.product_attribute_value_id
        custom_attributes = self.map_product_attributes_from_magento(product_attributes, available_attributes)
        data = {
            "product": {
                "name": product.magento_product_name,
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

        try:
            api_url = '/all/V1/products/%s' % product.magento_sku
            response = req(magento_instance, api_url, 'PUT', data)
        except Exception:
            text = "Error while Simple Product update in Magento.\n"
            ml_simp_products[product.magento_sku]['log_message'] += text
            return {}

        if response.get("sku"):
            ml_simp_products[product.magento_sku]['export_date_to_magento'] = response.get("updated_at")
            ml_simp_products[product.magento_sku]['magento_status'] = 'need_to_link'
            # export product images to Magento
            if len(product.odoo_product_id.product_template_image_ids):
                prod_media = {product.magento_sku: product.odoo_product_id.product_template_image_ids}
                self.export_bulk_media_to_magento(magento_instance, prod_media, ml_simp_products)
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
        for attr_val in product_attributes:
            for attr in available_attributes:
                if self.to_upper(attr_val.attribute_id.name) == self.to_upper(attr['default_label']):
                    for o in attr['options']:
                        if self.to_upper(attr_val.name) == self.to_upper(o['label']):
                            custom_attributes.append({
                                    "attribute_code": attr['attribute_code'],
                                    "value": o['value']
                            })
                            break

        return custom_attributes

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
        config_product_sku = product.odoo_product_id.categ_id.name
        product_attributes = product.odoo_product_id.product_template_attribute_value_ids.product_attribute_value_id
        config_prod_assigned_attr = ml_conf_products[config_product_sku]['config_attr']
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
            prod_attr_magento = {self.get_attr_name_by_id(available_attributes, attr.get("attribute_id")) for attr in
                                 attr_options if attr}
            prod_attr_odoo = {self.to_upper(attr) for attr in config_prod_assigned_attr if attr}
            if prod_attr_odoo != prod_attr_magento:
                # unlink updated attributes in Magento
                conf_prod_assign_attr_adj = [self.to_upper(o) for o in config_prod_assigned_attr if o]
                for opt in attr_options:
                    if self.to_upper(opt.get("label")) not in conf_prod_assign_attr_adj:
                        try:
                            api_url = '/V1/configurable-products/%s/options/%s' % (config_product_sku, opt.get("id"))
                            req(magento_instance, api_url, 'DELETE')
                        except Exception:
                            text = "Error while unlinking Assign Attribute of %s Config.Product " \
                                   "in Magento. \n" % config_product_sku
                            ml_simp_products[product.magento_sku]['log_message'] += text

        # assign new options to config.product with relevant info from Magento
        for attr_val in product_attributes:
            prod_attr_name = attr_val.attribute_id.name
            if prod_attr_name in config_prod_assigned_attr:
                if self.to_upper(prod_attr_name) not in prod_attr_magento:
                    # valid for new "assign" attributes for config.product to be created in Magento
                    for attr in available_attributes:
                        if self.to_upper(prod_attr_name) == self.to_upper(attr['default_label']):
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
                                    break

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

    def link_simple_to_config_product_in_magento(self, magento_instance, product, config_product_children,
                                                 ml_simp_products):
        """
        Link simple product to configurable product in Magento
        :param magento_instance: Instance of Magento
        :param product: Odoo Product object
        :param config_product_children: The children linked to Configurable Product
        :param ml_simp_products: Dictionary contains metadata for selected Simple Products (Odoo products)
        :return: None
        """
        config_product_sku = product.odoo_product_id.categ_id.name
        simple_product_sku = product.magento_sku

        # if already linked, skip
        if ml_simp_products[simple_product_sku]['magento_prod_id'] in config_product_children:
            ml_simp_products[product.magento_sku]['magento_status'] = 'in_magento'
            return

        # if not linked
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

    def check_product_attr_is_in_attributes_list(self, attributes_list, prod_attrs):
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
        magento_sku_list = list(ml_products_dict)
        sku_list = ','.join(magento_sku_list)
        search_criteria = 'searchCriteria[filterGroups][0][filters][0][field]=sku&searchCriteria[filterGroups]' \
                          '[0][filters][0][condition_type]=in&searchCriteria[filterGroups][0][filters][0][value]=%s' % \
                          sku_list
        try:
            api_url = '/V1/products?%s' % search_criteria
            response = req(magento_instance, api_url)
        except Exception:
            for prod in magento_sku_list:
                text = "Error while requesting product from Magento.\n"
                ml_products_dict[prod]['log_message'] += text
            return []

        if response.get('items'):
            return response.get('items')
        else:
            return []

    def create_bulk_of_new_conf_products_in_magento(self, magento_instance, new_conf_products, ml_conf_products,
                                                    attr_sets):
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
            for k in new_conf_products.keys():
                ml_conf_products[k]['export_date_to_magento'] = datetime.now()

    def create_single_conf_product_in_magento(self, magento_instance, new_conf_product, ml_conf_products, attr_sets):
        """
        Export(POST) to Magento new Configurable Product
        :param magento_instance: Instance of Magento
        :param new_conf_product: New Configurable Product to be exported
        :param ml_conf_products: Dictionary contains metadata for selected Configurable Products (Odoo categories)
        :param attr_sets: Attribute set dictionary with unique data for selected products
        :return: Magento Product or empty dict
        """
        if not new_conf_product:
            return {}
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
            return response

        return {}

    def create_new_bulk_of_simple_products_in_magento(self, magento_instance, odoo_products, new_simple_prod,
                                                      ml_simp_products, attr_sets):
        """
        Export(POST) to Magento new Simple Products in bulk (asynchronously)
        :param magento_instance: Instance of Magento
        :param odoo_products: Odoo Product objects
        :param new_simple_prod: List of new Simple Products to be exported
        :param ml_simp_products: Dictionary contains metadata for selected Simple Products (Odoo products)
        :param attr_sets: Attribute set dictionary with unique data for selected products
        :return: None
        """
        data = []
        prod_media = {}
        new_products_sku = new_simple_prod.keys()

        for prod in odoo_products:
            # map Odoo product attributes as in Magento
            if prod.magento_sku in new_products_sku:
                custom_attributes = self.map_product_attributes_from_magento(
                    prod.odoo_product_id.product_template_attribute_value_ids.product_attribute_value_id,
                    attr_sets[prod.odoo_product_id.categ_id.magento_attr_set]['attributes']
                )
                attr_set_id = attr_sets[prod.odoo_product_id.categ_id.magento_attr_set]['id']
                data.append({
                    "product": {
                        "sku": prod.magento_sku,
                        "name": prod.magento_product_name,  # update to x_magento_name
                        "attribute_set_id": attr_set_id,
                        "price": prod.lst_price,
                        "status": 1,  # Enabled
                        "visibility": 4,  # Catalog, Search
                        "type_id": "simple",
                        "weight": prod.odoo_product_id.weight,
                        "extension_attributes": {
                            "stock_item": {
                                "qty": prod.qty_available,
                                "is_in_stock": "true"
                            }
                        },
                        "custom_attributes": custom_attributes
                    }
                })

                # update product_media dict if product has images
                if len(prod.odoo_product_id.product_template_image_ids):
                    prod_media.update({prod.magento_sku: prod.odoo_product_id.product_template_image_ids})

        if data:
            try:
                api_url = '/async/bulk/V1/products'
                response = req(magento_instance, api_url, 'POST', data)
            except Exception:
                text = "Error while async new Simple Products creation in Magento.\n"
                for prod in odoo_products:
                    if prod.magento_sku in new_products_sku:
                        ml_simp_products[prod.magento_sku]['log_message'] += text
                return

            if not response.get('errors'):
                for prod in odoo_products:
                    if prod.magento_sku in new_products_sku:
                        ml_simp_products[prod.magento_sku]['export_date_to_magento'] = datetime.now()
                        ml_simp_products[prod.magento_sku]['magento_status'] = 'in_process'

                if prod_media:
                    self.export_bulk_media_to_magento(magento_instance, prod_media, ml_simp_products)

    def create_new_simple_product_in_magento(self, magento_instance, odoo_product, new_simple_prod, ml_simp_products,
                                             attr_sets):
        """
        Export(POST) to Magento new Simple Product
        :param magento_instance: Instance of Magento
        :param odoo_product: Odoo Product objects
        :param new_simple_prod: New Simple Product to be exported
        :param ml_simp_products: Dictionary contains metadata for selected Simple Products (Odoo products)
        :param attr_sets: Attribute set dictionary with unique data for selected products
        :return: {} or Created Product
        """
        if not odoo_product or odoo_product.magento_sku not in new_simple_prod:
            return {}
        data = {}
        prod_media = {}

        # map Odoo product attributes as in Magento
        custom_attributes = self.map_product_attributes_from_magento(
            odoo_product.odoo_product_id.product_template_attribute_value_ids.product_attribute_value_id,
            attr_sets[odoo_product.odoo_product_id.categ_id.magento_attr_set]['attributes']
        )
        attr_set_id = attr_sets[odoo_product.odoo_product_id.categ_id.magento_attr_set]['id']
        data.update({
            "product": {
                "sku": odoo_product.magento_sku,
                "name": odoo_product.magento_product_name,  # update to x_magento_name
                "attribute_set_id": attr_set_id,
                "price": odoo_product.lst_price,
                "status": 1,  # Enabled
                "visibility": 4,  # Catalog, Search
                "type_id": "simple",
                "weight": odoo_product.odoo_product_id.weight,
                "extension_attributes": {
                    "stock_item": {
                        "qty": odoo_product.qty_available,
                        "is_in_stock": "true"
                    }
                },
                "custom_attributes": custom_attributes
            }
        })

        # update product_media dict if product has images
        if len(odoo_product.odoo_product_id.product_template_image_ids):
            prod_media.update({odoo_product.magento_sku: odoo_product.odoo_product_id.product_template_image_ids})

        try:
            api_url = '/V1/products'
            response = req(magento_instance, api_url, 'POST', data)
        except Exception:
            text = "Error while new Simple Product creation in Magento.\n"
            ml_simp_products[odoo_product.magento_sku]['log_message'] += text
            return {}

        if response.get('sku'):
            ml_simp_products[odoo_product.magento_sku]['export_date_to_magento'] = response.get("updated_at")
            ml_simp_products[odoo_product.magento_sku]['magento_status'] = 'need_to_link'
            if prod_media:
                self.export_media_to_magento(magento_instance, prod_media, ml_simp_products)
            return response
        return {}

    def export_bulk_media_to_magento(self, magento_instance, products_media, ml_simp_products):
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

    def export_media_to_magento(self, magento_instance, products_media, ml_simp_products):
        """
        Export(POST) to Magento Product's Images
        :param magento_instance: Instance of Magento
        :param products_media: Dictionary with Product Images added in Odoo
        :param ml_simp_products: Dictionary contains metadata for selected Simple Products (Odoo products)
        :return: None
        """
        images = {}
        prod_sku = list(products_media.keys())[0]
        for img in products_media[prod_sku]:
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
                text = "Error while Simple Product Images export to Magento.\n"
                ml_simp_products[prod_sku]['log_message'] += text

    def assign_attr_to_config_products_in_bulk(self, magento_instance, odoo_products, new_simple_products,
                                               config_prod_assigned_attr, ml_simp_products, available_attributes):
        """
        Assigns Attributes to Configurable Products in bulk (asynchronously)
        :param magento_instance: Instance of Magento
        :param odoo_products: Odoo Product objects
        :param new_simple_products: List of new Simple Products to be exported
        :param config_prod_assigned_attr: Configurable Product Assigned Attributes
        :param ml_simp_products: Dictionary contains metadata for selected Simple Products (Odoo products)
        :param available_attributes: Dictionary with defined Attributes and their values in Magento
        :return: None
        """
        data = []
        new_products_sku = new_simple_products.keys()

        # assign new options to config.product with relevant info from Magento
        for simple_prod in odoo_products:
            if ml_simp_products[simple_prod.magento_sku]['log_message']:
                continue
            if simple_prod.magento_sku in new_products_sku:
                simp_prod_attrs = simple_prod.odoo_product_id.product_template_attribute_value_ids.product_attribute_value_id
                for attr_val in simp_prod_attrs:
                    attr_name = attr_val.attribute_id.name
                    categ_name = simple_prod.odoo_product_id.categ_id.name
                    mag_attr_set = simple_prod.odoo_product_id.categ_id.magento_attr_set
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
                req(magento_instance, api_url, 'POST', data)
            except Exception:
                text = "Error while async assign product attributes to Config.Product in Magento.\n"
                for prod in odoo_products:
                    if prod.magento_sku in new_products_sku:
                        ml_simp_products[prod.magento_sku]['log_message'] += text

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
                    "sku": simple_prod.odoo_product_id.categ_id.name
                })

        if data:
            try:
                api_url = '/async/bulk/V1/configurable-products/bySku/child'
                req(magento_instance, api_url, 'POST', data)
            except Exception:
                text = "Error while async linking Simple to Configurable Product in Magento. Possible reason: \n"
                for prod in odoo_products:
                    if prod.magento_sku in new_simple_products:
                        ml_simp_products[prod.magento_sku]['log_message'] += text

    def unlink_simple_and_config_prod(self, magento_instance, simp_prod_sku, conf_prod_sku):
        """
        Unlink Simple and Configurable Products in Magento
        :param magento_instance: Instance of Magento
        :param simp_prod_sku: Sku of simple product
        :param conf_prod_sku: Sku of configurable product
        :return: None
        """
        try:
            api_url = '/V1/configurable-products/%s/children/%s' % (conf_prod_sku, simp_prod_sku)
            req(magento_instance, api_url, 'DELETE')
        except Exception:
            return

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
                opt_dict.update({
                    self.to_upper(attr_opt.get('label')): self.to_upper(attr_opt.get('value'))
                })
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
            if attrs.attribute_id.name in [a.name for a in odoo_product.odoo_product_id.categ_id.magento_assigned_attr]:
                attr_dict.update({
                    self.to_upper(attrs.attribute_id.name): self.to_upper(attrs.name)
                })
        return attr_dict

    def update_conf_product_dict_with_magento_data(self, magento_prod, ml_conf_products_dict):
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
        ml_simp_products_dict[magento_prod.get("sku")].update({
            'magento_type_id': magento_prod.get('type_id'),
            'magento_prod_id': magento_prod.get("id"),
            'magento_update_date': magento_prod.get("updated_at")
        })

    def save_magento_data_to_database(self, instance_id, ml_simp_products, ml_conf_products):
        """
        Save Products' export_dates, log_messages and magento_statuses to database
        :param instance_id: ID of Magento Instance
        :param ml_simp_products: Dictionary contains metadata for selected Simple Products (Odoo products)
        :param ml_conf_products: Dictionary contains metadata for selected Configurable Products (Odoo categories)
        :return: None
        """
        for s in ml_simp_products:
            magento_product = self.env['magento.product.product'].search([
                ('magento_sku', '=', s), ('magento_instance_id', '=', instance_id)
            ])
            if ml_simp_products[s]['log_message']:
                ml_simp_products[s]['magento_status'] = 'log_error'
            magento_product.write({
                'magento_status': ml_simp_products[s]['magento_status']
            })

            if ml_simp_products[s]['to_export'] or ml_simp_products[s]['log_message']:
                categ_name = ml_simp_products[s]['category_name']
                magento_product.write({
                    'magento_export_date': ml_simp_products[s]['export_date_to_magento'],
                    'magento_export_date_conf': ml_conf_products[categ_name]['export_date_to_magento'],
                    'magento_log_message': ml_simp_products[s]['log_message'],
                    'magento_log_message_conf': ml_conf_products[categ_name]['log_message']
                })

    def create_conf_products_dict(self, instance_id, export_products):
        products_dict = {}
        products_dict.update({
            c.odoo_product_id.categ_id.name: {
                'attribute_set': c.odoo_product_id.categ_id.magento_attr_set,
                'config_attr': [a.name for a in c.odoo_product_id.categ_id.magento_assigned_attr],
                'children': [],
                'log_message': '',
                'export_date_to_magento': c.magento_export_date_conf,
                'latest_update_date': c.odoo_product_id.categ_id.write_date,
                'to_export': True
            } for c in export_products if instance_id == c.magento_instance_id.id
        })
        return products_dict

    def create_simple_products_dict(self, instance_id, export_products):
        products_dict = {}
        products_dict.update({
            s.magento_sku: {
                'category_name': s.odoo_product_id.categ_id.name,
                'log_message': '',
                'export_date_to_magento': s.magento_export_date,
                'latest_update_date': s.odoo_product_id.write_date,
                'conf_attributes': self.get_product_conf_attributes_dict(s),
                'magento_status': s.magento_status,
                'to_export': True
            } for s in export_products if instance_id == s.magento_instance_id.id
        })
        return products_dict

    def create_attribute_sets_dict(self, magento_instance, ml_conf_products_dict):
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