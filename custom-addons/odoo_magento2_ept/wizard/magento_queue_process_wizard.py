# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
"""
Describes Wizard for processing order queue
"""
from odoo.exceptions import UserError
from odoo import models, api, _


class MagentoQueueProcessEpt(models.TransientModel):
    """
    Describes Wizard for processing order queue
    """
    _name = 'magento.queue.process.ept'
    _description = 'Magento Queue Process Ept'

    def manual_queue_process(self):
        """
        Process order manually
        """
        queue_process = self._context.get('queue_process')
        if queue_process == "process_order_queue_manually":
            self.process_order_queue_manually()
        if queue_process == "process_product_queue_manually":
            self.process_product_queue_manually()

    @api.model
    def process_order_queue_manually(self):
        """
        Process queued orders manually
        """
        order_queue_ids = self._context.get('active_ids')
        order_queue_ids = self.env['magento.order.data.queue.ept'].browse(order_queue_ids).filtered(
            lambda x: x.state != 'done')
        self.env.cr.execute(
            """update magento_order_data_queue_ept set is_process_queue = False where is_process_queue = True""")
        self._cr.commit()
        for order_queue_id in order_queue_ids:
            queue_lines = order_queue_id.order_data_queue_line_ids.filtered(
                lambda line: line.state in ['draft', 'failed'])
            queue_lines.process_import_magento_order_queue_data()
        return True

    @api.model
    def process_product_queue_manually(self):
        """
        Process queued products manually
        """
        product_queue_ids = self._context.get('active_ids')
        product_queue_ids = self.env['sync.import.magento.product.queue'].\
            browse(product_queue_ids).filtered(lambda x: x.state != 'done')
        self.env.cr.execute(
            """update sync_import_magento_product_queue set is_process_queue = False where is_process_queue = True""")
        self._cr.commit()
        for product_queue_id in product_queue_ids:
            queue_lines = product_queue_id.import_product_queue_line_ids.filtered(
                lambda line: line.state in ['draft', 'failed'])
            queue_lines.process_import_product_queue_data()
        return True

    def set_to_completed_queue(self):
        """
        This method is used to change the queue state as completed.
        """
        queue_process = self._context.get('queue_process')
        if queue_process == "set_to_completed_order_queue":
            self.set_to_completed_order_queue_manually()
        if queue_process == "set_to_completed_product_queue":
            self.set_to_completed_product_queue_manually()

    def set_to_completed_order_queue_manually(self):
        """
        This method is used to set order queue as completed. You can call the method from here:
        Magento => Logs => Orders => SET TO COMPLETED
        :return:
        """
        order_queue_ids = self._context.get('active_ids')
        order_queue_ids = self.env['magento.order.data.queue.ept'].browse(order_queue_ids).filtered(
            lambda x: x.state != 'done')
        self.env.cr.execute(
            """update magento_order_data_queue_ept set is_process_queue = False where is_process_queue = True""")
        self._cr.commit()
        for order_queue_id in order_queue_ids:
            queue_lines = order_queue_id.order_data_queue_line_ids.filtered(
                lambda line: line.state in ['draft', 'failed'])
            queue_lines.write({'state': 'cancel'})
            order_queue_id.message_post(
                body=_("Manually set to cancel queue lines - %s ") % (queue_lines.mapped('magento_order_id')))
        return True

    def set_to_completed_product_queue_manually(self):
        """
        This method is used to set product queue as completed. You can call the method from here:
        Magento => Logs => Products => SET TO COMPLETED
        :return: True
        """
        product_queue_ids = self._context.get('active_ids')
        product_queue_ids = self.env['sync.import.magento.product.queue']. \
            browse(product_queue_ids).filtered(lambda x: x.state != 'done')
        self.env.cr.execute(
            """update sync_import_magento_product_queue set is_process_queue = False where is_process_queue = True""")
        self._cr.commit()
        for product_queue_id in product_queue_ids:
            queue_lines = product_queue_id.import_product_queue_line_ids.filtered(
                lambda line: line.state in ['draft', 'failed'])
            queue_lines.write({'state': 'cancel'})
            product_queue_id.message_post(
                body=_("Manually set to cancel queue lines - %s ") % (queue_lines.mapped('product_sku')))
        return True

    def magento_action_archive(self):
        """
        This method is used to call a child of the instance to active/inactive instance and its data.
        """
        instance_obj = self.env['magento.instance']
        instances = instance_obj.browse(self._context.get('active_ids'))
        for instance in instances:
            instance.magento_action_archive_unarchive()
