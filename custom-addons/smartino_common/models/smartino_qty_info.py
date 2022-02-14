from odoo import models, fields, api


class SmartinoQtyInfo(models.Model):
    _name = 'smartino.qty_info'
    _description = 'Smartino Quantity Info'

    order_id = fields.Many2one('sale.order')
    quantity = fields.Float(digits='Product Unit of Measure', required=True)
    uom_id = fields.Many2one('uom.uom', required=True)

    @api.model
    def create(self, vals):
        return super(SmartinoQtyInfo, self).create(vals)
