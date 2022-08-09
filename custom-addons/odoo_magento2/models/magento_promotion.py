# -*- coding: utf-8 -*-

from datetime import datetime

from odoo import fields, models, api
from odoo.exceptions import UserError

from ..python_library.api_request import req

import ast


class MagentoPromotion(models.Model):
    _name = 'magento.promotion'

    coupon_program_id = fields.Many2one('coupon.program', "Odoo Promotion")
    name = fields.Char("Name", related='coupon_program_id.name')
    rule_id = fields.Char("Rule ID", help='Magento Rule ID')
    magento_instance_id = fields.Many2one('magento.instance', 'Magento Instance')
    website_ids = fields.Many2many('magento.website', string='Magento Websites')
    customer_group_ids = fields.Many2many('magento.customer.groups', string='Magento Customer Groups')
    active = fields.Boolean("Active", default=True)
    rule_date_from = fields.Datetime("Start date", related="coupon_program_id.rule_date_from")
    rule_date_to = fields.Datetime("End date", related="coupon_program_id.rule_date_to")
    min_amount = fields.Float("Min. amount(incl.tax)", related="coupon_program_id.rule_minimum_amount")
    reward_type = fields.Selection(related="coupon_program_id.reward_type")
    promo_code = fields.Char(related="coupon_program_id.promo_code")
    discount_type = fields.Selection(related="coupon_program_id.discount_type")
    discount_perc = fields.Float(related="coupon_program_id.discount_percentage")
    discount_apply_on = fields.Selection(related="coupon_program_id.discount_apply_on")
    discounted_price = fields.Float("Price incl. discount", compute="_compute_discounted_price")

    gift_product_ids = fields.Many2many("magento.product.product", compute="_compute_gift_products",
                                        string="Gift/Discounted Products")
    rule_applied_to_product_ids = fields.Many2many("magento.product.product", compute="_compute_applied_to_products",
                                                   string="Applied to Products")
    applied_to_products = fields.Char(compute="_compute_applied_to_products", string="Applied to")
    issue = fields.Boolean("Issue", compute="_compute_promotion_has_an_issue")
    export_status = fields.Selection([
        ('not_exported', 'not Exported'),
        ('exported', 'Exported')
    ], string='Export Status', help='The status of Promotion rule export to Magento ', default='not_exported',
        copy=False)

    @api.depends('coupon_program_id.discount_specific_product_ids')
    def _compute_gift_products(self):
        for rec in self:
            rec.gift_product_ids = rec.coupon_program_id.discount_specific_product_ids.magento_product_ids.filtered(
                lambda x: x.magento_instance_id == rec.magento_instance_id).ids

    @api.depends('coupon_program_id.rule_products_domain')
    def _compute_applied_to_products(self):
        for rec in self:
            rule_domain = rec.coupon_program_id.rule_products_domain
            domain = ast.literal_eval(rule_domain) if rule_domain else []
            prod_variants = self.env['product.product'].search(domain)
            rec.rule_applied_to_product_ids = prod_variants.magento_product_ids.filtered(
                lambda x: x.magento_instance_id == rec.magento_instance_id).ids if prod_variants else False

            rec.applied_to_products = f"{rule_domain} - applied to {len(rec.rule_applied_to_product_ids)} products from Magento layer"

    def _compute_promotion_has_an_issue(self):
        for rec in self:
            rec.issue = True if (not rec.gift_product_ids or not rec.rule_applied_to_product_ids) else False

    @api.depends('discount_perc')
    def _compute_discounted_price(self):
        for rec in self:
            if rec.discount_type == 'percentage' and rec.discount_apply_on == 'specific_products' and rec.discount_perc:
                if rec.magento_instance_id and len(rec.website_ids) == 1 and len(rec.gift_product_ids) == 1:
                    simpl_prod = rec.gift_product_ids
                    rec.discounted_price = round(simpl_prod.get_product_price_for_website(
                        rec.website_ids, simpl_prod.odoo_product_id) * (1 - rec.discount_perc / 100), 2)
                    continue

            rec.discounted_price = 0

    def write(self, vals):
        if 'website_ids' in vals:
            if self.discount_perc and len(vals['website_ids'][0][2]) > 1:
                raise UserError("Cannot apply one discount percentage to multiple websites")

        return super(MagentoPromotion, self).write(vals)

    def get_valid_simple_products(self):
        form_view_id = self.env.ref('odoo_magento2.view_magento_product_form').id
        tree_view = self.env.ref('odoo_magento2.view_magento_product_tree').id

        return {
            'name': 'Magento Simple Products',
            'type': 'ir.actions.act_window',
            'view_mode': 'tree, form',
            'res_model': 'magento.product.product',
            'views': [(tree_view, 'tree'), (form_view_id, 'form')],
            'view_id': tree_view,
            'target': 'new',
            'domain': [('id', 'in', self.rule_applied_to_product_ids.ids)]
        }

    def process_promotion_delete_in_magento(self):
        self.ensure_one()

        if not self.rule_id:
            raise UserError("Promo Rule can't be deleted in Magento as it wasn't exported yet.")

        try:
            api_url = f"/all/V1/salesRules/{self.rule_id}"
            res = req(self.magento_instance_id, api_url, 'DELETE')
        except Exception as e:
            raise UserError(f"Failed to delete Promo Rule in Magento: {str(e)}")

        if res:
            self.write({'export_status': 'not_exported', 'rule_id': ''})
        else:
            raise UserError(f"Failed to delete Promo Rule in Magento: {str(res)}")

    def process_promotion_export_to_magento(self):
        """ Promotion has some setup specifications to be compatible with Magento possibilities:
        "rule_partners_domain" to be ignored,
        "maximum_use_number" to be ignored,
        rule_minimum_amount_tax_inclusion = tax_included,
        promo_applicability = on_current_order,
        reward_type = discount, x_product_discount,
        discount_type = percentage,
        discount_apply_on = specific_products"""
        self.ensure_one()

        if not self.magento_instance_id:
            raise UserError("The Promotion cannot be exported because of missed Magento Instance")

        if not self.website_ids:
            raise UserError("The Promotion cannot be exported because of missed Magento Website(s)")

        if self.discount_type == 'percentage':
            if self.discount_apply_on != 'specific_products':
                raise UserError("The promotion can't have 'Discount Applied on' other than 'On Specific Products' "
                                "for Magento to export")
            if not self.gift_product_ids:
                raise UserError("The Promotion cannot be exported because of missed Gift Product(s)")
        else:
            raise UserError("The Promotion cannot be exported to Magento with value other than 'Percentage' for "
                            "'Discount Type' field")

        if not self.rule_applied_to_product_ids:
            raise UserError("The Promotion cannot be exported because of missed products to be applied to")

        if self.min_amount and self.coupon_program_id.rule_minimum_amount_tax_inclusion == 'tax_excluded':
            raise UserError("The promotion with Tax Exclude amount cannot be exported to Magento.")

        if self.reward_type not in ['discount', 'x_product_discount']:
            raise UserError("The promotion has to have 'Discount' or 'Product Discount' reward type")

        data = self._prepare_promo_data()

        try:
            api_url = '/all/V1/salesRules'
            res = req(self.magento_instance_id, api_url, 'POST', data)
        except Exception as e:
            raise UserError(f"Failed to export Promotion rule to Magento: {str(e)}")

        if isinstance(res, dict) and res.get('rule_id'):
            rule_id = res['rule_id']

            if self.coupon_program_id.promo_code_usage == 'code_needed' and self.promo_code:
                self.process_coupon_code_creation_in_magento(rule_id)

            self.write({'export_status': 'exported', 'rule_id': rule_id})
        else:
            raise UserError(f"Failed to export Promo rule. Returned result: {str(data)}")

    def _prepare_promo_data(self):
        group_ids = self.customer_group_ids
        cust_groups = group_ids if group_ids else group_ids.search([('magento_instance_id', '=', self.magento_instance_id.id)])

        rule = {
            "name": self.name,
            "website_ids": self.website_ids.mapped('magento_website_id'),
            "customer_group_ids": cust_groups.mapped('group_id'),
            "is_active": True,
            "stop_rules_processing": False,
            "is_advanced": True,
            "simple_action": "offer_product",
            "discount_amount": 0,
            "apply_to_shipping": False,
            "coupon_type": "SPECIFIC_COUPON" if self.coupon_program_id.promo_code_usage == 'code_needed' else 'NO_COUPON',
            "simple_free_shipping": "0",
            "extension_attributes": {
                "gift_rule": {
                    "maximum_number_product": 1
                }
            }
        }

        from_date = datetime.strftime(self.rule_date_from if self.rule_date_from else datetime.now(), '%Y-%m-%d')
        rule.update({'from_date': from_date})

        if self.rule_date_to:
            to_date = datetime.strftime(self.rule_date_to, '%Y-%m-%d')
            rule.update({'to_date': to_date})

        if self.discount_perc:
            if len(self.website_ids) > 1 and len(self.gift_product_ids) > 1:
                raise UserError("It's not allowed to apply a single discount for more than one website within one Instance "
                                "and more than one 'gift' product at once. Please create another rule instead.")

            rule['extension_attributes']['gift_rule'].update({'gift_price': self.discounted_price})

        rule.update({"action_condition": self._get_promo_action_conditions()})
        rule.update({"condition": self._get_promo_conditions()})

        return {'rule': rule}

    def _get_promo_action_conditions(self):
        action_cond = {
            "condition_type": "Magento\\SalesRule\\Model\\Rule\\Condition\\Product\\Combine",
            "aggregator_type": "all",
            "operator": 'null',
            "value": "1"
        }

        if self.discount_type == 'percentage':
            action_cond.update({
                "conditions": [{
                    "condition_type": "Magento\\SalesRule\\Model\\Rule\\Condition\\Product",
                    "operator": "()",
                    "attribute_name": "sku",
                    "value": ','.join(self.gift_product_ids.mapped('magento_sku'))
                }],
            })

        return action_cond

    def _get_promo_conditions(self):
        applied_to_prods = self.rule_applied_to_product_ids

        is_all_prods = True if len(applied_to_prods.filtered(lambda x: x.magento_product_id)) == applied_to_prods.search([
            ('magento_instance_id', '=', self.magento_instance_id.id),
            ('magento_product_id', 'not in', [False, ''])
        ], count=True) else False

        data = {
            "condition_type": "Magento\\SalesRule\\Model\\Rule\\Condition\\Combine",
            "conditions": [],
            "aggregator_type": "all",
            "operator": 'null',
            "value": "1"
        }

        if is_all_prods:
            condition = {
                "condition_type": "Magento\\SalesRule\\Model\\Rule\\Condition\\Address",
                "operator": ">=",
                "attribute_name": "base_subtotal_total_incl_tax",
                "value": self.min_amount
            }
        else:
            condition = {
                "condition_type": "Magento\\SalesRule\\Model\\Rule\\Condition\\Product\\Subselect",
                "conditions": [{
                    "condition_type": "Magento\\SalesRule\\Model\\Rule\\Condition\\Product",
                    "operator": "()",
                    "attribute_name": "sku",
                    "value": ','.join(self.rule_applied_to_product_ids.mapped('magento_sku'))
                }],
                "aggregator_type": "all",
                "operator": ">=",
                "attribute_name": "base_row_total",
                "value": self.min_amount
            }

        data['conditions'].append(condition)

        return data

    def process_coupon_code_creation_in_magento(self, rule_id):
        promo_code = self.promo_code
        data = {
            'coupon': {
                'rule_id': rule_id,
                'code': promo_code,
                'is_primary': True
            }
        }

        try:
            api_url = '/all/V1/coupons'
            res = req(self.magento_instance_id, api_url, 'POST', data)
        except Exception as e:
            raise UserError(f"Failed to create Coupon Code '{promo_code}' in Magento: {str(e)}")

        if isinstance(res, dict) and not res.get('coupon_id'):
            raise UserError(f"Failed to create Coupon Code '{promo_code}' in Magento: {str(res)}")
