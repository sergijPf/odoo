from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    x_partner_country = fields.Many2one(related='partner_id.country_id', string='Partner Country', store=True,
                                        index=True)
    x_product_category_id = fields.Many2one(related='product_id.categ_id', store=True, index=True)
    x_team_id = fields.Many2one(related='move_id.team_id', store=True, index=True)
