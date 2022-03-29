# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError

RES_USERS = 'res.users'
EXPORT_PRODUCT_STOCK_CRON = 'odoo_magento2.ir_cron_export_product_stock_qty_instance_id_%d'
EXPORT_SHIPMENT_ORDER_STATUS_CRON = 'odoo_magento2.ir_cron_export_shipment_order_status_instance_id_%d'
EXPORT_INVOICE_CRON = 'odoo_magento2.ir_cron_export_invoice_instance_id_%d'
CRON_ERROR_MSG = 'Core settings of Magento are deleted, please upgrade Magento module to back this settings.'
MAGENTO_STR = 'Magento - '
IR_MODEL_DATA = 'ir.model.data'
IR_CRON = 'ir.cron'

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
    auto_export_product_stock = fields.Boolean(string='Auto Product Stock Export?')
    export_product_stock_interval_number = fields.Integer('Product Stock Export interval',
                                                          help="Export product stock every x interval.", default=1)
    export_product_stock_interval_type = fields.Selection(INTERVALS, string='Export Product Stock interval unit')
    export_product_stock_next_execution = fields.Datetime(string='Next Product Stock Export execution')
    export_product_stock_user_id = fields.Many2one(RES_USERS, string='Product Stock Export user',
                                                   help="Responsible user for Product Stock export")

    auto_export_invoice = fields.Boolean('Auto Invoice Export?')
    export_invoice_interval_number = fields.Integer(string='Invoice Export interval',
                                                    help="Export Invoice every x interval.", default=1)
    export_invoice_interval_type = fields.Selection(INTERVALS, string='Export Invoice interval unit')
    export_invoice_next_execution = fields.Datetime(string='Next Invoice Export execution')
    export_invoice_user_id = fields.Many2one(RES_USERS, string='Invoice Export user',
                                             help="Responsible user for Invoice export")

    auto_export_shipment_order_status = fields.Boolean(string='Auto Shipment Info Export?')
    export_shipment_order_status_interval_number = fields.Integer('Order Status(Shipment) Export interval',
                                                                  help="Export shipment every x interval.", default=1)
    export_shipment_order_status_interval_type = fields.Selection(INTERVALS, string='Export Shipment interval unit')
    export_shipment_order_status_next_execution = fields.Datetime(string='Next Order Status(Shipment) Export execution')
    export_shipment_order_status_user_id = fields.Many2one(RES_USERS, string='Order(Shipment) Export user',
                                                           help="Responsible User for shipment info export")

    @api.onchange("magento_instance_id")
    def onchange_magento_instance_id(self):
        magento_instance = self.magento_instance_id
        self.set_export_product_stock_cron(magento_instance)
        self.set_export_shipment_order_cron(magento_instance)
        self.set_export_invoice_cron(magento_instance)

    def set_export_product_stock_cron(self, instance):
        try:
            magento_export_product_stock_cron_exist = instance and self.env.ref(
                EXPORT_PRODUCT_STOCK_CRON % instance.id
            )
        except Exception:
            magento_export_product_stock_cron_exist = False

        if magento_export_product_stock_cron_exist:
            interval_number = magento_export_product_stock_cron_exist.interval_number or False
            interval_type = magento_export_product_stock_cron_exist.interval_type or False
            nextcall = magento_export_product_stock_cron_exist.nextcall or False
            user_id = magento_export_product_stock_cron_exist.user_id.id or False
            self.auto_export_product_stock = magento_export_product_stock_cron_exist.active or False
            self.export_product_stock_interval_number = interval_number
            self.export_product_stock_interval_type = interval_type
            self.export_product_stock_next_execution = nextcall
            self.export_product_stock_user_id = user_id

    def set_export_shipment_order_cron(self, instance):
        try:
            export_shipment_order_cron_exist = instance and self.env.ref(
                EXPORT_SHIPMENT_ORDER_STATUS_CRON % instance.id
            )
        except Exception:
            export_shipment_order_cron_exist = False

        if export_shipment_order_cron_exist:
            export_shipment_order_cron_active = export_shipment_order_cron_exist.active
            interval_number = export_shipment_order_cron_exist.interval_number or False
            interval_type = export_shipment_order_cron_exist.interval_type or False
            nextcall = export_shipment_order_cron_exist.nextcall or False
            user_id = export_shipment_order_cron_exist.user_id.id or False
            self.auto_export_shipment_order_status = export_shipment_order_cron_active or False
            self.export_shipment_order_status_interval_number = interval_number
            self.export_shipment_order_status_interval_type = interval_type
            self.export_shipment_order_status_next_execution = nextcall
            self.export_shipment_order_status_user_id = user_id

    def set_export_invoice_cron(self, magento_instance):
        try:
            export_invoice_cron_exist = magento_instance and self.env.ref(EXPORT_INVOICE_CRON % magento_instance.id)
        except Exception:
            export_invoice_cron_exist = False

        if export_invoice_cron_exist:
            interval_number = export_invoice_cron_exist.interval_number or False
            interval_type = export_invoice_cron_exist.interval_type or False
            self.auto_export_invoice = export_invoice_cron_exist.active or False
            self.export_invoice_interval_number = interval_number
            self.export_invoice_interval_type = interval_type
            self.export_invoice_next_execution = export_invoice_cron_exist.nextcall or False
            self.export_invoice_user_id = export_invoice_cron_exist.user_id.id or False

    def save_cron_configuration(self):
        vals = {}
        magento_instance = self.magento_instance_id
        self.generate_auto_export_product_stock_cron(magento_instance)
        self.generate_auto_export_shipment_order_status_cron(magento_instance)
        self.generate_auto_export_invoice_cron(magento_instance)
        vals['auto_export_product_stock'] = self.auto_export_product_stock or False
        vals['auto_export_shipment_order_status'] = self.auto_export_shipment_order_status or False
        vals['auto_export_invoice'] = self.auto_export_invoice or False
        magento_instance.write(vals)
        return True

    def generate_auto_export_product_stock_cron(self, magento_instance):
        cron_exist = self.env.ref(EXPORT_PRODUCT_STOCK_CRON % magento_instance.id, raise_if_not_found=False)

        if self.auto_export_product_stock:
            vals = {
                "active": True,
                "interval_number": self.export_product_stock_interval_number,
                "interval_type": self.export_product_stock_interval_type,
                "nextcall": self.export_product_stock_next_execution,
                "code": "model._scheduler_update_product_stock_qty({'magento_instance_id' : %d})" % (
                    magento_instance.id),
                "user_id": self.export_product_stock_user_id and self.export_product_stock_user_id.id,
                "magento_instance_id": magento_instance.id
            }

            if cron_exist:
                cron_exist.write(vals)
            else:
                export_product_stock_cron = self.env.ref('odoo_magento2.ir_cron_export_product_stock_qty',
                                                         raise_if_not_found=False)
                if not export_product_stock_cron:
                    raise UserError(_(CRON_ERROR_MSG))

                name = MAGENTO_STR + magento_instance.name + ': Update Stock Quantities'
                vals.update({'name': name})
                new_cron = export_product_stock_cron.copy(default=vals)
                self.env[IR_MODEL_DATA].create({
                    'module': 'odoo_magento2',
                    'name': 'ir_cron_export_product_stock_qty_instance_id_%d' % magento_instance.id,
                    'model': IR_CRON,
                    'res_id': new_cron.id,
                    'noupdate': True
                })
        else:
            if cron_exist:
                cron_exist.write({'active': False})

        return True

    def generate_auto_export_shipment_order_status_cron(self, magento_instance):
        cron_exist = self.env.ref(EXPORT_SHIPMENT_ORDER_STATUS_CRON % magento_instance.id, raise_if_not_found=False)

        if self.auto_export_shipment_order_status:
            export_ship_order_status_user = self.export_shipment_order_status_user_id
            vals = {
                "active": True,
                "interval_number": self.export_shipment_order_status_interval_number,
                "interval_type": self.export_shipment_order_status_interval_type,
                "nextcall": self.export_shipment_order_status_next_execution,
                "code": "model._scheduler_update_order_status({'magento_instance_id' : %d})" % magento_instance.id,
                "user_id": export_ship_order_status_user and export_ship_order_status_user.id,
                "magento_instance_id": magento_instance.id
            }

            if cron_exist:
                cron_exist.write(vals)
            else:
                update_order_status_cron = self.env.ref('odoo_magento2.ir_cron_export_shipment_order_status',
                                                        raise_if_not_found=False)
                if not update_order_status_cron:
                    raise UserError(_(CRON_ERROR_MSG))

                name = MAGENTO_STR + magento_instance.name + ': Export Shipment Information'
                vals.update({'name': name})
                new_cron = update_order_status_cron.copy(default=vals)
                self.env[IR_MODEL_DATA].create({
                    'module': 'odoo_magento2',
                    'name': 'ir_cron_export_shipment_order_status_instance_id_%d' % magento_instance.id,
                    'model': IR_CRON,
                    'res_id': new_cron.id,
                    'noupdate': True
                })
        else:
            if cron_exist:
                cron_exist.write({'active': False})

        return True

    def generate_auto_export_invoice_cron(self, magento_instance):
        cron_exist = self.env.ref(EXPORT_INVOICE_CRON % magento_instance.id, raise_if_not_found=False)

        if self.auto_export_invoice:
            vals = {
                "active": True,
                "interval_number": self.export_invoice_interval_number,
                "interval_type": self.export_invoice_interval_type,
                "nextcall": self.export_invoice_next_execution,
                "code": "model._scheduler_export_invoice({'magento_instance_id' : %d})" % magento_instance.id,
                "user_id": self.export_invoice_user_id and self.export_invoice_user_id.id,
                "magento_instance_id": magento_instance.id
            }

            if cron_exist:
                cron_exist.write(vals)
            else:
                export_inovice_cron = self.env.ref('odoo_magento2.ir_cron_export_invoice', raise_if_not_found=False)
                if not export_inovice_cron:
                    raise UserError(_(CRON_ERROR_MSG))

                name = MAGENTO_STR + magento_instance.name + ': Export Invoice'
                vals.update({'name': name})
                new_cron = export_inovice_cron.copy(default=vals)
                self.env[IR_MODEL_DATA].create({
                    'module': 'odoo_magento2',
                    'name': 'ir_cron_export_invoice_instance_id_%d' % magento_instance.id,
                    'model': IR_CRON,
                    'res_id': new_cron.id,
                    'noupdate': True
                })
        else:
            if cron_exist:
                cron_exist.write({'active': False})

        return True
