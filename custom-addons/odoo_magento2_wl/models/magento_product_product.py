# -*- coding: utf-8 -*-

import json

from odoo import fields, models, _
from datetime import datetime
from odoo.exceptions import UserError
from mimetypes import guess_type
from ...odoo_magento2_ept.models.api_request import req, create_search_criteria
from ...odoo_magento2_ept.python_library.php import Php

MAGENTO_DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'


class MagentoProductProduct(models.Model):
    """
    Extends Magento products module with export to Magento operation
    """
    _inherit = 'magento.product.product'

    # is_exported_to_magento = fields.Boolean(string="Exported to Magento")

    def prepare_products_export_to_magento(self):
        active_product_ids = self._context.get("active_ids", [])
        export_products = self.env["magento.product.product"].browse(active_product_ids)

        # refactoring
        ml_export_conf_products = {}
        ml_export_simple_products = {}
        attr_sets = {}
        magento_products = {}

        for mi in {i.magento_instance_id: {} for i in export_products}:

            # create unique attr_sets and get their id/attribute details(options)
            attr_sets.update({
                mi.name: {
                    s.odoo_product_id.categ_id.magento_attr_set: {} for s in export_products if
                    mi.id == s.magento_instance_id.id
                }
            })
            for a_set in attr_sets[mi.name]:
                attr_sets[mi.name][a_set].update({
                    'id': self.get_attribute_set_id_by_name(mi, a_set)
                })
                attr_sets[mi.name][a_set].update({
                    'attributes': self.get_available_attributes_from_magento(mi, attr_sets[mi.name][a_set].get('id'))
                })

            # create combined dict of selected products to export in Magento:
            # magento_layer_dict = {
            #   instance_name: {
            #       config_prod_name: {
            #           related_simple_prod_list: [],
            #           attr_set: name,
            #           config_attr: [],
            #           config_prod_children: [],
            #           is_in_magento: True/False
            #       }
            #   }
            # }
            ml_export_conf_products.update({
                mi.name: {
                    c.odoo_product_id.categ_id.name: {
                        'attribute_set_id': attr_sets[mi.name][c.odoo_product_id.categ_id.magento_attr_set]['id'],
                        'config_attr': [a.name for a in c.odoo_product_id.categ_id.magento_assigned_attr if a],
                        'children': [],
                        'is_in_magento': False
                    } for c in export_products if mi.id == c.magento_instance_id.id
                }
            })

            ml_export_simple_products.update({
                mi.name: {
                    s.magento_sku: {
                        'attribute_set_id': attr_sets[mi.name][s.odoo_product_id.categ_id.magento_attr_set]['id'],
                        'is_in_magento': False,
                        'is_ok_to_export': True
                    } for s in export_products if mi.id == s.magento_instance_id.id
                }
            })

            # get selected products and their config's(categ.) product from magento
            ml_config_products = list(
                {c.odoo_product_id.categ_id for c in export_products if mi.id == c.magento_instance_id.id})
            ml_simple_products = [s for s in export_products if mi.id == s.magento_instance_id.id]
            magento_products.update({
                mi.name: self.get_products_from_magento(mi, [s.magento_sku for s in ml_simple_products] +
                                                        [c.name for c in ml_config_products])
            })
            mag_prod_list = magento_products[mi.name]['items']
            mag_prod_sku_list = [p.get('sku') for p in mag_prod_list]

            # check if config products exist in Magento and create/update them.
            for prod in ml_config_products:
                if prod.name in mag_prod_sku_list:
                    attr_set_id = attr_sets[mi.name][prod.magento_attr_set]['id']
                    ml_export_conf_products[mi.name][prod.name]['is_in_magento'] = True
                    conf_prod = next(
                        (x for x in mag_prod_list if x.get('sku') == prod.name and x.get('type_id') == 'configurable'),
                        {})
                    if conf_prod:
                        prod_categ_update_date = datetime.strftime(prod.write_date, MAGENTO_DATETIME_FORMAT)
                        if prod_categ_update_date > conf_prod.get("updated_at"):
                            conf_prod = self.update_config_product_in_magento(mi, prod.name, conf_prod, attr_set_id)
                            for p in range(len(mag_prod_list)):
                                if mag_prod_list[p]['sku'] == conf_prod['sku']:
                                    mag_prod_list.insert(p, conf_prod)
                    else:
                        raise UserError(
                            _("Product with the following sku - \"%s\" already exists in Magento. " % prod.name))

            # update children fields for config products with data from Magento
            for ml_conf_prod in ml_export_conf_products[mi.name]:
                # update config's children if is_in_magento
                if ml_export_conf_products[mi.name][ml_conf_prod].get('is_in_magento'):
                    simple_prod_list = [i.get('sku') for i in self.get_config_children(mi, ml_conf_prod)]
                    ml_export_conf_products[mi.name][ml_conf_prod].update({'children': simple_prod_list})

            new_conf_prod_list = [{c: ml_export_conf_products[mi.name][c]} for c in ml_export_conf_products[mi.name] if
                                  not ml_export_conf_products[mi.name][c].get('is_in_magento')]
            bulk_info = self.create_new_bulk_of_conf_products_in_magento(mi, new_conf_prod_list)
            # mag_prod_list.extend(self.create_new_bulk_of_conf_products_in_magento(mi, new_conf_prod_list))
            # if not bulk_info['errors']:
            #     status = self.get_bulk_detailed_status(mi, bulk_info['bulk_uuid'])
            # mag_prod_list.append(self.create_new_configurable_product_in_magento(mi, prod.name, attr_set_id))

            # get storeViews from Magento
            magento_storeviews = self.get_storeviews_from_magento(mi) or []

            # check simple product exist in Magento and create/update them
            for prod in ml_simple_products:
                # Check if Simple product has attribute(s) to be used as assigned attributes
                # while linking with Config.product
                check_attr = self.check_product_attr_is_in_assigned_attributes(
                    [a.attribute_id.name for a in
                     prod.odoo_product_id.product_template_attribute_value_ids.product_attribute_value_id],
                    ml_export_conf_products[mi.name][prod.categ_id.name]['config_attr'],
                    prod.magento_sku
                )
                ml_export_simple_products[mi.name][prod.magento_sku]['is_ok_to_export'] = check_attr

                attr_set_id = attr_sets[mi.name][prod.odoo_product_id.categ_id.magento_attr_set]['id']
                available_attributes = attr_sets[mi.name][prod.odoo_product_id.categ_id.magento_attr_set]['attributes']

                # check if simple product attributes exist in Magento / create attr option if none.
                is_attrib_exist = self.check_product_attributes_exist_in_magento(
                    mi,
                    prod.odoo_product_id.product_template_attribute_value_ids.product_attribute_value_id,
                    available_attributes,
                    magento_storeviews
                )
                ml_export_simple_products[mi.name][prod.magento_sku]['is_ok_to_export'] = is_attrib_exist and \
                                                                                          ml_export_simple_products[
                                                                                              mi.name][
                                                                                              prod.magento_sku][
                                                                                              'is_ok_to_export']
                # attribute doesn't exist on Magento and have to be created manually
                if not is_attrib_exist:
                    raise UserError("Please check product attributes")

                if prod.magento_sku in mag_prod_sku_list:
                    ml_export_simple_products[mi.name][prod.magento_sku]['is_in_magento'] = True

                    simp_prod = next(
                        (x for x in mag_prod_list if x.get('sku') == prod.magento_sku and x.get('type_id') == 'simple'),
                        {})
                    if simp_prod:
                        odoo_update_date1 = datetime.strftime(prod.write_date, MAGENTO_DATETIME_FORMAT)
                        odoo_update_date2 = datetime.strftime(prod.odoo_product_id.write_date, MAGENTO_DATETIME_FORMAT)
                        if odoo_update_date1 > simp_prod.get("updated_at") or \
                                odoo_update_date2 > simp_prod.get("updated_at"):
                            self.update_simple_product_in_magento(mi, prod,
                                                                  prod.odoo_product_id.product_template_attribute_value_ids.product_attribute_value_id,
                                                                  available_attributes, attr_set_id)
                    else:
                        raise UserError("The Product with such sku is already created in Magento. "
                                        "Please check it. (Note it's type isn't Simple Product.) ")
                    # else:
                    # simp_prod = self.create_new_simple_product_in_magento(
                    #     mi,
                    #     prod,
                    #     prod.odoo_product_id.product_template_attribute_value_ids.product_attribute_value_id,
                    #     available_attributes,
                    #     attr_set_id
                    # )

                    # map simple to config product in magento
                    config_prod = next(
                        (x for x in mag_prod_list if
                         x.get('sku') == prod.categ_id.name and x.get('type_id') == 'configurable'), {})
                    is_assigned = self.assign_attr_to_config_product(
                        mi,
                        prod.categ_id.name,
                        prod.odoo_product_id.product_template_attribute_value_ids.product_attribute_value_id,
                        config_prod,
                        ml_export_conf_products[mi.name][prod.categ_id.name]['config_attr'],
                        available_attributes
                    )
                    if is_assigned:
                        self.link_simple_to_config_product_in_magento(
                            mi,
                            prod.categ_id.name,
                            ml_export_conf_products[mi.name][prod.categ_id.name]['children'],
                            prod.magento_sku
                        )
            new_simple_prod_dict = {}
            for s in ml_export_simple_products[mi.name]:
                if not ml_export_simple_products[mi.name][s]['is_in_magento'] and ml_export_simple_products[mi.name][s]['is_ok_to_export']:
                    new_simple_prod_dict.update({s: ml_export_simple_products[mi.name][s]})
            print(new_simple_prod_dict)
            # return
            # new_simple_prod_dict = {{s: ml_export_simple_products[mi.name][s]} for s in
            #                         ml_export_simple_products[mi.name] if
            #                         not ml_export_simple_products[mi.name][s]['is_in_magento'] and
            #                         ml_export_simple_products[mi.name][s]['is_ok_to_export']}
            bulk_info = self.create_new_bulk_of_simple_products_in_magento(mi, ml_simple_products, new_simple_prod_dict,
                                                                           attr_sets[mi.name])
            print(bulk_info)

        return {
            'effect': {
                'fadeout': 'slow',
                'message': " 'Export to Magento' Process Completed Successfully! {}".format(""),
                'img_url': '/web/static/src/img/smile.svg',
                'type': 'rainbow_man',
            }
        }

    # def export_product_to_magento(self, attribute_set_id, available_attributes):
    #     # to exclude
    #     # attribute_set_id = self.get_attribute_set_id_by_name(
    #     #     self.magento_instance_id,
    #     #     self.odoo_product_id.categ_id.magento_attr_set
    #     # )
    #     config_prod_assigned_attr = self.get_product_attributes(
    #         self.odoo_product_id.categ_id.name,
    #         self.odoo_product_id.categ_id.magento_assigned_attr,
    #         "Configurable"
    #     )
    #     simple_prod_attributes = self.get_product_attributes(
    #         self.magento_product_name,
    #         self.odoo_product_id.product_template_attribute_value_ids.product_attribute_value_id,
    #         "Simple"
    #     )
    #     # Check if Simple product has attribute(s) to be used as assigned attributes while linking with Config.product
    #     self.check_product_attr_is_in_assigned_attributes(
    #         simple_prod_attributes,
    #         config_prod_assigned_attr,
    #         self.magento_product_name
    #     )
    #
    #     # available_attributes = self.get_available_attributes_from_magento(self.magento_instance_id, attribute_set_id)
    #     is_attrib_exist = self.check_product_attributes_exist_in_magento(
    #         self.magento_instance_id,
    #         self.odoo_product_id.product_template_attribute_value_ids.product_attribute_value_id,
    #         available_attributes
    #     )
    #     if not is_attrib_exist:
    #         raise UserError("Please check product attributes")
    #
    #     # check Odoo Product Category is config.Product in Magento and create if not
    #     config_prod = self.check_odoo_product_category_is_config_product_in_magento(
    #         self.magento_instance_id,
    #         self.categ_id.name
    #     )
    #     if not config_prod:
    #         config_prod = self.create_new_configurable_product_in_magento(
    #             self.magento_instance_id,
    #             self.categ_id.name,
    #             attribute_set_id
    #         )
    #     else:
    #         prod_categ_update_date = datetime.strftime(self.categ_id.write_date, MAGENTO_DATETIME_FORMAT)
    #         if prod_categ_update_date > config_prod.get("updated_at"):
    #             config_prod = self.update_config_product_in_magento(
    #                 self.magento_instance_id,
    #                 self.categ_id.name,
    #                 config_prod,
    #                 attribute_set_id
    #             )
    #
    #     if config_prod:
    #         simple_prod = self.check_product_in_magento(self.magento_instance_id, self.magento_sku)
    #         if simple_prod:
    #             if simple_prod.get("type_id") == "simple":
    #                 odoo_update_date1 = datetime.strftime(self.write_date, MAGENTO_DATETIME_FORMAT)
    #                 odoo_update_date2 = datetime.strftime(self.odoo_product_id.write_date, MAGENTO_DATETIME_FORMAT)
    #                 if odoo_update_date1 > simple_prod.get("updated_at") or \
    #                         odoo_update_date2 > simple_prod.get("updated_at"):
    #                     simple_prod = self.update_simple_product_in_magento(
    #                         self.magento_instance_id,
    #                         self.magento_sku,
    #                         self.odoo_product_id.product_template_attribute_value_ids.product_attribute_value_id,
    #                         available_attributes,
    #                         attribute_set_id)
    #             else:
    #                 raise UserError("The Product with such sku is already created in Magento. "
    #                                 "Please check it. (Note it's type isn't Simple Product.) ")
    #         else:
    #             simple_prod = self.create_new_simple_product_in_magento(
    #                 self.magento_instance_id,
    #                 self.odoo_product_id.product_template_attribute_value_ids.product_attribute_value_id,
    #                 available_attributes,
    #                 attribute_set_id
    #             )
    #
    #         # map simple to config product in magento
    #         if simple_prod.get('id'):
    #             is_assigned = self.assign_attr_to_config_product(
    #                 self.magento_instance_id,
    #                 self.categ_id.name,
    #                 self.odoo_product_id.product_template_attribute_value_ids.product_attribute_value_id,
    #                 config_prod,
    #                 config_prod_assigned_attr,
    #                 available_attributes
    #             )
    #             if is_assigned:
    #                 self.link_simple_to_config_product_in_magento(
    #                     self.magento_instance_id,
    #                     self.categ_id.name,
    #                     simple_prod.get('sku')
    #                 )
    #     else:
    #         raise UserError("Odoo product category wasn't created nor updated as config.product in Magento.")

    def check_odoo_product_category_is_config_product_in_magento(self, magento_instance, magento_sku):
        """
        Check if exported product's category is in Magento as configurable product.
        Product category name = magento sku, and product type = configurable
        """
        config_prod = self.check_product_in_magento(magento_instance, magento_sku)
        if config_prod:
            if config_prod.get('type_id') == 'configurable':
                # conf_prod_links = response.get("extension_attributes").get("configurable_product_links") or []
                # config_prod.update({  "configurable_product_links": conf_prod_links })
                # conf_prod_options = response.get("extension_attributes").get("configurable_product_options") or []
                # config_prod.update({"configurable_product_options": conf_prod_options})
                # config_prod.update({"updated_at": response.get("updated_at")})
                #
                # print(config_prod)
                # raise UserError("stop Exec")
                return config_prod
            else:
                raise UserError(
                    _("Product with the following sku - \"%s\" already exists in Magento. " % magento_sku))
                # add exception on this case to stop execution and manual update of magento product
        else:
            return {}

    def create_new_configurable_product_in_magento(self, magento_instance, magento_sku, attribute_set_id):
        data = {
            "product": {
                "sku": magento_sku,
                "name": magento_sku.upper(),
                "attribute_set_id": attribute_set_id,
                "status": 1,  # Enabled
                "visibility": 4,  # Catalog, Search
                "type_id": "configurable",
                "custom_attributes": []
            }
        }

        try:
            api_url = '/V1/products'
            response = req(magento_instance, api_url, 'POST', data)
        except Exception as error:
            raise UserError(_("Error while new Configurable Product creation in Magento: " + str(error)))

        return response

    def update_config_product_in_magento(self, magento_instance, magento_sku, config_prod_magento,
                                         attribute_set_id):
        data = {
            "product": {
                "name": magento_sku.upper(),
                "type_id": "configurable"
            }
        }

        if config_prod_magento.get("attribute_set_id") != attribute_set_id:
            data['product'].update({"attribute_set_id": attribute_set_id})

        try:
            api_url = '/all/V1/products/%s' % magento_sku
            response = req(magento_instance, api_url, 'PUT', data)
        except Exception as error:
            raise UserError(_("Error while config.product update in Magento: " + str(error)))
        return response

    def check_product_attributes_exist_in_magento(self, magento_instance, product_attributes, available_attributes,
                                                  magento_storeviews):
        """
        Check if product attribute exists in Magento(avail.attr array).
        If yes: returns True, else returns False(need to be created manually in Magento
        """
        if len(product_attributes):
            log = ''
            default_lbl = [i['default_label'] for i in available_attributes]

            # logs if any of attributes are missed in Magento and creates new attr.option in Magento
            for attr_val in product_attributes:
                if attr_val.attribute_id.name.strip().upper() not in [i.strip().upper() for i in default_lbl if i]:
                    log += str(attr_val.attribute_id.name) + " - attribute has to be created on Magento side.\n"
                    print(log)  # update this part
                    return False
                else:
                    for attr in available_attributes:
                        if attr_val.attribute_id.name.strip().upper() == str(attr['default_label']).strip().upper():
                            if attr_val.name.strip().upper() not in [i.get('label').strip().upper() for i in
                                                                     attr['options']]:
                                self.create_new_attribute_option_in_magento(
                                    magento_instance,
                                    attr['default_label'],
                                    attr_val.name,
                                    magento_storeviews
                                )
            return True
        else:
            return False

    def create_new_attribute_option_in_magento(self, magento_instance, attribute_code, attribute_option,
                                               magento_storeviews):
        """Creates new option(swatch) for defined attribute in Magento"""
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
            req(magento_instance, api_url, 'POST', data)
        except Exception as error:
            raise UserError(_("Error while new Product Attribute Option(Swatch) creation in Magento: " + str(error)))

    def create_new_simple_product_in_magento(self, magento_instance, product, product_attributes, available_attributes,
                                             attribute_set_id):
        custom_attributes = self.map_product_attributes_from_magento(product_attributes, available_attributes)
        data = {
            "product": {
                "sku": product.magento_sku,
                "name": product.magento_product_name,  # update to x_magento_name
                "attribute_set_id": attribute_set_id,
                "price": product.lst_price,
                "status": 1,  # Enabled
                "visibility": 4,  # Catalog, Search
                "type_id": "simple",
                "weight": product.weight,
                "extension_attributes": {
                    "stock_item": {
                        "qty": product.qty_available,
                        "is_in_stock": "true"
                    }
                },
                "custom_attributes": custom_attributes
            }
        }

        try:
            api_url = '/V1/products'
            response = req(magento_instance, api_url, 'POST', data)
            print('new simple creation:', response)
        except Exception as error:
            raise UserError(_("Error while new Simple Product creation in Magento: " + str(error)))

        # export product images to Magento
        if response and len(product.odoo_product_id.product_template_image_ids):
            self.export_media_to_magento(magento_instance, response.get("sku"),
                                         product.odoo_product_id.product_template_image_ids)

        return response

    def update_simple_product_in_magento(self, magento_instance, product, product_attributes,
                                         available_attributes, attribute_set_id):
        custom_attributes = self.map_product_attributes_from_magento(product_attributes, available_attributes)
        data = {
            "product": {
                "name": product.magento_product_name,
                "attribute_set_id": attribute_set_id,
                "price": product.lst_price,
                "status": 1,
                "visibility": 4,
                "type_id": "simple",
                "weight": product.weight,
                "media_gallery_entries": [],
                "custom_attributes": custom_attributes
            }
        }

        try:
            api_url = '/V1/products/%s' % product.magento_sku
            response = req(magento_instance, api_url, 'PUT', data)
            print("simple update", response)
        except Exception as error:
            raise UserError(_("Error while Simple product update in Magento: " + str(error)))

        # export product images to Magento
        if response and len(product.odoo_product_id.product_template_image_ids):
            self.export_media_to_magento(magento_instance, response.get("sku"),
                                         product.odoo_product_id.product_template_image_ids)

        return response

    def map_product_attributes_from_magento(self, product_attributes, available_attributes):
        """Map Simple Product attributes from Odoo with attributes defined in Magneto."""
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

    def assign_attr_to_config_product(self, magento_instance, config_product_sku, product_attributes,
                                      config_prod_magento,
                                      config_prod_assigned_attr, available_attributes):
        """
        Assigns attributes to configurable product in Magento, in order to link it further
        """
        res = False
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
        attr_options = config_prod_magento.get("extension_attributes").get("configurable_product_options")
        prod_attr_magento = {}
        if attr_options:
            prod_attr_magento = {self.get_attr_name_by_id(available_attributes, attr.get("attribute_id")) for attr in
                                 attr_options if attr}
            prod_attr_odoo = {attr.strip().upper() for attr in config_prod_assigned_attr if attr}
            if prod_attr_odoo != prod_attr_magento:
                print("unlink needed")
                for opt in attr_options:
                    if opt.get("label").upper().strip() not in [o.upper().strip() for o in config_prod_assigned_attr]:
                        try:
                            api_url = '/V1/configurable-products/%s/options/%s' % (config_product_sku, opt.get("id"))
                            req(magento_instance, api_url, 'DELETE')
                        except Exception as error:
                            raise UserError(_("Error while unlinking Assign Attribute of %s "
                                              "Config.Product in Magento: " % config_product_sku + str(error)))

        # assign new options to config.product with relevant info from Magento
        for attr_val in product_attributes:
            if attr_val.attribute_id.name in config_prod_assigned_attr:
                if attr_val.attribute_id.name.strip().upper() in prod_attr_magento:
                    res = True
                    continue
                else:
                    # valid for new "assign" attributes to be created in Magento
                    res = False
                    for attr in available_attributes:
                        if attr_val.attribute_id.name.strip().upper() == str(attr['default_label']).strip().upper():
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
                                res = req(magento_instance, api_url, 'POST', data)
                            except Exception as error:
                                raise UserError(_("Error while assign product attributes to %s "
                                                  " Config.Product in Magento: " % config_product_sku))
        return True if res else False

    def link_simple_to_config_product_in_magento(self, magento_instance, config_product_sku, config_product_children,
                                                 simple_product_sku):
        """Links simple product to configurable product in Magento"""
        if simple_product_sku in config_product_children:
            return

        # if not linked
        data = {
            "childSku": simple_product_sku
        }
        try:
            api_url = '/V1/configurable-products/%s/child' % config_product_sku
            req(magento_instance, api_url, 'POST', data)
        except Exception as error:
            raise UserError(_("Error while linking Simple to Configurable Product in Magento. Possible reason:"
                              "1. Config.product already contains such attribute set values as %s" % simple_product_sku))

    def check_product_in_magento(self, magento_instance, magento_sku):
        """Check if product with defined sku exists in Magento"""
        try:
            api_url = '/V1/products/%s' % magento_sku
            response = req(magento_instance, api_url)
        except Exception as err:
            print(err)  # add logging
            return {}
        return response

    def get_available_attributes_from_magento(self, magento_instance, attribute_set_id):
        """Get available attributes and their related options(swatches) from Magento"""
        available_attributes = []
        try:
            api_url = '/V1/products/attribute-sets/%s/attributes' % attribute_set_id
            response = req(magento_instance, api_url)
        except Exception as error:
            raise UserError("Error while getting product attributes from Magento" + str(error))

        # generate the list of available attributes and their options from Magento
        for attr in response:
            available_attributes.append({
                "attribute_id": attr.get("attribute_id"),
                "attribute_code": attr.get('attribute_code'),
                'default_label': attr.get('default_frontend_label'),
                'options': attr.get('options')
            })
        return available_attributes

    def get_attribute_set_id_by_name(self, magento_instance, magento_attribute_set, magento_entity_id=4):
        """Receive Magento attribute name and return id of it"""
        filter = {
            'attribute_set_name': magento_attribute_set,
            'entity_type_id': magento_entity_id
        }
        search_criteria = create_search_criteria(filter)
        query_string = Php.http_build_query(search_criteria)
        api_url = '/V1/eav/attribute-sets/list?%s' % query_string

        try:
            response = req(magento_instance, api_url)
        except Exception as error:
            raise UserError(_("Error while requesting attribute set from Magento") + str(error))

        if response.get('items'):
            return response.get('items')[0].get('attribute_set_id')
        else:
            raise UserError("Attribute Set - \"%s\" not found." % magento_attribute_set)

    def get_product_attributes(self, product_name, product_attributes, product_type):
        if not len(product_attributes):
            if product_type == 'Configurable':
                raise UserError("Need to define Magento Configurable Attribute(s) at first. "
                                "Product Category - \"%s\" - Magento Details " % product_name)
            else:
                raise UserError("Product \"%s\" has to have at least one attribute" % product_name)

        prod_assigned_attr = []
        for attr in product_attributes:
            prod_assigned_attr.append(attr.name if product_type == "Configurable" else attr.attribute_id.name)
        return prod_assigned_attr

    def check_product_attr_is_in_assigned_attributes(self, simple_prod_attributes, config_prod_assigned_attr,
                                                     prod_sku):
        for attr in config_prod_assigned_attr:
            if attr not in simple_prod_attributes:
                return False
                # raise UserError("Product \"%s\" has to have \"%s\" attribute defined." % (prod_sku, attr))
        return True

    def get_attr_name_by_id(self, available_attributes, attr_id):
        for attr in available_attributes:
            if str(attr.get('attribute_id')) == str(attr_id):
                return str(attr.get('default_label')).strip().upper()

    def export_media_to_magento(self, magento_instance, product_sku, odoo_images):
        for img in odoo_images:
            attachment = self.env['ir.attachment'].sudo().search([('res_field', '=', 'image_256'),
                                                                  ('res_model', '=', 'product.image'),
                                                                  ('res_id', '=', img.id)
                                                                  ])
            image = {
                "entry": {
                    "media_type": "image",
                    "content": {
                        "base64EncodedData": img.image_256.decode('utf-8'),
                        "type": attachment.mimetype,
                        "name": attachment.mimetype.replace("/", ".")
                    }
                }
            }
            try:
                api_url = '/V1/products/%s/media' % product_sku
                req(magento_instance, api_url, 'POST', image)
            except Exception as error:
                raise UserError(_("Error while Simple Product Images export to Magento: " + str(error)))

    def get_products_from_magento(self, instance, magento_sku_list):
        filters = {}
        filters.setdefault('sku', {})
        filters['sku']['in'] = magento_sku_list
        search_criteria = create_search_criteria(filters)
        query_string = Php.http_build_query(search_criteria)
        api_url = '/V1/products?%s' % query_string

        try:
            response = req(instance, api_url)
        except Exception as error:
            raise UserError(_("Error while requesting attribute set from Magento") + str(error))

        return response

    def get_config_children(self, magento_instance, config_product_sku):
        """get all children assigned to config.product in Magento """
        try:
            api_url = '/all/V1/configurable-products/%s/children' % config_product_sku
            response = req(magento_instance, api_url)
        except Exception as error:
            raise UserError(_("Error while getting Configurable Products children from Magento: " + str(error)))
        return response

    def get_storeviews_from_magento(self, magento_instance):
        """get store_views from Magento, if error - remains [] (admin only)"""
        try:
            api_url = '/V1/store/storeViews'
            response = req(magento_instance, api_url)
        except Exception as error:
            response = []
        return response

    def create_new_bulk_of_conf_products_in_magento(self, magento_instance, config_products_list):
        data = []

        for prod in config_products_list:
            prod_sku = str(list(prod.keys())[0])
            data.append({
                "product": {
                    "sku": prod_sku,
                    "name": prod_sku.upper(),
                    "attribute_set_id": prod[prod_sku]['attribute_set_id'],
                    "status": 1,  # Enabled
                    "visibility": 4,  # Catalog, Search
                    "type_id": "configurable",
                    "custom_attributes": []
                }
            })

        try:
            api_url = '/async/bulk/V1/products'
            response = req(magento_instance, api_url, 'POST', data)
        except Exception as error:
            raise UserError(_("Error while new Configurable Product creation in Magento: " + str(error)))

        return response

    def get_bulk_detailed_status(self, magento_instance, bulk_uuid):
        try:
            api_url = '/V1/bulk/%s/detailed-status' % bulk_uuid
            response = req(magento_instance, api_url)
        except Exception as error:
            raise UserError(_("Error while getting bulk detailed-status: " + str(error)))

        return response

    def create_new_bulk_of_simple_products_in_magento(self, magento_instance, odoo_products, ml_export_simple_products,
                                                      available_attributes_dict):
        data = []

        for prod in odoo_products:
            if prod.magento_sku in ml_export_simple_products.keys():
                custom_attributes = self.map_product_attributes_from_magento(
                    prod.odoo_product_id.product_template_attribute_value_ids.product_attribute_value_id,
                    available_attributes_dict[prod.odoo_product_id.categ_id.magento_attr_set]['attributes']
                )
                data.append({
                    "product": {
                        "sku": prod.magento_sku,
                        "name": prod.magento_product_name,  # update to x_magento_name
                        "attribute_set_id": ml_export_simple_products[prod.magento_sku]['attribute_set_id'],
                        "price": prod.lst_price,
                        "status": 1,  # Enabled
                        "visibility": 4,  # Catalog, Search
                        "type_id": "simple",
                        "weight": prod.weight,
                        "extension_attributes": {
                            "stock_item": {
                                "qty": prod.qty_available,
                                "is_in_stock": "true"
                            }
                        },
                        "custom_attributes": custom_attributes
                    }
                })

        try:
            api_url = '/async/bulk/V1/products'
            response = req(magento_instance, api_url, 'POST', data)
        except Exception as error:
            raise UserError(_("Error while new Simple Products creation in Magento: " + str(error)))

        # export product images to Magento
        # if response and len(odoo_products.odoo_product_id.product_template_image_ids):
        #     self.export_media_to_magento(magento_instance, response.get("sku"),
        #                                  odoo_products.odoo_product_id.product_template_image_ids)

        return response
