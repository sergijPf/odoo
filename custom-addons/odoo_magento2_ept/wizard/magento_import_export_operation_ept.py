# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
"""
Describes product import export process.
"""
import base64
import csv
from csv import DictWriter
from io import StringIO
from datetime import datetime, timedelta
from odoo.exceptions import ValidationError, Warning
from odoo import fields, models, api, _
from odoo.exceptions import UserError

MAGENTO_DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'
MAGENTO_ORDER_DATA_QUEUE_EPT = 'magento.order.data.queue.ept'
IR_ACTION_ACT_WINDOW = 'ir.actions.act_window'
IR_MODEL_DATA = 'ir.model.data'
VIEW_MODE = 'tree,form'
COMPLETED_STATE = "[('state', '!=', 'completed' )]"
# IMPORT_MAGENTO_PRODUCT_QUEUE = 'sync.import.magento.product.queue'
MAGENTO_PRODUCT_PRODUCT = 'magento.product.product'


class MagentoImportExportEpt(models.TransientModel):
    """
    Describes Magento Process for import/ export operations
    """
    _name = 'magento.import.export.ept'
    _description = 'Magento Import Export Ept'

    magento_instance_ids = fields.Many2many('magento.instance', string="Instances",
                                            help="This field relocates Magento Instance")
    operations = fields.Selection([
        ('import_customer', 'Import Customer'),
        ('import_sale_order', 'Import Sale Order'),
        ('import_specific_order', 'Import Specific Order'),
        # ('import_products', 'Import Products'),
        # ('map_products', 'Map Products'),
        # ('import_specific_product', 'Import Specific Product'),
        ('import_product_stock', 'Import Product Stock'),
        ('export_shipment_information', 'Export Shipment Information'),
        ('export_invoice_information', 'Export Invoice Information'),
        ('export_product_stock', 'Export Product Stock')
    ], string='Import/ Export Operations', help='Import/ Export Operations')

    start_date = fields.Datetime(string="From Date", help="From date.")
    end_date = fields.Datetime("To Date", help="To date.")
    import_specific_sale_order = fields.Char(
        string="Sale Order Reference",
        help="You can import Magento Order by giving order number here,Ex.000000021 \n "
             "If multiple orders are there give order number comma (,) seperated "
    )
    # import_specific_product = fields.Char(
    #     string='Product Reference',
    #     help="You can import Magento product by giving product sku here, Ex.24-MB04 \n "
    #          "If Multiple product are there give product sku comma(,) seperated"
    # )
    datas = fields.Binary(string="Choose File", filters="*.csv")
    is_import_shipped_orders = fields.Boolean(
        string="Import Shipped Orders?",
        help="If checked, Shipped orders will be imported"
    )
    export_method = fields.Selection([
        ("direct", "Export in Magento Layer")
        # ("direct", "Export in Magento Layer"), ("csv", "Export in CSV file")
    ], default="direct")
    # do_not_update_existing_product = fields.Boolean(
    #     string="Do not update existing Products?",
    #     help="If checked and Product(s) found in odoo/magento layer, then not update the Product(s)"
    # )

    @api.onchange('operations')
    def on_change_operation(self):
        """
        Set end date when change operations
        """
        # if self.operations in ["import_products", "import_sale_order", "import_customer"]:
        if self.operations in ["import_sale_order", "import_customer"]:
            self.start_date = datetime.today() - timedelta(days=10)
            self.end_date = datetime.now()
        else:
            self.start_date = None
            self.end_date = None

    def execute(self):
        """
        Execute different Magento operations based on selected operation,
        """
        magento_instance = self.env['magento.instance']
        account_move = self.env['account.move']
        picking = self.env['stock.picking']
        message = ''
        if self.magento_instance_ids:
            instances = self.magento_instance_ids
        else:
            instances = magento_instance.search([])
        result = False
        if self.operations == 'import_customer':
            self.import_customer_operation(instances)
        # elif self.operations == 'map_products':
        #     self.map_product_operation(instances)
        elif self.operations == 'import_sale_order':
            result = self.import_sale_order_operation(instances)
        elif self.operations == 'import_specific_order':
            result = self.import_specific_sale_order_operation(instances)
        # elif self.operations == 'import_products':
        #     result = self.import_products_operation(instances)
        # elif self.operations == 'import_specific_product':
        #     result = self.import_specific_product_operation(instances)
        elif self.operations == 'import_product_stock':
            result = self.import_product_stock_operation(instances)
        elif self.operations == 'export_shipment_information':
            picking.export_shipment_to_magento(instances)
        elif self.operations == 'export_invoice_information':
            account_move.export_invoice_to_magento(instances)
        elif self.operations == 'export_product_stock':
            self.export_product_stock_operation(instances)
        if not result:
            title = [vals for key, vals in self._fields['operations'].selection if key == self.operations]
            return {
                'effect': {
                    'fadeout': 'slow',
                    'message': " {} Process Completed Successfully! {}".format(title[0], message),
                    'img_url': '/web/static/src/img/smile.svg',
                    'type': 'rainbow_man',
                }
            }
        return result

    # def map_product_operation(self, instances):
    #     """
    #     Perform map product operation.
    #     :param instances: Magento instances
    #     """
    #     if not self.datas:
    #         raise UserError(_("Please Upload File to Continue Mapping Products..."))
    #     for instance in instances:
    #         self.import_magento_csv(instance.id)

    def import_customer_operation(self, instances):
        """
        Create queue of imported customers.
        :param instances: Magento instances
        """
        customer_data_queue_obj = self.env['magento.customer.data.queue.ept']
        kwargs = {'start_date': self.start_date, 'end_date': self.end_date}
        for instance in instances:
            kwargs.update({'magento_instance': instance})
            customer_data_queue_obj.magento_create_customer_data_queues(**kwargs)

    def import_sale_order_operation(self, instances):
        """
        Create queue of imported sale orders
        :param instances: Magento Instances
        :return:
        """
        magento_order_data_queue_obj = self.env[MAGENTO_ORDER_DATA_QUEUE_EPT]
        from_date = datetime.strftime(self.start_date, MAGENTO_DATETIME_FORMAT) if self.start_date else {}
        to_date = datetime.strftime(self.end_date, MAGENTO_DATETIME_FORMAT)
        for instance in instances:
            order_queue_data = magento_order_data_queue_obj.magento_create_order_data_queues(
                instance, from_date, to_date, True
            )
        result = self.return_order_queue_form_or_tree_view(order_queue_data)
        return result

    def import_specific_sale_order_operation(self, instances):
        """
        Create queue of imported specific order.
        :param instances: Magento Instances
        :return:
        """
        if not self.import_specific_sale_order:
            raise Warning(_("Please enter Magento sale "
                            "order Reference for performing this operation."))
        magento_order_data_queue_obj = self.env[MAGENTO_ORDER_DATA_QUEUE_EPT]
        sale_order_list = self.import_specific_sale_order.split(',')
        for instance in instances:
            order_queue_data = magento_order_data_queue_obj.import_specific_order(
                instance, sale_order_list
            )
        result = self.return_order_queue_form_or_tree_view(order_queue_data)
        return result

    def return_order_queue_form_or_tree_view(self, order_queue_data):
        """
        it's return the tree view or form view based on the total_order_queues.
        :param order_queue_data: {'order_queue': magento.order.data.queue.ept(X,), 'count': X, 'total_order_queues': X}
        :return: view with domain
        """
        result = {
            'name': _('Magento Order Data Queue'),
            'res_model': MAGENTO_ORDER_DATA_QUEUE_EPT,
            'type': IR_ACTION_ACT_WINDOW,
        }
        if order_queue_data.get('total_order_queues') == 1:
            view_ref = self.env[IR_MODEL_DATA].get_object_reference(
                'odoo_magento2_ept', 'view_magento_order_data_queue_ept_form'
            )
            view_id = view_ref[1] if view_ref else False
            result.update({
                'views': [(view_id, 'form')],
                'view_mode': 'form',
                'view_id': view_id,
                'res_id': order_queue_data.get('order_queue').id,
                'target': 'current'
            })
        else:
            result.update({
                'view_mode': VIEW_MODE,
                'domain': COMPLETED_STATE
            })
        return result

    # def import_products_operation(self, instances):
    #     """
    #     Create queues of imported products
    #     :param instances: Magento Instances
    #     :return:
    #     """
    #     magento_import_product_queue_obj = self.env[IMPORT_MAGENTO_PRODUCT_QUEUE]
    #     from_date = datetime.strftime(self.start_date, MAGENTO_DATETIME_FORMAT) if self.start_date else {}
    #     to_date = datetime.strftime(self.end_date, MAGENTO_DATETIME_FORMAT)
    #     do_not_update_product = self.do_not_update_existing_product
    #     for instance in instances:
    #         product_queue_data = magento_import_product_queue_obj.create_sync_import_product_queues(
    #             instance, from_date, to_date, do_not_update_product)
    #     result = self.return_form_or_tree_view(product_queue_data)
    #     return result

    # def return_form_or_tree_view(self, product_queue_data):
    #     """
    #     it's return the tree view or form view based on the total_product_queues.
    #     :param product_queue_data: {'product_queue': sync.import.magento.product.queue(X,), 'count': X, 'total_product_queues': X}
    #     :return: view with domain
    #     """
    #     result = {
    #         'name': _('Magento Product Data Queue'),
    #         'res_model': IMPORT_MAGENTO_PRODUCT_QUEUE,
    #         'type': IR_ACTION_ACT_WINDOW,
    #     }
    #     if product_queue_data.get('total_product_queues') == 1:
    #         view_ref = self.env[IR_MODEL_DATA].get_object_reference(
    #             'odoo_magento2_ept', 'view_sync_import_magento_product_queue_ept_form'
    #         )
    #         view_id = view_ref[1] if view_ref else False
    #         result.update({
    #             'views': [(view_id, 'form')],
    #             'view_mode': 'form',
    #             'view_id': view_id,
    #             'res_id': product_queue_data.get('product_queue').id,
    #             'target': 'current'
    #         })
    #     else:
    #         result.update({
    #             'view_mode': VIEW_MODE,
    #             'domain': COMPLETED_STATE
    #         })
    #     return result

    # def import_specific_product_operation(self, instances):
    #     """
    #     Create queue of imported specific product
    #     :param instances: Magento Instances
    #     :return:
    #     """
    #     if not self.import_specific_product:
    #         raise Warning(_("Please enter Magento product"
    #                         " SKU for performing this operation."))
    #     magento_import_product_queue_obj = self.env[IMPORT_MAGENTO_PRODUCT_QUEUE]
    #     product_sku_lists = self.import_specific_product.split(',')
    #     do_not_update_product = self.do_not_update_existing_product
    #     for instance in instances:
    #         product_queue_data = magento_import_product_queue_obj.import_specific_product(
    #             instance,
    #             product_sku_lists,
    #             do_not_update_product
    #         )
    #     result = self.return_form_or_tree_view(product_queue_data)
    #     return result

    def import_product_stock_operation(self, instances):
        """
        Create inventory adjustment lines of imported product stock.
        :param instances: Magento Instances
        :return:
        """
        magento_inventory_locations_obj = self.env['magento.inventory.locations']
        magento_product_product = self.env[MAGENTO_PRODUCT_PRODUCT]
        is_log_exist = False
        for instance in instances:
            if not instance.is_import_product_stock:
                raise Warning(_("You are trying to import product stock."
                                "But your configuration for the imported stock is disabled for this instance."
                                "Please enable it and try it again."))
            if instance.magento_version in ['2.1', '2.2'] or not instance.is_multi_warehouse_in_magento:
                is_log_exist = magento_product_product.create_product_inventory(instance)
            else:
                inventory_locations = magento_inventory_locations_obj.search([
                    ('magento_instance_id', '=', instance.id)])
                magento_product_product.create_product_multi_inventory(instance, inventory_locations)
        if is_log_exist:
            result = {
                'name': _('Magento Product Import Stock'),
                'res_model': 'common.log.book.ept',
                'type': IR_ACTION_ACT_WINDOW
            }
            view_ref = self.env[IR_MODEL_DATA].get_object_reference(
                'common_connector_library', 'action_common_log_book_ept_form'
            )
            view_id = view_ref[1] if view_ref else False
            result.update({
                'views': [(view_id, 'form')],
                'view_mode': 'form',
                'view_id': view_id,
                'res_id': is_log_exist.id,
                'target': 'current'
            })
            return result
        else:
            return {
                'name': _('Magento Product Inventory Adjustments'),
                'res_model': 'stock.inventory',
                'type': IR_ACTION_ACT_WINDOW,
                'view_mode': VIEW_MODE,
            }

    def export_product_stock_operation(self, instances):
        """
        Export product stock from Odoo to Magento.
        :param instances: Magento Instances
        :return:
        """
        magento_inventory_locations_obj = self.env['magento.inventory.locations']
        magento_product_product = self.env[MAGENTO_PRODUCT_PRODUCT]
        for instance in instances:
            if instance.magento_version in ['2.1', '2.2'] or not instance.is_multi_warehouse_in_magento:
                magento_product_product.export_multiple_product_stock_to_magento(instance)
            else:
                inventory_locations = magento_inventory_locations_obj.search([
                    ('magento_instance_id', '=', instance.id)])
                magento_product_product.export_product_stock_to_multiple_locations(instance, inventory_locations)
            instance.last_update_stock_time = datetime.now()

    def prepare_product_for_export_in_magento(self):
        """
        This method is used to export products in Magento layer as per selection.
        If "direct" is selected, then it will direct export product into Magento layer.
        If "csv" is selected, then it will export product data in CSV file, if user want to do some
        modification in name, description, etc. before importing into Magento.
        """
        active_template_ids = self._context.get("active_ids", [])
        templates = self.env["product.template"].browse(active_template_ids)
        product_templates = templates.filtered(lambda template: template.type != "service")
        if not product_templates:
            raise Warning(_("It seems like selected products are not Storable products."))
        if self.export_method == "direct":
            self.prepare_product_for_magento(product_templates)
            return {
                'effect': {
                    'fadeout': 'slow',
                    'message': " 'Export in Magento Layer' Process Completed Successfully! {}".format(""),
                    'img_url': '/web/static/src/img/smile.svg',
                    'type': 'rainbow_man',
                }
            }
        # elif self.export_method == "csv":
        #     return self.export_product_for_magento(product_templates)

    # def export_product_for_magento(self, odoo_templates):
    #     """
    #     Create and download CSV file for export product in Magento.
    #     :param odoo_templates: Odoo product template object
    #     """
    #     field_name = ['product_template_id', 'product_id', 'template_name', 'product_name',
    #                   'product_default_code', 'magento_sku', 'description', 'sale_description', 'instance_id']
    #     buffer = StringIO()
    #     csv_writer = DictWriter(buffer, field_name, delimiter=',')
    #     csv_writer.writer.writerow(field_name)
    #     product_dic = []
    #     for instance in self.magento_instance_ids:
    #         for odoo_template in odoo_templates:
    #             if len(odoo_template.product_variant_ids.ids) == 1 and not odoo_template.default_code:
    #                 continue
    #             for variant in odoo_template.product_variant_ids.filtered(
    #                     lambda variant: variant.default_code != False):
    #                 row = self.prepare_data_for_export_to_csv_ept(odoo_template, variant, instance)
    #                 product_dic.append(row)
    #     if not product_dic:
    #         raise Warning(_('No data found to be exported.\n\nPossible Reasons:\n   - SKU(s) are not set properly.'))
    #     csv_writer.writerows(product_dic)
    #     buffer.seek(0)
    #     file_data = buffer.read().encode("utf-8")
    #     magento_product_export_file_encoded = base64.b64encode(file_data)
    #     self.write({'datas': magento_product_export_file_encoded})
    #     return {
    #         'type': 'ir.actions.act_url',
    #         'url': '/web/binary/download_document?model=magento.import.export.ept&'
    #                'field=datas&id=%s&filename=magento_product_export_%s.csv' % (
    #                    self.id, datetime.now().strftime("%m_%d_%Y-%H_%M_%S")),
    #         'target': 'self',
    #     }

    # @staticmethod
    # def prepare_data_for_export_to_csv_ept(odoo_template, variant, instance):
    #     """
    #     Prepare data for Export Operations at map Odoo Products csv with Magento Products.
    #     :param odoo_template: product.template()
    #     :param variant: product.product()
    #     :param instance: magento.instance()
    #     :return: dictionary
    #     """
    #     position = 0
    #     return {
    #         'product_template_id': odoo_template.id,
    #         'product_id': variant.id,
    #         'template_name': odoo_template.name,
    #         'product_name': variant.name,
    #         'product_default_code': variant.default_code,
    #         'magento_sku': variant.default_code,
    #         'description': variant.description or "",
    #         'sale_description': odoo_template.description_sale if position == 0 and odoo_template.description_sale else '',
    #         'instance_id': instance.id
    #     }

    def prepare_product_for_magento(self, odoo_templates):
        """
        Add product and product template into Magento.
        :param odoo_templates: Odoo product template object
        :return:
        """
        magento_sku_missing = {}
        product_dict = {}
        for instance in self.magento_instance_ids:
            product_dict.update({'instance_id': instance.id})
            for odoo_template in odoo_templates:
                product_dict.update({'product_template_id': odoo_template.id})
                magento_sku_missing = self.mapped_magento_products(product_dict, magento_sku_missing)
        if magento_sku_missing:
            raise UserError(_('Missing Internal References For %s', str(list(magento_sku_missing.values()))))
        return True

    # def import_magento_csv(self, instance_id):
    #     """
    #     Import CSV file and add product and product template into magento.
    #     :param instance: instance of magento.
    #     """
    #     magento_sku_missing = {}
    #     csv_reader = csv.DictReader(StringIO(base64.b64decode(self.datas).decode()), delimiter=',')
    #     for product_dict in csv_reader:
    #         if int(product_dict.get('instance_id')) == instance_id:
    #             magento_sku_missing = self.mapped_magento_products(product_dict, magento_sku_missing)
    #     return magento_sku_missing

    def mapped_magento_products(self, product_dict, magento_sku_missing):
        """
        Map Odoo products with Magento Products
        :param product_dict: dict of line from product csv file
        :param magento_sku_missing: dictionary of lines where magento sku is not set.
        :return: dict of missing magento sku
        """
        if not product_dict.get('product_id'):
            odoo_template = self.env['product.template'].browse(int(product_dict.get('product_template_id')))
            for variant in odoo_template.product_variant_ids:
                product_dict.update({
                    'magento_sku': variant.default_code,
                    'description': variant.description,
                    'sale_description': variant.description_sale
                })
                magento_sku_missing = self.create_or_update_magento_product_variant(product_dict, variant,
                                                                                    magento_sku_missing)
        else:
            odoo_product = self.env['product.product'].browse(int(product_dict.get('product_id')))
            magento_sku_missing = self.create_or_update_magento_product_variant(product_dict, odoo_product,
                                                                                magento_sku_missing)
        if magento_sku_missing:
            self._cr.commit()
        return magento_sku_missing

    def create_or_update_magento_product_template(self, product_dict, product):
        """
        Create or update magento product template when import product using CSV.
        :param product_dict: dict of csv file line
        :return: Magento Product Template Object
        """
        magento_template_object = self.env['magento.product.template']
        template_domain = self.prepare_magento_template_search_domain(product_dict, product)
        magento_template = magento_template_object.search(template_domain)
        if not magento_template:
            odoo_template = self.env['product.template'].browse(int(product_dict.get('product_template_id')))
            template_vals = self.prepare_magento_product_template_vals_ept(product_dict, odoo_template)
            magento_template = magento_template_object.create(template_vals)
            self.create_magento_template_images(magento_template, odoo_template)
        return magento_template

    @staticmethod
    def prepare_magento_template_search_domain(product_dict, product):
        if len(product.product_tmpl_id.product_variant_ids) > 1:
            return [('magento_instance_id', '=', int(product_dict.get('instance_id'))),
                    ('odoo_product_template_id', '=', int(product_dict.get('product_template_id')))]
        else:
            return [('magento_instance_id', '=', int(product_dict.get('instance_id'))),
                    #('odoo_product_template_id', '=', int(product_dict.get('product_template_id'))),
                    ('magento_sku', '=', product_dict.get('magento_sku'))]

    def prepare_magento_product_template_vals_ept(self, product_dict, odoo_template):
        ir_config_parameter_obj = self.env["ir.config_parameter"]
        magneto_product_template_dict = {
            'magento_instance_id': product_dict.get('instance_id'),
            'odoo_product_template_id': product_dict.get('product_template_id'),
            'product_type': 'configurable' if odoo_template.product_variant_count > 1 else 'simple',
            'magento_product_name': odoo_template.name,
            'magento_sku': False if odoo_template.product_variant_count > 1 else product_dict.get('magento_sku'),
            # 'export_product_to_all_website': True
        }
        if ir_config_parameter_obj.sudo().get_param("odoo_magento2_ept.set_magento_sales_description"):
            magneto_product_template_dict.update({
                'description': product_dict.get('description'),
                'short_description': product_dict.get('sale_description'),
            })
        return magneto_product_template_dict

    def create_or_update_magento_product_variant(self, product_dict, product, magento_sku_missing):
        """
        Create or update Magento Product Variant when import product using CSV.
        :param product_dict: dict {}
        :param product: product.product()
        :param magento_sku_missing: Missing SKU dictionary
        :return: Missing SKU dictionary
        """
        magento_product_object = self.env[MAGENTO_PRODUCT_PRODUCT]
        magento_prod_sku = product_dict.get('magento_sku')
        if not product_dict.get('magento_sku', False) and product.default_code:
            magento_prod_sku = product.default_code
        if not magento_prod_sku or magento_prod_sku == 'False':
            magento_sku_missing.update({product.id: product.name})
        else:
            domain = self.prepare_domain_for_magento_product_ept(product_dict, product)
            magento_variant = magento_product_object.search(domain)
            if not magento_variant:
                magento_template = self.create_or_update_magento_product_template(product_dict, product)
                prod_vals = self.prepare_magento_product_vals_ept(product_dict, product, magento_template,
                                                                  magento_prod_sku)
                magento_product = magento_product_object.create(prod_vals)
                self.create_magento_product_images(magento_template, product, magento_product)
            # else:
            #   magento_variant.write({'magento_sku': magento_prod_sku})
        return magento_sku_missing

    @staticmethod
    def prepare_domain_for_magento_product_ept(product_dict, product):
        """
        Prepare Domain for Search Magento Products
        :param product_dict: dict
        :param product: product.product()
        :return: list(tuple())
        """
        return [('magento_instance_id', '=', int(product_dict.get('instance_id'))),
                # ('odoo_product_id', '=', product.id),
                ('magento_sku', '=', product_dict.get('magento_sku'))]

    def prepare_magento_product_vals_ept(self, product_dict, product, magento_template, magento_prod_sku):
        ir_config_parameter_obj = self.env["ir.config_parameter"]
        magento_product_vals = {
            'magento_instance_id': product_dict.get('instance_id'),
            'odoo_product_id': product.id,
            'magento_tmpl_id': magento_template.id,
            'magento_sku': magento_prod_sku,
            'prod_categ_name': product.categ_id.magento_name or product.categ_id.magento_sku,
            'magento_product_name': product.name
        }
        if ir_config_parameter_obj.sudo().get_param("odoo_magento2_ept.set_magento_sales_description"):
            magento_product_vals.update({
                'description': product_dict.get('description'),
                'short_description': product_dict.get('sale_description'),
            })
        return magento_product_vals

    # def download_sample_attachment(self):
    #     """
    #     This Method relocates download sample file of internal transfer.
    #     :return: This Method return file download file.
    #     """
    #     attachment = self.env['ir.attachment'].search([('name', '=', 'magento_product_export.csv')])
    #     return {
    #         'type': 'ir.actions.act_url',
    #         'url': '/web/content/%s?download=true' % (attachment.id),
    #         'target': 'new',
    #         'nodestroy': False,
    #     }

    def create_magento_template_images(self, magento_template, odoo_template):
        """
        This method is use to create images in Magento layer.
        :param magento_template: magento product template object
        :param odoo_template: product template object
        """
        magento_product_image_obj = self.env["magento.product.image"]
        magento_product_image_list = []
        sequence = 1
        for odoo_image in odoo_template.ept_image_ids.filtered(lambda x: not x.product_id):
            if odoo_template.image_1920 and odoo_image.image == odoo_template.image_1920:
                sequence = 0
            magento_product_image = magento_product_image_obj.search(
                [("magento_tmpl_id", "=", magento_template.id),
                 ("odoo_image_id", "=", odoo_image.id)])
            if not magento_product_image:
                magento_product_image_list.append({
                    "odoo_image_id": odoo_image.id,
                    "magento_tmpl_id": magento_template.id,
                    'url': odoo_image.url,
                    'image': odoo_image.image,
                    'magento_instance_id': magento_template.magento_instance_id.id,
                    'sequence': sequence
                })
            sequence += 1
        if magento_product_image_list:
            magento_product_image_obj.create(magento_product_image_list)

    def create_magento_product_images(self, magento_template, odoo_product, magento_product):
        """
        This method is use to create images in Magento layer.
        :param magento_template: magneto product template object
        :param odoo_product: product  object
        :param magento_product: magento product object
        """
        magento_product_image_obj = self.env["magento.product.image"]
        magento_product_image_list = []
        sequence = 1
        for odoo_image in odoo_product.ept_image_ids:
            if odoo_product.image_1920 and odoo_image.image == odoo_product.image_1920:
                sequence = 0
            magento_product_image = magento_product_image_obj.search(
                [("magento_tmpl_id", "=", magento_template.id),
                 ("magento_product_id", "=", magento_product.id),
                 ("odoo_image_id", "=", odoo_image.id)])
            if not magento_product_image:
                magento_product_image_list.append({
                    "odoo_image_id": odoo_image.id,
                    "magento_tmpl_id": magento_template.id,
                    "magento_product_id": magento_product.id if magento_product else False,
                    'url': odoo_image.url,
                    'image': odoo_image.image,
                    'magento_instance_id': magento_template.magento_instance_id.id,
                    'sequence': sequence
                })
            sequence += 1
        if magento_product_image_list:
            magento_product_image_obj.create(magento_product_image_list)
