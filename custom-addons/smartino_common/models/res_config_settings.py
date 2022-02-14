from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    create_quotations_at_checkout = fields.Boolean(related='website_id.create_quotations_at_checkout', readonly=False,
                                                   help='Create quotations at checkout')
