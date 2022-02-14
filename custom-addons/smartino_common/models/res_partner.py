from odoo import models, fields


class ResPartner(models.Model):
    _inherit = 'res.partner'

    x_partner_counselor_ids = fields.Many2many('res.users', string='Partner Counselors')
