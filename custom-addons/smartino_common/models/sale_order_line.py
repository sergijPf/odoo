from odoo import models, fields


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    x_additional_status = fields.Selection([
        ('ok', 'OK'),
        ('check_moq', 'Check MOQ'),
        ('new_moq', 'New MOQ'),
        ('wrong_qty', 'Wrong Quantity'),
        ('impossible_deadline', 'Impossible Deadline'),
        ('missing_raw_materials', 'Missing Raw Materials'),
        ('impossible_combination', 'Impossible Combination'),
        ('to_be_confirmed', 'To be confirmed'),
        ('new_price', 'New Price'),
    ], string='Additional Status')

    x_partner_choice = fields.Selection([('ok', 'OK'), ('cancel', 'Cancel')], string='Partner Choice')
