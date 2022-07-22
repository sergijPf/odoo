import ast

# noinspection PyProtectedMember
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class CouponProgram(models.Model):
    _inherit = 'coupon.program'

    x_rule_partner_ids = fields.Many2many('res.partner', compute='_x_compute_rule_partner_ids',
                                          context={'active_test': False})
    x_rule_product_ids = fields.Many2many('product.product', compute='_x_compute_rule_product_ids')
    x_auto_product_ids = fields.Many2many('product.template', relation='x_auto_coupon_to_product_tmpl',
                                          column1='program_id', column2='product_tmpl_id',
                                          domain=[('sale_ok', '=', True)],
                                          string='Automatic coupon creation for products')

    @api.depends('rule_partners_domain')
    def _x_compute_rule_partner_ids(self):
        for program in self:
            program.x_rule_partner_ids = self.env['res.partner'] \
                .search(ast.literal_eval(program.rule_partners_domain or '[]'))
            program.x_rule_partner_ids |= self.env.ref('base.public_partner')

    @api.depends('rule_products_domain')
    def _x_compute_rule_product_ids(self):
        for program in self:
            program.x_rule_product_ids = self.env['product.product'] \
                .search(ast.literal_eval(program.rule_products_domain or '[]'))

    @api.constrains('x_auto_product_ids')
    def _x_check_auto_products(self):
        for product in self.x_auto_product_ids:
            if self.search([('x_auto_product_ids', '=', product.id)], count=True) > 1:
                raise ValidationError(_('One Auto Product could be set in only one coupon program. '
                                        'Product %s', product.name))
