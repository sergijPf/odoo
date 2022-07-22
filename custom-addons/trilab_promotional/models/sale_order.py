from odoo import models, _


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _get_reward_line_values(self, program):
        if program.reward_type == 'x_product_discount':
            return []
        # noinspection PyProtectedMember
        return super(SaleOrder, self)._get_reward_line_values(program)

    def _update_existing_reward_lines(self):
        self.ensure_one()

        # Checks if all reward line values are not empty to prevent IndexError
        applied_programs = self._get_applied_programs_with_rewards_on_current_order()
        if all(self._get_reward_line_values(program) for program in applied_programs):
            # noinspection PyProtectedMember
            return super(SaleOrder, self)._update_existing_reward_lines()

    # noinspection PyProtectedMember
    def _create_new_no_code_promo_reward_lines(self):
        super(SaleOrder, self)._create_new_no_code_promo_reward_lines()

        # set discount on x_product_discount programs when line discount is lower than program discount_percentage
        programs = self._get_applicable_no_code_promo_program() \
            ._keep_only_most_interesting_auto_applied_global_discount_program() \
            .filtered(lambda p: p.reward_type == 'x_product_discount' and p.discount_type == 'percentage')
        for program in programs:
            discount = program.discount_percentage
            valid_product_ids = program._get_valid_products(self.order_line.product_id)
            self.order_line.filtered(lambda line: line.product_id in valid_product_ids and line.discount < discount) \
                .write({'discount': discount})
            self.no_code_promo_program_ids |= program

    def x_action_select_promotion(self):
        self.ensure_one()
        ctx = dict(self.env.context, default_order_id=self.id)

        self._remove_invalid_reward_lines()
        return {
            'name': _('Select Promotion'),
            'type': 'ir.actions.act_window',
            'res_model': 'trilab_promotional.select_promotion_wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': ctx,
        }
