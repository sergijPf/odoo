# -*- coding: utf-8 -*-

from odoo import fields, models, _
from datetime import datetime
from odoo.exceptions import UserError
from ...odoo_magento2_ept.models.api_request import req, create_search_criteria
from ...odoo_magento2_ept.python_library.php import Php

MAGENTO_DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'


class MagentoProductProduct(models.Model):
    """
    Extends Magento products module with export to Magento operation
    """
    _inherit = 'magento.product.product'

    def export_product_to_magento(self):
        attribute_set_id = self.get_attribute_set_id_by_name(
            self.magento_instance_id,
            self.odoo_product_id.categ_id.magento_attr_set
        )
        config_prod_assigned_attr = self.get_product_attributes(
            self.odoo_product_id.categ_id.name,
            self.odoo_product_id.categ_id.magento_assigned_attr,
            "Configurable"
        )
        simple_prod_attributes = self.get_product_attributes(
            self.magento_product_name,
            self.odoo_product_id.product_template_attribute_value_ids.product_attribute_value_id,
            "Simple"
        )
        # Check if Simple product has attribute(s) to be used as assigned attributes while linking with Config.product
        self.check_product_attr_is_in_assigned_attributes(
            simple_prod_attributes,
            config_prod_assigned_attr,
            self.magento_product_name
        )

        available_attributes = self.get_available_attributes_from_magento(self.magento_instance_id, attribute_set_id)
        is_attrib_exist = self.check_product_attributes_exist_in_magento(
            self.magento_instance_id,
            self.odoo_product_id.product_template_attribute_value_ids.product_attribute_value_id,
            available_attributes
        )
        if not is_attrib_exist:
            raise UserError("Please check product attributes")

        config_prod = {}
        simple_prod = {}

        # check Odoo Product Category is config.Product in Magento and create if not
        config_prod = self.check_odoo_product_category_is_config_product_in_magento(
            self.magento_instance_id,
            self.categ_id.name
        )
        if not config_prod:
            config_prod = self.create_new_configurable_product_in_magento(
                self.magento_instance_id,
                self.categ_id.name,
                attribute_set_id
            )
        else:
            prod_categ_update_date = datetime.strftime(self.categ_id.write_date, MAGENTO_DATETIME_FORMAT)
            if prod_categ_update_date > config_prod.get("updated_at"):
                config_prod = self.update_config_product_in_magento(
                    self.magento_instance_id,
                    self.categ_id.name,
                    config_prod,
                    attribute_set_id
                )

        if config_prod:
            simple_prod = self.check_product_in_magento(self.magento_instance_id, self.magento_sku)
            if simple_prod:
                if simple_prod.get("type_id") == "simple":
                    odoo_update_date1 = datetime.strftime(self.write_date, MAGENTO_DATETIME_FORMAT)
                    odoo_update_date2 = datetime.strftime(self.odoo_product_id.write_date, MAGENTO_DATETIME_FORMAT)
                    if odoo_update_date1 > simple_prod.get("updated_at") or\
                            odoo_update_date2 > simple_prod.get("updated_at"):
                        simple_prod = self.update_simple_product_in_magento(
                            self.magento_instance_id,
                            self.magento_sku,
                            self.odoo_product_id.product_template_attribute_value_ids.product_attribute_value_id,
                            available_attributes,
                            attribute_set_id)
                else:
                    raise UserError("The Product with such sku is already created in Magento. "
                                    "Please check it. (Note it's type isn't Simple Product.) ")
            else:
                simple_prod = self.create_new_simple_product_in_magento(
                    self.magento_instance_id,
                    self.odoo_product_id.product_template_attribute_value_ids.product_attribute_value_id,
                    available_attributes,
                    attribute_set_id
                )
            # map simple to config product in magento
            if simple_prod.get('id'):
                is_assigned = self.assign_attr_to_config_product(
                    self.magento_instance_id,
                    self.categ_id.name,
                    self.odoo_product_id.product_template_attribute_value_ids.product_attribute_value_id,
                    config_prod,
                    config_prod_assigned_attr,
                    available_attributes
                )

                if is_assigned:
                    is_linked = self.link_simple_to_config_product_in_magento(
                        self.magento_instance_id,
                        self.categ_id.name,
                        simple_prod.get('sku')
                    )
                    if is_linked:
                        return {
                            'effect': {
                                'fadeout': 'slow',
                                'message': " 'Export to Magento' Process Completed Successfully! {}".format(""),
                                'img_url': '/web/static/src/img/smile.svg',
                                'type': 'rainbow_man',
                            }
                        }
        else:
            raise UserError("Odoo product category wasn't created nor updated as config.product in Magento.")

    def update_simple_product_in_magento(self, magento_instance, magento_sku, product_attributes,
                                         available_attributes, attribute_set_id):
        custom_attributes = self.map_product_attributes_from_magento(product_attributes, available_attributes)
        data = {
            "product": {
                "name": self.magento_product_name,
                "attribute_set_id": attribute_set_id,
                "price": self.lst_price,
                "status": 1,
                "visibility": 4,
                "type_id": "simple",
                "weight": self.weight,
                "custom_attributes": custom_attributes
            }
        }

        try:
            api_url = '/V1/products/%s' % magento_sku
            response = req(magento_instance, api_url, 'PUT', data)
            print("simple update", response)
        except Exception as error:
            raise UserError(_("Error while Simple product update in Magento: " + str(error)))
        return response

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
            # unlink product's website data in Magento (can cause an error while update)
            # for website in magento_instance.magento_website_ids:
            #     try:
            #         api_url = '/V1/products/%s/websites/%s' % (magento_sku, website.id)
            #         req(magento_instance, api_url, 'DELETE')
            #     except Exception as err:
            #         raise UserError(_("Error while unlinking website from product: '%s'. " % magento_sku) + str(err))
            # update product
            api_url = '/all/V1/products/%s' % magento_sku
            response = req(magento_instance, api_url, 'PUT', data)
        except Exception as error:
            raise UserError(_("Error while config.product update in Magento: " + str(error)))
        return response

    def check_product_attributes_exist_in_magento(self, magento_instance, product_attributes, available_attributes):
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
                                    attr_val.name
                                )
            return True
        else:
            return False

    def create_new_attribute_option_in_magento(self, magento_instance, attribute_code, attribute_option):
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
        try:
            api_url = '/V1/store/storeViews'
            response = req(magento_instance, api_url)
        except Exception as error:
            response = []
        if response:
            store_labels = []
            for view in response:
                store_labels.append({"store_id": view.get('id'), "label": str(attribute_option).upper()})
            data['option'].update({"store_labels": store_labels})

        # create new attribute option(swatch)
        try:
            api_url = '/V1/products/attributes/%s/options' % attribute_code
            req(magento_instance, api_url, 'POST', data)
        except Exception as error:
            raise UserError(_("Error while new Product Attribute Option(Swatch) creation in Magento: " + str(error)))

    def create_new_simple_product_in_magento(self, magento_instance, product_attributes, available_attributes,
                                             attribute_set_id):
        custom_attributes = self.map_product_attributes_from_magento(product_attributes, available_attributes)
        data = {
            "product": {
                "sku": self.magento_sku,
                "name": self.magento_product_name,  # update to x_magento_name
                "attribute_set_id": attribute_set_id,
                "price": self.lst_price,
                "status": 1,  # Enabled
                "visibility": 4,  # Catalog, Search
                "type_id": "simple",
                "weight": self.weight,
                "extension_attributes": {
                    "stock_item": {
                        "qty": self.qty_available,
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

    def assign_attr_to_config_product(self, magento_instance, config_product_sku, product_attributes, config_prod_magento,
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

        #check if config.product assign attributes are the same in magento and odoo
        attr_options = config_prod_magento.get("extension_attributes").get("configurable_product_options")
        prod_attr_magento = { attr["label"].strip().upper() for attr in attr_options if attr }
        prod_attr_odoo = { attr.strip().upper() for attr in config_prod_assigned_attr if attr }
        if attr_options:
            if prod_attr_odoo != prod_attr_magento:
                print("unlink needed")
                for opt in attr_options:
                    if opt.get("label").upper().strip() not in [o.upper().strip() for o in config_prod_assigned_attr]:
                        try:
                            api_url = '/V1/configurable-products/%s/options/%s' % (config_product_sku, opt.get("id"))
                            res = req(magento_instance, api_url, 'DELETE')
                            print("delete_assign_attr", res)
                        except Exception as error:
                            raise UserError(_("Error while unlinking Assign Attribute of Configurable Product in Magento: " +
                                              str(error)))

        # update data with relevant info from Magento
        for attr_val in product_attributes:
            if attr_val.attribute_id.name in config_prod_assigned_attr:
                if attr_val.attribute_id.name.strip().upper() in prod_attr_magento:
                    print("already assigned")
                    res = True
                    continue
                else:
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
                                print(res, data)
                            except Exception as error:
                                raise UserError(
                                    _("Error while assign product attributes to Configurable Product in Magento: " + str(
                                        error)))
        return True if res else res

    def link_simple_to_config_product_in_magento(self, magento_instance, config_product_sku, simple_product_sku):
        """Links simple product to configurable product in Magento"""
        data = {
            "childSku": simple_product_sku
        }
        try:
            api_url = '/V1/configurable-products/%s/child' % config_product_sku
            response = req(magento_instance, api_url, 'POST', data)
        except Exception as error:
            raise UserError(_("Error while linking Simple to Configurable Product in Magento: " + str(error)))

        return True if response else False

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
            raise UserError("Attribute Set - \"%s\" not found."%magento_attribute_set)

    def get_product_attributes(self, product_name, product_attributes, product_type):
        if not len(product_attributes):
            if product_type == 'Configurable':
                raise UserError("Need to define Magento Configurable Attribute(s) at first. "
                                "Product Category - \"%s\" - Magento Details "%product_name)
            else:
                raise UserError("Product \"%s\" has to have at least one attribute" % product_name)

        prod_assigned_attr = []
        for attr in product_attributes:
            prod_assigned_attr.append(attr.name if product_type == "Configurable" else attr.attribute_id.name)
        return prod_assigned_attr

    def check_product_attr_is_in_assigned_attributes(self, simple_prod_attributes, config_prod_assigned_attr, prod_name):
        for attr in config_prod_assigned_attr:
            if attr not in simple_prod_attributes:
                raise UserError("Product \"%s\" has to have \"%s\" attribute defined."%(prod_name,attr))