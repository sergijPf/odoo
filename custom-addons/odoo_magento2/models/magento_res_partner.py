# -*- coding: utf-8 -*-

import secrets
import string
from odoo import models, fields
from odoo.exceptions import UserError
from ..python_library.api_request import req


class MagentoResPartner(models.Model):
    _name = "magento.res.partner"
    _description = "Magento Res Partner"

    magento_customer_id = fields.Char(string="Magento Customer", help="Magento Customer Id")
    partner_id = fields.Many2one("res.partner", "Customer", ondelete='cascade')
    name = fields.Char(related="partner_id.name", string="Name *")
    phone = fields.Char(related="partner_id.phone", string="Phone")
    email = fields.Char(related="partner_id.email", string="Email *")
    is_company = fields.Boolean(related="partner_id.is_company", string="Is company")
    magento_instance_id = fields.Many2one('magento.instance', string='Magento Instance')
    magento_website_id = fields.Many2one("magento.website", string="Magento Website *")
    customer_group_id = fields.Many2one("magento.customer.groups", string="Customer groups")
    customer_group_name = fields.Char(related="customer_group_id.group_name", string="Customer group *", store=True)
    customer_address_ids = fields.One2many("magento.customer.addresses", 'customer_id',
                                           string="Magento Customer Addresses")
    status = fields.Selection([
        ('imported', 'Imported'),
        ('to_export', 'To be Exported'),
        ('exported', 'Exported')
    ], string="Import/Export status")

    def get_magento_customer(self, magento_instance, customer_dict, odoo_partner, website):
        customer_id = str(customer_dict.get("customer_id"))
        customer_group_id = str(customer_dict.get("customer_group_id"))
        customer_group_name = str(customer_dict.get("customer_group_name"))
        billing_address = customer_dict.get("billing_address")
        delivery_addresses = customer_dict.get("extension_attributes", {}).get("shipping_assignments")
        magento_customer = self.search([('magento_instance_id', '=', magento_instance.id),
                                        ('magento_customer_id', '=', customer_id)])
        if magento_customer:
            # check magento customer group
            if str(magento_customer.customer_group_id.id) != str(customer_group_id):
                group_id = self.customer_group_id.get_customer_group(
                    magento_instance, customer_group_id, customer_group_name
                )
                magento_customer.write({
                    "customer_group_id": group_id.id
                })
            # check customer billing address(magento layer) / invoice address(odoo) exist
            if not len(magento_customer.customer_address_ids.filtered(
                    lambda x: x.magento_customer_address_id == str(billing_address.get('entity_id')) and
                              x.address_type == 'billing')):
                magento_customer.customer_address_ids.create_and_link_customer_address(
                    billing_address, magento_customer, odoo_partner, 'billing'
                )
            # check customer shipping addresses(magento_layer) / delivery address(odoo) exist
            for address in delivery_addresses:
                addr = address.get('shipping', {}).get('address', {})
                if not len(magento_customer.customer_address_ids.filtered(
                        lambda x: x.magento_customer_address_id == str(addr.get('entity_id')) and
                                  x.address_type == 'shipping')):
                    magento_customer.customer_address_ids.create_and_link_customer_address(
                        addr, magento_customer, odoo_partner, 'shipping'
                    )
        else:
            group_id = self.customer_group_id.get_customer_group(magento_instance, customer_group_id, customer_group_name)

            try:
                magento_customer = self.create({
                    'magento_customer_id': customer_id,
                    "customer_group_id": group_id.id,
                    'partner_id': odoo_partner.id,
                    'magento_instance_id': magento_instance.id,
                    'status': 'imported',
                    'magento_website_id':  website.id
                })
            except Exception:
                return

            magento_customer.customer_address_ids.create_and_link_customer_address(
                billing_address, magento_customer, odoo_partner, 'billing'
            )
            for address in delivery_addresses:
                addr = address.get('shipping', {}).get('address', {})
                magento_customer.customer_address_ids.create_and_link_customer_address(
                    addr, magento_customer, odoo_partner, 'shipping'
                )

        return magento_customer

    def export_to_magento(self):
        active_ids = self._context.get("active_ids", [])
        selection = self.browse(active_ids).filtered(lambda x: x.status == 'to_export')
        failed = []

        for instance in {c.magento_instance_id for c in selection}:
            for customer in selection:
                data = self.prepare_customer_data_before_export(customer, failed)
                if data:
                    try:
                        api_url = '/V1/customers'
                        res = req(instance, api_url, 'POST', data)
                    except Exception:
                        failed.append(customer.name)
                        continue
                    if res.get("id"):
                        customer.write({
                            'magento_customer_id': res.get("id"),
                            'status': 'exported'
                        })

        if failed:
            raise UserError("Some of the customers (%s) were failed to export because of missed info for required "
                            "customer(address) fields or there is already customer with such an "
                            "email in Magento" % str(", ".join(failed)))
        else:
            return {
                'effect': {
                    'fadeout': 'slow',
                    'message': " 'Export to Magento' Process Completed Successfully! {}".format(""),
                    'img_url': '/web/static/img/smile.svg',
                    'type': 'rainbow_man',
                }
            }

    def prepare_customer_data_before_export(self, customer, failed):
        if customer.customer_group_id and customer.email and customer.name and customer.magento_website_id:
            name = customer.name.split(',') if customer.name.find(',') > 0 else customer.name.split()
            alphabet = string.ascii_letters + string.digits
            while True:
                password = ''.join(secrets.choice(alphabet) for i in range(10))
                if (any(c.islower() for c in password)
                        and any(c.isupper() for c in password)
                        and sum(c.isdigit() for c in password) >= 3):
                    break

            data = {
                "customer": {
                    "group_id": customer.customer_group_id.group_id,
                    "email": customer.email,
                    "firstname": name[0] if len(name) > 1 else "".join(name),
                    "lastname": " ".join(name[1:]) if len(name) > 1 else "".join(name),
                    "website_id": customer.magento_website_id.magento_website_id,
                    "addresses": []
                },
                "password": password
            }

            for address in customer.customer_address_ids:
                if address.city and address.zip and address.odoo_partner_id.country_id and (address.street or address.street2):
                    name = address.name if address.name else customer.name
                    name = name.split(',') if address.name.find(',') > 0 else address.name.split()

                    data['customer']['addresses'].append({
                        "city": address.city,
                        "country_id": address.odoo_partner_id.country_id.code,
                        "firstname": name[0] if len(name) > 1 else "".join(name),
                        "lastname": " ".join(name[1:]) if len(name) > 1 else "".join(name),
                        "telephone": address.odoo_partner_id.phone,
                        "postcode": address.zip,
                        "street": [s for s in [address.street, address.street2] if s]
                    })
                else:
                    failed.append(customer.name)
                    return
            return data
        else:
            failed.append(customer.name)
            return


class MagentoCustomerAddresses(models.Model):
    _name = "magento.customer.addresses"
    _description = "Magento Customer Addresses"

    address_type = fields.Selection([
        ('shipping', 'Shipping'),
        ('billing', 'Billing'),
        ('other', 'Other')
    ], string="Address Type")
    customer_id = fields.Many2one('magento.res.partner', "Magento Customer")
    magento_customer_address_id = fields.Char(string="Address ID")
    odoo_partner_id = fields.Many2one("res.partner", "Customer", ondelete='cascade')
    name = fields.Char(related="odoo_partner_id.name", string="Name")
    country = fields.Char(related="odoo_partner_id.country_id.code", string="Country *")
    city = fields.Char(related="odoo_partner_id.city", string="City *")
    street = fields.Char(related="odoo_partner_id.street", string="Street *")
    street2 = fields.Char(related="odoo_partner_id.street2", string="Street2")
    zip = fields.Char(related="odoo_partner_id.zip", string="Postcode *")

    def create_and_link_customer_address(self, address_dict, magento_customer, odoo_partner, addr_type):
        if addr_type == 'billing':
            _type = 'invoice'
        elif addr_type == 'shipping':
            _type = 'delivery'
        else:
            _type = 'other'

        country = self.get_country(address_dict.get('country_id'))
        streets = self.get_street_and_street2(address_dict.get('street'))

        # create address in Odoo res.partners
        odoo_address = self.odoo_partner_id.with_context(tracking_disable=True).create({
            'type': _type,
            'parent_id': odoo_partner.id,
            'phone': address_dict.get('telephone'),
            'email': address_dict.get('email'),
            'country_id': country.id if country else False,
            'city': address_dict.get('city'),
            'street': streets.get('street', ''),
            'street2': streets.get('street2', ''),
            'name': address_dict.get('firstname') + ', ' + address_dict.get('lastname'),
            'zip': address_dict.get('postcode'),
            'is_magento_customer': True
        })

        # create address in magento layer
        address_id = self.create({
            'address_type': addr_type,
            'magento_customer_address_id': address_dict.get('entity_id'),
            'customer_id': magento_customer.id,
            'odoo_partner_id': odoo_address.id
        })

        magento_customer.write({
            'customer_address_ids': [(4, address_id.id)]
        })

    def get_country(self, country_name_or_code):
        """
        Usage : Search Country by name or code if not found then use =ilike operator for ignore 'case sensitive'
        search and set limit 1 because it may be possible to find multiple emails due to =ilike operator
        :param country_name_or_code: Country Name or Country Code, Type: Char
        """
        country = self.env['res.country'].search(['|', ('code', '=', country_name_or_code),
                                                  ('name', '=ilike', country_name_or_code)], limit=1)
        return country

    @staticmethod
    def get_street_and_street2(streets):
        """
        Find Street and street2 from customer address
        :param streets: Customer address street
        :return: dictionary of street and street2
        """
        result = {}
        if streets:
            if len(streets) == 1:
                result = {'street': streets[0], 'street2': False}
            elif len(streets) == 2:
                result = {'street': streets[0], 'street2': streets[1]}
            elif len(streets) == 3:
                result = {
                    'street': streets[0] + ' , ' + streets[1],
                    'street2': streets[2]
                }
            elif len(streets) == 4:
                result = {
                    'street': streets[0] + ' , ' + streets[1],
                    'street2': streets[2] + ' , ' + streets[3]
                }
        return result


class MagentoCustomerGroups(models.Model):
    _name = "magento.customer.groups"
    _description = "Magento Customer Groups"
    _rec_name = 'group_name'

    group_id = fields.Char("Magento Group ID", required=True)
    group_name = fields.Char("Magento Group Name")
    active = fields.Boolean("Active", default=True)
    magento_instance_id = fields.Many2one('magento.instance', string='Magento Instance')
    # magento_website_ids = fields.Many2many("magento.website", string="Magento Website")
    # pricelist_id = fields.Many2one('product.pricelist', string="Pricelist", help="Price list related to customer group")

    def get_customer_group(self, magento_instance, customer_group_id, customer_group_name):
        group_id = self.search([('group_id', '=', customer_group_id),
                                ('magento_instance_id', '=', magento_instance.id)])
        if not group_id:
            group_id = self.create({
                'group_id': customer_group_id,
                'group_name': customer_group_name,
                'magento_instance_id': magento_instance.id
            })

        return group_id
