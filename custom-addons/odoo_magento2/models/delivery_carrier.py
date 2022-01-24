# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
"""
Describes methods and fields for Magento's Delivery Carriers
"""
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class DeliveryCarrier(models.Model):
    """
    Inherited for Magento's carriers.
    """
    _inherit = "delivery.carrier"

    magento_carrier = fields.Many2one('magento.delivery.carrier', help="This field relocates Magento Delivery Carrier")
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
