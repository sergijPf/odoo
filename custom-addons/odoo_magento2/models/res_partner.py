# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
"""
Describes methods for importing magento customers into Odoo.
"""
from odoo import models, fields, api

MAGENTO_RES_PARTNER = 'magento.res.partner'


class ResPartner(models.Model):
    _inherit = "res.partner"

    is_magento_customer = fields.Boolean(string="Is Magento Customer?",
                                         help="Used for identified that the customer is imported from Magento store.")
    magento_res_partner_ids = fields.One2many(MAGENTO_RES_PARTNER, "partner_id", string='Magento Customers')
    allow_search_fiscal_based_on_origin_warehouse = fields.Boolean("Search fiscal based on origin warehouse?",
                                                                   default=False)

    @api.model
    def create(self, vals):
        """
        Inherited for calling onchange method.
        We got issue of not setting the gst_treatment field automatically of Indian accounting and same field is
        required and readonly in Sale order.
        """
        partner = super(ResPartner, self).create(vals)
        partner._onchange_country_id()
        return partner

    def process_customer_creation_or_update(self, magento_instance, customer_dict, website):
        message = ""
        odoo_partner = self.get_odoo_customer(customer_dict, website)
        if not odoo_partner:
            message = 'Error while Magento Customer creation in Odoo'
            return False, False, message

        magento_partner = self.env[MAGENTO_RES_PARTNER].get_magento_customer(
            magento_instance, customer_dict, odoo_partner, website
        )
        if not magento_partner:
            message = 'Error while Magento Customer creation in Magento Layer'
            return False, False, message

        return odoo_partner, magento_partner, message

    def get_odoo_customer(self, customer_dict, website):
        customer_email = customer_dict.get("customer_email")
        odoo_partner = self.with_context(active_test=False).search([('email', '=', customer_email),
                                                                    ('type', '=', 'contact'),
                                                                    ('parent_id', '=', False)])
        if len(odoo_partner) > 1:
            odoo_partner = odoo_partner.search([('is_magento_customer', '=', True)], order='date desc', limit=1)

        if odoo_partner:
            if not odoo_partner.active:
                odoo_partner.write({'active': True})
            if not odoo_partner.is_magento_customer:
                odoo_partner.write({'is_magento_customer': True})
        else:
            try:
                odoo_partner = self.create({
                    'email': customer_email,
                    'type': 'contact',
                    'name': customer_dict.get("customer_firstname") + ', ' + customer_dict.get("customer_lastname"),
                    'property_product_pricelist': website.pricelist_id.id,
                    'is_magento_customer': True
                })
            except Exception as e:
                return

        return odoo_partner

