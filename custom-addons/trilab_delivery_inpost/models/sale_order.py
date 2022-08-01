from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    inpost_locker_code = fields.Char(string='InPost Locker Code', copy=False)
    inpost_locker_id = fields.Many2one('inpost.point', string='InPost Locker', copy=False)
    inpost_sending_point_id = fields.Many2one('inpost.point', string='InPost sending Point', copy=False)
    carrier_delivery_type = fields.Selection(related='carrier_id.delivery_type')
    inpost_delivery_carrier_code = fields.Char(related='carrier_id.inpost_delivery_carrier_id.code')

    @api.onchange('carrier_id')
    def _onchange_carrier_id(self):
        self.inpost_locker_id = self.inpost_locker_code = None

    @api.onchange('inpost_locker_id')
    def _onchange_inpost_locker_id(self):
        for rec in self:
            rec.inpost_locker_code = rec.inpost_locker_id.name
