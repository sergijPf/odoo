# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
"""
Describes methods for importing magento customers into Odoo.
"""
import json
import time
import logging
from datetime import datetime
from odoo import models, fields, _
from odoo.exceptions import UserError
from .api_request import req, create_search_criteria
from ..python_library.php import Php

MAGENTO_DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'
_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = "res.partner"

    magento_instance_id = fields.Many2one('magento.instance', string='Instance',
                                          help="This field relocates magento instance")
    magento_website_id = fields.Many2one("magento.website", string="Magento Website",
                                         help="Magento Website")
    magento_customer_id = fields.Char(string="Magento Customer", help="Magento Customer Id")
    address_id = fields.Char(string="Address", help="Address Id")

    def import_specific_customer(self, customer_queue_line, country_dict, state_dict, magento_customer):
        """
        Search Customers with magento customer id, if not found then search from email and website id
        If customer found in Odoo then update magento instance and customer id otherwise create new customer.
        :param customer_queue_line: Customer Queue line
        :param country_dict:  Dictionary of Country
        :param state_dict: Dictionary of State
        :param magento_customer: Magento Customer Dictionary
        :return: magento_customer, country_dict, state_dict
        """
        magento_instance = customer_queue_line.magento_instance_id
        customer_response = json.loads(customer_queue_line.customer_data)
        if customer_response.get('vat_id'):
            vat_number = customer_response.get('vat_id')
        else:
            vat_number = customer_response.get('taxvat')
        website_id = magento_instance.magento_website_ids.filtered(
            lambda l: l.magento_website_id == str(customer_response.get('website_id'))).id or False
        partner_vals = {
            'name': "%s %s" % (customer_response.get('firstname'), customer_response.get('lastname')),
            'email': customer_response.get('email'), 'type': 'contact',
            'vat': vat_number, 'magento_website_id': website_id}
        partner = self.search([('magento_customer_id', '=', customer_response.get('id')),
                               ('magento_instance_id', '=', magento_instance.id)], limit=1)
        if not partner:
            partner = self.search([('email', '=', customer_response.get('email')), ('address_id', '=', False),
                                   ('magento_website_id', '=', website_id)])
            if len(partner) > 1:
                partner = self.search([('parent_id', '=', False)])
            if not partner:
                partner_vals.update({
                    'magento_instance_id': magento_instance.id,
                    'magento_customer_id': customer_response.get('id')})
                partner = self.create(partner_vals)
        magento_customer.update({customer_response.get('id'): partner})
        self.create_or_update_child_magento_customer(
            customer_response, state_dict, country_dict, magento_instance, partner.id)
        customer_queue_line.sudo().unlink()
        return magento_customer, country_dict, state_dict

    def create_or_update_child_magento_customer(self, item, state_dict, country_dict, magento_instance, partner_id):
        """
        Create or update child invoice/ shipping partner.
        :param item: item received from Magento
        :param state_dict: Dictionary of state
        :param country_dict: Dictionary of country
        :param magento_instance: Magento Instance
        :param partner_id: Res partner object
        :return:
        """
        website_id = magento_instance.magento_website_ids.filtered(
            lambda l: l.magento_website_id == str(item.get('website_id'))).id or False
        for customer_address in item.get('addresses', []):
            partner_values = self.prepare_customer_vals(
                state_dict, country_dict, magento_instance, customer_address, website_id, item=item)
            address_type = self.get_magento_partner_type_ept(customer_address)
            partner_values.update({'type': address_type})
            company = customer_address.get('company')
            exist_partner = self.find_magento_partner_by_key(partner_values)
            if not exist_partner:
                self.create_non_existing_partner_ept(company, partner_id, partner_values)
            else:
                self.update_existing_partner_ept(company, exist_partner, partner_values)
        return True

    def create_non_existing_partner_ept(self, company, partner_id, partner_values):
        """
        Create New partner if not found in Odoo
        :param company: company id from magento response
        :param partner_id: res.partner()
        :param partner_values: dict()
        :return: Boolean(True)
        """
        partner_values.update({'parent_id': partner_id})
        if company:
            partner_values.pop('company_name')
        child_partner = self.create(partner_values)
        if company:
            child_partner.write({'company_name': company})
        return True

    def update_existing_partner_ept(self, company, exist_partner, partner_values):
        """
        Update missing information to existing odoo customer.
        :param company: magento company id
        :param exist_partner: res.partner
        :param partner_values: dict()
        :return: Boolean (True)
        """
        if (exist_partner.company_name and company and exist_partner.company_name != company) or (
                not exist_partner.company_name and company):
            partner_values.update({'company_name': company})
            self.with_context(tracking_disable=True).create(partner_values)
        elif exist_partner.company_name and not company:
            # partner_values.pop('company_name')
            exist_partner.write(partner_values)
        return True

    @staticmethod
    def get_magento_partner_type_ept(customer_address):
        """
        Find Partner type for as per customer addresses in Magento.
        :param customer_address: dictionary
        :return: string
        """
        default_billing = customer_address.get('default_billing') or False
        default_shipping = customer_address.get('default_shipping') or False
        if default_billing:
            address_type = 'invoice'
        elif default_shipping:
            address_type = 'delivery'
        else:
            address_type = 'other'
        return address_type

    def prepare_customer_vals(self, state_dict, country_dict, magento_instance, customer_address,
                              website_id, customer_id=False, item=False, ship=False):
        """
        This method prepares the customer vals
        :param ship:
        :param state_dict: State dictionary
        :param country_dict: Country dictionary
        :param magento_instance: Instance of Magento
        :param customer_address: Dictionary of customer Address
        :param website_id: Magento Website Id
        :param customer_id: Magento Customer Id or False
        :param item: Customer response received from Magento or False.
        :return: customer values dictionary
        """
        country, state = self.get_country_and_state_dict(country_dict, state_dict, customer_address)
        partner_name = "%s %s" % (customer_address.get('firstname'), customer_address.get('lastname'))
        streets = self.get_street_and_street2(customer_address.get('street'))
        if customer_address.get('vat_id'):
            vat_number = customer_address.get('vat_id')
        else:
            vat_number = customer_address.get('taxvat')
        partner_vals = {
            'name': partner_name,
            'street': streets.get('street', ''),
            'street2': streets.get('street2', ''),
            'city': customer_address.get('city', ''),
            'state_id': state.id if state else False,
            'country_id': country.id if country else False,
            'phone': customer_address.get('telephone', ''),
            'email': item.get('email') if item else customer_address.get('email'),
            'zip': customer_address.get('postcode', ''),
            'lang': magento_instance.lang_id.code,
            'vat' : vat_number,
            'address_id': customer_address.get('id') if item else customer_address.get('entity_id'),
            'magento_instance_id': magento_instance.id, 'magento_website_id': website_id
        }
        if not ship:
            partner_vals.update({'magento_customer_id': item.get('id') if not customer_id and item else customer_id})
        if customer_address.get('company'):
            partner_vals.update({'company_name': customer_address.get('company')})
        return partner_vals

    @staticmethod
    def get_magento_customer_name_ept(item, customer_address):
        """
        Get Customer First Name and Last Name from respective dictionaries of addresses.
        :param item: address dict
        :param customer_address:
        :return: Partner Name String
        """
        if item:
            partner_name = "%s %s" % (item.get('firstname'), item.get('lastname'))
        else:
            partner_name = "%s %s" % (customer_address.get('firstname'), customer_address.get('lastname'))
        return partner_name

    def get_country_and_state_dict(self, country_dict, state_dict, customer_address):
        """
        Get state and country object from customer address.
        :param country_dict: Dictionary of Countries
        :param state_dict: Dictionary of states.
        :param customer_address: Customer address received from Magento.
        :return: Dictionary of state and country
        """
        country = country_dict.get(customer_address.get('country_id'))
        if not country:
            country = self.get_country(customer_address.get('country_id'))
            country_dict.update({customer_address.get('country_id'): country})
        # Get region_code from customer if region
        if not str(customer_address.get('region')):
            region_code = customer_address.get('region').get('region_code', False)
        else:
            region_code = customer_address.get('region_code', False)
        state = state_dict.get(region_code)
        if not state and country:
            state = self.create_or_update_state_ept(country.code, region_code,
                                                    customer_address.get('postcode', False))
            state_dict.update({region_code: state})
        return country, state

    @staticmethod
    def get_street_and_street2(streets):
        """
        Find Street and street2 from customer address.
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

    def find_magento_partner_by_key(self, partner_values):
        """
        Find Partner by specific parameters
        :param partner_values: Partner values dictionary.
        :return: res partner object or False
        """
        key_list = ['name']
        if partner_values.get('street'):
            key_list.append('street')
        if partner_values.get('street2'):
            key_list.append('street2')
        if partner_values.get('city'):
            key_list.append('city')
        if partner_values.get('zip'):
            key_list.append('zip')
        if partner_values.get('phone'):
            key_list.append('phone')
        if partner_values.get('state_id'):
            key_list.append('state_id')
        if partner_values.get('country_id'):
            key_list.append('country_id')
        if partner_values.get('company_name'):
            key_list.append('company_name')
        exist_partner = self._find_partner_ept(partner_values, key_list)
        return exist_partner

    def create_or_update_magento_customer(self, magento_instance, response, magento_invoice_customer,
                                          magento_delivery_customer, state_dict, country_dict,
                                          skip_order, log_book_id, order_dict_id):
        """
        Create or update Magento Customer when create order into Odoo.
        :param magento_instance: Instance of Magento
        :param response: Response received from Magento
        :param magento_invoice_customer: dictionary of magento invoice customer
        :param magento_delivery_customer: dictionary of magento delivery customer
        :param state_dict: dictionary of state
        :param country_dict: dictionary of country
        :return: partner dictionary and Log line
        """
        customer_id = response.get('customer_id', False)
        magento_store = magento_instance.magento_website_ids.store_view_ids.filtered(
            lambda l: l.magento_storeview_id == str(response.get('store_id')))
        customer = self.search([('magento_customer_id', '=', customer_id)], limit=1)
        partner_args = {'magento_invoice_customer': magento_invoice_customer,
                        'magento_delivery_customer': magento_delivery_customer,
                        'customer': customer,
                        'magento_instance': magento_instance,
                        'state_dict': state_dict,
                        'country_dict': country_dict,
                        'magento_store': magento_store}
        # If guest customer or customer id not found in existing invoice customers
        # or customer company name is different from response, then create or update invoice customer.
        invoice_partner = self.get_magento_sale_order_invoice_partner(response, partner_args)
        partner_args.update({'invoice_partner': invoice_partner})
        # If guest customer or customer id not found in existing delivery customers
        # or customer company name is different from response, then create or update delivery customer.
        skip_order, shipping_partner = self.get_magento_sale_order_shipping_partner(response, partner_args,
                                                                                    order_dict_id = order_dict_id,
                                                                                    log_book_id=log_book_id,
                                                                                    skip_order=skip_order)
        if not skip_order:
            shipping_partner = shipping_partner.id if shipping_partner else invoice_partner.id
            partner_dict = {'invoice_partner': invoice_partner.id, 'shipping_partner': shipping_partner}
        else:
            partner_dict = False
        return skip_order, partner_dict

    def get_magento_sale_order_shipping_partner(self, response, partner_args, order_dict_id, log_book_id, skip_order= False):
        """
        Find Shipping Partner from Odoo if not found then create it.
        :param response: dict()
        :param partner_args: dict()
        :return: shipping partner id (integer)
        """
        extension_attributes = response.get('extension_attributes')
        customer_id = response.get('customer_id', False)
        guest_customer = response.get('customer_is_guest')
        shipping_assignments = extension_attributes.get('shipping_assignments')[0]
        ship_address_info = shipping_assignments.get('shipping').get('address') or False
        if not ship_address_info:
            shipping_partner = False
            skip_order = True
            message = _("Shipping detail is not set for customer : Email : %s \n Name : %s %s") \
                      % (response.get('customer_email'), response.get('customer_firstname') or False,
                         response.get('customer_lastname') or False)
            log_book_id.add_log_line(message, response.get('increment_id'),
                                     order_dict_id,"magento_order_data_queue_line_id")
        else:
            ship_company_name = ship_address_info.get('company')
            if guest_customer or (customer_id and customer_id not in partner_args.get('magento_delivery_customer')) or \
                    (partner_args.get('customer').company_name and ship_company_name and
                     partner_args.get('customer').company_name != ship_company_name):
                # Prepare customer values from partner arguments
                partner_vals = self.prepare_customer_vals(partner_args.get('state_dict'), partner_args.get('country_dict'),
                                                          partner_args.get('magento_instance'),
                                                          ship_address_info,
                                                          partner_args.get('magento_store').magento_website_id.id,
                                                          customer_id, ship=True)
                shipping_partner = self.create_or_update_delivery_partner(partner_vals,
                                                                          partner_args.get('magento_delivery_customer'),
                                                                          partner_args.get('invoice_partner'))
            elif not customer_id:
                shipping_partner = False
                skip_order = True
                message = _("Error While Requesting to Access Customer with Email : %s \n Name : %s %s")\
                          % (response.get('customer_email'), response.get('customer_firstname') or False,
                             response.get('customer_lastname') or False)
                log_book_id.add_log_line(message, response.get('increment_id'),
                                         order_dict_id,
                                         "magento_order_data_queue_line_id")
            else:
                shipping_partner = partner_args.get('magento_delivery_customer').get(customer_id)
        return skip_order, shipping_partner

    def get_magento_sale_order_invoice_partner(self, response, partner_args):
        """
        Find Invoice Partner from Odoo if not found then create it.
        :param response: dict()
        :param partner_args: dict()
        :return: invoice partner id (int)
        """
        guest_customer = response.get('customer_is_guest')
        customer_id = response.get('customer_id', False)
        bill_address_info = response.get('billing_address')
        bill_company_name = bill_address_info.get('company')
        if guest_customer or (customer_id and customer_id not in partner_args.get('magento_invoice_customer')) \
                or (partner_args.get('customer').company_name and
                        bill_company_name and
                        partner_args.get('customer').company_name != bill_company_name):
            # Create/Update invoice Partner
            invoice_partner = False
            if bill_address_info:
                partner_vals = self.prepare_customer_vals(partner_args.get('state_dict'),
                                                          partner_args.get('country_dict'),
                                                          partner_args.get('magento_instance'), bill_address_info,
                                                          partner_args.get('magento_store').magento_website_id.id,
                                                          customer_id)
                invoice_partner = self.create_or_update_invoice_partner(partner_vals,
                                                                        partner_args.get('magento_instance'),
                                                                        partner_args.get('magento_invoice_customer'))
        else:
            invoice_partner = partner_args.get('magento_invoice_customer').get(customer_id)
        return invoice_partner

    def create_or_update_invoice_partner(self, partner_vals, instance, magento_invoice_customer):
        """
        Creates or update customer for particular Magento website.
        :param partner_vals: Dictionary of Partner values
        :param instance: instance of Magento
        :param magento_invoice_customer: Magento invoice customer dictionary
        :return: dictionary of invoice address and delivery address.
        """
        magento_customer_id = partner_vals.get('magento_customer_id')
        company_name = partner_vals.get('company_name')
        partner_vals.update({'type': 'invoice'})
        if not magento_customer_id:
            invoice_partner = self.create_or_update_invoice_partner_for_guest_magento_customer(partner_vals,
                                                                                               company_name)
        else:
            invoice_partner = self.create_or_update_invoice_partner_for_magento_customer(partner_vals,
                                                                                         company_name, instance)
        if magento_customer_id:
            magento_invoice_customer.update({magento_customer_id: invoice_partner})
        return invoice_partner

    def create_or_update_invoice_partner_for_guest_magento_customer(self, partner_vals, company_name):
        """
        Create or update invoice partner for Magento Guest Customers.
        :param partner_vals: Dictionary of Partner values
        :param company_name: Company name received from Magento.
        :return: res partner object
        """
        exist_partner = self.find_magento_partner_by_key(partner_vals)
        if company_name:
            partner_vals.pop('company_name')
        if not exist_partner:
            partner_vals.update({'magento_customer_id': 'Guest Customer'})
            exist_partner = self.create(partner_vals)
            self.magento_update_company_name_in_partner(exist_partner, company_name)
        elif (exist_partner.company_name and company_name and exist_partner.company_name != company_name) or (
                not exist_partner.company_name and company_name):
            exist_partner = self.with_context(tracking_disable=True).create(partner_vals)
            self.magento_update_company_name_in_partner(exist_partner, company_name)
        elif exist_partner.company_name and not company_name:
            exist_partner.write(partner_vals)
        invoice_partner = exist_partner
        return invoice_partner

    def create_or_update_invoice_partner_for_magento_customer(self, partner_vals, company_name, instance):
        """
        Create or update invoice type partner for Magento website.
        :param partner_vals: Dictionary of partner values
        :param company_name: company name received from Magento
        :param instance: Magento instance object
        :return: res partner object
        """
        exist_partner = self.search([('magento_customer_id', '=', partner_vals.get('magento_customer_id')),
                                     ('is_company', '=', False), '|', ('company_id', '=', False),
                                     ('company_id', '=', instance.company_id.id),('email','=',partner_vals.get('email'))], limit=1)
        if company_name:
            partner_vals.pop('company_name')
        if not exist_partner:
            invoice_partner = self.with_context(tracking_disable=True).create(partner_vals)
            self.magento_update_company_name_in_partner(invoice_partner, company_name)
        elif partner_vals.get('name') and exist_partner.name != partner_vals.get('name'):
            invoice_partner = self.with_context(tracking_disable=True).create({
                'parent_id': exist_partner.id, **partner_vals})
            self.magento_update_company_name_in_partner(invoice_partner, company_name)
        else:
            if (exist_partner.company_name and company_name and exist_partner.company_name != company_name) or (
                    not exist_partner.company_name and company_name):
                exist_partner = self.create(partner_vals)
                self.magento_update_company_name_in_partner(exist_partner, company_name)
            elif exist_partner.company_name and not company_name:
                exist_partner.write(partner_vals)
            invoice_partner = exist_partner
        return invoice_partner

    @staticmethod
    def magento_update_company_name_in_partner(partner, company_name):
        """
        Update company name in partner if available in response of API.
        :param partner: res.partner()
        :param company_name: string
        :return: boolean
        """
        if company_name:
            partner.write({'company_name': company_name})

    def create_or_update_delivery_partner(self, partner_vals, magento_delivery_customer, invoice_partner):
        """
        Creates or update customer for particular Magento website.
        :param partner_vals: Dictionary of Partner values
        :param magento_delivery_customer: Magento delivery customer dictionary
        :param invoice_partner: invoice partner object
        :return: res.partner()
        """
        zip_code = partner_vals.get('zip_code')
        company_name = partner_vals.get('company_name')
        delivery = invoice_partner if \
            (invoice_partner and invoice_partner.name == partner_vals.get('name')
             and invoice_partner.street == partner_vals.get('street')
             and (not invoice_partner.street2 or invoice_partner.street2 == partner_vals.get('street2'))
             and invoice_partner.zip == zip_code and invoice_partner.city == partner_vals.get('city')
             and invoice_partner.country_id.id == partner_vals.get('country_id')
             and invoice_partner.state_id.id == partner_vals.get('state_id')) else None
        if not delivery:
            delivery = self.find_magento_partner_by_key(partner_vals)
            if not delivery:
                delivery = self.create_delivery_partner(partner_vals, invoice_partner)
            elif delivery.company_name and company_name and delivery.company_name != company_name:
                delivery = self.create_delivery_partner(partner_vals, invoice_partner)
            elif delivery.company_name and not company_name:
                delivery.write(partner_vals)
        magento_delivery_customer.update({partner_vals.get('magento_customer_id'): delivery})
        return delivery

    def create_delivery_partner(self, partner_vals, invoice_partner):
        """
        Create delivery type partner
        :param partner_vals: Dictionary of partner values
        :param invoice_partner: res partner object
        :return:
        """
        company_name = partner_vals.get('company_name')
        delivery = self.with_context(tracking_disable=True).create({
            'type': 'delivery',
            'parent_id': invoice_partner and invoice_partner.id or False,
            **partner_vals,
        })
        if company_name:
            delivery.write({'company_name': company_name})
        return delivery
