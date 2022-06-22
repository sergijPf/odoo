# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from ..python_library.api_request import req


class MagentoDeliveryCarrier(models.Model):
    _name = 'magento.delivery.carrier'
    _description = 'Magento Delivery Carrier'
    _rec_name = 'carrier_code'

    magento_instance_id = fields.Many2one('magento.instance', string="Magento Instance")
    delivery_carrier_ids = fields.One2many("delivery.carrier", "magento_carrier", string="Odoo Delivery Carriers")
    carrier_label = fields.Char(string="Carrier Label")
    carrier_code = fields.Char(string="Carrier Code")
    magento_carrier_title = fields.Char(string="Carrier Title")

    _sql_constraints = [('unique_magento_delivery_code', 'unique(magento_instance_id,carrier_code)',
                         'This delivery carrier code is already exists')]

    @api.depends('carrier_label', 'carrier_code')
    def name_get(self):
        result = []
        for carrier in self:
            instance_name = (' - ' + carrier.magento_instance_id.name) if carrier.magento_instance_id else ''
            name = "[" + str(carrier.carrier_label) + "]  " + str(carrier.carrier_code) + instance_name
            result.append((carrier.id, name))

        return result

    @staticmethod
    def import_delivery_methods(instance):
        try:
            url = '/V1/shippingmethod'
            delivery_methods = req(instance, url)
        except Exception as e:
            raise UserError(e)

        for dm in delivery_methods:
            for dm_value in dm.get('value'):
                code = dm_value.get('value')
                delivery_carrier = instance.shipping_method_ids.filtered(lambda x: x.carrier_code == code)

                if not delivery_carrier:
                    delivery_carrier.create({
                        'carrier_code': code,
                        'carrier_label': dm_value.get('label'),
                        'magento_instance_id': instance.id,
                        'magento_carrier_title': dm.get('label')
                    })


class DeliveryCarrier(models.Model):
    _inherit = "delivery.carrier"

    magento_carrier = fields.Many2one('magento.delivery.carrier', string="Magento Delivery Carrier", copy=False)
    magento_carrier_code = fields.Char(related='magento_carrier.carrier_code', string='Base Carrier Code')

    @api.constrains('magento_carrier')
    def _check_magento_carrier_id_is_linked_to_one_delivery_method(self):
        for rec in self:
            delivery_carrier = self.search([('magento_carrier', '=', rec.magento_carrier.id),
                                            ('id', '!=', rec.id)])

            if delivery_carrier:
                raise UserError(_("Current 'Magento Delivery Carrier' is already linked to"
                                  " another Delivery Method - %s" % delivery_carrier.mapped('name')))
