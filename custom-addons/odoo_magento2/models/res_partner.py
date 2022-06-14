# -*- coding: utf-8 -*-

from odoo import models, fields


class ResPartner(models.Model):
    _inherit = "res.partner"

    is_magento_customer = fields.Boolean(string="Is Magento Customer?",
                                         help="Used for identified that the customer is imported from Magento store.")
    magento_res_partner_ids = fields.One2many('magento.res.partner', "partner_id", string='Magento Customers')

    def check_customer_and_addresses_exist(self, instance, customer_dict, website):
        message = ""
        odoo_partner = self.get_odoo_res_partner(customer_dict, website)

        if not odoo_partner or isinstance(odoo_partner, str):
            message = 'Error creating Customer in Odoo ' + odoo_partner if isinstance(odoo_partner, str) else '.'
            return False, False, message

        magento_addresses = self.env['magento.res.partner'].get_magento_res_partner(
            instance, customer_dict, odoo_partner, website
        )
        if not magento_addresses or isinstance(magento_addresses, str):
            message = f'Error while Magento Customer creation in ' \
                      f'Magento Layer {magento_addresses if isinstance(magento_addresses, str) else ""}'
            return False, False, message

        return odoo_partner, magento_addresses, message

    def get_odoo_res_partner(self, customer_dict, website):
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
                    'name': f'{customer_dict.get("customer_firstname", "")}, {customer_dict.get("customer_lastname", "")}',
                    'property_product_pricelist': website.pricelist_id.id,
                    'is_magento_customer': True
                })
            except Exception as e:
                return str(e) + '.'

        return odoo_partner

    def check_address_exists(self, address_dict):
        country, streets, type = self.get_address_details(address_dict)
        city = address_dict.get('city')
        street = streets.get('street', '')
        street2 = streets.get('street2', '')
        zip = address_dict.get('postcode')

        exists = self.filtered(
            lambda x: x.type == type and
                      {x.country_id.id, x.city, x.zip, x.street or '', x.street2 or ''} == {country.id, city, zip, street, street2}
        )

        if exists and not exists[0]['is_magento_customer']:
            exists[0]['is_magento_customer'] = True

        return True if exists else False

    def get_address_details(self, address_dict):
        addr_type = address_dict.get('address_type')
        country_code = address_dict.get('country_id')
        country = self.env['res.country'].search(['|', ('code', '=', country_code),
                                                  ('name', '=ilike', country_code)], limit=1)
        streets = self.get_street_and_street2(address_dict.get('street'))

        if addr_type == 'billing':
            _type = 'invoice'
        elif addr_type == 'shipping':
            _type = 'delivery'
        else:
            _type = 'other'

        return country, streets, _type

    @staticmethod
    def get_street_and_street2(streets):
        result = {}

        if streets:
            if len(streets) == 1:
                result = {'street': streets[0], 'street2': ""}
            elif len(streets) == 2:
                result = {'street': streets[0], 'street2': streets[1]}
            elif len(streets) == 3:
                result = {
                    'street': streets[0] + ', ' + streets[1],
                    'street2': streets[2]
                }
            elif len(streets) == 4:
                result = {
                    'street': streets[0] + ', ' + streets[1],
                    'street2': streets[2] + ', ' + streets[3]
                }

        return result
