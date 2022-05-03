# -*- coding: utf-8 -*-

from odoo import models, fields, _
from ..python_library.api_request import req

STOCK_PICKING = 'stock.picking'


class StockPicking(models.Model):
    _inherit = STOCK_PICKING
    _description = 'Stock Picking'

    is_magento_picking = fields.Boolean('Magento Picking?', help="If checked, It is Magento Picking")
    is_in_magento = fields.Boolean("Is in Magento?", help="Checked means Shipment is in Magento")
    magento_instance_id = fields.Many2one('magento.instance', 'Instance')
    magento_shipping_id = fields.Char(string="Magento Shipping Id")
    is_shipment_exportable = fields.Boolean("Is Shipment exportable", compute='_compute_shipment_exportable',
                                            store=False)

    def _compute_shipment_exportable(self):
        if (self.location_dest_id.id == self.env.ref('stock.stock_location_customers').id):
            self.is_shipment_exportable = True
        else:
            self.is_shipment_exportable = False

    def export_shipments_to_magento(self, magento_instance, is_cron_call):
        pickings = self.search([
            ('magento_instance_id', 'in', magento_instance.ids),
            ('is_in_magento', '=', False),
            ('state', 'in', ['done']),
            ('location_dest_id', '=', self.env.ref('stock.stock_location_customers').id)
        ])

        for picking in pickings:
            resp = picking.export_single_shipment_to_magento(is_cron_call)
            if resp and not resp.get('effect'):
                return resp

    def export_single_shipment_to_magento(self, is_cron_call=False):
        order_item = []
        log_book_rec = self.env['magento.shipments.log.book'].search([('picking_id', '=', self.id)])

        track_numbers, message = self.add_tracking_number()

        if message:
            data = {'picking_id': self.id, 'log_message': message}
            log_book_rec.write(data) if log_book_rec else log_book_rec.create(data)

            if is_cron_call:
                return
            else:
                return {
                    'name': 'Shipment Error Logs',
                    'view_mode': 'tree,form',
                    'res_model': 'magento.shipments.log.book',
                    'type': 'ir.actions.act_window'
                }

        for move in self.move_lines:
            if move.sale_line_id and move.sale_line_id.magento_sale_order_line_ref:
                order_item.append({
                    'orderItemId': move.sale_line_id.magento_sale_order_line_ref,
                    'qty': move.quantity_done
                })

        values = {
            "items": order_item,
            "tracks": track_numbers or []
        }

        res = self.call_export_shipment_api(values, log_book_rec)

        if not is_cron_call:
            if res:
                return {
                    'effect': {
                        'fadeout': 'slow',
                        'message': "Process Completed Successfully!",
                        'img_url': '/web/static/img/smile.svg',
                        'type': 'rainbow_man',
                    }
                }
            else:
                return {
                    'name': 'Shipment Error Logs',
                    'view_mode': 'tree,form',
                    'res_model': 'magento.shipments.log.book',
                    'type': 'ir.actions.act_window'
                }

    def call_export_shipment_api(self, vals, log_book_rec):
        try:
            api_url = f'/V1/order/{self.sale_id.magento_order_id}/ship/'
            response = req(self.magento_instance_id, api_url, 'POST', vals)

            if response:
                self.write({'magento_shipping_id': response, 'is_in_magento': True})

                if log_book_rec:
                    log_book_rec.write({'active': False})

                return True
            else:
                message = 'Error while exporting shipment info to Magento'
                data = {'picking_id': self.id, 'log_message': message}
                log_book_rec.write(data) if log_book_rec else log_book_rec.create(data)

        except Exception as e:
            message = _("The request could not be satisfied and shipment couldn't be created in Magento for "
                        "Sale Order: %s & Picking: %s. The received error: %s. \n"
                        "Possible reasons: \n"
                        "1. A picking can't be created when an order has a status of 'On Hold/Canceled/Closed'\n"
                        "2. A picking can't be created without products. Add products and try again.\n"
                        "3. The shipment information hasn't been exported due to either missing carrier or "
                        "tracking number details.\n") % (self.sale_id.name, self.name, str(e))
            data = {'picking_id': self.id, 'log_message': message}
            log_book_rec.write(data) if log_book_rec else log_book_rec.create(data)

    def add_tracking_number(self):
        tracking_numbers = []
        carrier = self.carrier_id

        if carrier and not carrier.magento_carrier_code:
            return [], "Error while exporting shipment info to Magento: %s Carrier(Delivery Method) specified " \
                       "for this order is missing Magento Carrier Code." % (str(carrier.name))

        vals = {
            'carrierCode': carrier.magento_carrier_code or False,
            'title': carrier.magento_carrier.magento_carrier_title or '',
            'trackNumber': ''
        }

        if self.package_ids:
            for package in self.package_ids:
                vals.update({
                    'trackNumber': (package.tracking_no if package.tracking_no else self.carrier_tracking_ref) or ''
                })

                tracking_numbers.append(vals.copy())

        else:
            if self.carrier_tracking_ref:
                vals.update({'trackNumber': self.carrier_tracking_ref})
                tracking_numbers.append(vals)

        return tracking_numbers, ''


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _get_new_picking_values(self):
        res = super(StockMove, self)._get_new_picking_values()

        sale_order = self.group_id.sale_id

        if sale_order and sale_order.order_line and sale_order.magento_instance_id:
            res.update({
                'magento_instance_id': sale_order.magento_instance_id.id,
                'is_in_magento': False,
                'is_magento_picking': True
            })

        return res


class StockQuantPackage(models.Model):
    _inherit = 'stock.quant.package'

    tracking_no = fields.Char("Additional Reference", help="This field is used for storing the tracking number.")
