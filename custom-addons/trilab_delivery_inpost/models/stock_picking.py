from odoo import fields, models


class StockPicking(models.Model):

    _inherit = 'stock.picking'

    inpost_shipment_id = fields.Char('Inpost Shipment ID')
    inpost_shipment_status = fields.Selection(
        [
            ('created', 'Shipment created'),
            ('offers_prepared', 'Offers prepared'),
            ('offer_selected', 'Offer selected'),
            ('confirmed', 'Prepared by Sender'),
        ]
    )
    inpost_locker_code = fields.Char(
        string='InPost Locker Code', related='move_lines.sale_line_id.order_id.inpost_locker_code'
    )
    inpost_sending_point_id = fields.Many2one(related='move_lines.sale_line_id.order_id.inpost_sending_point_id')
    inpost_delivery_show_point = fields.Boolean(related='carrier_id.inpost_default_service_type_id.show_point')

    def inpost_can_show_cancel_btn(self, value):
        return value and bool(self.inpost_shipment_id)
