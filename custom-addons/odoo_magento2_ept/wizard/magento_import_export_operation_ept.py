# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
"""
Describes product import export process.
"""
# import base64
# import csv
# from csv import DictWriter
# from io import StringIO
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
        # ('import_product_stock', 'Import Product Stock'),
        ('export_shipment_information', 'Export Shipment Information'),
        ('export_invoice_information', 'Export Invoice Information'),
        ('export_product_stock', 'Export Product Stock')
    ], string='Import/ Export Operations', help='Import/ Export Operations')

    start_date = fields.Datetime(string="From Date", help="From date.")
    end_date = fields.Datetime("To Date", help="To date.")
    import_specific_sale_order = fields.Char(
        string="Sale Order Reference",
        help="You can import Magento Order by giving order number here,Ex.000000021 \n "
             "If multiple orders are there give order number comma (,) separated "
    )
    # import_specific_product = fields.Char(
    #     string='Product Reference',
    #     help="You can import Magento product by giving product sku here, Ex.24-MB04 \n "
    #          "If Multiple product are there give product sku comma(,) seperated"
    # )
    # datas = fields.Binary(string="Choose File", filters="*.csv")
    # is_import_shipped_orders = fields.Boolean(
    #     string="Import Shipped Orders?",
    #     help="If checked, Shipped orders will be imported"
    # )
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
        # elif self.operations == 'import_product_stock':
        #     result = self.import_product_stock_operation(instances)
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
            order_queue_data = magento_order_data_queue_obj.magento_create_order_data_queues(instance, from_date,
                                                                                             to_date, True)
        result = self.return_order_queue_form_or_tree_view(order_queue_data)
        return result

    def import_specific_sale_order_operation(self, instances):
        """
        Create queue of imported specific order.
        :param instances: Magento Instances
        :return:
        """
        if not self.import_specific_sale_order:
            raise Warning(_("Please enter Magento sale order Reference for performing this operation."))
        magento_order_data_queue_obj = self.env[MAGENTO_ORDER_DATA_QUEUE_EPT]
        sale_order_list = self.import_specific_sale_order.split(',')
        for instance in instances:
            order_queue_data = magento_order_data_queue_obj.import_specific_order(instance, sale_order_list)
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

    # def import_product_stock_operation(self, instances):
    #     """
    #     Create inventory adjustment lines of imported product stock.
    #     :param instances: Magento Instances
    #     :return:
    #     """
    #     magento_inventory_locations_obj = self.env['magento.inventory.locations']
    #     magento_product_product = self.env[MAGENTO_PRODUCT_PRODUCT]
    #     is_log_exist = False
    #     for instance in instances:
    #         if not instance.is_import_product_stock:
    #             raise Warning(_("You are trying to import product stock."
    #                             "But your configuration for the imported stock is disabled for this instance."
    #                             "Please enable it and try it again."))
    #         if instance.magento_version in ['2.1', '2.2'] or not instance.is_multi_warehouse_in_magento:
    #             is_log_exist = magento_product_product.create_product_inventory(instance)
    #         else:
    #             inventory_locations = magento_inventory_locations_obj.search([
    #                 ('magento_instance_id', '=', instance.id)])
    #             magento_product_product.create_product_multi_inventory(instance, inventory_locations)
    #     if is_log_exist:
    #         result = {
    #             'name': _('Magento Product Import Stock'),
    #             'res_model': 'common.log.book.ept',
    #             'type': IR_ACTION_ACT_WINDOW
    #         }
    #         view_ref = self.env[IR_MODEL_DATA].get_object_reference(
    #             'common_connector_library', 'action_common_log_book_ept_form'
    #         )
    #         view_id = view_ref[1] if view_ref else False
    #         result.update({
    #             'views': [(view_id, 'form')],
    #             'view_mode': 'form',
    #             'view_id': view_id,
    #             'res_id': is_log_exist.id,
    #             'target': 'current'
    #         })
    #         return result
    #     else:
    #         return {
    #             'name': _('Magento Product Inventory Adjustments'),
    #             'res_model': 'stock.inventory',
    #             'type': IR_ACTION_ACT_WINDOW,
    #             'view_mode': VIEW_MODE,
    #         }

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
                magento_product_product.export_products_stock_to_magento(instance)
            else:
                inventory_locations = magento_inventory_locations_obj.search([
                    ('magento_instance_id', '=', instance.id)])
                magento_product_product.export_product_stock_to_multiple_locations(instance, inventory_locations)
            instance.last_update_stock_time = datetime.now()

    def prepare_product_for_export_in_magento(self):
        """
        This method is used to export products in Magento layer as per selection.
        If "direct" is selected, then it will direct export product into Magento layer.
        """
        active_template_ids = self._context.get("active_ids", [])
        selection = self.env["product.product"].browse(active_template_ids)
        odoo_products = selection.filtered(lambda product: product.type != "service")
        if not odoo_products:
            raise Warning(_("It seems like selected products are not Storable products."))
        if self.export_method == "direct":
            self.add_products_to_magento_layer(odoo_products)
            return {
                'effect': {
                    'fadeout': 'slow',
                    'message': " 'Export in Magento Layer' Process Completed Successfully! {}".format(""),
                    'img_url': '/web/static/src/img/smile.svg',
                    'type': 'rainbow_man',
                }
            }

    def add_products_to_magento_layer(self, odoo_products):
        """
        Add product and product categories to Magento Layer in Odoo.
        :param odoo_products: Odoo product objects
        :return:
        """
        magento_sku_missing = {}
        conf_missing = []
        product_dict = {}
        for instance in self.magento_instance_ids:
            product_dict.update({'instance_id': instance.id})
            for odoo_prod in odoo_products:
                product_dict.update({'odoo_product_id': odoo_prod})
                magento_sku_missing, conf_missing = self.create_or_update_magento_product_variant(product_dict,
                                                                                                  magento_sku_missing,
                                                                                                  conf_missing)
        if magento_sku_missing:
            # self._cr.commit()
            raise UserError(_('Missing Internal References For %s', str(list(magento_sku_missing.values()))))
        if conf_missing:
            text = _("Missing Configurable Product for:\n")
            for conf in conf_missing:
                text += '%s\n' % conf
            raise UserError(text)

        return True

    def create_or_update_magento_product_variant(self, product_dict, magento_sku_missing, conf_missing):
        """
        Create or update Magento Product Variant
        :param product_dict: dict {}
        :param magento_sku_missing: Missing SKU dictionary
        :return: Missing SKU dictionary
        """
        magento_product_object = self.env[MAGENTO_PRODUCT_PRODUCT]
        product = product_dict.get('odoo_product_id')
        magento_prod_sku = product.default_code
        product_category = product.config_product_id

        if not magento_prod_sku:
            magento_sku_missing.update({product.id: product.name})
        if not product_category:
            conf_missing.append(magento_prod_sku)

        if magento_prod_sku and product_category:
            conf_product = self.create_or_update_configurable_product_in_magento_layer(product_dict)
            domain = [('magento_instance_id', '=', int(product_dict.get('instance_id'))),
                      ('magento_sku', '=', magento_prod_sku)]
            magento_variant = magento_product_object.with_context(active_test=False).search(domain)
            if not magento_variant:
                prod_vals = self.prepare_magento_product_variant_dict(product_dict, conf_product)
                magento_product_object.create(prod_vals)
            elif not magento_variant.active:
                # magento_variant.write({'magento_product_name': product.name, 'active': True})
                magento_variant.write({'active': True})

        return magento_sku_missing, conf_missing

    def create_or_update_configurable_product_in_magento_layer(self, product_dict):
        configurable_product_object = self.env['magento.configurable.product']
        product = product_dict.get('odoo_product_id')
        domain = [('magento_instance_id', '=', int(product_dict.get('instance_id'))),
                  ('odoo_prod_category', '=', product.config_product_id.id)]
        configurable_product = configurable_product_object.with_context(active_test=False).search(domain)
        if not configurable_product:
            values = {
                'magento_instance_id': product_dict.get('instance_id'),
                'odoo_prod_category': product.config_product_id.id,
                'magento_sku': product.config_product_id.with_context(lang='en_US').name.replace(' ','_').
                    replace('%','').replace('#','').replace('/','')
                # 'magento_product_name': product.config_product_id.name
            }
            configurable_product = configurable_product_object.create(values)
        elif not configurable_product.active:
            configurable_product.write({
                # 'magento_product_name': product.config_product_id.name,
                'magento_sku': product.config_product_id.with_context(lang='en_US').name.replace(' ','_').
                    replace('%','').replace('#','').replace('/',''), # to remove later
                'active': True
            })
        return configurable_product

    def prepare_magento_product_variant_dict(self, product_dict, conf_product):
        product = product_dict.get('odoo_product_id')
        magento_product_vals = {
            'magento_instance_id': product_dict.get('instance_id'),
            'odoo_product_id': product.id,
            'magento_sku': product.default_code,
            # 'magento_product_name': product.name,
            'magento_conf_product': conf_product.id

        }
        return magento_product_vals
