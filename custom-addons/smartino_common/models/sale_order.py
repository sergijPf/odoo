from odoo import models, fields, api
import json


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    x_line_data = fields.Char()
    x_qty_info_ids = fields.One2many('smartino.qty_info', compute='_x_compute_qty_info', string='Qty Info')

    @api.constrains('order_line')
    def x_constrain_line_values(self):
        for order in self:
            new_line_data = [[
                line.product_id.id, line.product_uom_qty, line.product_uom.id,
                line.price_unit, line.tax_id.id, line.price_total,
            ] for line in order.order_line]
            old_line_data = json.loads(order.x_line_data) if order.x_line_data else []
            while len(new_line_data) < len(old_line_data):
                new_line_data.append((False, 0, False, 0, False, 0))
            while len(new_line_data) > len(old_line_data):
                old_line_data.append((False, 0, False, 0, False, 0))

            change_msg = ''

            for item in range(len(new_line_data)):
                if old_line_data[item] != new_line_data[item]:
                    line_msg = '<strong>Order Line {} updated</strong>' \
                               '<ul>' \
                               '<li>Product: {} => {}</li>' \
                               '<li>Quantity: {:.2f} => {:.2f}</li>' \
                               '<li>UoM: {} => {}</li>' \
                               '<li>Unit Price: {:.2f} => {:.2f}</li>' \
                               '<li>Tax: {} => {}</li>' \
                               '<li>Total Price: {:.2f} => {:.2f}</li>' \
                               '</ul>'
                    line_msg = line_msg.format(
                        item + 1,
                        self.env['product.product'].browse(old_line_data[item][0]).name if old_line_data[item][
                            0] else False,
                        self.env['product.product'].browse(new_line_data[item][0]).name if new_line_data[item][
                            0] else False,
                        old_line_data[item][1],
                        new_line_data[item][1],
                        self.env['uom.uom'].browse(old_line_data[item][2]).name if old_line_data[item][2] else False,
                        self.env['uom.uom'].browse(new_line_data[item][2]).name if new_line_data[item][2] else False,
                        old_line_data[item][3],
                        new_line_data[item][3],
                        self.env['account.tax'].browse(old_line_data[item][4]).name if old_line_data[item][
                            4] else False,
                        self.env['account.tax'].browse(new_line_data[item][4]).name if new_line_data[item][
                            4] else False,
                        old_line_data[item][5],
                        new_line_data[item][5],
                    )
                    change_msg += line_msg

            if change_msg:
                order.message_post(body=change_msg)

            order.x_line_data = json.dumps(new_line_data)

    def x_create_stock_pickings(self):
        old_state = self.state
        self.action_confirm()
        self.state = old_state

    @api.depends('order_line.product_uom', 'order_line.product_uom_qty')
    def _x_compute_qty_info(self):
        for order in self:
            order.x_qty_info_ids = [(6, 0, 0)]
            if order.id:
                for uom_id in order.order_line.product_uom:
                    qty = sum(order.order_line.filtered(lambda i: i.product_uom == uom_id).mapped('product_uom_qty'))
                    qty_info_id = self.x_qty_info_ids.search([('uom_id', '=', uom_id.id), ('order_id', '=', order.id)], limit=1)

                    if qty_info_id:
                        qty_info_id.quantity = qty
                        order.x_qty_info_ids += qty_info_id
                    else:
                        order.x_qty_info_ids += self.env['smartino.qty_info'].sudo().create({'order_id': order.id,
                                                                                             'uom_id': uom_id.id,
                                                                                             'quantity': qty})
