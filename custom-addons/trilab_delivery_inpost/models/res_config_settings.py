from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    module_trilab_delivery_inpost = fields.Boolean('InPost Connector')
