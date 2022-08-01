from odoo import fields, models


class PackageType(models.Model):
    _inherit = 'stock.package.type'

    package_carrier_type = fields.Selection(selection_add=[('inpost', 'InPost')])
    inpost_carrier_id = fields.Many2one('inpost.carrier', string='InPost Carrier', index=True)
