# -*- coding: utf-8 -*-

from odoo import fields, models


class MagentoCustomerGroupUpdate(models.TransientModel):
    _name = "magento.customer.group.update"
    _description = "Update Customer Group for Magento Customers"

    magento_instance_id = fields.Many2one('magento.instance', 'Magento Instance')
    customer_group_id = fields.Many2one('magento.customer.groups', 'Customer group')

    def update_customer_group_for_exported_customers(self):
        active_ids = self._context.get("active_ids", [])
        customers_to_update = self.env['magento.res.partner'].browse(active_ids).filtered(
            lambda x: x.magento_instance_id.id == self.magento_instance_id.id and x.status == 'to_export'
        )
        if customers_to_update:
            customers_to_update.write({
                'customer_group_id': self.customer_group_id.id
            })
