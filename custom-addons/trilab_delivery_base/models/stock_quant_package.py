
from odoo import fields, models


class StockQuantPackage(models.Model):
    _inherit = 'stock.quant.package'

    x_delivery_carrier_type = fields.Selection(related='package_type_id.package_carrier_type')

    def x_get_content_description(self):
        return ', '.join(f'{quant.product_id.name} [{quant.quantity} {quant.product_uom_id.name}]'
                         for quant in self.quant_ids) or f'PACK {self.name}'
