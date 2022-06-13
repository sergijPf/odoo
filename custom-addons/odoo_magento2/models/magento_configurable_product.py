# -*- coding: utf-8 -*-

import json, re

from datetime import datetime
from odoo import fields, models, api
from odoo.exceptions import UserError
from ..python_library.php import Php
from ..python_library.api_request import req, create_search_criteria

PRODUCTS_BATCH = 250
MAX_SIZE_FOR_IMAGES = 2500000  # should be aligned with MYSQL - max_allowed_packet (currently 4M), !!! NOTE 4M is
                               # converted size and constant value is before convertion


class MagentoConfigurableProduct(models.Model):
    _name = 'magento.configurable.product'
    _description = 'Magento Configurable Product'
    _rec_name = 'magento_product_name'

    magento_instance_id = fields.Many2one('magento.instance', 'Magento Instance',
                                          help="This field relocates magento instance")
    magento_sku = fields.Char(string="Magento Conf.Product SKU")
    magento_website_ids = fields.Many2many('magento.website', string='Magento Product Websites', readonly=False,
                                           domain="[('magento_instance_id','=',magento_instance_id)]")
    magento_status = fields.Selection([
        ('not_exported', 'not Exported'),
        ('in_process', 'In Process'),
        ('update_needed', 'Need to Update'),
        ('extra_info', 'Extra info needed'),
        ('in_magento', 'In Magento'),
        ('no_need', 'Not needed'),
        ('log_error', 'Error to Export'),
    ], string='Export Status', help='The status of Configurable Product Export to Magento ', default='not_exported')
    image_1920 = fields.Image(related="odoo_prod_template_id.image_1920")
    is_enabled = fields.Boolean(string="Is Enabled in Magento?", default=False)
    product_image_ids = fields.One2many(related="odoo_prod_template_id.product_template_image_ids")
    magento_product_id = fields.Char(string="Magento Product Id")
    active = fields.Boolean("Active", default=True)
    odoo_prod_template_id = fields.Many2one('product.template', string='Odoo Product Template')
    magento_product_name = fields.Char(string="Magento Configurable Product Name", related='odoo_prod_template_id.name')
    category_ids = fields.Many2many("magento.product.category", string="Product Categories", store=True,
                                    help="Magento Product Categories", compute="_compute_config_product_categories")
    magento_attr_set = fields.Char(string='Magento Product Attribute Set', default="Default")
    do_not_create_flag = fields.Boolean(related="odoo_prod_template_id.x_magento_no_create",
                                        string="Don't create Product in Magento")
    x_magento_assign_attr_ids = fields.Many2many('product.attribute', string="Configurable Attribute(s)",
                                                 compute="_compute_configurable_product_attributes", store=True)
    x_magento_main_config_attr = fields.Char(string="Hover Attribute", compute="_compute_configurable_product_attributes",
                                             help="Configurable Attribute to be visible while hovering on Product",
                                             store=True)
    x_magento_single_attr_ids = fields.Many2many('product.template.attribute.line',
                                                 string="Config.Product's Single Attribute(s)",
                                                 compute="_compute_single_attributes_of_configurable_product")
    magento_export_date = fields.Datetime(string="Last Export Date", help="Config.Product last Export Date to Magento")
    force_update = fields.Boolean(string="Force export", help="Force run of Configurable Product Export", default=False)
    simple_product_ids = fields.One2many('magento.product.product', 'magento_conf_product_id', 'Magento Products',
                                         required=True, context={'active_test': False})
    product_simple_count = fields.Integer('Simple Products #', compute='_compute_magento_product_simple_count')
    product_variant_count = fields.Integer('Simple Products #', related='odoo_prod_template_id.product_variant_count')
    sipmle_count_equal = fields.Boolean("Is product count equal?", compute='_compute_simple_and_variant_count_equal')
    bulk_log_ids = fields.Many2many('magento.async.bulk.logs', string="Async Bulk Logs")
    related_product_ids = fields.Many2many('magento.configurable.product', 'related_products_rel', 'src_id', 'dest_id',
                                           string="Related Products", compute="_compute_related_products")
    cross_sell_product_ids = fields.Many2many('magento.configurable.product', 'cross_sell_products_rel', 'src_id',
                                              'dest_id', string="Cross-Sell Products", compute="_compute_cross_sell_products")
    product_label_ids = fields.Many2many("magento.product.label", string="Product Labels",
                                         help="Product labels to be marked on Product on Magento's frontpage")
    issue = fields.Char('Issue with product', compute="_check_config_product_has_issues")

    _sql_constraints = [('_magento_conf_product_unique_constraint',
                         'unique(magento_sku,magento_instance_id)',
                         "Magento Configurable Product SKU must be unique within Magento instance")]

    @api.depends('odoo_prod_template_id.attribute_line_ids')
    def _compute_configurable_product_attributes(self):
        for rec in self:
            prod_attr_lines = rec.odoo_prod_template_id.attribute_line_ids
            ### recalculate config.attributes
            rec.x_magento_assign_attr_ids = prod_attr_lines.filtered(
                lambda x: x.magento_config and not x.attribute_id.is_ignored_in_magento).attribute_id
            ### recalc main config.(hover) attr
            line = prod_attr_lines.with_context(lang='en_US').filtered(lambda x: x.magento_config and x.main_conf_attr)
            line = line[0] if len(line) > 1 else line
            rec.x_magento_main_config_attr = line.attribute_id.name if line else ''

    @api.depends('odoo_prod_template_id.attribute_line_ids')
    def _compute_single_attributes_of_configurable_product(self):
        for rec in self:
            rec.x_magento_single_attr_ids = rec.odoo_prod_template_id.attribute_line_ids.filtered(
                lambda x: not x.magento_config and not x.attribute_id.is_ignored_in_magento and len(x.value_ids) == 1)

    @api.depends('odoo_prod_template_id.public_categ_ids')
    def _compute_config_product_categories(self):
        for rec in self:
            public_categs = rec.odoo_prod_template_id.public_categ_ids
            if public_categs and public_categs.magento_prod_categ_ids:
                rec.category_ids = public_categs.magento_prod_categ_ids.filtered(
                    lambda x: x.instance_id == rec.magento_instance_id
                ).ids
            else:
                rec.category_ids = False

    @api.depends('simple_product_ids')
    def _compute_magento_product_simple_count(self):
        for template in self:
            # do not pollute variants to be prefetched when counting variants
            template.product_simple_count = len(template.with_prefetch().simple_product_ids)

    @api.depends('product_simple_count', 'product_variant_count')
    def _compute_simple_and_variant_count_equal(self):
        for rec in self:
            rec.sipmle_count_equal = True if rec.product_simple_count == rec.product_variant_count else False

    @api.depends('odoo_prod_template_id.alternative_product_ids', 'odoo_prod_template_id.accessory_product_ids', 'do_not_create_flag')
    def _compute_related_products(self):
        for rec in self:
            alternatives = rec.odoo_prod_template_id.alternative_product_ids.magento_conf_prod_ids.filtered(
                lambda x: x.magento_instance_id.id == rec.magento_instance_id.id and not x.do_not_create_flag)
            accessories = rec.odoo_prod_template_id.accessory_product_ids.magento_conf_prod_ids.filtered(
                lambda x: x.magento_instance_id.id == rec.magento_instance_id.id and not x.do_not_create_flag)

            rec.related_product_ids = [(6, 0, (alternatives + accessories).ids)]

    @api.depends('odoo_prod_template_id.optional_product_ids', 'do_not_create_flag')
    def _compute_cross_sell_products(self):
        for rec in self:
            rec.cross_sell_product_ids = [
                (6, 0, rec.odoo_prod_template_id.optional_product_ids.magento_conf_prod_ids.filtered(
                    lambda x: x.magento_instance_id.id == rec.magento_instance_id.id and not x.do_not_create_flag).ids)]

    @api.depends('magento_product_id', 'is_enabled', 'magento_website_ids')
    def _check_config_product_has_issues(self):
        for prod in self:
            prod.issue = ''
            if prod.magento_product_id:
                if not prod.is_enabled:
                    prod.issue = "Disabled in Magento. "
                if not prod.magento_website_ids:
                    prod.issue += "No websites linked to product."

    def write(self, vals):
        if 'magento_attr_set' in vals or 'product_label_ids' in vals:
            vals.update({'force_update': True})

        if 'active' in vals:
            for rec in self:
                if rec.magento_product_id:
                    raise UserError("You're not able to archive product until it is in Magento. Please delete it first!")
                if rec.simple_product_ids:
                    rec.simple_product_ids.write({'active': vals["active"]})

        return super(MagentoConfigurableProduct, self).write(vals)

    def unlink(self):
        to_reject = []
        [to_reject.append(prod.magento_sku) for prod in self if
         len(prod.simple_product_ids.with_context(active_test=False)) or prod.magento_product_id]

        if to_reject:
            raise UserError("You can't remove these Product(s) until they are in Magento and have related Simple "
                            "Products: %s" % str(to_reject))

        return super(MagentoConfigurableProduct, self).unlink()

    def get_list_of_product_variants(self):
        tree_view = self.env.ref('product.product_product_tree_view').id

        return {
            'name': 'Product Variants',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'tree',
            'res_model': 'product.product',
            'views': [(tree_view, 'tree')],
            'view_id': tree_view,
            'target': 'current',
            'domain': [("product_tmpl_id", "=", self.odoo_prod_template_id.id)]
        }

    def delete_product_in_magento(self, simple_product=False):
        self.ensure_one()

        if not simple_product:
            related_simple_prods = self.simple_product_ids.with_context(active_test=False).filtered(
                lambda x: x.magento_product_id)

            for simp_prod in related_simple_prods:
                simp_prod.delete_simple_product_in_magento()

        try:
            magento_sku = simple_product.magento_sku if simple_product else self.magento_sku
            instance = simple_product.magento_instance_id if simple_product else self.magento_instance_id

            api_url = '/V1/products/%s' % magento_sku
            response = req(instance, api_url, 'DELETE')
        except Exception as err:
            raise UserError("Error while delete product in Magento. " + str(err))

        if response is True:
            prod_rec = simple_product if simple_product else self
            prod_rec.write({
                'magento_status': 'not_exported',
                'magento_product_id': '',
                'magento_export_date': '',
                'is_enabled': False,
                'force_update': False,
                'magento_website_ids': [(5, 0, 0)],
                'bulk_log_ids': [(5, 0, 0)]
            })

    def processing_products_export_to_magento(self, update_export_statuses=False, is_cron=False):
        """
        The main method to process Products Export to Magento. The Product Templates are treated as
        Configurable Products and Odoo Product Variants as Simple Products in Magento
        """
        active_products = self._context.get("active_ids", []) or [self.id]

        if update_export_statuses:
            processing_products = self.browse(active_products) if active_products else self.search([])
        else:
            async_export = self.env.context.get("async_export", False)
            self.check_async_export_can_be_processed() if async_export else self.check_direct_export_can_be_processed(active_products)
            processing_products = self.browse(active_products)

        for instance in processing_products.magento_instance_id:
            conf_product_recs = processing_products.filtered(
                lambda x: x.magento_instance_id.id == instance.id and x.simple_product_ids.filtered(lambda x: x.active)
            )
            attribute_sets = {prod.magento_attr_set for prod in conf_product_recs}
            attr_sets_dict = self.create_attribute_sets_dict(instance, attribute_sets)
            self.check_conf_attributes_can_be_configurable(instance, conf_product_recs, attr_sets_dict)

            simple_product_recs = self.env['magento.product.product']

            for conf_prod in conf_product_recs:
                products = conf_prod.simple_product_ids.filtered(lambda x: x.active)
                if simple_product_recs:
                    simple_product_recs += products
                else:
                    simple_product_recs = products

                if conf_prod != conf_product_recs[-1] and len(simple_product_recs) < PRODUCTS_BATCH:
                    continue
                else:
                    conf_prods_dict, simp_prods_dict = self.configure_products_metadata_dicts(
                        instance, simple_product_recs, attr_sets_dict, update_export_statuses
                    )

                    if not update_export_statuses:
                        self.process_configurable_products_create_or_update(
                            instance, conf_prods_dict, attr_sets_dict, async_export
                        )
                        simple_product_recs.process_simple_products_export(
                            instance, attr_sets_dict, conf_prods_dict, simp_prods_dict, async_export
                        )

                    simple_product_recs.save_magento_products_info_to_database(
                        instance, conf_prods_dict, simp_prods_dict, update_export_statuses, is_cron
                    )

                    simple_product_recs = self.env['magento.product.product']

    def check_async_export_can_be_processed(self):
        async_bulk_logs_obj = self.env['magento.async.bulk.logs']
        async_bulk_logs_obj.clear_invalid_records()

        bulk_logs = async_bulk_logs_obj.search([])
        latest_bulk_log = bulk_logs and bulk_logs[-1]

        if latest_bulk_log and latest_bulk_log.check_bulk_log_status():
            raise UserError("There are some API requests still processing by RabbitMQ. "
                            "Please wait a bit until it completes or run Direct Export.")

    @staticmethod
    def check_direct_export_can_be_processed(active_prods):
        if len(active_prods) > 10:
            raise UserError("You can't export directly more than 10 products at once. Please use async export instead.")

    def create_attribute_sets_dict(self, magento_instance, attribute_sets):
        """
        Create Attribute-Sets dictionary for selected Products with Attribute ID and Attributes available in Magento
        """
        attr_sets_dict = {}.fromkeys(attribute_sets, {})

        for attr_set in attr_sets_dict:
            attr_sets_dict[attr_set].update({'id': self.get_id_of_attribute_set_by_name(magento_instance, attr_set)})

            attr_sets_dict[attr_set].update({
                'attributes': self.get_available_attributes_from_magento(magento_instance, attr_sets_dict[attr_set]['id'])
            })

        return attr_sets_dict

    @staticmethod
    def get_id_of_attribute_set_by_name(magento_instance, attribute_set_name, magento_entity_id=4):
        search_criteria = create_search_criteria({
            'attribute_set_name': attribute_set_name,
            'entity_type_id': magento_entity_id
        })
        query_string = Php.http_build_query(search_criteria)
        api_url = '/V1/eav/attribute-sets/list?%s' % query_string
        try:
            response = req(magento_instance, api_url)
        except Exception:
            response = {}

        if response.get('items'):
            return response.get('items')[0].get('attribute_set_id')
        return False

    def get_available_attributes_from_magento(self, magento_instance, attribute_set_id):
        available_attributes = {}

        if attribute_set_id:
            try:
                api_url = '/all/V1/products/attribute-sets/%s/attributes' % attribute_set_id
                response = req(magento_instance, api_url)
            except Exception:
                response = []

            if response:
                [available_attributes.update({
                    self.to_upper(attr.get('default_frontend_label')): {
                        'attribute_id': attr.get('attribute_id'),
                        'attribute_code': attr.get('attribute_code'),
                        'frontend_input': attr.get('frontend_input'),
                        'options': attr.get('options'),
                        'can_be_configurable': True if attr.get('is_user_defined') else False
                    }
                }) for attr in response if attr.get('default_frontend_label')]

        return available_attributes

    def check_conf_attributes_can_be_configurable(self, magento_instance, configurable_products, attr_sets_dict):
        conf_attr_names = {a.with_context(lang='en_US').name for a in configurable_products.x_magento_assign_attr_ids}

        # for the case when multiple Attribute sets applied within one instance (Default, etc)
        all_avail_attributes = {}
        for attr_set in attr_sets_dict:
            all_avail_attributes.update(attr_sets_dict[attr_set]['attributes'])

        for attr_name in conf_attr_names:
            attr_upper = self.to_upper(attr_name)
            if attr_upper in all_avail_attributes:
                api_url = '/all/V1/products/attributes/%s' % all_avail_attributes[attr_upper]['attribute_id']
                try:
                    response = req(magento_instance, api_url)
                except Exception:
                    response = {}

                if response.get("scope", False) != 'global':
                    for attr_set in attr_sets_dict:
                        if attr_upper in attr_sets_dict[attr_set]['attributes']:
                            attr_sets_dict[attr_set]['attributes'][attr_upper]['can_be_configurable'] = False

    def configure_products_metadata_dicts(self, instance, simple_products, attr_sets, update_export_statuses):
        conf_products_dict, simp_products_dict = self.create_metadata_dict(simple_products)

        # get selected products info from Magento(if any) and update meta-dict with Magento data
        [self.update_conf_product_dict_with_magento_data(prod, conf_products_dict)
         for prod in self.get_products_from_magento(instance, conf_products_dict)]

        [simple_products.update_simple_product_dict_with_magento_data(prod, simp_products_dict)
         for prod in self.get_products_from_magento(instance, simp_products_dict)]

        # check product's export statuses to define which product(s) need to be created/updated in Magento
        self.check_config_products_for_errors_and_update_export_statuses(conf_products_dict, attr_sets)

        simple_products.check_simple_products_for_errors_and_update_export_statuses(
            conf_products_dict, simp_products_dict, attr_sets, update_export_statuses
        )

        return conf_products_dict, simp_products_dict

    def create_metadata_dict(self, export_products):
        """
        Create dictionary which contains metadata for selected Configurable Products and related Simple Products
        :param export_products: Odoo Product(s) in Magento Layer to be exported
        :return: Configurable and Simple products dictionaries
        """
        configurable_products = {c for c in export_products.magento_conf_product_id}

        conf_products_dict = {
            str(c.magento_sku): {
                'conf_prod_rec': c,
                'config_attr': {self.to_upper(a.name) for a in c.with_context(lang='en_US').x_magento_assign_attr_ids},
                'children': [],
                'magento_status': c.magento_status,
                'log_message': '',
                'force_update': c.force_update,
                'export_date_to_magento': '',
                'to_export': False if c.do_not_create_flag else True
            } for c in configurable_products
        }

        text = "Configurable Product is missing 'Magento Product SKU' field. "
        simp_products_dict = {
            str(s.magento_sku): {
                'simple_prod_rec': s,
                'log_message': '' if s.magento_conf_prod_sku else text,
                'export_date_to_magento': '',
                'magento_status': s.magento_status,
                'force_update': s.force_update,
                'to_export': True
            } for s in export_products
        }

        return conf_products_dict, simp_products_dict

    @staticmethod
    def get_products_from_magento(magento_instance, ml_products_dict):
        res = []
        step = 20
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
            except Exception as e:
                for prod in magento_sku_list[cur_page:step * (1 + cnt)]:
                    text = "Error while requesting product from Magento. " + str(e)
                    ml_products_dict[prod]['log_message'] += text
                cur_page += step
                continue

            res += (response.get('items', []))
            cur_page += step

        return res

    def update_conf_product_dict_with_magento_data(self, magento_prod, ml_conf_products_dict):
        attr_opt = magento_prod.get("extension_attributes").get("configurable_product_options")
        children = magento_prod.get("extension_attributes").get("configurable_product_links")
        link_data = magento_prod.get("extension_attributes").get("configurable_product_link_data")
        website_ids = magento_prod.get("extension_attributes").get("website_ids")
        category_links = magento_prod.get("extension_attributes").get("category_links", [])

        ml_conf_products_dict[magento_prod.get('sku')].update({
            'magento_type_id': magento_prod.get('type_id'),
            'magento_prod_id': magento_prod.get("id"),
            'is_magento_enabled': True if magento_prod.get('status') == 1 else False,
            'magento_attr_set_id': magento_prod.get("attribute_set_id"),
            'magento_conf_prod_options': attr_opt,
            'children': children,
            'magento_website_ids': website_ids,
            'category_links': [cat['category_id'] for cat in category_links],
            'magento_configurable_product_link_data': self.convert_json_to_dict(link_data),
            'media_gallery': [i['id'] for i in magento_prod.get("media_gallery_entries", []) if i],
            'magento_update_date': magento_prod.get("updated_at"),
            'product_links_cnt': len(magento_prod.get("product_links", []))
        })

    def check_config_products_for_errors_and_update_export_statuses(self, ml_conf_products, attr_sets):
        for prod in ml_conf_products:
            if ml_conf_products[prod]['log_message']:
                continue

            conf_prod = ml_conf_products[prod]['conf_prod_rec']
            magento_attr_set = conf_prod.magento_attr_set
            prod_attr_set_id = attr_sets.get(magento_attr_set, {}).get('id')
            avail_attributes = attr_sets.get(magento_attr_set, {}).get('attributes')
            conf_prod_attr = ml_conf_products[prod]['config_attr']

            if not magento_attr_set:
                text = "Missed 'Magento Product Attribute Set' field for Config.Product. \n"
                ml_conf_products[prod]['log_message'] += text
                continue

            if not prod_attr_set_id:
                text = "Error while getting attribute set id for - %s from Magento. \n" % magento_attr_set
                ml_conf_products[prod]['log_message'] += text
                continue

            if not avail_attributes:
                text = "Error while getting attributes for - %s Attribute-Set from Magento. \n" % magento_attr_set
                ml_conf_products[prod]['log_message'] += text
                continue

            if conf_prod.do_not_create_flag:
                ml_conf_products[prod]['magento_status'] = 'no_need'
                continue

            if not conf_prod_attr:
                text = "Configurable Product has no configurable(assign) attributes defined. \n"
                ml_conf_products[prod]['log_message'] += text
                continue

            instance = conf_prod.magento_instance_id
            if not conf_prod.check_config_product_attributes(instance, ml_conf_products, avail_attributes, conf_prod_attr):
                continue

            if conf_prod.force_update:
                if ml_conf_products[prod]['magento_status'] in ['in_magento', 'extra_info']:
                    ml_conf_products[prod]['magento_status'] = 'update_needed'
                continue

            if ml_conf_products[prod].get('magento_update_date', ''):
                if ml_conf_products[prod]['magento_type_id'] == 'configurable':
                    # check if product images need to be updated
                    magento_images = ml_conf_products[prod].get('media_gallery', [])
                    prod_images = conf_prod.product_image_ids
                    thumb_image = conf_prod.image_1920

                    if len(magento_images) != (len(prod_images) + (1 if thumb_image else 0)):
                        ml_conf_products[prod]['magento_status'] = 'update_needed'
                        continue

                    # check if configurable attribute(s) and attribute-set are the same in Magento and Odoo
                    if ml_conf_products[prod]['magento_attr_set_id'] == prod_attr_set_id:
                        magento_attrs = ml_conf_products[prod]['magento_conf_prod_options']
                        if not self.check_config_product_assign_attributes_match(magento_attrs, conf_prod_attr, avail_attributes):
                            ml_conf_products[prod]['magento_status'] = 'update_needed'
                            continue
                    else:
                        text = 'Attribute set for current product is different in Odoo and Magento. '
                        ml_conf_products[prod]['log_message'] += text
                        continue

                    # check related products:
                    if ml_conf_products[prod]['product_links_cnt'] != \
                            (len(conf_prod.related_product_ids) + len(conf_prod.cross_sell_product_ids)):
                        ml_conf_products[prod]['magento_status'] = 'extra_info'
                    else:
                        ml_conf_products[prod]['magento_status'] = 'in_magento'

                    ml_conf_products[prod]['to_export'] = False

                else:
                    text = "Product with such sku already exists in Magento. And it's type is not configurable. "
                    ml_conf_products[prod]['log_message'] += text
            elif ml_conf_products[prod]['magento_status'] == 'in_magento':
                    ml_conf_products[prod]['magento_status'] = 'update_needed'

    def process_configurable_products_create_or_update(self, instance, ml_conf_products, attr_sets, async_export):
        new_conf_prods_list = []

        for sku in ml_conf_products:
            if not ml_conf_products[sku]['to_export'] or ml_conf_products[sku]['log_message']:
                continue

            conf_prod = ml_conf_products[sku]['conf_prod_rec']
            conf_prod.bulk_log_ids = [(5, 0, 0)]

            if ml_conf_products[sku].get('magento_update_date'):
                result = conf_prod.export_single_conf_product_to_magento(ml_conf_products, attr_sets, 'PUT')
            else:
                if async_export:
                    result = False
                    new_conf_prods_list.append(sku)
                else:
                    result = conf_prod.export_single_conf_product_to_magento(ml_conf_products, attr_sets)

            if result and isinstance(result, dict):
                self.update_conf_product_dict_with_magento_data(result, ml_conf_products)

        if new_conf_prods_list:
            self.export_new_conf_products_to_magento_in_bulk(instance, new_conf_prods_list, ml_conf_products, attr_sets)

    def check_config_product_attributes(self, instance, ml_conf_products, magento_attributes, config_attrs):
        sku = self.magento_sku
        pp_attrs = self.odoo_prod_template_id.categ_id.x_attribute_ids
        prod_page_attrs = list({
            self.to_upper(a.with_context(lang='en_US').categ_group_id.name) for a in pp_attrs if a.categ_group_id
        })
        single_attr_recs = self.with_context(lang='en_US').x_magento_single_attr_ids
        single_attrs_list = list({self.to_upper(a.attribute_id.name) for a in single_attr_recs})
        product_label = ['PRODUCTLABELS'] if self.product_label_ids else []

        # if self.odoo_prod_template_id.x_status:
        #     single_attrs.update({
        #         "PRODUCTLIFEPHASE": self.with_context(lang='en_US').odoo_prod_template_id.x_status
        #     })

        missed_attrs = set(
            list(config_attrs) + prod_page_attrs + single_attrs_list + product_label).difference(magento_attributes)
        if missed_attrs:
            text = "Attribute(s) - '%s' have to be manually created and linked to relevant Attribute-set" \
                   " on Magento side. \n" % missed_attrs
            ml_conf_products[sku]['log_message'] += text
            return False

        # check conf.attributes can be configurable
        failed_config = list(filter(lambda a: not magento_attributes[a]['can_be_configurable'], config_attrs))
        if failed_config:
            text = "The attribute(s): %s can't be assigned as configurable in Magento. " \
                   "Make sure each of it has 'Global' scope and was created manually. \n" % (str(failed_config))
            ml_conf_products[sku]['log_message'] += text
            return False

        # check attribute options exist in Magento
        for attribute in single_attrs_list:
            mag_attr = magento_attributes[attribute]
            attr_vals = single_attr_recs.filtered(lambda x: self.to_upper(x.attribute_id.name) == attribute)
            attr_val_rec = attr_vals.value_ids
            if len(attr_val_rec) > 1 and mag_attr['frontend_input'] != 'multiselect':
                text = f"'{attribute}' attribute can't be used as multiselect as it has single select" \
                       f" setup in Magento."
                ml_conf_products[sku]['log_message'] += text
                return False
            for rec in attr_val_rec:
                if self.to_upper(rec.name) not in [self.to_upper(i.get('label')) for i in mag_attr['options']]:
                    val_id, err = self.create_new_attribute_option_in_magento(
                        instance, mag_attr['attribute_code'], rec
                    )
                    if err:
                        ml_conf_products[sku]['log_message'] += err
                        return False
                    else:
                        mag_attr['options'].append({'label': rec.name.upper(), 'value': val_id})

        return True

    def create_new_attribute_option_in_magento(self, magento_instance, attribute_code, attribute_value):
        store_labels = []
        magento_storeviews = [w.store_view_ids for w in magento_instance.magento_website_ids]
        is_string = True if isinstance(attribute_value, str) else False

        data = {
            "option": {
                "label": attribute_value if is_string else attribute_value.name,
                "value": "",
                "sort_order": 0,
                "is_default": "false",
                "store_labels": []
            }
        }

        if not is_string:
            attachment_rec = self.env['ir.attachment'].sudo().search([
                ('res_field', '=', 'x_image'),
                ('res_model', '=', 'product.attribute.value'),
                ('res_id', '=', attribute_value.id)
            ])
            color = attribute_value.html_color
            html_color = color if color and color[0] == '#' else ""
            attachment = attachment_rec.mimetype.replace("/", f"_{attachment_rec.id}.") if attachment_rec else ""
            value = html_color if html_color else attachment

            if not html_color and attachment_rec:
                entry = {
                    "entry": {
                        'base64_encoded_data': attribute_value.x_image.decode('utf-8'),
                        "type": attachment_rec.mimetype,
                        "name": value,
                        "sub_folder": ""
                    }
                }

                try:
                    api_url = '/V1/products/attributes/swatch/upload'
                    req(magento_instance, api_url, 'POST', entry)
                except Exception as e:
                    return 0, "Error while Product Attribute Option(Swatch) Image upload for %s Attribute: %s\n" % \
                           (attribute_code, e)

            data['option']['value'] = ("/" if not html_color and attachment_rec else "") + value

            avail_translations = self.env['ir.translation'].search([
                ('name', '=', 'product.attribute.value,name'),
                ('res_id', '=', attribute_value.id)
            ])

            for view in magento_storeviews:
                translated_label = ''
                for item in avail_translations:
                    if item.lang and (str(item.lang[:2]).upper()) == view.magento_storeview_code.upper():
                        translated_label = str(item.value if item.value else item.src).upper()
                        break
                store_labels.append({"store_id": view.magento_storeview_id, "label": translated_label})

            data['option']['store_labels'] = store_labels

        try:
            api_url = '/all/V1/products/attributes/%s/options' % attribute_code
            val_id = req(magento_instance, api_url, 'POST', data)

            try:
                val_id = int(val_id)
            except Exception:
                raise "Attribute value ID has incompatible type."
        except Exception as e:
            return 0, "Error while new Product Attribute Option(Swatch) creation for %s Attribute: %s. " % \
                   (attribute_code, e)

        return str(val_id), ""

    def check_config_product_assign_attributes_match(self, magento_prod_attrs, odoo_prod_attr, avail_attributes):
        prod_attr_magento = {
            self.get_attribute_name_by_id(avail_attributes, at.get("attribute_id")) for at in magento_prod_attrs if at
        }

        if odoo_prod_attr == prod_attr_magento:
            return True

        return False

    @staticmethod
    def get_attribute_name_by_id(available_attributes, attr_id):
        for attr in available_attributes:
            if str(available_attributes[attr]['attribute_id']) == str(attr_id):
                return attr

    def export_single_conf_product_to_magento(self, ml_conf_products, attr_sets, method='POST'):
        prod_sku = self.magento_sku
        instance = self.magento_instance_id
        conf_prod_dict = ml_conf_products[prod_sku]
        categ_list = [cat.magento_category for cat in self.category_ids]
        lang_code = self.env['res.lang']._lang_get(self.env.user.lang).code
        custom_attributes = self.add_conf_product_attributes(attr_sets, lang_code)

        data = {
            "product": {
                "name": self.magento_product_name,
                "attribute_set_id": attr_sets[self.magento_attr_set]['id'],
                "type_id": "configurable",
                "status": 2,  # 1-enabled / 2-disabled
                "visibility": 4,  # Catalog, Search
                "custom_attributes": custom_attributes,
                "product_links": [],
                "extension_attributes": {
                    "stock_item": {"is_in_stock": "true"},
                    "category_links": [{"position": 0, "category_id": cat_id} for cat_id in categ_list]
                }
            }
        }

        if method == 'POST':
            data['product'].update({
                "sku": prod_sku
            })
        else:
            magento_attributes = attr_sets[self.magento_attr_set]['attributes']
            config_attrs = conf_prod_dict['config_attr']
            magento_prod_attrs = conf_prod_dict.get('magento_conf_prod_options', {})
            if not self.check_config_product_assign_attributes_match(magento_prod_attrs, config_attrs, magento_attributes):
                # here if False - means "config" attributes were changed and need to unlink all related simple products
                data['product']["extension_attributes"].update({"configurable_product_links": []})

        try:
            api_url = '/all/V1/products' + ('' if method == "POST" else ('/%s' % prod_sku))
            response = req(instance, api_url, method, data)
        except Exception as err:
            text = "Error while Config.Product %s in Magento.\n" % ('update' if method == "PUT" else "creation")
            conf_prod_dict['log_message'] += text + str(err)
            return {}

        if response.get('sku'):
            if method == "POST":
                self.link_product_with_websites_in_magento(prod_sku, instance, ml_conf_products, response)
            self.process_storeview_data_export(instance, ml_conf_products, data, attr_sets)

            trigger = False
            if method == "PUT":
                magento_images = conf_prod_dict.get('media_gallery', [])

                if len(magento_images) != (len(self.product_image_ids) + (1 if self.image_1920 else 0)):
                    trigger = True
                    if magento_images:
                        self.remove_product_images_from_magento(instance, ml_conf_products, prod_sku)

            if method == "POST" or trigger:
                self.process_images_export_to_magento(instance, ml_conf_products)

            conf_prod_dict['export_date_to_magento'] = response.get("updated_at")
            conf_prod_dict['magento_status'] = 'extra_info'

            return response

        return {}

    def export_new_conf_products_to_magento_in_bulk(self, magento_instance, new_conf_prods_list, ml_conf_products, attr_sets):
        data = []
        lang_code = self.env['res.lang']._lang_get(self.env.user.lang).code

        for prod_sku in new_conf_prods_list:
            conf_prod_dict = ml_conf_products[prod_sku]
            conf_product = conf_prod_dict['conf_prod_rec']
            categ_list = [cat.magento_category for cat in conf_product.category_ids]
            custom_attributes = conf_product.add_conf_product_attributes(attr_sets, lang_code)

            data.append({
                "product": {
                    "sku": prod_sku,
                    "name": conf_product.magento_product_name,
                    "attribute_set_id": attr_sets[conf_product.magento_attr_set]['id'],
                    "status": 2,  # 1-enabled / 2-disabled
                    "visibility": 4,  # Catalog, Search
                    "type_id": "configurable",
                    "custom_attributes": custom_attributes,
                    "product_links": [],
                    "extension_attributes": {
                        "stock_item": {"is_in_stock": "true"},
                        "category_links": [{"position": 0, "category_id": cat_id} for cat_id in categ_list]
                    }
                }
            })

        try:
            api_url = '/all/async/bulk/V1/products'
            response = req(magento_instance, api_url, 'POST', data)
            datetime_stamp = datetime.now()
        except Exception as e:
            for prod_sku in new_conf_prods_list:
                text = "Error while new Configurable Products creation in Magento. " \
                       "Please check RabbitMQ works properly. " + str(e)
                ml_conf_products[prod_sku]['log_message'] += text
            return

        if not response.get('errors', True):
            product_websites = []
            prod_media = {}

            log_id = self.bulk_log_ids.create({
                'bulk_uuid': response.get("bulk_uuid"),
                'topic': 'Product Export'
            })

            for prod_sku in new_conf_prods_list:
                prod_media.update({prod_sku: []})
                conf_product = ml_conf_products[prod_sku]['conf_prod_rec']
                ml_conf_products[prod_sku]['export_date_to_magento'] = datetime_stamp
                ml_conf_products[prod_sku]['magento_status'] = 'in_process'
                conf_product.write({'bulk_log_ids': [(6, 0, [log_id.id])]})

                conf_product.prepare_websites_and_images_data_to_export(magento_instance, product_websites, prod_media)

            if product_websites:
                res = self.link_product_with_websites_in_magento_in_bulk(
                    magento_instance, product_websites, new_conf_prods_list, ml_conf_products
                )
                if not res.get('errors', True):
                    log_id = self.bulk_log_ids.create({
                        'bulk_uuid': res.get("bulk_uuid"),
                        'topic': 'Website info export'
                    })
                    for prod_sku in new_conf_prods_list:
                        ml_conf_products[prod_sku]['conf_prod_rec'].write({'bulk_log_ids': [(4, log_id.id)]})

            self.process_conf_prod_storeview_data_export_in_bulk(magento_instance, data, attr_sets, ml_conf_products)

            if prod_media:
                self.export_media_to_magento_in_bulk(magento_instance, prod_media, ml_conf_products)

    def add_conf_product_attributes(self, attr_sets, lang_code):
        custom_attributes = []
        available_attributes = attr_sets[self.magento_attr_set]['attributes']

        self.add_translatable_conf_product_attributes(custom_attributes, available_attributes, lang_code)

        # add main config attribute (hover attribute)
        code = ''
        if self.x_magento_main_config_attr:
            main_attr_name = self.to_upper(self.x_magento_main_config_attr)
            code = available_attributes[main_attr_name]['attribute_code']
        custom_attributes.append({
            "attribute_code": 'main_config_attribute',
            "value": code
        })

        # add single attributes specific to conf.product
        unique_attr = set(self.with_context(lang='en_US').x_magento_single_attr_ids.attribute_id.mapped('name'))
        for attr_name in unique_attr:
            value = ''
            mag_attr = available_attributes[self.to_upper(attr_name)]
            single_attr_vals = self.with_context(lang='en_US').x_magento_single_attr_ids.filtered(
                lambda x: x.attribute_id.name == attr_name)
            for rec in single_attr_vals:
                opt = next((o for o in mag_attr['options'] if o.get('label') and
                            self.to_upper(o['label']) == self.to_upper(rec.value_ids.name)), {})
                if opt:
                    value = opt['value'] if not value else f"{value},{opt['value']}"

            if value:
                custom_attributes.append({
                    "attribute_code": mag_attr['attribute_code'],
                    "value": value
                })

        # add product labels
        val = ''
        for label in self.product_label_ids:
            val = f"{val},{label.name}" if val else label.name
        attr = available_attributes["PRODUCTLABELS"]
        custom_attributes.append({
            "attribute_code": attr['attribute_code'],
            "value": val
        })

        # product life phase attribute
        # prod_status = conf_product.with_context(lang='en_US').odoo_prod_template_id.x_status
        # if prod_status:
        #     attr = available_attributes["PRODUCTLIFEPHASE"]
        #     opt = next((o for o in attr['options'] if o.get('label') and
        #                 self.to_upper(o['label']) == self.to_upper(prod_status)), {})
        #     if opt:
        #         custom_attributes.append({
        #             "attribute_code": attr['attribute_code'],
        #             "value": opt['value']
        #         })

        # custom_attributes.append({
        #     "attribute_code": 'tax_class_id',
        #     "value": '0'
        # })

        return custom_attributes

    def add_translatable_conf_product_attributes(self, custom_attributes, available_attributes, lang_code):
        prod_attributes = self.odoo_prod_template_id.categ_id.x_attribute_ids
        prod_attr_groups = prod_attributes.categ_group_id

        if self.odoo_prod_template_id.website_description:
            value = self.with_context(lang=lang_code).odoo_prod_template_id.website_description
            value_stripped = str(value).lstrip('<p>').rstrip('</p>').rstrip('<br>')
            if value_stripped:
                self.add_to_custom_attributes_list(custom_attributes, 'short_description', value_stripped)

        for group in prod_attr_groups:
            attr_name = group.with_context(lang='en_US').name
            attr_code = available_attributes[self.to_upper(attr_name)]['attribute_code']

            if attr_name == 'size table':
                vals = ''
                attr_vals = prod_attributes.filtered(lambda x: x.categ_group_id.name == group.name).sorted('sequence')

                for attr in attr_vals:
                    val = re.sub(re.compile('<p.*?><br></p>'), '', str(attr.attribute_value))
                    if val:
                        vals += val + '<br>'

                value = vals
            else:
                value = self.to_html_listitem(prod_attributes.filtered(lambda x: x.categ_group_id.name == group.name), lang_code)

            if value:
                self.add_to_custom_attributes_list(custom_attributes, attr_code, value)

    def prepare_websites_and_images_data_to_export(self, instance, product_websites, prod_media):
        prod_sku = self.magento_sku

        for site in instance.magento_website_ids:
            product_websites.append({
                "productWebsiteLink": {"sku": prod_sku, "website_id": site.magento_website_id},
                "sku": prod_sku
            })

        prod_media[prod_sku] = self.prepare_images_list(instance)

    @staticmethod
    def add_to_custom_attributes_list(custom_attributes, attr_code, attr_value):
        elem_in_list = next((o for o in custom_attributes if o['attribute_code'] == attr_code), {})

        if elem_in_list:
            elem_in_list['value'] = attr_value
        else:
            custom_attributes.append({
                "attribute_code": attr_code,
                "value": attr_value
            })

    @staticmethod
    def link_product_with_websites_in_magento(prod_sku, magento_instance, ml_products, product, method="POST"):
        website_ids = []
        data = {"productWebsiteLink": {"sku": prod_sku}}

        for site in magento_instance.magento_website_ids:
            data["productWebsiteLink"].update({"website_id": site.magento_website_id})
            try:
                api_url = '/V1/products/%s/websites' % prod_sku
                res = req(magento_instance, api_url, method, data)
                if res is True:
                    website_ids.append(site.magento_website_id)
            except Exception as e:
                text = "Error while adding website to product in Magento. " + str(e)
                ml_products[prod_sku]['log_message'] += text

        if website_ids:
            product.get('extension_attributes', {'extension_attributes': {}}).update({'website_ids': website_ids})

    def process_storeview_data_export(self, magento_instance, ml_products, data, attr_sets):
        text = ''
        prod_sku = self.magento_sku
        magento_storeviews = [w.store_view_ids for w in magento_instance.magento_website_ids]

        for storeview in magento_storeviews:
            lang_code = storeview.lang_id.code
            storeview_code = storeview.magento_storeview_code
            prod_dict = data['product']
            prod_dict['name'] = self.with_context(lang=lang_code).odoo_prod_template_id.name

            self.add_translatable_conf_product_attributes(
                prod_dict['custom_attributes'], attr_sets[self.magento_attr_set]['attributes'], lang_code
            )

            try:
                api_url = '/%s/V1/products/%s' % (storeview_code, prod_sku)
                req(magento_instance, api_url, 'PUT', data)
            except Exception as e:
                text = ("Error while exporting product data to '%s' store view. " % storeview_code) + str(e)
                break

        if text:
            ml_products[prod_sku]['log_message'] += text
            ml_products[prod_sku]['force_update'] = True

    def process_images_export_to_magento(self, magento_instance, ml_conf_products):
        prod_media = self.prepare_images_list(magento_instance)

        if prod_media:
            self.export_media_to_magento(magento_instance, {self.magento_sku: prod_media}, ml_conf_products)

    def prepare_images_list(self, instance, simple_prod=False):
        prod_media_list = []
        product_rec = simple_prod or self

        for img in product_rec.product_image_ids:
            attachment = self.env['ir.attachment'].sudo().search([
                ('res_field', '=', instance.image_resolution or 'image_1024'),
                ('res_model', '=', 'product.image'),
                ('res_id', '=', img.id)
            ])
            if attachment:
                prod_media_list.append((attachment, img.name, [img.image_role]))

        if product_rec.image_1920:     # product Thumbnail image
            res_field = 'image_128'
            roles = ['thumbnail']
            attachment = False

            if not product_rec.product_image_ids.filtered(lambda x: x.image_role == 'small_image'):
                res_field = instance.image_resolution or 'image_1024'
                roles += ['small_image']

            if simple_prod:
                attachment = self.env['ir.attachment'].sudo().search([
                    ('res_field', '=', 'image_variant_128'),
                    ('res_model', '=', 'product.product'),
                    ('res_id', '=', simple_prod.odoo_product_id.id)
                ])

            if not attachment:
                attachment = self.env['ir.attachment'].sudo().search([
                    ('res_field', '=', res_field),
                    ('res_model', '=', 'product.template'),
                    ('res_id', '=', product_rec.odoo_prod_template_id.id)
                ])

            if attachment:
                prod_media_list.append((attachment, '', roles))

        return prod_media_list

    @staticmethod
    def export_media_to_magento(magento_instance, products_media, ml_products):
        images = {}
        prod_sku = list(products_media.keys())[0]

        for img in products_media[prod_sku]:
            attachment, name, role = img

            images.update({
                "entry": {
                    "media_type": "image",
                    "types": role,
                    "disabled": "true" if role == ['thumbnail'] else "false",
                    "label": name,
                    "content": {
                        "base64EncodedData": attachment.datas.decode('utf-8'),
                        "type": attachment.mimetype,
                        "name": attachment.mimetype.replace("/", ".")
                    }
                }
            })

            try:
                api_url = '/all/V1/products/%s/media' % prod_sku
                req(magento_instance, api_url, 'POST', images)
            except Exception as e:
                ml_products[prod_sku]['force_update'] = True
                text = f"Error while Product ({role}) Image(s) export to Magento: {e} "
                ml_products[prod_sku]['log_message'] += text

    @staticmethod
    def remove_product_images_from_magento(magento_instance, ml_products, magento_sku):
        for img_id in ml_products[magento_sku]['media_gallery']:
            try:
                api_url = '/all/V1/products/%s/media/%s' % (magento_sku, img_id)
                req(magento_instance, api_url, 'DELETE')
            except Exception as e:
                ml_products[magento_sku]['force_update'] = True
                text = "Error while Product Images remove from Magento. " + str(e)
                ml_products[magento_sku]['log_message'] += text

    @staticmethod
    def link_product_with_websites_in_magento_in_bulk(magento_instance, product_websites, product_list, ml_products):
        try:
            api_url = '/all/async/bulk/V1/products/bySku/websites'
            res = req(magento_instance, api_url, 'POST', product_websites)
        except Exception as e:
            text = "Error while assigning website(s) in bulk to product in Magento. " + str(e)
            for prod_sku in product_list:
                ml_products[prod_sku]['log_message'] += text
            return {}
        return res

    def process_conf_prod_storeview_data_export_in_bulk(self, magento_instance, data, attr_sets, ml_conf_products):
        magento_storeviews = [w.store_view_ids for w in magento_instance.magento_website_ids]

        for storeview in magento_storeviews:
            data_lst = []
            lang_code = storeview.lang_id.code
            storeview_code = storeview.magento_storeview_code

            for product in data:
                sku = product['product']['sku']
                conf_prod = ml_conf_products[sku]['conf_prod_rec']
                custom_attributes = product['product']['custom_attributes']

                conf_prod.add_translatable_conf_product_attributes(
                    custom_attributes, attr_sets[conf_prod.magento_attr_set]['attributes'], lang_code
                )

                prod = {
                    'product': {
                        'name': conf_prod.with_context(lang=lang_code).odoo_prod_template_id.name,
                        'sku': sku,
                        'custom_attributes': custom_attributes
                    }
                }
                data_lst.append(prod)

            try:
                api_url = '/%s/async/bulk/V1/products' % storeview_code
                res = req(magento_instance, api_url, 'PUT', data_lst)
            except Exception as e:
                for product in data:
                    text = ("Error while exporting products' data to '%s' store view.\n" % storeview_code) + str(e)
                    ml_conf_products[product['product']['sku']]['log_message'] += text
                break

            if not res.get('errors', True):
                log_id = self.bulk_log_ids.create({
                    'bulk_uuid': res.get("bulk_uuid"),
                    'topic': 'Storeview-%s info export' % storeview_code
                })
                for product in data:
                    sku = product['product']['sku']
                    ml_conf_products[sku]['conf_prod_rec'].write({'bulk_log_ids': [(4, log_id.id)]})

    @staticmethod
    def export_media_to_magento_in_bulk(instance, products_media, ml_products):
        files_size = 0
        images = []
        last_prod = list(products_media)[-1]

        def process(imgs):
            try:
                api_url = '/all/async/bulk/V1/products/bySku/media'
                req(instance, api_url, 'POST', imgs)
            except Exception as e:
                text = "Error while Product Images export to Magento in bulk. " + str(e)
                for sku in {i["sku"] for i in imgs}:
                    if not ml_products[sku]['log_message']:
                        ml_products[sku]['force_update'] = True
                        ml_products[sku]['log_message'] += text
            return [], 0

        for prod_sku in products_media:
            for img in products_media[prod_sku]:
                if ml_products[prod_sku]['log_message']:
                    continue

                attachment, name, role = img

                if files_size and (files_size + attachment.file_size) > MAX_SIZE_FOR_IMAGES:
                    images, files_size = process(images)

                images.append({
                    "entry": {
                        "media_type": "image",
                        "types": role,
                        "disabled": "true" if role == ['thumbnail'] else "false",
                        "label": name,
                        "content": {
                            "base64EncodedData": attachment.datas.decode('utf-8'),
                            "type": attachment.mimetype,
                            "name": attachment.mimetype.replace("/", ".")
                        }
                    },
                    "sku": prod_sku
                })
                files_size += attachment.file_size

                if prod_sku == last_prod and img == products_media[prod_sku][-1]:
                    images, files_size = process(images)

    def export_products_extra_info_to_magento_in_bulk(self, instances):
        for instance in instances:
            valid_products = self.search([]).filtered(
                lambda x: x.magento_instance_id.id == instance.id and x.magento_product_id
            )

            data = []
            for product in valid_products:
                items = []
                sku = product.magento_sku
                for rel_prod in product.related_product_ids.filtered(lambda p: p.magento_product_id):
                    items.append({
                        'sku': sku,
                        'link_type': 'related',
                        'linked_product_sku': rel_prod.magento_sku
                    })

                for cs_prod in product.cross_sell_product_ids.filtered(lambda p: p.magento_product_id):
                    items.append({
                        'sku': sku,
                        'link_type': 'crosssell',
                        'linked_product_sku': cs_prod.magento_sku
                    })

                data.append({'items': items, 'sku': sku})

            if data:
                try:
                    api_url = '/all/async/bulk/V1/products/bySku/links'
                    req(instance, api_url, 'POST', data)
                except Exception as e:
                    raise UserError ("Error while exporting configurable product extra info to Magento: %s" % e)

    def export_products_extra_info_to_magento(self):
        self.ensure_one()

        if self.magento_product_id:
            items = []
            sku = self.magento_sku
            for rel_prod in self.related_product_ids.filtered(lambda p: p.magento_product_id):
                items.append({
                    'sku': sku,
                    'link_type': 'related',
                    'linked_product_sku': rel_prod.magento_sku
                })

            for cs_prod in self.cross_sell_product_ids.filtered(lambda p: p.magento_product_id):
                items.append({
                    'sku': sku,
                    'link_type': 'crosssell',
                    'linked_product_sku': cs_prod.magento_sku
                })

            if items:
                try:
                    api_url = '/all/V1/products/%s/links' % sku
                    req(self.magento_instance_id, api_url, 'POST', {'items': items})
                except Exception as e:
                    raise UserError ("Error while exporting configurable product extra info to Magento: %s" % e)

        response = self.simple_product_ids.export_product_prices_to_magento(self.magento_instance_id)
        if not response:
            self.processing_products_export_to_magento(True)
        else:
            return response

    def convert_json_to_dict(self, json_data):
        if not json_data:
            return {}

        link_data_dict = {}
        for prod in json_data:
            opt_dict = {}
            new_dict = json.loads(prod)
            [opt_dict.update({
                self.to_upper(opt.get('label')): self.to_upper(opt.get('value'))
            }) for opt in new_dict.get('simple_product_attribute')]

            link_data_dict.update({new_dict['simple_product_sku']: opt_dict})

        return link_data_dict

    @staticmethod
    def to_upper(val):
        if val:
            return "".join(str(val).split()).upper()
        else:
            return val

    @staticmethod
    def to_html_listitem(attributes, lang_code):
        lst = "<ul>"
        for attr in attributes.sorted('sequence'):
            val = str(attr.with_context(lang=lang_code).attribute_value).lstrip('<p>').rstrip('</p>').rstrip('<br>')
            if val:
                lst += "<li>" + val + "</li>"

        return lst + "</ul>"


class MagentoProductLabels(models.Model):
    _name = 'magento.product.label'
    _description = 'Magento Product Label'
    _rec_name = 'name'

    name = fields.Char("Name")