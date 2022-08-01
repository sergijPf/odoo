from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    x_delivery_type = fields.Selection(related='carrier_id.delivery_type', string='Delivery Type')
