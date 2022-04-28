# -*- coding: utf-8 -*-

from odoo import models, fields, api

RES_USERS = 'res.users'
IR_MODEL_DATA = 'ir.model.data'
IR_CRON = 'ir.cron'
EXPORT_PRODUCT_STOCK_CRON = 'odoo_magento2.ir_cron_export_product_stock_qty_instance_id_%d'
EXPORT_PRODUCT_PRICES_CRON = 'odoo_magento2.ir_cron_export_product_prices_instance_id_%d'
EXPORT_SHIPMENT_ORDER_STATUS_CRON = 'odoo_magento2.ir_cron_export_shipment_order_status_instance_id_%d'
EXPORT_INVOICE_CRON = 'odoo_magento2.ir_cron_export_invoice_instance_id_%d'
MAGENTO_STR = 'Magento-'
INTERVALS = [
    ('minutes', 'Minutes'),
    ('hours', 'Hours'),
    ('days', 'Days'),
    ('weeks', 'Weeks'),
    ('months', 'Months')
]


class MagentoCronConfiguration(models.TransientModel):
    _name = "magento.cron.configuration"
    _description = "Magento Cron Configuration"

    def _get_magento_instance(self):
        return self.env.context.get('magento_instance_id', False)

    magento_instance_id = fields.Many2one('magento.instance', string='Magento Instance', default=_get_magento_instance,
                                          readonly=True)
    # product stock
    auto_export_product_stock = fields.Boolean(string='Auto Product Stock Export?')
    export_product_stock_interval_number = fields.Integer('Stock export interval',
                                                          help="Export product stock every x interval.", default=1)
    export_product_stock_interval_type = fields.Selection(INTERVALS, string='Stock interval unit')
    export_product_stock_next_execution = fields.Datetime(string='Stock next execution')
    export_product_stock_user_id = fields.Many2one(RES_USERS, string='Stock responsible user',
                                                   help="Responsible user for Product Stock export")
    # product prices
    auto_export_product_prices = fields.Boolean(string='Auto Product Prices Export?')
    export_product_prices_interval_number = fields.Integer('Prices export interval',
                                                           help="Export product prices every x interval.", default=1)
    export_product_prices_interval_type = fields.Selection(INTERVALS, string='Prices interval unit')
    export_product_prices_next_execution = fields.Datetime(string='Prices next execution')
    export_product_prices_user_id = fields.Many2one(RES_USERS, string='Prices responsible user',
                                                    help="Responsible user for Product Prices export")
    # invoices
    auto_export_invoice = fields.Boolean('Auto Invoice Export?')
    export_invoice_interval_number = fields.Integer(string='Invoice export interval',
                                                    help="Export Invoice every x interval.", default=1)
    export_invoice_interval_type = fields.Selection(INTERVALS, string='Invoice interval unit')
    export_invoice_next_execution = fields.Datetime(string='Invoice next execution')
    export_invoice_user_id = fields.Many2one(RES_USERS, string='Invoice responsible user',
                                             help="Responsible user for Invoice export")
    # shipment order statuses
    auto_export_shipment_order_status = fields.Boolean(string='Auto Shipment Info Export?')
    export_shipment_order_status_interval_number = fields.Integer('Export interval',
                                                                  help="Export shipment every x interval.", default=1)
    export_shipment_order_status_interval_type = fields.Selection(INTERVALS, string='Interval unit')
    export_shipment_order_status_next_execution = fields.Datetime(string='Next execution')
    export_shipment_order_status_user_id = fields.Many2one(RES_USERS, string='Responsible user',
                                                           help="Responsible User for shipment info export")

    @api.onchange("magento_instance_id")
    def onchange_magento_instance_id(self):
        magento_instance = self.magento_instance_id
        self.set_export_product_stock_cron(magento_instance)
        self.set_export_product_prices_cron(magento_instance)
        self.set_export_shipment_order_status_cron(magento_instance)
        self.set_export_invoice_cron(magento_instance)

    def set_export_product_stock_cron(self, instance):
        try:
            export_product_stock_cron = instance and self.env.ref(EXPORT_PRODUCT_STOCK_CRON % instance.id)
        except Exception:
            return

        self.auto_export_product_stock = export_product_stock_cron.active or False
        self.export_product_stock_interval_number = export_product_stock_cron.interval_number or False
        self.export_product_stock_interval_type = export_product_stock_cron.interval_type or False
        self.export_product_stock_next_execution = export_product_stock_cron.nextcall or False
        self.export_product_stock_user_id = export_product_stock_cron.user_id.id or False

    def set_export_product_prices_cron(self, instance):
        try:
            export_product_prices_cron = instance and self.env.ref(EXPORT_PRODUCT_PRICES_CRON % instance.id)
        except Exception:
            return

        self.auto_export_product_prices = export_product_prices_cron.active or False
        self.export_product_prices_interval_number = export_product_prices_cron.interval_number or False
        self.export_product_prices_interval_type = export_product_prices_cron.interval_type or False
        self.export_product_prices_next_execution = export_product_prices_cron.nextcall or False
        self.export_product_prices_user_id = export_product_prices_cron.user_id.id or False

    def set_export_shipment_order_status_cron(self, instance):
        try:
            export_shipment_order_cron = instance and self.env.ref(EXPORT_SHIPMENT_ORDER_STATUS_CRON % instance.id)
        except Exception:
            return

        self.auto_export_shipment_order_status = export_shipment_order_cron.active or False
        self.export_shipment_order_status_interval_number = export_shipment_order_cron.interval_number or False
        self.export_shipment_order_status_interval_type = export_shipment_order_cron.interval_type or False
        self.export_shipment_order_status_next_execution = export_shipment_order_cron.nextcall or False
        self.export_shipment_order_status_user_id = export_shipment_order_cron.user_id.id or False

    def set_export_invoice_cron(self, magento_instance):
        try:
            export_invoice_cron = magento_instance and self.env.ref(EXPORT_INVOICE_CRON % magento_instance.id)
        except Exception:
            return

        self.auto_export_invoice = export_invoice_cron.active or False
        self.export_invoice_interval_number = export_invoice_cron.interval_number or False
        self.export_invoice_interval_type = export_invoice_cron.interval_type or False
        self.export_invoice_next_execution = export_invoice_cron.nextcall or False
        self.export_invoice_user_id = export_invoice_cron.user_id.id or False

    def save_cron_configuration(self):
        vals = {}
        magento_instance = self.magento_instance_id

        self.generate_auto_export_product_stock_cron(magento_instance)
        self.generate_auto_export_product_prices_cron(magento_instance)
        self.generate_auto_export_shipment_order_status_cron(magento_instance)
        self.generate_auto_export_invoice_cron(magento_instance)

        vals['auto_export_product_stock'] = self.auto_export_product_stock or False
        vals['auto_export_product_prices'] = self.auto_export_product_prices or False
        vals['auto_export_shipment_order_status'] = self.auto_export_shipment_order_status or False
        vals['auto_export_invoice'] = self.auto_export_invoice or False

        magento_instance.write(vals)

    def generate_auto_export_product_stock_cron(self, instance):
        cron_exist = self.env.ref(EXPORT_PRODUCT_STOCK_CRON % instance.id, raise_if_not_found=False)

        if self.auto_export_product_stock:
            cron_name = MAGENTO_STR + instance.name + ': Update Stock Quantities'
            ref_name = 'ir_cron_export_product_stock_qty_instance_id_%d' % instance.id
            vals = {
                "active": True,
                "interval_number": self.export_product_stock_interval_number,
                "interval_type": self.export_product_stock_interval_type,
                "nextcall": self.export_product_stock_next_execution,
                "code": "model._scheduler_update_product_stock_qty({'magento_instance_id' : %d})" % instance.id,
                "user_id": self.export_product_stock_user_id and self.export_product_stock_user_id.id,
                "magento_instance_id": instance.id,
                "numbercall": -1,
                "model_id": self.env['ir.model'].search([("model", "=", "magento.instance")]).id
            }

            self.create_or_update_cron(cron_exist, vals, cron_name, ref_name)

        elif cron_exist:
            cron_exist.write({'active': False})

    def generate_auto_export_product_prices_cron(self, instance):
        cron_exist = self.env.ref(EXPORT_PRODUCT_PRICES_CRON % instance.id, raise_if_not_found=False)

        if self.auto_export_product_prices:
            cron_name = MAGENTO_STR + instance.name + ': Update Product Prices'
            ref_name = 'ir_cron_export_product_prices_instance_id_%d' % instance.id
            vals = {
                "active": True,
                "interval_number": self.export_product_prices_interval_number,
                "interval_type": self.export_product_prices_interval_type,
                "nextcall": self.export_product_prices_next_execution,
                "code": "model._scheduler_update_product_prices({'magento_instance_id' : %d})" % instance.id,
                "user_id": self.export_product_prices_user_id and self.export_product_prices_user_id.id,
                "magento_instance_id": instance.id,
                "numbercall": -1,
                "model_id": self.env['ir.model'].search([("model", "=", "magento.instance")]).id
            }

            self.create_or_update_cron(cron_exist, vals, cron_name, ref_name)

        elif cron_exist:
            cron_exist.write({'active': False})

    def generate_auto_export_shipment_order_status_cron(self, instance):
        cron_exist = self.env.ref(EXPORT_SHIPMENT_ORDER_STATUS_CRON % instance.id, raise_if_not_found=False)

        if self.auto_export_shipment_order_status:
            cron_name = MAGENTO_STR + instance.name + ': Export Shipment Information'
            ref_name = 'ir_cron_export_shipment_order_status_instance_id_%d' % instance.id
            vals = {
                "active": True,
                "interval_number": self.export_shipment_order_status_interval_number,
                "interval_type": self.export_shipment_order_status_interval_type,
                "nextcall": self.export_shipment_order_status_next_execution,
                "code": "model._scheduler_update_order_status({'magento_instance_id' : %d})" % instance.id,
                "user_id": self.export_shipment_order_status_user_id and self.export_shipment_order_status_user_id.id,
                "magento_instance_id": instance.id,
                "numbercall": -1,
                "model_id": self.env['ir.model'].search([("model", "=", "magento.instance")]).id
            }

            self.create_or_update_cron(cron_exist, vals, cron_name, ref_name)

        elif cron_exist:
            cron_exist.write({'active': False})

    def generate_auto_export_invoice_cron(self, instance):
        cron_exist = self.env.ref(EXPORT_INVOICE_CRON % instance.id, raise_if_not_found=False)

        if self.auto_export_invoice:
            cron_name = MAGENTO_STR + instance.name + ': Export Invoice'
            ref_name = 'ir_cron_export_invoice_instance_id_%d' % instance.id
            vals = {
                "active": True,
                "interval_number": self.export_invoice_interval_number,
                "interval_type": self.export_invoice_interval_type,
                "nextcall": self.export_invoice_next_execution,
                "code": "model._scheduler_export_invoice({'magento_instance_id' : %d})" % instance.id,
                "user_id": self.export_invoice_user_id and self.export_invoice_user_id.id,
                "magento_instance_id": instance.id,
                "numbercall": -1,
                "model_id": self.env['ir.model'].search([("model", "=", "magento.instance")]).id
            }

            self.create_or_update_cron(cron_exist, vals, cron_name, ref_name)

        elif cron_exist:
            cron_exist.write({'active': False})

    def create_or_update_cron(self, cron_exist, vals, cron_name, ref_name):
        if cron_exist:
            cron_exist.write(vals)
        else:
            vals.update({'name': cron_name})
            new_cron_id = self.env[IR_CRON].create(vals).id

            self.env[IR_MODEL_DATA].create({
                'module': 'odoo_magento2',
                'name': ref_name,
                'model': IR_CRON,
                'res_id': new_cron_id,
                'noupdate': True
            })
