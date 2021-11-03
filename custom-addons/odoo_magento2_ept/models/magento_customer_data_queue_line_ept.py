# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
"""
Describes methods to store Customer Data queue line
"""
import time
import json
# from datetime import timedelta, datetime
from odoo import models, fields
MAGENTO_CUSTOMER_DATA_QUEUE_EPT = "magento.customer.data.queue.ept"


class MagentoCustomerDataQueueLineEpt(models.Model):
    """
    Describes Customer Data Queue Line
    """
    _name = "magento.customer.data.queue.line.ept"
    _description = "Magento Customer Data Queue Line EPT"
    _rec_name = "magento_customer_id"
    magento_customer_data_queue_id = fields.Many2one(MAGENTO_CUSTOMER_DATA_QUEUE_EPT, ondelete="cascade")
    magento_instance_id = fields.Many2one(
        'magento.instance',
        string='Magento Instance',
        help="Customer imported from this Magento Instance."
    )
    state = fields.Selection([
        ("draft", "Draft"),
        ("failed", "Failed"),
        ("done", "Done")
    ], default="draft", copy=False)
    magento_customer_id = fields.Char(help="Id of imported customer.", copy=False)
    customer_id = fields.Many2one(
        "res.partner",
        copy=False,
        help="Customer created in Odoo."
    )
    customer_data = fields.Text(help="Data imported from Magento of current customer.", copy=False)
    processed_at = fields.Datetime(
        help="Shows Date and Time, When the data is processed",
        copy=False
    )
    magento_customer_common_log_lines_ids = fields.One2many(
        "common.log.lines.ept",
        "magento_customer_data_queue_line_id",
        help="Log lines created against which line."
    )

    def create_import_customer_queue_line(self, customers, magento_instance):
        """
        Creates an imported customer queue line
        :param customers: Items received from Magento
        :param magento_instance: Instance of Magento
        :return: True
        """
        customer_queue = self.magento_create_customer_queue(magento_instance)
        for customer in customers:
            magento_customer_id = customer.get('id', False)
            data = json.dumps(customer)
            customer_queue_line_values = {
                'magento_customer_id': magento_customer_id,
                'magento_instance_id': magento_instance and magento_instance.id or False,
                'customer_data': data,
                'magento_customer_data_queue_id': customer_queue and customer_queue.id or False,
                'state': 'draft',
            }
            self.create(customer_queue_line_values)
        return True

    def magento_create_customer_queue(self, magento_instance):
        """
        Creates Imported Magento Customer queue
        :param magento_instance: Instance of Magento
        :return: Magento Customer Data queue object
        """
        customer_queue_vals = {
            'magento_instance_id': magento_instance and magento_instance.id or False,
            'state': 'draft',
        }
        customer_queue_data = self.env[MAGENTO_CUSTOMER_DATA_QUEUE_EPT].create(
            customer_queue_vals
        )
        return customer_queue_data

    def auto_import_customer_queue_data(self):
        """
        This method used to process synced magento customer data in batch of 50 queue lines.
        This method is called from cron job.
        """
        customer_queue_ids = []
        country_dict = {}
        state_dict = {}
        customer_dict = {}
        magento_order_data_queue_obj = self.env[MAGENTO_CUSTOMER_DATA_QUEUE_EPT]
        start = time.time()
        query = """select queue.id from magento_customer_data_queue_line_ept as queue_line
                inner join magento_customer_data_queue_ept as queue on queue_line.magento_customer_data_queue_id = queue.id
                where queue_line.state='draft' ORDER BY queue_line.create_date ASC"""
        self._cr.execute(query)
        customer_data_queue_list = self._cr.fetchall()
        for result in customer_data_queue_list:
            customer_queue_ids.append(result[0])
        if customer_queue_ids:
            customer_queues = magento_order_data_queue_obj.browse(list(set(customer_queue_ids)))
            customer_queue_process_cron_time = customer_queues.magento_instance_id.get_magento_cron_execution_time(
                "odoo_magento2_ept.magento_ir_cron_to_process_customer_queue_data")
            for customer_queue in customer_queues:
                customer_queue_lines = customer_queue.customer_queue_line_ids.filtered(lambda x: x.state == "draft")
                if customer_queue_lines:
                    customer_dict, country_dict, state_dict = customer_queue_lines.process_import_customer_queue_data(
                        country_dict, state_dict, customer_dict)
                if time.time() - start > customer_queue_process_cron_time - 60:
                    return True
        return True

    def process_import_customer_queue_data(self, country_dict, state_dict, customer_dict):
        """
        This method processes order queue lines.
        """
        partner_obj = self.env['res.partner']
        customer_queue = self.magento_customer_data_queue_id
        for customer_queue_line in self:
            customer_dict, country_dict, state_dict = partner_obj.import_specific_customer(
                customer_queue_line, country_dict, state_dict, customer_dict)
        if not customer_queue.customer_queue_line_ids:
            customer_queue.sudo().unlink()
        return customer_dict, country_dict, state_dict
