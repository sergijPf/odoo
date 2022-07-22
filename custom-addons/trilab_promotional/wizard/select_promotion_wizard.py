from odoo import models, fields, api


class SelectPromotionWizard(models.TransientModel):
    _name = 'trilab_promotional.select_promotion_wizard'
    _description = 'Trilab Promotional Select Promotion Wizard'

    order_id = fields.Many2one('sale.order', readonly=True, required=True)
    available_program_ids = fields.Many2many('coupon.program', compute='_compute_available_program_ids', readonly=True)
    program_id = fields.Many2one('coupon.program', required=True)

    @api.depends('order_id')
    def _compute_available_program_ids(self):
        for wizard in self:
            # noinspection PyProtectedMember
            wizard.available_program_ids = wizard.order_id._get_applicable_no_code_promo_program()

    def button_apply_program(self):
        self.ensure_one()

        program = self.program_id
        order = self.order_id

        # noinspection PyProtectedMember
        error_status = program._check_promo_code(order, False)
        if not error_status.get('error'):
            if program.promo_applicability == 'on_next_order':
                # noinspection PyProtectedMember
                order.state != 'cancel' and order._create_reward_coupon(program)
            elif program.reward_type == 'x_product_discount' and program.discount_type == 'percentage':
                discount = program.discount_percentage
                # noinspection PyProtectedMember
                valid_product_ids = program._get_valid_products(order.order_line.product_id)
                order.order_line \
                    .filtered(lambda line: line.product_id in valid_product_ids and line.discount < discount) \
                    .write({'discount': discount})
            elif program.discount_line_product_id.id not in order.order_line.mapped('product_id').ids:
                # noinspection PyProtectedMember
                order.write({'order_line': [(0, 0, value) for value in order._get_reward_line_values(program)]})
            order.no_code_promo_program_ids |= program
