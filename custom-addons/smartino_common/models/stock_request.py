from odoo import models, api, _
from odoo.exceptions import ValidationError


class StockRequest(models.Model):
    _inherit = 'stock.request'

    @api.constrains('product_uom_qty', 'product_uom_id', 'product_id')
    def x_constrain_line_quantity(self):
        for line in self:
            quantity = line.product_uom_id._compute_quantity(line.product_uom_qty, line.product_id.uom_id)
            raise_msg = False
            if quantity < line.product_id.x_minimal_quantity:
                raise_msg = _('Minimal quantity for product "%s" is %s %s', line.product_id.name,
                              line.product_id.x_minimal_quantity, line.product_id.uom_id.name)
            elif line.product_id.x_quantity_multiplicity and quantity % line.product_id.x_quantity_multiplicity:
                raise_msg = _('Quantity multiplicity for product "%s" is %s %s', line.product_id.name,
                              line.product_id.x_quantity_multiplicity, line.product_id.uom_id.name)
            if raise_msg:
                raise ValidationError(raise_msg)
