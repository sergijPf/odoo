from odoo import models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _x_auto_create_coupons(self):
        order_to_send_mail_ids = self.env['sale.order']
        for order in self:
            self = self.with_context(lang=order.partner_id.lang).sudo()
            for line in order.order_line.filtered(lambda l: l.product_id):
                coupon_program = self.env['coupon.program'].search([
                    ('x_auto_product_ids', '=', line.product_id.product_tmpl_id.id),
                    ('currency_id', '=', order.currency_id.id)
                ], limit=1)
                if coupon_program:
                    generated_coupons = len(order.generated_coupon_ids
                                            .filtered(lambda c: c.program_id == coupon_program))
                    coupons_to_generate = int(line.product_uom_qty) - generated_coupons
                    for count in range(coupons_to_generate):
                        self.env['coupon.coupon'].create([{'program_id': coupon_program.id, 'order_id': order.id}])
                        order_to_send_mail_ids |= order

        # noinspection PyProtectedMember
        order_to_send_mail_ids._send_reward_coupon_mail()

    def _action_confirm(self):
        # noinspection PyProtectedMember
        res = super(SaleOrder, self)._action_confirm()
        self._x_auto_create_coupons()
        return res
