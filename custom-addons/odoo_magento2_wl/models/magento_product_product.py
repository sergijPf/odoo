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
    magento_export_date = fields.Datetime(string="Last Export Date to Magento", copy=False)
    magento_export_date_conf = fields.Datetime(string="Configurable Product last Export Date to Magento", copy=False)
    magento_log_message = fields.Char(string="Error Messages while Export to Magento")
    magento_log_message_conf = fields.Char(string="Conf.Product Error Messages while Export to Magento")

    def process_products_export_to_magento(self):
        """
        The main method to process Products Export to Magento. The Product's Categories are treated as Configurable
        Products and regular Odoo Products as Simple Products in Magento.
        """
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
        ml_conf_products_dict = {}
        ml_simp_products_dict = {}
        attr_sets = {}

        for mi in {i.magento_instance_id: {} for i in export_products}:
            # create dict which collects meta-data for unique selected configurable/simple products
            ml_conf_products_dict.update({
                c.odoo_product_id.categ_id.name: {
                    'attribute_set': c.odoo_product_id.categ_id.magento_attr_set,
                    'config_attr': [a.name for a in c.odoo_product_id.categ_id.magento_assigned_attr],
                    'children': [],
                    'log_message': '',
                    'export_date_to_magento': c.magento_export_date_conf,
                    'latest_update_date': c.odoo_product_id.categ_id.write_date,
                    'magento_update_date': '',
                    'to_export': True
                } for c in export_products if mi.id == c.magento_instance_id.id
            })
            ml_simp_products_dict.update({
                s.magento_sku: {
                    'category_name': s.odoo_product_id.categ_id.name,
                    'log_message': '',
                    'export_date_to_magento': s.magento_export_date,
                    'latest_update_date': s.write_date
                    if s.write_date > s.odoo_product_id.write_date else s.odoo_product_id.write_date,
                    'conf_attributes': self.get_product_conf_attributes_dict(s),
                    'magento_update_date': '',
                    'link_only': False,
                    'to_export': True
                } for s in export_products if mi.id == s.magento_instance_id.id
            })

            # get selected products from Magento if any
            magento_conf_products = self.get_products_from_magento(mi, ml_conf_products_dict)
            magento_simp_products = self.get_products_from_magento(mi, ml_simp_products_dict)

            # update conf/simp dictionaries with Magento data
            for prod in magento_conf_products:
                prod_sku = prod.get("sku")
                ml_conf_products_dict[prod_sku].update({
                    'magento_type_id': prod.get('type_id'),
                    'magento_attr_set_id': prod.get("attribute_set_id"),
                    'magento_conf_prod_options': prod.get("extension_attributes").get("configurable_product_options"),
                    'children': prod.get("extension_attributes").get("configurable_product_links"),
                    'magento_configurable_product_link_data': self.convert_to_dict(prod.get("extension_attributes").get(
                        "configurable_product_link_data")),
                    'magento_update_date': prod.get("updated_at")
                })
            for prod in magento_simp_products:
                ml_simp_products_dict[prod.get("sku")].update({
                    'magento_type_id': prod.get('type_id'),
                    'magento_prod_id': prod.get("id"),
                    'magento_update_date': prod.get("updated_at")
                })

            del magento_conf_products
            del magento_simp_products

            # create unique attribute-sets and get their id/attribute(options) data from Magento
            attr_sets.update({
                ml_conf_products_dict[s]['attribute_set']: {} for s in
                ml_conf_products_dict.keys() if ml_conf_products_dict[s]['attribute_set']
            })
            for a_set in attr_sets:
                attr_sets[a_set].update({
                    'id': self.get_attribute_set_id_by_name(mi, a_set, ml_conf_products_dict)
                })
                attr_sets[a_set].update({
                    'attributes': self.get_available_attributes_from_magento(mi, a_set, ml_conf_products_dict,
                                                                             attr_sets)
                })

            # check and update 'to_export' field of ml_dict for products which don't need to be exported
            self.check_config_products_to_export(ml_conf_products_dict, attr_sets)
            self.check_simple_products_to_export(ml_simp_products_dict, ml_conf_products_dict)

            # filter selected Odoo Products and their Configurable Products to be exported to Magento
            ml_list_of_conf_prod = list({
                c.odoo_product_id.categ_id for c in export_products
                if mi.id == c.magento_instance_id.id and ml_conf_products_dict[c.odoo_product_id.categ_id.name][
                    'to_export'] and not ml_conf_products_dict[c.odoo_product_id.categ_id.name]['log_message']
            })
            ml_list_of_simp_prod = export_products.filtered(
                lambda prod: prod.magento_instance_id.id == mi.id and
                             ml_simp_products_dict[prod.magento_sku]['to_export'] and
                             not ml_simp_products_dict[prod.magento_sku]['log_message']
            )

            # if there are some config.products to export
            for prod in ml_list_of_conf_prod:
                if ml_conf_products_dict[prod.name]['log_message']:
                    continue
                # check if attribute_set_id and assign_attributes assigned to configurable product
                prod_attr_set_id = attr_sets[prod.magento_attr_set]['id']
                prod_conf_attr = ml_conf_products_dict[prod.name]['config_attr']
                if prod_attr_set_id and prod_conf_attr:
                    # check if configurable attributes of all selected products exist in Magento
                    # logs error when attribute doesn't exist in Magento
                    available_attributes = [str(a['default_label']).strip().upper() for a in
                                            attr_sets[prod.magento_attr_set]['attributes']]
                    conf_prod_attr = [str(c).strip().upper() for c in prod_conf_attr if c]
                    if not self.check_product_attr_is_in_attributes_list(available_attributes, conf_prod_attr):
                        text = "Some of configurable attributes of %s Product doesn't exist in Magento. " \
                               "Attribute has to be created at first on Magento side.\n" % prod.name
                        ml_conf_products_dict[prod.name]['log_message'] += text

                    # check & update (PUT) every single conf.product if it exists in Magento and there are no errors
                    if ml_conf_products_dict[prod.name]['magento_update_date']:
                        if ml_conf_products_dict[prod.name]['magento_type_id'] == 'configurable':
                            # check if assign attributes are the same in Magento and Odoo
                            mag_attr_options = ml_conf_products_dict[prod.name]['magento_conf_prod_options']
                            check_assign_attr = self.check_config_product_assign_attributes(
                                mag_attr_options,
                                attr_sets[prod.magento_attr_set]['attributes'],
                                prod_conf_attr
                            )
                            conf_prod = self.update_single_conf_product_in_magento(
                                mi,
                                prod.name,
                                prod_attr_set_id,
                                ml_conf_products_dict,
                                check_assign_attr
                            )
                            # update magento data in ml_conf_products_dict,
                            # later will be used while linking with simple prod
                            if conf_prod:
                                attr_opt = conf_prod.get("extension_attributes").get("configurable_product_options")
                                children = conf_prod.get("extension_attributes").get("configurable_product_links")
                                link_data = conf_prod.get("extension_attributes").get("configurable_product_link_data")
                                ml_conf_products_dict[prod.name].update({
                                    'magento_attr_set_id': conf_prod.get("attribute_set_id"),
                                    'magento_conf_prod_options': attr_opt,
                                    'children': children,
                                    'magento_configurable_product_link_data': self.convert_to_dict(link_data),
                                    'magento_update_date': conf_prod.get("updated_at")
                                })
                        else:
                            ml_conf_products_dict[prod.name]['log_message'] += \
                                "Product with the following sku - \"%s\" already exists in Magento. " \
                                "And it's type is not Configurable.\n" % prod.name
                else:
                    if not prod_attr_set_id:
                        text = "Missed Magento Product Attribute Set for %s configurable product.\n" % prod.name
                        ml_conf_products_dict[prod.name]['log_message'] += text

                    if not prod_conf_attr:
                        text = "Missed Configurable Attribute(s) for %s configurable product.\n" % prod.name
                        ml_conf_products_dict[prod.name]['log_message'] += text

            # create (POST) a bulk of new configurable products to be exported to Magento
            new_conf_prod = {k: v for k, v in ml_conf_products_dict.items() if
                             not ml_conf_products_dict[k]['magento_update_date'] and not
                             ml_conf_products_dict[k]['log_message']
                             }
            if new_conf_prod:
                self.create_bulk_of_new_conf_products_in_magento(mi, new_conf_prod, ml_conf_products_dict, attr_sets)

            # check if product attributes of all selected simple products exist in Magento
            # logs error when product has no attributes and when needed - creates new attribute options(swatch)
            self.check_product_attributes_exist_in_magento(mi, ml_list_of_simp_prod, attr_sets, ml_simp_products_dict)

            for prod in ml_list_of_simp_prod:
                # check if any log_messages for current product or it's configurable
                if ml_simp_products_dict[prod.magento_sku]['log_message']:
                    continue
                elif ml_conf_products_dict[prod.odoo_product_id.categ_id.name]['log_message']:
                    text = "Configurable product for the current simple product is not ok. Please check it first.\n"
                    ml_simp_products_dict[prod.magento_sku]['log_message'] += text
                    continue

                # check if product has assign attributes defined in it's configurable product
                simp_prod_attr = prod.odoo_product_id.product_template_attribute_value_ids.product_attribute_value_id
                check_assign_attr = self.check_product_attr_is_in_attributes_list(
                    [a.attribute_id.name for a in simp_prod_attr],
                    ml_conf_products_dict[prod.odoo_product_id.categ_id.name]['config_attr']
                )
                if not check_assign_attr:
                    text = 'Simple product - %s is missing attribute(s) defined as configurable in Product Category ' \
                           'table.\n' % prod.magento_sku
                    ml_simp_products_dict[prod.magento_sku]['log_message'] += text
                    continue

                prod_attr_set = prod.odoo_product_id.categ_id.magento_attr_set
                available_attributes = attr_sets[prod_attr_set]['attributes']

                # check if configurable product already contains such set of "Attribute: Value" pair
                # if not False - will be unable to link it further
                check_attr_values = self.check_products_set_of_attribute_values(
                    ml_conf_products_dict,
                    prod.odoo_product_id.categ_id.name,
                    simp_prod_attr,
                    available_attributes,
                    ml_simp_products_dict,
                    prod.magento_sku
                )
                if check_attr_values:
                    text = "The same configurable Set of Attribute Values was found in Product - %s.\n" % check_attr_values
                    ml_simp_products_dict[prod.magento_sku]['log_message'] += text
                    continue

                # the code below relates only to Simple Products to be updated in Magento
                if ml_simp_products_dict[prod.magento_sku]['magento_update_date']:
                    if not ml_conf_products_dict[prod.odoo_product_id.categ_id.name]['magento_update_date']:
                        # log warning that newly created config.products via async-bulk request possibly are not created
                        # in Magento yet (at the moment of further code execution)
                        text = "The Configurable Product - %s related to current product is not in Magento yet. " \
                               "And they cannot be linked so far.\n" % prod.odoo_product_id.categ_id.name
                        ml_simp_products_dict[prod.magento_sku]['log_message'] += text
                        continue

                    if ml_simp_products_dict[prod.magento_sku]['magento_type_id'] == 'simple':
                        # to skip this step if only linking with parent needs to be done
                        if not ml_simp_products_dict[prod.magento_sku]['link_only']:
                            self.update_single_simple_product_in_magento(
                                mi,
                                prod,
                                available_attributes,
                                attr_sets[prod_attr_set]['id'],
                                ml_simp_products_dict
                            )
                            if ml_simp_products_dict[prod.magento_sku]['log_message']:
                                continue
                    else:
                        text = "The Product with such sku is already created in Magento. " \
                               "(And it's type isn't Simple Product.)\n"
                        ml_simp_products_dict[prod.magento_sku]['log_message'] += text
                        continue

                    self.assign_attr_to_config_product(
                        mi,
                        prod,
                        available_attributes,
                        ml_conf_products_dict,
                        ml_simp_products_dict
                    )
                    if not ml_conf_products_dict[prod.odoo_product_id.categ_id.name]['log_message']:
                        self.link_simple_to_config_product_in_magento(
                            mi,
                            prod,
                            ml_conf_products_dict[prod.odoo_product_id.categ_id.name]['children'],
                            ml_simp_products_dict
                        )

                    # check if simple product assigned to any other of selected config.product than current one and unlink it
                    for conf_prod in ml_conf_products_dict:
                        prod_id = ml_simp_products_dict[prod.magento_sku]['magento_prod_id']
                        if conf_prod != prod.odoo_product_id.categ_id.name and prod_id in \
                                ml_conf_products_dict[conf_prod]['children']:
                            self.unlink_simple_and_config_prod(mi, prod.magento_sku, conf_prod)

            # process mass upload of simple products to Magento, assign attributes to config.products and link them
            new_simple_prod = {}
            for s in ml_simp_products_dict:
                if not ml_simp_products_dict[s]['magento_update_date'] and not ml_simp_products_dict[s]['log_message']:
                    new_simple_prod.update({s: ml_simp_products_dict[s]})
            if new_simple_prod:
                self.create_new_bulk_of_simple_products_in_magento(
                    mi,
                    ml_list_of_simp_prod,
                    new_simple_prod,
                    ml_simp_products_dict,
                    attr_sets
                )
                self.assign_attr_to_config_products_in_bulk(
                    mi,
                    ml_list_of_simp_prod,
                    new_simple_prod,
                    ml_conf_products_dict,
                    ml_simp_products_dict,
                    attr_sets
                )
                self.link_simple_to_config_products_in_bulk(
                    mi,
                    ml_list_of_simp_prod,
                    new_simple_prod,
                    ml_simp_products_dict
                )

            # save data with export dates and log_messages to Db
            for s in ml_simp_products_dict:
                magento_product = self.env['magento.product.product'].search([
                    ('magento_sku', '=', s), ('magento_instance_id', '=', mi.id)
                ])
                if ml_simp_products_dict[s]['to_export'] or ml_simp_products_dict[s]['log_message']:
                    categ_name = ml_simp_products_dict[s]['category_name']
                    magento_product.write({
                        'magento_export_date': ml_simp_products_dict[s]['export_date_to_magento'],
                        'magento_export_date_conf': ml_conf_products_dict[categ_name]['export_date_to_magento'],
                        'magento_log_message': ml_simp_products_dict[s]['log_message'],
                        'magento_log_message_conf': ml_conf_products_dict[categ_name]['log_message']
                    })

            {print({k: v}) for k, v in ml_conf_products_dict.items() if ml_conf_products_dict[k]['log_message']}
            {print({k: v}) for k, v in ml_simp_products_dict.items() if ml_simp_products_dict[k]['log_message']}

        return {
            'effect': {
                'fadeout': 'slow',
                'message': "'Export to Magento' Process Completed Successfully!",
                'img_url': '/web/static/src/img/smile.svg',
                'type': 'rainbow_man',
            }
        }

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
            exp_date_c = ml_conf_products_dict[prod]['export_date_to_magento']
            exp_date_c = datetime.strftime(exp_date_c, MAGENTO_DATETIME_FORMAT) if exp_date_c else ''

            upd_date_c = ml_conf_products_dict[prod]['latest_update_date']
            upd_date_c = datetime.strftime(upd_date_c, MAGENTO_DATETIME_FORMAT) if upd_date_c else ''

            mag_date_c = ml_conf_products_dict[prod]['magento_update_date']
            mag_date_c = mag_date_c if mag_date_c else ''

            if exp_date_c:
                if exp_date_c > upd_date_c:
                    if mag_date_c > exp_date_c:
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

    def check_simple_products_to_export(self, ml_simp_products_dict, ml_conf_products_dict):
        """
        Check if Simple Product Export to Magento needed
        :param ml_simp_products_dict: Dictionary contains metadata for selected Simple Products (Odoo products)
        :param ml_conf_products_dict: Dictionary contains metadata for selected Configurable Products (Odoo categories)
        :return: None
        """
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
            exp_date_s = ml_simp_products_dict[prod]['export_date_to_magento']
            exp_date_s = datetime.strftime(exp_date_s, MAGENTO_DATETIME_FORMAT) if exp_date_s else ''

            upd_date_s = ml_simp_products_dict[prod]['latest_update_date']
            upd_date_s = datetime.strftime(upd_date_s, MAGENTO_DATETIME_FORMAT) if upd_date_s else ''

            upd_date_c = ml_conf_products_dict[categ_name]['latest_update_date']
            upd_date_c = datetime.strftime(upd_date_c, MAGENTO_DATETIME_FORMAT) if upd_date_s else ''

            mag_date_s = ml_simp_products_dict[prod]['magento_update_date']
            mag_date_s = mag_date_s if mag_date_s else ''

            if exp_date_s:
                if exp_date_s > upd_date_s and exp_date_s > upd_date_c:
                    if mag_date_s > exp_date_s:
                        if ml_simp_products_dict[prod]['magento_prod_id'] in \
                                ml_conf_products_dict[categ_name]['children']:
                            ml_simp_products_dict[prod]['to_export'] = False
                        else:
                            ml_simp_products_dict[prod]['link_only'] = True

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

        ml_conf_products[magento_sku]['export_date_to_magento'] = datetime.now()
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

        # get store_views in order to create new product attribute options(swatches) if none
        magento_storeviews = self.get_storeviews_from_magento(magento_instance) or []

        for prod in odoo_products:
            prod_attr = prod.odoo_product_id.product_template_attribute_value_ids.product_attribute_value_id
            if not len(prod_attr):
                text = "Product - %s has no attributes.\n" % prod.magento_sku
                ml_product_dict[prod.magento_sku]['log_message'] += text
                continue

            prod_attr_set = prod.odoo_product_id.categ_id.magento_attr_set
            avail_attr_list = available_attributes[prod_attr_set]['attributes']
            # logs if any of attributes are missed in Magento and creates new attr.option in Magento
            for attr in prod_attr:
                attr_name = attr.attribute_id.name.strip().upper()
                at = next(
                    (a for a in avail_attr_list if a and attr_name == str(a.get('default_label')).strip().upper()), {})
                if not at:
                    text = "Attribute - %s has to be created at first on Magento side.\n" % attr.attribute_id.name
                    ml_product_dict[prod.magento_sku]['log_message'] += text
                else:
                    if attr.name.strip().upper() not in [i.get('label').strip().upper() for i in at['options']]:
                        id, err = self.create_new_attribute_option_in_magento(
                            magento_instance,
                            at['attribute_code'],
                            attr.name,
                            magento_storeviews
                        )
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

    def create_new_attribute_option_in_magento(self, magento_instance, attribute_code, attribute_option,
                                               magento_storeviews):
        """
        Creates new option(swatch) for defined attribute in Magento
        :param magento_instance: Instance of Magento
        :param attribute_code: The Code of Attribute defined in Magento
        :param attribute_option: Dictionary with defined Attributes and their values in Magento
        :param magento_storeviews: The StoreViews the created option will be applied to
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

        # get store_views from Magento to update store_labels field, if error - store_label remains [] (admin only)
        if magento_storeviews:
            store_labels = []
            for view in magento_storeviews:
                store_labels.append({"store_id": view.get('id'), "label": str(attribute_option).upper()})
            data['option'].update({"store_labels": store_labels})

        # create new attribute option(swatch)
        try:
            api_url = '/V1/products/attributes/%s/options' % attribute_code
            res = req(magento_instance, api_url, 'POST', data)
        except Exception:
            return 0, "Error while new Product Attribute Option(Swatch) creation in Magento.\n"
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
        :return: None
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
            api_url = '/V1/products/%s' % product.magento_sku
            response = req(magento_instance, api_url, 'PUT', data)
        except Exception:
            text = "Error while Simple Product update in Magento.\n"
            ml_simp_products[product.magento_sku]['log_message'] += text
            return

        if response.get("sku"):
            ml_simp_products[product.magento_sku]['export_date_to_magento'] = datetime.now()

        # export product images to Magento
        if response.get("sku") and len(product.odoo_product_id.product_template_image_ids):
            prod_media = {product.magento_sku: product.odoo_product_id.product_template_image_ids}
            self.export_bulk_media_to_magento(magento_instance, prod_media, ml_simp_products)

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
                if attr_val.attribute_id.name.strip().upper() == str(attr['default_label']).strip().upper():
                    for o in attr['options']:
                        if attr_val.name.strip().upper() == str(o['label']).strip().upper():
                            custom_attributes.append(
                                {
                                    "attribute_code": attr['attribute_code'],
                                    "value": o['value']
                                }
                            )

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
            prod_attr_odoo = {attr.strip().upper() for attr in config_prod_assigned_attr if attr}
            if prod_attr_odoo != prod_attr_magento:
                # unlink updated attributes in Magento
                conf_prod_assign_attr_adj = [o.upper().strip() for o in config_prod_assigned_attr if o]
                for opt in attr_options:
                    if opt.get("label").upper().strip() not in conf_prod_assign_attr_adj:
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
                if prod_attr_name.strip().upper() not in prod_attr_magento:
                    # valid for new "assign" attributes for config.product to be created in Magento
                    for attr in available_attributes:
                        if prod_attr_name.strip().upper() == str(attr['default_label']).strip().upper():
                            for o in attr['options']:
                                if attr_val.name.strip().upper() == str(o['label']).strip().upper():
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
        prod_attr_odoo = {attr.strip().upper() for attr in conf_prod_assigned_attr if attr}
        if prod_attr_odoo == prod_attr_magento:
            return True
        return False

    def link_simple_to_config_product_in_magento(self, magento_instance, product, config_product_children,
                                                 ml_simp_products):
        """
        Links simple product to configurable product in Magento
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
            return

        # if not linked
        data = {
            "childSku": simple_product_sku
        }

        try:
            api_url = '/V1/configurable-products/%s/child' % config_product_sku
            req(magento_instance, api_url, 'POST', data)
        except Exception:
            text = "Error while linking %s to %s Configurable Product in Magento. Possible reason:\n " \
                   "1. Config.product already contains such attribute-set values" % (
                       simple_product_sku, config_product_sku)
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
            attr_name = ml_conf_products_dict[prod]['attribute_set']
            if attr_name == attribute_set_name:
                text = "Error while getting attributes for - %s attribute set from Magento.\n" % attr_name
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
        filter = {
            'attribute_set_name': attribute_set_name,
            'entity_type_id': magento_entity_id
        }
        search_criteria = create_search_criteria(filter)
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
                return str(attr.get('default_label')).strip().upper()

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
                          '[0][filters][0][condition_type]=in&searchCriteria[filterGroups][0][filters][0][value]=%s' % sku_list
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

    def get_storeviews_from_magento(self, magento_instance):
        """
        Get StoreViews from Magento, if error - [] (admin only)
        :param magento_instance: Instance of Magento
        :return: List of StoreViews
        """
        try:
            api_url = '/V1/store/storeViews'
            response = req(magento_instance, api_url)
        except Exception:
            response = []
        return response

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

                if len(prod.odoo_product_id.product_template_image_ids):
                    prod_media.update({prod.magento_sku: prod.odoo_product_id.product_template_image_ids})

        try:
            api_url = '/async/bulk/V1/products'
            response = req(magento_instance, api_url, 'POST', data)
        except Exception:
            text = "Error while async new Simple Products creation in Magento.\n"
            for prod in odoo_products:
                ml_simp_products[prod.magento_sku]['log_message'] += text
            return

        if not response.get('errors'):
            for prod in odoo_products:
                ml_simp_products[prod.magento_sku]['export_date_to_magento'] = datetime.now()

        if not response.get('errors') and prod_media:
            self.export_bulk_media_to_magento(magento_instance, prod_media, ml_simp_products)

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
                attachment = self.env['ir.attachment'].sudo().search([('res_field', '=', 'image_256'),
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
                    if attr_val.attribute_id.name in \
                            config_prod_assigned_attr.get(simple_prod.odoo_product_id.categ_id.name)['config_attr']:
                        mag_avail_attrs = \
                            available_attributes.get(simple_prod.odoo_product_id.categ_id.magento_attr_set)[
                                'attributes']
                        for attr in mag_avail_attrs:
                            if attr_val.attribute_id.name.strip().upper() == str(attr['default_label']).strip().upper():
                                for o in attr['options']:
                                    if attr_val.name.strip().upper() == str(o['label']).strip().upper():
                                        data.append({
                                            'option': {
                                                "attribute_id": attr["attribute_id"],
                                                "label": attr["default_label"],
                                                # "position": 0,
                                                "is_use_default": "false",
                                                "values": [{"value_index": o["value"]}]
                                            },
                                            'sku': simple_prod.odoo_product_id.categ_id.name
                                        })

        try:
            api_url = '/async/bulk/V1/configurable-products/bySku/options'
            req(magento_instance, api_url, 'POST', data)
        except Exception:
            text = "Error while async assign product attributes to Config.Product in Magento.\n"
            for prod in odoo_products:
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

        try:
            api_url = '/async/bulk/V1/configurable-products/bySku/child'
            req(magento_instance, api_url, 'POST', data)
        except Exception:
            text = "Error while async linking Simple to Configurable Product in Magento. Possible reason: \n" \
                   "1. Config.product already contains such attribute-set values.\n"
            for prod in odoo_products:
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
        # create dict of simple product attributes: value for config.attributes only
        for prod_attr in simp_prod_attr:
            prod_attr_name = prod_attr.attribute_id.name
            if prod_attr_name in conf_prod_attributes:
                for avail_attr in available_attributes:
                    if avail_attr.get('default_label') and \
                            str(avail_attr.get('default_label').strip().upper()) == str(prod_attr_name).strip().upper():
                        for opt in avail_attr.get('options'):
                            if opt.get('label') and \
                                    str(opt.get('label')).strip().upper() == str(prod_attr.name).strip().upper():
                                simp_attr_val.update({
                                    str(avail_attr.get('default_label')).strip().upper(): str(
                                        opt.get('label')).strip().upper()
                                })
                                break

        # check if simple product's "attribute: value" is already linked to configurable product in Magento
        for prod in magento_conf_prod_links:
            if magento_conf_prod_links[prod] == simp_attr_val and prod != magento_sku:
                return prod

        # check if simple product's "attribute: value" is within exported products
        for prod in ml_simple_prod:
            if ml_simple_prod[prod]['category_name'] == categ_name and \
                    ml_simple_prod[prod]['conf_attributes'] == simp_attr_val and prod != magento_sku:
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
                opt_dict.update(
                    {str(attr_opt.get('label')).strip().upper(): str(attr_opt.get('value')).strip().upper()})
            link_data_dict.update({new_dict['simple_product_sku']: opt_dict})

        return link_data_dict

    def get_product_conf_attributes_dict(self, odoo_product):
        """
        Extract each Product's "Attribute: Value" pair (only configurable) to one single dict
        :param odoo_product: Odoo Product object
        :return: Dictionary with Product's "Attribute: Value" data
        """
        attr_dict = {}
        for attrs in odoo_product.odoo_product_id.product_template_attribute_value_ids.product_attribute_value_id:
            if attrs.attribute_id.name in [a.name for a in odoo_product.odoo_product_id.categ_id.magento_assigned_attr]:
                attr_dict.update({
                    str(attrs.attribute_id.name).strip().upper(): str(attrs.name).strip().upper()
                })

        return attr_dict
