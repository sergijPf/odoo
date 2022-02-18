# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
"""
Describes methods and fields for Magento Delivery Carriers
"""
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from ..python_library.api_request import req


class MagentoDeliveryCarrier(models.Model):
    """
    Model for Magento's carriers.
    """
    _name = 'magento.delivery.carrier'
    _rec_name = 'carrier_code'
    _description = 'Magento Delivery Carrier'

    magento_instance_id = fields.Many2one('magento.instance', "Instance",  help="This field relocates Magento Instance")
    delivery_carrier_ids = fields.One2many("delivery.carrier", "magento_carrier", help="Delivery Methods for Magento")
    carrier_label = fields.Char(string="Label", help="Carrier Label")
    carrier_code = fields.Char(string="Code", help="Carrier Code")
    magento_carrier_title = fields.Char(string="Title", help="Carrier Title")
    active = fields.Boolean(string="Status", default=True)

    _sql_constraints = [('unique_magento_delivery_code', 'unique(magento_instance_id,carrier_code)',
                         'This delivery carrier code is already exists')]

    @api.depends('carrier_code')
    def name_get(self):
        """
        Append the Magento instance name with Delivery Carrier code in the list only.
        :return:
        """
        result = []
        for delivery in self:
            instance_name = ' - ' + delivery.magento_instance_id.name if delivery.magento_instance_id else False
            name = "[" + str(delivery.carrier_label) + "]  " + str(delivery.carrier_code) +\
                   instance_name if instance_name else delivery.carrier_code
            result.append((delivery.id, name))
        return result

    @staticmethod
    def import_delivery_method(instance):
        try:
            url = '/V1/shippingmethod'
            delivery_methods = req(instance, url)
        except Exception as e:
            raise UserError(e)

        for dm in delivery_methods:
            for dm_value in dm.get('value'):
                code = dm_value.get('value')
                odoo_delivery_carrier = instance.shipping_method_ids.with_context(active_test=False).filtered(
                    lambda x: x.carrier_code == code)

                if not odoo_delivery_carrier:
                    odoo_delivery_carrier.create({
                        'carrier_code': code,
                        'carrier_label': dm_value.get('label'),
                        'magento_instance_id': instance.id,
                        'magento_carrier_title': dm.get('label')
                    })


    class DeliveryCarrier(models.Model):
        """
        Inherited for Magento's carriers.
        """
        _inherit = "delivery.carrier"

        magento_carrier = fields.Many2one('magento.delivery.carrier',
                                          help="This field relocates Magento Delivery Carrier")
        magento_carrier_code = fields.Char(related='magento_carrier.carrier_code', string='Base Carrier Code')

        @api.constrains('magento_carrier')
        def _check_magento_carrier_id(self):
            """
            User can only map one Magento carrier code with odoo's single Delivery Method per instance.
            """
            delivery_carrier_obj = self.magento_carrier.delivery_carrier_ids.filtered(lambda x: x.id != self.id)
            if delivery_carrier_obj:
                raise UserError(_("Can't set the same Magento carrier "
                                  "with multiple Delivery Methods for the same Magento Instance"))
