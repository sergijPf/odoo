from odoo import models, fields


class StockPickingType(models.Model):
    _inherit = 'stock.picking.type'

    x_producer_id = fields.Many2one('res.partner', string='Producer')
