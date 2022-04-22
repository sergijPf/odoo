# -*- coding: utf-8 -*-

from odoo import models, fields, _
from odoo.exceptions import UserError
from ..python_library.api_request import req

STOCK_PICKING = 'stock.picking'


class StockPicking(models.Model):
    _inherit = STOCK_PICKING
    _description = 'Stock Picking'

    is_magento_picking = fields.Boolean('Magento Picking?', help="If checked, It is Magento Picking")
    related_backorder_ids = fields.One2many(comodel_name=STOCK_PICKING, inverse_name='backorder_id',
                                            string="Related backorders", help="This field relocates related backorders")
    magento_website_id = fields.Many2one("magento.website", "Magento Website", compute="_compute_set_magento_info",
                                         readonly=True)
    storeview_id = fields.Many2one("magento.storeview", "Magento Store Views", compute="_compute_set_magento_info",
                                   readonly=True)
    is_exported_to_magento = fields.Boolean("Exported to Magento?", help="If checked, Picking is exported to Magento")
    magento_instance_id = fields.Many2one('magento.instance', 'Instance')
    magento_shipping_id = fields.Char(string="Magento Shipping Id")
    is_shipment_exportable = fields.Boolean("Is Shipment exportable", compute='_compute_shipment_exportable',
                                            store=False)

    def _compute_shipment_exportable(self):
        module_obj = self.env['ir.module.module']
        purchase_module = module_obj.sudo().search([('name', '=', 'purchase'), ('state', '=', 'installed')])
        # check purchase module is installed or not and if it's installed then
        # picking is purchase's picking & is_export_dropship_picking is True
        # or
        # purchase is not installed and that picking is SO's picking
        if (self.location_dest_id.id == self.env.ref('stock.stock_location_customers').id) and \
                ((purchase_module and not self.purchase_id and self.sale_id) or (not purchase_module and self.sale_id)):
            self.is_shipment_exportable = True
        else:
            self.is_shipment_exportable = False

    def _compute_set_magento_info(self):
        for record in self:
            if record.sale_id.magento_order_id:
                record.magento_website_id = record.sale_id.magento_website_id
                record.storeview_id = record.sale_id.store_id
            else:
                record.magento_website_id = False
                record.storeview_id = False

    def export_shipments_to_magento(self, magento_instance):
        pickings = self.search([
            ('is_exported_to_magento', '=', False),
            ('state', 'in', ['done']),
            ('magento_instance_id', 'in', magento_instance.ids),
            ('location_dest_id', '=', self.env.ref('stock.stock_location_customers').id)
        ])
        module_obj = self.env['ir.module.module']
        purchase_module = module_obj.sudo().search([('name', '=', 'purchase'), ('state', '=', 'installed')])

        for picking in pickings:
            # if purchase_module and picking.purchase_id and picking.magento_instance_id and \
            #         not picking.magento_instance_id.is_export_dropship_picking:
            if purchase_module and picking.purchase_id:
                # check purchase module is installed or not
                # if installed then picking is purchase's picking
                # and is_export_dropship_picking set as False, then skip that picking to export to Magento
                continue
            picking.export_single_shipment_to_magento(False)

    def export_single_shipment_to_magento(self, is_single_call=True):
        order_item = []
        log_book_obj = self.env['magento.shipments.log.book']

        for move in self.move_lines:
            if move.sale_line_id and move.sale_line_id.magento_sale_order_line_ref:
                order_item_id = move.sale_line_id.magento_sale_order_line_ref
                qty_delivered = move.quantity_done
                # only ship those qty with is done in picking. Not for whole order qty done
                order_item.append({
                    'orderItemId': order_item_id,
                    'qty': qty_delivered
                })

        track_numbers, message = self.add_tracking_number()

        if message:
            if is_single_call:
                raise UserError(message)
            else:
                data = {'picking_id': self.id, 'log_message': message}
                shipment_err = log_book_obj.search([('picking_id', '=', self.id)])
                shipment_err.write(data) if shipment_err else shipment_err.create(data)
                return

        values = {
            "items": order_item,
            "tracks": track_numbers or []
        }
        try:
            api_url = '/V1/order/{}/ship/'.format(self.sale_id.magento_order_id)
            response = req(self.magento_instance_id, api_url, 'POST', values)
        except Exception:
            message = _("The request could not be satisfied and shipment couldn't be created in Magento for "
                        "Sale Order: %s & Picking: %s due to any of the following reasons.\n"
                        "1. A picking can't be created when an order has a status of 'On Hold/Canceled/Closed'\n"
                        "2. A picking can't be created without products. Add products and try again.\n"
                        "3. The shipment information hasn't been exported due to either missing carrier or tracking number details.\n"
                        "The order doesn't allow shipment to be created") % (self.sale_id.name, self.name)

            data = {'picking_id': self.id, 'log_message': message}
            shipment_err = log_book_obj.search([('picking_id', '=', self.id)])
            shipment_err.write(data) if shipment_err else shipment_err.create(data)

            if is_single_call:
                return {
                    'name': 'Shipment Error Logs',
                    'view_mode': 'tree,form',
                    'res_model': 'magento.shipments.log.book',
                    'type': 'ir.actions.act_window'
                }
            else:
                return

        if response:
            self.write({'magento_shipping_id': int(response), 'is_exported_to_magento': True})

            shipment_err = log_book_obj.search([('picking_id', '=', self.id)])
            if shipment_err:
                shipment_err.write({'active': False})

            if is_single_call:
                return {
                    'effect': {
                        'fadeout': 'slow',
                        'message': "Process Completed Successfully!",
                        'img_url': '/web/static/img/smile.svg',
                        'type': 'rainbow_man',
                    }
                }

    def add_tracking_number(self):
        if self.carrier_id and not self.carrier_id.magento_carrier_code:
            return [], "You are trying to 'Export Shipment Information'.\n But still, you didn't set the Magento " \
                       "Carrier Code for '%s' Delivery Method" % (str(self.carrier_id.name))

        tracking_numbers = []
        magento_carrier_code = self.carrier_id.magento_carrier_code or ''
        magento_carrier_title = self.carrier_id.magento_carrier.magento_carrier_title or ''
        if self.package_ids:
            for package in self.package_ids:
                tracking_numbers.append({
                    'carrierCode': magento_carrier_code,
                    'title': magento_carrier_title,
                    'trackNumber': package.tracking_no if package.tracking_no else self.carrier_tracking_ref or ''
                })
        else:
            if self.carrier_tracking_ref:
                tracking_numbers.append({
                    'carrierCode': magento_carrier_code,
                    'title': magento_carrier_title,
                    'trackNumber': self.carrier_tracking_ref or ''
                })

        return tracking_numbers, ''

    def _action_done(self):
        """
        create and paid invoice on the basis of auto invoice work flow
        when invoicing policy is 'delivery'.
        """
        result = super(StockPicking, self)._action_done()
        for picking in self:
            if picking.sale_id.invoice_status == 'invoiced':
                continue

            order = picking.sale_id
            work_flow_process_record = order and order.auto_workflow_process_id
            delivery_lines = picking.move_line_ids.filtered(lambda l: l.product_id.invoice_policy == 'delivery')

            if work_flow_process_record and delivery_lines and work_flow_process_record.create_invoice and \
                    picking.picking_type_id.code == 'outgoing':
                order.validate_invoice(work_flow_process_record)
        return result

    def send_to_shipper(self):
        """
        usage: If auto_processed_orders = True passed in Context then we can not call send shipment from carrier
        This change is used in case of Import Shipped Orders for all connectors.
        """
        context = dict(self._context)
        if context.get('auto_processed_orders', False):
            return True
        return super(StockPicking, self).send_to_shipper()


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _get_new_picking_values(self):
        res = super(StockMove, self)._get_new_picking_values()
        sale_order = self.group_id.sale_id
        sale_line_id = sale_order.order_line
        if sale_order and sale_line_id and sale_order.magento_instance_id:
            res.update({
                'magento_instance_id': sale_order.magento_instance_id.id,
                'is_exported_to_magento': False,
                'is_magento_picking': True
            })
        return res

    def _action_assign(self):
        """
        In Dropshipping case, While create picking
        set magento instance id and magento picking as True
        if the order is imported from the Magento Instance.
        :return:
        """
        res = super(StockMove, self)._action_assign()
        picking_ids = self.mapped('picking_id')
        for picking in picking_ids:
            if not picking.magento_instance_id and picking.sale_id and picking.sale_id.magento_instance_id:
                picking.write({
                    'magento_instance_id': picking.sale_id.magento_instance_id.id,
                    'is_exported_to_magento': False,
                    'is_magento_picking': True
                })
        return res


class StockQuantPackage(models.Model):
    _inherit = 'stock.quant.package'

    tracking_no = fields.Char("Additional Reference", help="This field is used for storing the tracking number.")
