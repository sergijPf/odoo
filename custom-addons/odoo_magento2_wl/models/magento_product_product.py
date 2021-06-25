# -*- coding: utf-8 -*-

from odoo import fields, models, _
from odoo.exceptions import UserError
from ...odoo_magento2_ept.models.api_request import req, create_search_criteria
from ...odoo_magento2_ept.python_library.php import Php


class MagentoProductProduct(models.Model):
    """
    Extends Magento products module with export to Magento operation
    """
    _inherit = 'magento.product.product'

    attribute_set = fields.Char(string='Magento Product Attribute Set', help='Magento Attribute set', default="Default")

    def export_product_to_magento(self):
        attribute_set_id = self.get_attribute_set_id_by_name(self.magento_instance_id, self.attribute_set)

        available_attributes = self.get_available_attributes_from_magento(self.magento_instance_id, attribute_set_id)
        config_prod = {}
        simple_prod = {}

        # check Odoo Product Category is config.Product in Magento and create if not
        is_config = self.check_odoo_product_category_is_config_product_in_magento(
            self.magento_instance_id,
            self.categ_id.name,
            attribute_set_id
        )
        if not is_config:
            config_prod = self.create_new_configurable_product_in_magento(
                self.magento_instance_id,
                self.categ_id.name,
                attribute_set_id
            )
            is_config = True
        if is_config:
            prod_attrib = self.check_product_attributes_exist_in_magento(
                self.magento_instance_id,
                self.odoo_product_id.product_template_attribute_value_ids.product_attribute_value_id,
                available_attributes
            )
            if prod_attrib:
                if self.check_product_in_magento(self.magento_instance_id, self.magento_sku):
                    # to add update functionality
                    print("Product already exist. Need to add 'update' functionality")
                else:
                    simple_prod = self.create_new_simple_product_in_magento(
                        self.magento_instance_id,
                        self.odoo_product_id.product_template_attribute_value_ids.product_attribute_value_id,
                        available_attributes,
                        attribute_set_id
                    )
                    if simple_prod.get('id'):
                        is_assigned = self.assign_attr_for_config_product(
                            self.magento_instance_id,
                            self.categ_id.name,
                            self.odoo_product_id.product_template_attribute_value_ids.product_attribute_value_id,
                            available_attributes
                        )
                        if is_assigned:
                            is_linked = self.link_simple_to_config_product_in_magento(
                                self.magento_instance_id,
                                self.categ_id.name,
                                simple_prod.get('sku')
                            )
                            print("Successfully linked!")
            else:
                print("stop execution. Need to create product attribute in Magento or add attribute to product in Odoo")


    def update_config_product_in_magento(self, magento_instance, magento_sku, attribute_set_id):
        data = {
            "product": {
                "name": magento_sku.upper(),
                "attribute_set_id": attribute_set_id,
                "type_id": "configurable"
            }
        }
        try:
            #unlink product's website data in Magento (can cause an error while update)
            for website in magento_instance.magento_website_ids:
                try:
                    api_url = '/V1/products/%s/websites/%s'%(magento_sku, website.id)
                    response = req(magento_instance, api_url, 'DELETE')
                except Exception as err:
                    raise UserError(_("Error while unlinking website from product: '%s'. "%magento_sku) + str(err))
            #update product
            api_url = '/V1/products/%s'%magento_sku
            response = req(magento_instance, api_url, 'PUT', data)
        except Exception as error:
            raise UserError(_("Error while Config.Product update in Magento: " + str(error)))
        return response

    def check_odoo_product_category_is_config_product_in_magento(self, magento_instance, magento_sku, attribute_set_id):
        """
        Check if exported product's category is in Magento as configurable product.
        Product category name = magento sku, and product type = configurable
        """
        response = self.check_product_in_magento(magento_instance, magento_sku)

        if response and response.get('type_id') == 'configurable':
            return True
        elif response:
            res = self.update_config_product_in_magento(magento_instance, magento_sku, attribute_set_id)
            if not res.get("id"):
                raise UserError(
                _("The product with \"%s\" sku is not configurable in Magento. Error while updating it. " % magento_sku))
                # add exception on this case to stop execution and manual update of magento product
            else:
                print("updated", res)
                return True
        else:
            return False

    def create_new_configurable_product_in_magento(self, magento_instance, magento_sku, attribute_set_id):
        response = False
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

    def check_product_attributes_exist_in_magento(self, magento_instance, product_attributes, available_attributes):
        """
        Check if product attribute exists in Magento(avail.attr).
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
            response = {}
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
        response = False
        custom_attributes = []
        data = {
            "product": {
                "sku": str(self.magento_sku),
                "name": str(self.name),  # update to x_magento_name
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
                "custom_attributes": []
            }
        }

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
        data["product"].update({"custom_attributes": custom_attributes})

        try:
            api_url = '/V1/products'
            response = req(magento_instance, api_url, 'POST', data)
        except Exception as error:
            raise UserError(_("Error while new Simple Product creation in Magento: " + str(error)))

        return response

    def assign_attr_for_config_product(self, magento_instance, config_product_sku, product_attributes,
                                       available_attributes):
        """
        Assigns attributes of exported simple product to configurable product in Magento, in order to link it further
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

        for attr_val in product_attributes:
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
                    print(data)

                    try:
                        api_url = '/V1/configurable-products/%s/options' % config_product_sku
                        res = req(magento_instance, api_url, 'POST', data)
                    except Exception as error:
                        raise UserError(
                            _("Error while assign attributes to Configurable Product in Magento: " + str(error)))

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

        return response

    def check_product_in_magento(self, magento_instance, magento_sku):
        """Checks if product with defined sku exists in Magento"""
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
        # request available attributes of defined attribute-set
        try:
            api_url = '/V1/products/attribute-sets/%s/attributes' % attribute_set_id
            response = req(magento_instance, api_url)
        except Exception as error:
            log = error
            return False
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
        except:
            raise UserError(_("Error while requesting attribute set from Magento"))

        if response:
            return response.get('items')[0].get('attribute_set_id')
