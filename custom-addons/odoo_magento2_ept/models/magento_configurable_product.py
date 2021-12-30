# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
"""
Describes fields and methods for Magento configurable products
"""
import json
from odoo import fields, models, api
from odoo.exceptions import UserError
from datetime import datetime
from .api_request import req, create_search_criteria
from ..python_library.php import Php

MAGENTO_DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'
MAX_SIZE_FOR_IMAGES = 2500000 # should be aligned with MYSQL - max_allowed_size (currently 4M), !!! NOTE 4M is converted size and constant value is before convertion
PRODUCTS_THRESHOLD = 250
IMG_SIZE = 'image_1024'


class MagentoConfigurableProduct(models.Model):
    """
    Describes fields and methods for Magento products
    """
    _name = 'magento.configurable.product'
    _description = 'Magento Configurable Product'
    _rec_name = 'magento_product_name'

    magento_instance_id = fields.Many2one('magento.instance', 'Magento Instance',
                                          help="This field relocates magento instance")
    magento_sku = fields.Char(string="Magento Product SKU")
    magento_website_ids = fields.Many2many('magento.website', string='Magento Product Websites', readonly=False,
                                           domain="[('magento_instance_id','=',magento_instance_id)]")
    magento_status = fields.Selection([
        ('not_exported', 'not Exported'),
        ('in_process', 'In Process'),
        ('in_magento', 'In Magento'),
        ('no_need', 'Not needed'),
        ('log_error', 'Error to Export'),
        ('update_needed', 'Need to Update'),
        ('deleted', 'Deleted in Magento')
    ], string='Export Status', help='The status of Configurable Product Export to Magento ',
        default='not_exported')
    image_1920 = fields.Image(related="odoo_prod_template.image_1920")
    product_images = fields.One2many(related="odoo_prod_template.product_template_image_ids")
    magento_product_id = fields.Char(string="Magento Product Id")
    active = fields.Boolean("Active", default=True)
    odoo_prod_template = fields.Many2one('product.template', string='Odoo Product Template')
    magento_product_name = fields.Char(string="Magento Configurable Product Name", related='odoo_prod_template.name')
    category_ids = fields.Many2many("magento.product.category", string="Product Categories", help="Magento Categories",
                                    domain="[('instance_id','=',magento_instance_id)]")
    magento_attr_set = fields.Char(string='Magento Product Attribute Set', help='Magento Attribute set',
                                   default="Default")
    do_not_create_flag = fields.Boolean(related="odoo_prod_template.x_magento_no_create",
                                        string="Don't create Product in Magento")
    # magento_assign_attrs = fields.Many2many(related="odoo_prod_template.x_magento_attr_ids",
    #                                         string="Configurable Attribute(s)")
    x_magento_assign_attrs = fields.Many2many('product.attribute', string="Configurable Attribute(s)",
                                              compute="_compute_config_attributes")
    x_magento_main_config_attr = fields.Many2one('product.attribute', string="Main Config.Attribute",
                                              compute="_compute_main_config_attribute")
    magento_export_date = fields.Datetime(string="Last Export Date",
                                          help="Configurable Product last Export Date to Magento")
    force_update = fields.Boolean(string="To force run of Configurable Product Export", default=False)
    simple_product_ids = fields.One2many('magento.product.product', 'magento_conf_product_id', 'Magento Products',
                                          required=True, context={'active_test': False})
    product_variant_count = fields.Integer('# Product Variants', compute='_compute_magento_product_variant_count')
    bulk_log_ids = fields.Many2many('magento.async.bulk.logs', string="Async Bulk Logs")

    _sql_constraints = [('_magento_conf_product_unique_constraint',
                         'unique(magento_sku,magento_instance_id)',
                         "Magento Configurable Product SKU must be unique within Magento instance")]

    @api.depends('odoo_prod_template.attribute_line_ids')
    def _compute_config_attributes(self):
        for rec in self:
            rec.x_magento_assign_attrs = rec.odoo_prod_template.attribute_line_ids.filtered(
                lambda x: x.magento_config and not x.attribute_id.is_ignored_in_magento).attribute_id

    @api.depends('odoo_prod_template.attribute_line_ids')
    def _compute_main_config_attribute(self):
        for rec in self:
            rec.x_magento_main_config_attr = rec.odoo_prod_template.attribute_line_ids.filtered(
                lambda x: x.magento_config and x.main_conf_attr).attribute_id or False

    def write(self, vals):
        if 'magento_attr_set' in vals or 'category_ids' in vals:
            vals.update({'force_update': True})

        # archive/unarchive related simple products
        if 'active' in vals:
            if self.simple_product_ids:
                self.simple_product_ids.write({'active': vals["active"]})
        res = super(MagentoConfigurableProduct, self).write(vals)
        return res

    def unlink(self):
        if len(self.simple_product_ids.with_context(active_test=False)):
            raise UserError("You can't remove this Product until it has related Simple Products: %s" % \
                  str([s.magento_sku for s in self.simple_product_ids.with_context(active_test=False)]))
        result = super(MagentoConfigurableProduct, self).unlink()
        return result

    # @api.depends('simple_product_ids.magento_conf_product_id')
    @api.depends('simple_product_ids')
    def _compute_magento_product_variant_count(self):
        for template in self:
            # do not pollute variants to be prefetched when counting variants
            template.product_variant_count = len(template.with_prefetch().simple_product_ids)

    def delete_in_magento(self):
        """
        Delete Configurable Product in Magento, available in Magento Product Form view for products with Magento Product Id
        :return: None
        """
        self.ensure_one()
        if len(self.simple_product_ids.with_context(active_test=False)):
            raise UserError("You can't remove this Product until it has related Simple Products: %s" % \
                  str([s.magento_sku for s in self.simple_product_ids.with_context(active_test=False)]))
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
                'force_update': False,
                'magento_website_ids': [(5, 0, 0)]
            })

    def process_products_export_to_magento(self, single=0, status_check=False):
        """
        The main method to process Products Export to Magento. The Product Templates are treated as
        Configurable Products and Odoo Product Variants as Simple Products in Magento
        :param single: Odoo product Id in case of direct export from Odoo to Magento2 (omitting RabbitMQ) or 0
        :param status_check: Check(Update) Product(s) Export Status only, won't export Products
        :return: None
        """
        active_product_ids = single if single else self._context.get("active_ids", [])
        export_products = self.browse(active_product_ids)

        # create dict with "config_product_name: (attr_set, [related_simple_product_ids], {product_config_attributes})"
        # for each magento instance to process export by product categories and specified quantity (threshold)
        products_dict = {i.magento_instance_id: {} for i in export_products}
        for mag_inst in products_dict:
            products = export_products.filtered(lambda p: p.magento_instance_id.id == mag_inst.id and p.active)
            products_dict[mag_inst].update({
                conf.magento_sku: (
                    conf.magento_attr_set,
                    conf.simple_product_ids,
                    [a.name for a in conf.x_magento_assign_attrs]
                ) for conf in products
            })
        del export_products

        for mag_inst in products_dict:
            # create Attribute-sets dict which contains id/attribute(options) info received from Magento
            inst_dict = products_dict[mag_inst]
            prod_attibute_sets = {inst_dict[a][0] for a in inst_dict if inst_dict[a][0]}
            attr_sets = self.create_attribute_sets_dict(mag_inst, prod_attibute_sets)

            # check if config.product attributes passed the rules
            conf_attributes = []
            for prod in inst_dict:
                [conf_attributes.append(a) for a in inst_dict[prod][2]]
            conf_attributes = dict.fromkeys(conf_attributes, 0)
            self.check_configurable_attributes(mag_inst, conf_attributes, attr_sets)

            # proceed with products export
            export_products = []
            conf_products_list = list(inst_dict.keys())
            for conf_prod in conf_products_list:
                if export_products:
                    export_products += inst_dict[conf_prod][1]
                else:
                    export_products = inst_dict[conf_prod][1]

                if conf_prod != conf_products_list[-1] and len(export_products) < PRODUCTS_THRESHOLD:
                    continue
                else:
                    ml_conf_products_dict, ml_simp_products_dict = self.create_products_metadata_dict(
                        export_products, single, status_check
                    )
                    # get selected products from Magento(if any) and update meta-dict with Magento data
                    magento_conf_products = self.get_products_from_magento(mag_inst, ml_conf_products_dict)
                    for prod in magento_conf_products:
                        self.update_conf_product_dict_with_magento_data(prod, ml_conf_products_dict)
                    del magento_conf_products
                    magento_simp_products = self.get_products_from_magento(mag_inst, ml_simp_products_dict)
                    for prod in magento_simp_products:
                        export_products.update_simp_product_dict_with_magento_data(prod, ml_simp_products_dict)
                    del magento_simp_products

                    # check product's export statuses to define which product(s) need to be created/updated in Magento
                    self.check_config_products_to_export(ml_conf_products_dict, attr_sets)
                    export_products.check_simple_products_to_export(
                        export_products, ml_simp_products_dict, ml_conf_products_dict
                    )
                    if status_check:
                        self.save_magento_products_info_to_database(mag_inst.magento_website_ids, ml_simp_products_dict,
                                                                    ml_conf_products_dict, export_products, True)
                    else:
                        # check if product attributes of all selected Configurable Products exist in Magento
                        # and create new attribute options(swatch) if needed
                        self.check_conf_product_attributes_and_options_exist_in_magento(ml_conf_products_dict,
                                                                                        attr_sets)
                        self.process_config_products_create_or_update(mag_inst, ml_conf_products_dict, attr_sets, single)

                        # filter selected Odoo Product Variants to be exported to Magento
                        odoo_simp_prod = export_products.filtered(
                            lambda prd: prd.magento_sku in ml_simp_products_dict and
                                        ml_simp_products_dict[prd.magento_sku]['to_export'] is True and
                                        not ml_simp_products_dict[prd.magento_sku]['log_message']
                        )
                        # check if product attributes of all selected Simple Products exist in Magento
                        # log error when product has no attributes and create new attribute options(swatch) if needed
                        odoo_simp_prod.check_simp_product_attributes_and_options_exist_in_magento(
                            mag_inst, odoo_simp_prod, attr_sets, ml_simp_products_dict
                        )
                        odoo_simp_prod.check_simple_products_for_errors_before_export(
                            odoo_simp_prod, ml_simp_products_dict, ml_conf_products_dict, attr_sets
                        )
                        # process simple products update in Magento
                        products_to_update = []
                        for s in odoo_simp_prod:
                            if ml_simp_products_dict[s.magento_sku].get('magento_update_date', '') and \
                                    not ml_simp_products_dict[s.magento_sku]['log_message']:
                                products_to_update.append(s.magento_sku)
                        odoo_simp_prod.process_simple_products_create_or_update(
                            mag_inst, products_to_update, odoo_simp_prod, ml_simp_products_dict, attr_sets,
                            ml_conf_products_dict, single, 'PUT'
                        )
                        # process new simple products creation in Magento, assign attributes to config.products and link them
                        products_to_create = []
                        for s in odoo_simp_prod:
                            if not ml_simp_products_dict[s.magento_sku].get('magento_update_date') and \
                                    not ml_simp_products_dict[s.magento_sku]['log_message']:
                                products_to_create.append(s.magento_sku)
                        odoo_simp_prod.process_simple_products_create_or_update(
                            mag_inst, products_to_create, odoo_simp_prod, ml_simp_products_dict, attr_sets,
                            ml_conf_products_dict, single, 'POST'
                        )
                        # save data of export dates, magento statuses and log_messages to Db
                        self.save_magento_products_info_to_database(mag_inst.magento_website_ids, ml_simp_products_dict,
                                                                    ml_conf_products_dict, export_products, False)

                    export_products = []

    def create_attribute_sets_dict(self, magento_instance, attribute_sets):
        """
        Create Attribute-Sets dictionary for selected Products with Attribute ID and Attributes available in Magento
        :param magento_instance: Magento Instance
        :param attribute_sets: Python set of Product's 'Attribute-sets' defined in Product Categories
        :return: Attribute sets dictionary
        """
        attr_sets = {}.fromkeys(attribute_sets, {})

        for a_set in attr_sets:
            attr_sets[a_set].update({
                'id': self.get_attribute_set_id_by_name(magento_instance, a_set)
            })
            attr_sets[a_set].update({
                'attributes': self.get_available_attributes_from_magento(magento_instance, a_set, attr_sets)
            })
        return attr_sets

    def get_attribute_set_id_by_name(self, magento_instance, attribute_set_name, magento_entity_id=4):
        """
        Get Attribute ID from Magento by name defined in Odoo
        :param magento_instance: Instance of Magento
        :param attribute_set_name: Attribute-Set Name defined in Odoo Product's Category
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
        return False

    def get_available_attributes_from_magento(self, magento_instance, attribute_set_name, attr_sets):
        """
        Get available attributes and related options(swatches) from Magento
        :param magento_instance: Instance of Magento
        :param attribute_set_name: Attribute Set Name defined in Odoo Product's Category
        :param attr_sets: Attribute-Set dictionary with unique data for selected products
        :return: Available in Magento Attributes list and their options
        """
        attribute_set_id = attr_sets[attribute_set_name]['id']
        if attribute_set_id:
            available_attributes = []
            try:
                api_url = '/all/V1/products/attribute-sets/%s/attributes' % attribute_set_id
                response = req(magento_instance, api_url)
            except Exception:
                response = []

            # generate the list of available attributes and their options from Magento
            if response:
                for attr in response:
                    if attr.get('default_frontend_label'):
                        available_attributes.append({
                            "attribute_id": attr.get("attribute_id"),
                            "attribute_code": attr.get('attribute_code'),
                            'default_label': self.to_upper(attr.get('default_frontend_label')),
                            'options': attr.get('options'),
                            'can_be_configurable': True if attr.get('is_user_defined') else False
                        })
                return available_attributes
        return []

    def check_configurable_attributes(self, magento_instance, conf_attributes, attr_sets):

        avail_attributes = []
        for at_set in attr_sets:
            avail_attributes += attr_sets[at_set]['attributes']

        # find attribute_id in Magento available attributes (if not found = 0)
        conf_attributes = {k: self.get_attribute_id_by_name(avail_attributes, k) for k, v in conf_attributes.items()}

        # request each config.attribute from Magento separately
        for _id in conf_attributes.values():
            if _id:
                api_url = '/all/V1/products/attributes/%s' % _id
                try:
                    response = req(magento_instance, api_url)
                except Exception:
                    response = {}

                # check attribute scope (must be global)
                if response.get("scope") and response.get("scope") != 'global':
                    for at_set in attr_sets:
                        attr = next((a for a in attr_sets[at_set]['attributes'] if str(a['attribute_id']) == str(_id)), {})
                        attr['can_be_configurable'] = False

    def get_attribute_id_by_name(self, available_attributes, odoo_attribute):
        attr = next((a for a in available_attributes if self.to_upper(odoo_attribute) == a['default_label']), {})
        if attr:
            return attr.get('attribute_id')
        else:
            return 0

    def create_products_metadata_dict(self, export_products, single, status_check):
        """
        Create dictionary which contains metadata for selected Configurable(Odoo categories) and Simple Products
        :param export_products: Magento Layer's Odoo Product(s) to be exported
        :param single: In case of direct (Odoo-Magento) single product export - True, else - False
        :param status_check: If method runs in "check_status' mode
        :return: Configurable and Simple products dictionary
        """
        products_dict_conf = {
            c.magento_conf_prod_sku: {
                'conf_object': c.magento_conf_product_id,
                'config_attr': {a.name for a in c.magento_conf_product_id.x_magento_assign_attrs},
                'children': [],
                'magento_status': c.magento_conf_product_id.magento_status,
                'log_message': '',
                'force_update': c.magento_conf_product_id.force_update,
                'export_date_to_magento': c.magento_conf_product_id.magento_export_date,
                'to_export': False if c.magento_conf_product_id.odoo_prod_template.x_magento_no_create else True
            } for c in export_products
        }

        text = "Product Category is missing 'Magento Product SKU' field. \n"
        if single and not status_check:
            export_products.filtered(lambda prod: prod.magento_status == 'deleted').write({
                'magento_status': 'not_exported'
            })
        products_dict_simp = {
            s.magento_sku: {
                'conf_sku': s.magento_conf_prod_sku,
                'log_message': '' if s.magento_conf_prod_sku else text,
                'export_date_to_magento': s.magento_export_date,
                # 'latest_update_date': max(s.odoo_product_id.write_date, s.odoo_product_id.product_tmpl_id.write_date, s.update_date),
                'latest_update_date': max(s.odoo_product_id.write_date, s.odoo_product_id.product_tmpl_id.write_date),
                'conf_attributes': s.get_product_conf_attributes_dict(),
                'magento_status': s.magento_status,
                'do_not_export_conf': s.magento_conf_product_id.odoo_prod_template.x_magento_no_create,
                'product_categ': [],
                'force_update': s.force_update,
                'to_export': True
            } for s in export_products if s.magento_status != 'deleted'
        }

        return products_dict_conf, products_dict_simp

    def get_products_from_magento(self, magento_instance, ml_products_dict):
        """
        Get selected Products from Magento
        :param magento_instance: Instance of Magento
        :param ml_products_dict: Dictionary contains metadata for selected Simple/Configurable Products
        :return: List of Products from Magento
        """
        res = []
        step = 50
        cur_page = 0
        magento_sku_list = list(ml_products_dict)
        times = (len(magento_sku_list) // step) + (1 if len(magento_sku_list) % step else 0)
        for cnt in range(times):
            sku_list = ','.join(magento_sku_list[cur_page:step * (1 + cnt)])
            search_criteria = 'searchCriteria[filterGroups][0][filters][0][field]=sku&searchCriteria[filterGroups][0]' \
                              '[filters][0][condition_type]=in&searchCriteria[filterGroups][0][filters][0][value]=%s' % \
                              sku_list
            api_url = '/V1/products?%s' % search_criteria
            try:
                response = req(magento_instance, api_url)
            except Exception:
                for prod in magento_sku_list[cur_page:step * (1 + cnt)]:
                    text = "Error while requesting product from Magento.\n"
                    ml_products_dict[prod]['log_message'] += text
                cur_page += step
                continue

            res += (response.get('items', []))
            cur_page += step

        return res

    def check_config_products_to_export(self, ml_conf_products, attr_sets):
        """
        Check if Configurable Product Export to Magento needed
        :param ml_conf_products: Dictionary contains metadata for selected Configurable Products (Odoo categories)
        :param attr_sets: Attribute-Set dictionary with available in Magento Attributes info for selected products
        :return: None
        """
        for prod in ml_conf_products:
            if ml_conf_products[prod]['log_message']:
                ml_conf_products[prod]['to_export'] = False
                continue
            conf_obj = ml_conf_products[prod]['conf_object']
            mag_attr_set = conf_obj.magento_attr_set

            if not mag_attr_set:
                text = "Missed 'Magento Product Attribute Set' field in Product Category. \n"
                ml_conf_products[prod]['log_message'] += text
                ml_conf_products[prod]['to_export'] = False
                continue

            prod_attr_set_id = attr_sets[mag_attr_set]['id']
            if not prod_attr_set_id:
                text = "Error while getting attribute set id for - %s from Magento. \n" % mag_attr_set
                ml_conf_products[prod]['log_message'] += text
                ml_conf_products[prod]['to_export'] = False
                continue

            avail_attributes = attr_sets[mag_attr_set]['attributes']
            if not avail_attributes:
                text = "Error while getting attributes for - %s Attribute-Set from Magento. \n" % mag_attr_set
                ml_conf_products[prod]['log_message'] += text
                ml_conf_products[prod]['to_export'] = False
                continue

            if conf_obj.odoo_prod_template.x_magento_no_create:
                ml_conf_products[prod]['magento_status'] = 'no_need'
                continue

            prod_conf_attr = ml_conf_products[prod]['config_attr']
            if not prod_conf_attr:
                text = "Missed 'Configurable Attribute(s)' for %s configurable product.\n" % prod
                ml_conf_products[prod]['log_message'] += text
                continue

            for attr in conf_obj.x_magento_assign_attrs:
                if attr.is_ignored_in_magento:
                    text = "The '%s' attribute cannot be used in Configurable Product.\n" % attr.name
                    ml_conf_products[prod]['log_message'] += text
                    continue

            # apply compatible date format to compare Product's dates
            exp_date = ml_conf_products[prod]['export_date_to_magento']
            export_date = self.format_to_magento_date(exp_date)
            magento_date = ml_conf_products[prod].get('magento_update_date', '')

            if not export_date or conf_obj.force_update:
                if ml_conf_products[prod]['magento_status'] == 'in_magento':
                    ml_conf_products[prod]['magento_status'] = 'update_needed'
                continue

            if magento_date and magento_date >= export_date:
                if ml_conf_products[prod]['magento_type_id'] == 'configurable':
                    # check if product images need to be updated
                    magento_images = ml_conf_products[prod].get('media_gallery', [])
                    if conf_obj.odoo_prod_template and (len(magento_images) != len(conf_obj.product_images)):
                    # if prod_template and (len(magento_images) != (len(prod_template.product_template_image_ids) +
                    #                                              (1 if prod_template.image_256 else 0))):
                        ml_conf_products[prod]['magento_status'] = 'update_needed'
                        continue
                    # check if assign attribute(s) and attribute-set are the same in Magento and Odoo
                    if ml_conf_products[prod]['magento_attr_set_id'] == prod_attr_set_id:
                        mag_attr_options = ml_conf_products[prod]['magento_conf_prod_options']
                        check_assign_attr = self.check_config_product_assign_attributes_match(
                            mag_attr_options, prod_conf_attr, avail_attributes
                        )
                        if check_assign_attr:
                            ml_conf_products[prod]['to_export'] = False
                            ml_conf_products[prod]['magento_status'] = 'in_magento'
                            continue
                    if ml_conf_products[prod]['magento_status'] == 'in_magento':
                        ml_conf_products[prod]['magento_status'] = 'update_needed'
            elif ml_conf_products[prod]['magento_status'] not in ['log_error', 'in_process']:
                ml_conf_products[prod]['magento_status'] = 'update_needed'


    def update_conf_product_dict_with_magento_data(self, magento_prod, ml_conf_products_dict):
        """
        Update Conf.Products 'Meta-dictionary' with data from Magento
        :param magento_prod: Product dict received from Magento
        :param ml_conf_products_dict: Dictionary contains metadata for selected Configurable Products (Odoo categories)
        :return: None
        """
        attr_opt = magento_prod.get("extension_attributes").get("configurable_product_options")
        children = magento_prod.get("extension_attributes").get("configurable_product_links")
        link_data = magento_prod.get("extension_attributes").get("configurable_product_link_data")
        website_ids = magento_prod.get("extension_attributes").get("website_ids")
        category_links = magento_prod.get("extension_attributes").get("category_links", [])
        ml_conf_products_dict[magento_prod.get('sku')].update({
            'magento_type_id': magento_prod.get('type_id'),
            'magento_prod_id': magento_prod.get("id"),
            'magento_attr_set_id': magento_prod.get("attribute_set_id"),
            'magento_conf_prod_options': attr_opt,
            'children': children,
            'magento_website_ids': website_ids,
            'category_links': [cat['category_id'] for cat in category_links],
            'magento_configurable_product_link_data': self.convert_to_dict(link_data),
            'media_gallery': [i['id'] for i in magento_prod.get("media_gallery_entries", []) if i],
            'magento_update_date': magento_prod.get("updated_at")
        })

    def save_magento_products_info_to_database(self, magento_websites, ml_simp_products, ml_conf_products,
                                               export_products, status_check):
        """
        Save Products' export_dates, websites, magento_statuses and log_messages to database
        :param magento_websites: Magento available websites related to current instance
        :param ml_simp_products: Dictionary contains metadata for selected Simple Products (Odoo products)
        :param ml_conf_products: Dictionary contains metadata for selected Configurable Products (Odoo categories)
        :param export_products: Magento Layer's Odoo Product to be exported
        :param status_check: Check if method runs as status check (Boolean)
        :return: None
        """
        for c_prod in ml_conf_products:
            odoo_product = ml_conf_products[c_prod]['conf_object']
            if ml_conf_products[c_prod]['log_message']:
                ml_conf_products[c_prod]['magento_status'] = 'log_error'

            if ml_conf_products[c_prod]['magento_status'] == 'in_magento' and [
                p for p in ml_simp_products if ml_simp_products[p]['conf_sku'] == odoo_product.magento_sku and
                                               ml_simp_products[p]['magento_status'] != 'in_magento']:
                ml_conf_products[c_prod]['magento_status'] = 'update_needed'

            values = self.prepare_data_before_save(ml_conf_products, c_prod, odoo_product, magento_websites,
                                                   status_check)
            odoo_product.write(values)

        for s_prod in ml_simp_products:
            export_product = export_products.filtered(lambda prod: prod.magento_sku == s_prod)
            conf_sku = ml_simp_products[s_prod].get('conf_sku')

            if ml_simp_products[s_prod]['log_message']:
                ml_simp_products[s_prod]['magento_status'] = 'log_error'
                self.save_error_message_to_log_book(
                    ml_simp_products[s_prod]['log_message'],
                    ml_conf_products.get(conf_sku, {}).get('log_message', ''),
                    export_product.id
                )

            values = self.prepare_data_before_save(ml_simp_products, s_prod, export_product, magento_websites,
                                                   status_check)
            export_product.write(values)

    def prepare_data_before_save(self, ml_products, prod_sku, odoo_product, websites, status_check):
        mag_prod_websites = ml_products[prod_sku].get('magento_website_ids', [])
        odoo_websites = {str(p.magento_website_id) for p in odoo_product.magento_website_ids}

        values = {'magento_status': ml_products[prod_sku]['magento_status']}

        # assign Magento product id to Product in Magento Layer
        mag_prod_id = ml_products[prod_sku].get('magento_prod_id')
        if mag_prod_id:
            if str(mag_prod_id) != odoo_product.magento_product_id:
                values.update({'magento_product_id': mag_prod_id})
        elif odoo_product.magento_product_id:
            values.update({'magento_product_id': ''})

        # check if Product's website(s) are the same in Odoo ML and Magento (M2 has priority)
        if mag_prod_websites:
            if odoo_websites != set(mag_prod_websites):
                ids = [w.id for w in websites if str(w.magento_website_id) in mag_prod_websites]
                values.update({'magento_website_ids': [(6, 0, ids)]})
        elif odoo_websites:
            values.update({'magento_website_ids': [(5, 0, 0)]})

        # add product categories to Simple Products
        if ml_products[prod_sku].get('product_categ'):
            values.update({'category_ids': [(6, 0, ml_products[prod_sku]['product_categ'])]})

        if not status_check:
            if ml_products[prod_sku]['to_export']:
                values.update({'magento_export_date': ml_products[prod_sku]['export_date_to_magento']})

            if ml_products[prod_sku]['force_update'] and ml_products[prod_sku]['magento_status'] != 'log_error':
                ml_products[prod_sku]['force_update'] = False
                values.update({'force_update': False})

        if ml_products[prod_sku]['force_update']:
            values.update({'force_update': True})

        return values

    def save_error_message_to_log_book(self, simp_log_message, conf_log_message, product_id):
        """
        Save Product's Error Message to Product's log book
        :param simp_log_message: Simple Product log message
        :param conf_log_message: Conf.Product log message
        :param product_id: Id of Odoo product in Magento Layer
        :return: None
        """
        vals = {
            'magento_log_message': simp_log_message,
            'magento_log_message_conf': conf_log_message
        }
        log_book = self.env['magento.product.log.book'].search([('magento_product_id', '=', product_id)])
        if not len(log_book):
            vals.update({'magento_product_id': product_id})
            log_book.create(vals)
        else:
            log_book.write(vals)

    def check_conf_product_attributes_and_options_exist_in_magento(self, ml_product_dict, attribute_sets):
        """
        Check if Product's Attributes exist in Magento
        :param attribute_sets: Dictionary with defined Attributes and their options in Magento
        :param ml_product_dict: Dictionary contains metadata for selected Simple Products (Odoo products)
        :return: None
        """
        for prod in ml_product_dict:
            conf_prod = ml_product_dict[prod]['conf_object']
            available_attributes = attribute_sets[conf_prod.magento_attr_set]['attributes']
            prod_attributes = conf_prod.odoo_prod_template.categ_id.x_attribute_ids
            # create list of unique groups of product attributes to be used as attributes in magento
            prod_attr_list = list({a.categ_group_id.name for a in prod_attributes if a.categ_group_id})

            # logs if any of attributes are missed in Magento and creates new attr.option in Magento if needed
            for prod_attr in prod_attr_list:
                attr = next((a for a in available_attributes if a and self.to_upper(prod_attr) == a['default_label']), {})
                if not attr:
                    text = "Attribute - %s has to be created on Magento side and attached " \
                           "to Attribute Set.\n" % prod_attr
                    ml_product_dict[prod]['log_message'] += text

    def process_config_products_create_or_update(self, instance, ml_conf_products, attr_sets, single):
        """
        Process Configurable Products (Odoo Product Categories) creation or update in Magento
        :param instance: Magento Instance
        :param ml_conf_products: Dictionary contains metadata for selected Configurable Products (Odoo categories)
        :param attr_sets: Attribute-Set dictionary with available in Magento Attributes info for selected products
        :param single: In case of direct (Odoo-Magento) single product export - True, else - False
        :return: None
        """
        new_conf_products = []
        for prod in ml_conf_products:
            if not ml_conf_products[prod]['to_export'] or ml_conf_products[prod]['log_message']:
                continue
            mag_attr_set = ml_conf_products[prod]['conf_object'].magento_attr_set
            # prod_attr_set_id = attr_sets[mag_attr_set]['id']
            prod_attr_mag = attr_sets[mag_attr_set]['attributes']
            prod_conf_attr = ml_conf_products[prod]['config_attr']

            # check if Product's configurable attribute(s) exist in Magento
            available_attributes = [a['default_label'] for a in prod_attr_mag]
            conf_prod_attr = [self.to_upper(c) for c in prod_conf_attr if c]
            if not self.check_product_attr_are_in_attributes_list(available_attributes, conf_prod_attr):
                text = "Some of Configurable Product's attribute doesn't exist in Magento. " \
                       "It has to be created at first on Magento side.\n"
                ml_conf_products[prod]['log_message'] += text
                continue
            if not self.check_conf_attributes_can_be_configurable(conf_prod_attr, prod_attr_mag):
                text = "Some of Configurable Product's attribute can't be assigned as configurable in Magento. " \
                       "Make sure it has 'Global' scope and was created manually. "
                ml_conf_products[prod]['log_message'] += text
                continue

            # update (PUT) Conf.Product if it exists in Magento
            if ml_conf_products[prod].get('magento_update_date', ''):
                if ml_conf_products[prod]['magento_type_id'] != 'configurable':
                    text = "Product with the following sku - \"%s\" already exists in Magento. " \
                           "And it's type is not Configurable.\n" % prod
                    ml_conf_products[prod]['log_message'] += text
                # check if assign attributes are the same in Magento and Odoo
                mag_attr_options = ml_conf_products[prod]['magento_conf_prod_options']
                check_assign_attr = self.check_config_product_assign_attributes_match(
                    mag_attr_options, prod_conf_attr, attr_sets[mag_attr_set]['attributes']
                )
                conf_prod = self.export_single_conf_product_to_magento(
                    instance, prod, ml_conf_products, attr_sets, check_assign_attr, 'PUT'
                )
                # update magento data in ml_conf_products_dict, later will be used while linking with simple prod
                if conf_prod:
                    self.update_conf_product_dict_with_magento_data(conf_prod, ml_conf_products)
            else:
                new_conf_products.append(prod)

        # create (POST) new configurable products in Magento
        # if single - with regular API, else - via async request (RabbitMQ)
        if new_conf_products:
            if single:
                res = self.export_single_conf_product_to_magento(instance, new_conf_products[0], ml_conf_products,
                                                                 attr_sets)
                if res:
                    self.update_conf_product_dict_with_magento_data(res, ml_conf_products)
            else:
                self.export_new_conf_products_to_magento_in_bulk(instance, new_conf_products, ml_conf_products,
                                                                 attr_sets)

    def export_single_conf_product_to_magento(self, magento_instance, prod_sku, ml_conf_products, attr_sets,
                                              check_assign_attr=True, method='POST'):
        """
        Export to Magento Single Configurable Product
        :param magento_instance: Instance of Magento
        :param prod_sku: New Configurable Product SKU to be exported
        :param ml_conf_products: Dictionary contains metadata for selected Configurable Products (Odoo categories)
        :param attr_sets: Attribute set dictionary with unique data for selected products
        :param check_assign_attr: Assign attributes are the same in Odoo and Magento (Boolean)
        :param method Http method (POST/PUT)
        :return: Magento Product or empty dict
        """
        conf_product = ml_conf_products[prod_sku]['conf_object']
        categ_list = [cat.category_id for cat in conf_product.category_ids]
        lang_code = self.env['res.lang']._lang_get(self.env.user.lang).code
        custom_attributes = self.add_conf_product_attributes(conf_product, attr_sets, lang_code)

        data = {
            "product": {
                "name": str(conf_product.magento_product_name).upper(),
                "attribute_set_id": attr_sets[conf_product.magento_attr_set]['id'],
                "type_id": "configurable",
                "status": 1,  # Enabled (1) / Disabled (0)
                "visibility": 2,  # Catalog
                "custom_attributes": custom_attributes,
                "extension_attributes": {
                    "category_links": [{"position": 0, "category_id": cat_id} for cat_id in categ_list]
                }
            }
        }

        if method == 'POST':
            data['product'].update({
                "sku": prod_sku
            })

        # here if not True - means assign attributes were changed and will unlink all related simple products
        if not check_assign_attr:
            data['product']["extension_attributes"].update({"configurable_product_links": []})

        try:
            api_url = '/all/V1/products' if method == "POST" else '/all/V1/products/%s' % prod_sku
            response = req(magento_instance, api_url, method, data)
        except Exception:
            text = "Error while Config.Product %s in Magento.\n" % ('update' if method == "PUT" else "creation")
            ml_conf_products[prod_sku]['log_message'] += text
            return {}

        if response.get('sku'):
            if method == "POST":
                self.process_product_websites_export(magento_instance, ml_conf_products, prod_sku, response)

            # export data related to each storeview(product name/description)
            self.process_storeview_data_export(magento_instance, conf_product, ml_conf_products, prod_sku, data,
                                               attr_sets, True)

            if conf_product.odoo_prod_template:
                trigger = False
                if method == "PUT":
                    magento_images = ml_conf_products[prod_sku].get('media_gallery', [])
                    export_date_to_magento = ml_conf_products[prod_sku]['export_date_to_magento']
                    export_date_to_magento = export_date_to_magento or datetime.min
                    if conf_product.odoo_prod_template.write_date > export_date_to_magento or \
                            len(magento_images) != len(conf_product.product_images):
                            # len(magento_images) != (len(conf_product.product_images) + (1 if conf_product.odoo_prod_template.image_256 else 0)):
                        trigger = True
                        if len(magento_images):
                            self.remove_product_images_from_magento(magento_instance, ml_conf_products, prod_sku)

                if method =="POST" or trigger:
                    self.process_images_export_to_magento(magento_instance, ml_conf_products, prod_sku)

            ml_conf_products[prod_sku]['export_date_to_magento'] = response.get("updated_at")
            ml_conf_products[prod_sku]['magento_status'] = 'in_magento'
            return response
        return {}

    def export_new_conf_products_to_magento_in_bulk(self, magento_instance, new_conf_products, ml_conf_products, attr_sets):
        """
        Export(POST) to Magento new Configurable Products in bulk (asynchronously)
        :param magento_instance: Instance of Magento
        :param new_conf_products: List of new Configurable Products to be exported
        :param ml_conf_products: Dictionary contains metadata for selected Configurable Products (Odoo categories)
        :param attr_sets: Attribute set dictionary with unique data for selected products
        :return: None
        """
        data = []
        lang_code = self.env['res.lang']._lang_get(self.env.user.lang).code
        for prod in new_conf_products:
            conf_product = ml_conf_products[prod]['conf_object']
            categ_list = [cat.category_id for cat in conf_product.category_ids]
            custom_attributes = self.add_conf_product_attributes(conf_product, attr_sets, lang_code)

            data.append({
                "product": {
                    "sku": prod,
                    "name": str(conf_product.magento_product_name).upper(),
                    "attribute_set_id": attr_sets[conf_product.magento_attr_set]['id'],
                    "status": 1,  # enabled / disabled
                    "visibility": 2,  # Catalog.
                    "type_id": "configurable",
                    "custom_attributes": custom_attributes,
                    "extension_attributes": {
                        "category_links": [{"position": 0, "category_id": cat_id} for cat_id in categ_list]
                    }
                }
            })

        try:
            api_url = '/all/async/bulk/V1/products'
            response = req(magento_instance, api_url, 'POST', data)
        except Exception:
            for prod in new_conf_products:
                text = "Error while new Configurable Products creation in Magento. " \
                       "Please check if rabbitmq works properly.\n"
                ml_conf_products[prod]['log_message'] += text
            return

        if not response.get('errors', True):
            product_websites = []
            prod_media = {}
            # thumb_images = {}
            log_id = self.bulk_log_ids.create({
                'bulk_uuid': response.get("bulk_uuid"),
                'topic': 'Product Export'
            })

            for prod in new_conf_products:
                conf_product = ml_conf_products[prod]['conf_object']
                ml_conf_products[prod]['export_date_to_magento'] = datetime.now()
                ml_conf_products[prod]['magento_status'] = 'in_process'
                conf_product.write({'bulk_log_ids': [(6, 0, [log_id.id])]})

                # prepare websites export
                for site in magento_instance.magento_website_ids:
                    product_websites.append({
                        "productWebsiteLink": {"sku": prod, "website_id": site.magento_website_id},
                        "sku": prod
                    })

                # prepare images export
                if conf_product.odoo_prod_template:
                    # update product_media dict if product has images
                    if len(conf_product.product_images):
                        prod_media.update({
                            prod: [(img.id, img.name, getattr(img, IMG_SIZE), img.image_role)
                                   for img in conf_product.product_images if img]
                        })
                    # update if product has thumbnail image
                    # if config_prod.image_256:
                    #     thumb_images.update({prod: [(config_prod.id, '', config_prod.image_256)]})

            if product_websites:
                res = self.process_product_website_data_export_in_bulk(magento_instance, product_websites,
                                                                       new_conf_products, ml_conf_products)
                if not res.get('errors', True):
                    log_id = self.bulk_log_ids.create({
                        'bulk_uuid': res.get("bulk_uuid"),
                        'topic': 'Website info export'
                    })
                    for prod in new_conf_products:
                        ml_conf_products[prod]['conf_object'].write({'bulk_log_ids': [(4, log_id.id)]})

            self.process_conf_prod_storeview_data_export_in_bulk(magento_instance, data, attr_sets, ml_conf_products)

            if prod_media:
                self.export_media_to_magento_in_bulk(magento_instance, prod_media, ml_conf_products, 'product.image')
            # if thumb_images:
            #     self.export_media_to_magento_in_bulk(magento_instance, thumb_images, ml_conf_products,
            #                                          'product.public.category', True)

    def add_conf_product_attributes(self, conf_product, attr_sets, lang_code):
        custom_attributes = []
        available_attributes = attr_sets[conf_product.magento_attr_set]['attributes']
        prod_attributes = conf_product.odoo_prod_template.categ_id.x_attribute_ids
        prod_attr_list = list(
            {(a.categ_group_id.name, a.categ_group_id.id) for a in prod_attributes if a.categ_group_id})
        # add product's attributes
        for prod_attr in prod_attr_list:
            attr = next((a for a in available_attributes if a['default_label'] and
                         self.to_upper(prod_attr[0]) == a['default_label']), {})
            if attr:
                custom_attributes.append({
                    "attribute_code": attr['attribute_code'],
                    "value": self.to_html_listitem(
                        prod_attributes.filtered(lambda x: x.categ_group_id.id == prod_attr[1]), lang_code)
                })

        # add Product's Website Description
        if conf_product.odoo_prod_template.website_description:
            custom_attributes.append({
                "attribute_code": 'description',
                "value": conf_product.with_context(lang=lang_code).odoo_prod_template.website_description
            })

        # add main config attribute if any
        if conf_product.x_magento_main_config_attr:
            attr = next((a for a in available_attributes if a['default_label'] and
                         self.to_upper(conf_product.x_magento_main_config_attr.name) == a['default_label']), {})
            custom_attributes.append({
                "attribute_code": 'main_config_attribute',
                "value": attr.get('attribute_code', False)
            })

        return custom_attributes

    @staticmethod
    def process_product_websites_export(magento_instance, ml_products, prod_sku, product, method="POST"):
        # add all available Websites to Product in case of initial export
        website_ids = []
        data = {"productWebsiteLink": {"sku": prod_sku}}
        for site in magento_instance.magento_website_ids:
            data["productWebsiteLink"].update({"website_id": site.magento_website_id})
            try:
                api_url = '/V1/products/%s/websites' % prod_sku
                res = req(magento_instance, api_url, method, data)
                if res is True:
                    website_ids.append(site.magento_website_id)
            except Exception:
                text = "Error while adding website to product in Magento.\n"
                ml_products[prod_sku]['log_message'] += text

        if website_ids:
            product.get('extension_attributes', {'extension_attributes': {}}).update(
                {'website_ids': website_ids})

    def process_storeview_data_export(self, magento_instance, product, ml_products, prod_sku, data, attr_sets, is_config):
        product_price = 0
        text = ''
        magento_storeviews = [(w, w.store_view_ids) for w in magento_instance.magento_website_ids]

        if not is_config and magento_instance.catalog_price_scope == 'global':
            if not len(magento_instance.pricelist_id):
                text += "There are no pricelist(s) defined for '%s' instance.\n" % magento_instance.name
            else:
                product_price = magento_instance.pricelist_id.get_product_price(product.odoo_product_id, 1.0, False)

        for view in magento_storeviews:
            lang_code = view[1].lang_id.code
            if is_config:
                data['product']['name'] = str(product.with_context(lang=lang_code).odoo_prod_template.name).upper()
                data['product']['custom_attributes'] = self.add_conf_product_attributes(product, attr_sets, lang_code)
            else:
                # valid for simple products only
                data["product"]["name"] = product.with_context(lang=lang_code).odoo_product_id.name + ' ' +\
                                          ' '.join(product.attribute_value_ids.product_attribute_value_id.mapped('name'))

                # find description attribute to add translations for each storeview
                # descr_attr = next(
                #     (a for a in data["product"]["custom_attributes"] if a.get('attribute_code') == 'description'), {}
                # )
                # if descr_attr:
                #     descr_attr["value"] = product.with_context(lang=lang_code).odoo_product_id.website_description

                # apply product prices for each website
                if magento_instance.catalog_price_scope == 'website':
                    if not len(view[0].pricelist_id):
                        text += "There are no pricelist defined for '%s' website.\n" % view[0].name
                    else:
                        if view[0].magento_base_currency.id != view[0].pricelist_id.currency_id.id:
                            text += "Pricelist '%s' currency is different than Magento base currency " \
                                    "for '%s' website.\n" % (view[0].pricelist_id.name, view[0].name)
                            break
                        price_and_rule = view[0].pricelist_id.get_product_price_rule(product.odoo_product_id, 1.0, False)
                        product_price = 0 if price_and_rule[1] is False else price_and_rule[0]

                if product_price:
                    data["product"]["price"] = product_price
                else:
                    data["product"]["price"] = data["product"]["status"] = 0
                    if not text:
                        text += "There are no or '0' price defined for product in '%s' " \
                                "website price-lists.\n" % (view[0].name)
            try:
                api_url = '/%s/V1/products/%s' % (view[1].magento_storeview_code, prod_sku)
                req(magento_instance, api_url, 'PUT', data)
            except Exception:
                text = "Error while exporting product's data to '%s' store view.\n" % view[1].magento_storeview_code
                break

        if text:
            ml_products[prod_sku]['log_message'] += text
            ml_products[prod_sku]['force_update'] = True

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
                opt_dict.update({self.to_upper(attr_opt.get('label')): self.to_upper(attr_opt.get('value'))})
            link_data_dict.update({new_dict['simple_product_sku']: opt_dict})
        return link_data_dict

    def check_config_product_assign_attributes_match(self, mag_attr_options, conf_prod_assigned_attr, available_attributes):
        """
        Check if Config.Product (Product Category in Odoo) "assign" attributes are the same in Magento and Odoo
        :param mag_attr_options: Product Attributes defined as configurable in Magento
        :param available_attributes: Dictionary with available Attributes and their options in Magento
        :param conf_prod_assigned_attr: Product Attributes defined as configurable in Odoo
        :return: Boolean, True if the same, False if not
        """
        prod_attr_magento = {self.get_attribute_name_by_id(available_attributes, attr.get("attribute_id")) for attr in
                             mag_attr_options if attr}
        prod_attr_odoo = {self.to_upper(attr) for attr in conf_prod_assigned_attr if attr}
        if prod_attr_odoo == prod_attr_magento:
            return True
        return False

    def process_images_export_to_magento(self, magento_instance, ml_conf_products, magento_sku):
        # product images (Base)
        conf_prod = ml_conf_products[magento_sku]['conf_object']
        if len(conf_prod.product_images):
            prod_media = {
                magento_sku: [(img.id, img.name, getattr(img, IMG_SIZE), img.image_role)
                              for img in conf_prod.product_images if img]
            }
            self.export_media_to_magento(magento_instance, prod_media, ml_conf_products, 'product.image')
        # product images (Thumbnail)
        # if prod_template.image_256:
        #     thumb_image = {magento_sku: [(prod_template.id, '', prod_template.image_256)]}
        #     self.export_media_to_magento(magento_instance, thumb_image, ml_conf_products,
        #                                  'product.template', True)

    def export_media_to_magento(self, magento_instance, products_media, ml_products, res_model):
        """
        Export(POST) to Magento Product's Images
        :param magento_instance: Instance of Magento
        :param products_media: Dictionary with list of Product's Image tuples (img_id, img_name, img_bytecode)
        :param ml_products: Dictionary contains metadata for selected Conf/Simple Products
        :param res_model: Model to be referenced to find image in attachment model
        :return: None
        """
        images = {}
        prod_sku = list(products_media.keys())[0]
        for img in products_media[prod_sku]:
            role = img[3]
            attachment = self.env['ir.attachment'].sudo().search([
                ('res_field', '=', 'image_256' if role == 'thumbnail' else IMG_SIZE),
                ('res_model', '=', res_model),
                ('res_id', '=', img[0])
            ])
            if not len(attachment):
                continue
            images.update({
                "entry": {
                    "media_type": "image",
                    # "types": ["thumbnail"] if is_thumbnail else [],
                    "types": [role],
                    "disabled": "true" if role == 'thumbnail' else "false",
                    "label": img[1],
                    "content": {
                        "base64EncodedData": img[2].decode('utf-8'),
                        "type": attachment.mimetype,
                        "name": attachment.mimetype.replace("/", ".")
                    }
                }
            })
            try:
                api_url = '/all/V1/products/%s/media' % prod_sku
                req(magento_instance, api_url, 'POST', images)
            except Exception:
                ml_products[prod_sku]['force_update'] = True
                text = "Error while Product (%s) Images export to Magento.\n" % str(role)
                ml_products[prod_sku]['log_message'] += text

    @staticmethod
    def remove_product_images_from_magento(magento_instance, ml_products, magento_sku):
        for _id in ml_products[magento_sku]['media_gallery']:
            try:
                api_url = '/all/V1/products/%s/media/%s' % (magento_sku, _id)
                req(magento_instance, api_url, 'DELETE')
            except Exception:
                ml_products[magento_sku]['force_update'] = True
                text = "Error while Product Images remove from Magento. \n"
                ml_products[magento_sku]['log_message'] += text

    @staticmethod
    def process_product_website_data_export_in_bulk(magento_instance, product_websites, product_list, ml_products):
        try:
            api_url = '/async/bulk/V1/products/bySku/websites'
            res = req(magento_instance, api_url, 'POST', product_websites)
        except Exception:
            text = "Error while assigning website(s) to product in Magento"
            for prod_sku in product_list:
                ml_products[prod_sku]['log_message'] += text
            return {}
        return res

    def process_conf_prod_storeview_data_export_in_bulk(self, magento_instance, data, attr_sets, ml_conf_products):
        magento_storeviews = [(w, w.store_view_ids) for w in magento_instance.magento_website_ids]

        for view in magento_storeviews:
            data_lst = []
            lang_code = view[1].lang_id.code
            for product in data:
                sku = product['product']['sku']
                conf_prod = ml_conf_products[sku]['conf_object']
                prod = {
                    'product': {
                        'name': str(conf_prod.with_context(lang=lang_code).odoo_prod_template.name).upper(),
                        'sku': sku,
                        'custom_attributes': self.add_conf_product_attributes(conf_prod, attr_sets, lang_code)
                    }
                }
                data_lst.append(prod)

            try:
                api_url = '/%s/async/bulk/V1/products' % view[1].magento_storeview_code
                res = req(magento_instance, api_url, 'PUT', data_lst)
            except Exception:
                for product in data:
                    text = "Error while exporting products' data to '%s' store view.\n" % view[1].magento_storeview_code
                    ml_conf_products[product['product']['sku']]['log_message'] += text
                break

            if not res.get('errors', True):
                log_id = self.bulk_log_ids.create({
                    'bulk_uuid': res.get("bulk_uuid"),
                    'topic': 'Storeview-%s info export' % view[1].magento_storeview_code
                })
                for product in data:
                    sku = product['product']['sku']
                    ml_conf_products[sku]['conf_object'].write({'bulk_log_ids': [(4, log_id.id)]})

    def export_media_to_magento_in_bulk(self, magento_instance, products_media, ml_simp_products, res_model):
        """
        Export(POST) to Magento Product's Images in bulk (asynchronously)
        :param magento_instance: Instance of Magento
        :param products_media: Dictionary with Product Images added in Odoo
        :param ml_simp_products: Dictionary contains metadata for selected Simple Products (Odoo products)
        :param res_model: Model to be referenced to find image in attachment model
        :return: None
        """
        files_size = 0
        images = []
        last_prod = list(products_media)[-1]

        def process(images):
            try:
                api_url = '/all/async/bulk/V1/products/bySku/media'
                req(magento_instance, api_url, 'POST', images)
            except Exception:
                text = "Error while Product Images export to Magento in bulk. \n"
                for sku in {img["sku"] for img in images}:
                    if not ml_simp_products[sku]['log_message']:
                        ml_simp_products[sku]['force_update'] = True
                        ml_simp_products[sku]['log_message'] += text
            return [], 0

        for prod_sku in products_media:
            for img in products_media[prod_sku]:
                role = img[3]
                if ml_simp_products[prod_sku]['log_message']:
                    continue
                attachment = self.env['ir.attachment'].sudo().search([
                    ('res_field', '=', 'image_256' if role == 'thumbnail' else IMG_SIZE),
                    ('res_model', '=', res_model),
                    ('res_id', '=', img[0])
                ])
                if not len(attachment):
                    continue

                if files_size and files_size + attachment.file_size > MAX_SIZE_FOR_IMAGES:
                    images, files_size = process(images)

                images.append({
                    "entry": {
                        "media_type": "image",
                        # "types": ["thumbnail"] if is_thumbnail else [],
                        "types": [role],
                        "disabled": "true" if role == 'thumbnail' else "false",
                        "label": img[1],
                        "content": {
                            "base64EncodedData": img[2].decode('utf-8'),
                            "type": attachment.mimetype,
                            "name": attachment.mimetype.replace("/", ".")
                        }
                    },
                    "sku": prod_sku
                })
                files_size += attachment.file_size

                # valid for the last image of last product
                if prod_sku == last_prod and img == products_media[prod_sku][-1]:
                    images, files_size = process(images)

    @staticmethod
    def get_attribute_name_by_id(available_attributes, attr_id):
        """
        Get Attribute Name by it's Id
        :param available_attributes: List with available in Magento Product Attributes
        :param attr_id: Attribute's Id
        :return: Attribute's Name or None
        """
        for attr in available_attributes:
            if str(attr.get('attribute_id')) == str(attr_id):
                return attr.get('default_label')

    @staticmethod
    def to_upper(val):
        if val:
            return "".join(str(val).split()).upper()
        else:
            return val

    @staticmethod
    def check_product_attr_are_in_attributes_list(attributes_list, prod_attrs):
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

    @staticmethod
    def check_conf_attributes_can_be_configurable(conf_prod_attributes, product_attributes_in_magento):
        for attr_name in conf_prod_attributes:
            attr = next((a for a in product_attributes_in_magento if str(a['default_label']) == attr_name), {})
            if not attr['can_be_configurable']:
                return False
        return True

    @staticmethod
    def to_html_listitem(attributes, lang_code):
        lst = '<ul>'
        for attr in attributes.sorted('sequence'):
            if attr['attribute_value']:
               lst += "<li>" + attr.with_context(lang=lang_code)['attribute_value'] + "</li>"
        return lst + "</ul>"

    def process_manually(self):
        """
        Process Product's Export (create/update) with regular Magento API process (without RabbitMQ)
        :return: None
        """
        self.ensure_one()
        self.process_products_export_to_magento(self.id)

    def status_check_of_export(self):
        """
        Check (Update) Product(s) Export Status
        """
        status_check = self.env.context.get("status_check", False)
        single = self.env.context.get("single", False)
        self.process_products_export_to_magento(self.id if single else 0, status_check)

    @staticmethod
    def format_to_magento_date(odoo_date):
        if odoo_date:
            return datetime.strftime(odoo_date, MAGENTO_DATETIME_FORMAT)
        else:
            return ""