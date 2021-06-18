# -*- coding: utf-8 -*-

from odoo import models, fields

class SaleOrder(models.Model):
    """
    Describes fields and methods for create/ update sale order
    """
    _inherit = 'sale.order'


    magento_carrier_title = fields.Char(
        related='magento_shipping_method_id.magento_carrier_title',
        string='Magento Carrier Title'
    )
    magento_carrier_label = fields.Char(
        related='magento_shipping_method_id.carrier_label',
        string='Magento Carrier Label'
    )
    magento_carrier_name = fields.Char(
        compute="_carrier_name",
        string="Magento Carrier Name",

    )

    def _carrier_name(self):
        """"
        Computes Magento carrier Title and Label
        :return:
        """
        for record in self:
            self.magento_carrier_name = str(self.magento_carrier_title) + ' / ' + str(self. magento_carrier_label)
