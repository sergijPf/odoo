from odoo import models, fields


class CouponReward(models.Model):
    _inherit = 'coupon.reward'

    reward_type = fields.Selection(selection_add=[('x_product_discount', 'Product Discount')])
