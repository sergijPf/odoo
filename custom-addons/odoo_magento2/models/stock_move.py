# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
"""
Describes methods for stock move.
"""
from odoo import models


class StockMove(models.Model):
    """
    Describes Magento order stock picking values
    """
    _inherit = 'stock.move'

    def _get_new_picking_values(self):
        """
        We need this method to set our custom fields in Stock Picking
        :return:
        """
        res = super(StockMove, self)._get_new_picking_values()
        sale_order = self.group_id.sale_id
        sale_line_id = sale_order.order_line
        if sale_order and sale_line_id and sale_order.magento_instance_id:
            res.update({
                'magento_instance_id': sale_order.magento_instance_id.id,
                'is_exported_to_magento': False,
                'is_magento_picking': True
            })
        return res

    def _action_assign(self):
        """
        In Dropshipping case, While create picking
        set magento instance id and magento picking as True
        if the order is imported from the Magento Instance.
        :return:
        """
        res = super(StockMove, self)._action_assign()
        picking_ids = self.mapped('picking_id')
        for picking in picking_ids:
            if not picking.magento_instance_id and picking.sale_id and picking.sale_id.magento_instance_id:
                picking.write({
                    'magento_instance_id': picking.sale_id.magento_instance_id.id,
                    'is_exported_to_magento': False,
                    'is_magento_picking': True
                })
        return res

