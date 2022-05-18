# -*- coding: utf-8 -*-

import json
from odoo import fields, models
from odoo.exceptions import UserError
from ..python_library.api_request import req


class MagentoAsyncBulkLogs(models.Model):
    _name = 'magento.async.bulk.logs'
    _description = 'Logs of Async Export data to Magento'
    _rec_name = 'bulk_uuid'

    bulk_uuid = fields.Char('Bulk ID')
    magento_product_ids = fields.Many2many('magento.product.product', string="Magento Product", ondelete='cascade')
    magento_conf_product_ids = fields.Many2many('magento.configurable.product', string="Magento Conf.Product", ondelete='cascade')
    log_details_ids = fields.One2many('magento.async.bulk.log.details', 'bulk_log_id', 'Log details')
    topic = fields.Char(string="Related topic")
    is_conf_prod = fields.Boolean("Is configurable product?", compute="_check_if_config_or_not")

    def _check_if_config_or_not(self):
        for record in self:
            record.is_conf_prod = True if len(record.magento_conf_product_ids) else\
                False if len(record.magento_product_ids) else None

    def update_bulk_log_status(self):
        self.ensure_one()

        if not self.bulk_uuid:
            raise UserError("Missed Bulk ID")

        if self.log_details_ids:
            self.log_details_ids.sudo().unlink()

        response = self.get_detailed_status_of_log()

        for item in response.get('operations_list', []):
            data = {}
            ser_data = item.get("result_serialized_data", "") or item.get("serialized_data", "")
            if ser_data:
                data = json.loads(ser_data)
                if not isinstance(data, dict):
                    data = {}

            self.log_details_ids.create({
                'bulk_log_id': self.id,
                'log_line_id': item.get('id'),
                'sku': data.get("sku", ""),
                'log_status': str(item.get('status', '0')),
                'result_message': item.get('result_message', '')
            })

    def get_detailed_status_of_log(self):
        instance = self.with_context(active_test=False).magento_conf_product_ids.magento_instance_id or \
                   self.with_context(active_test=False).magento_product_ids.magento_instance_id

        if not instance:
            return {}

        try:
            api_url = '/V1/bulk/%s/detailed-status' % self.bulk_uuid
            response = req(instance, api_url)
        except Exception as e:
            raise UserError("Error while requesting Magento data!" + str(e))

        return response if isinstance(response, dict) else {}

    def check_bulk_log_status(self):
        response = self.get_detailed_status_of_log()
        log_statuses = [i.get('status', 0) for i in response.get('operations_list', []) if i and isinstance(i, dict)]

        return True if 4 in log_statuses else False

    def clear_invalid_records(self):
        unlinked_records = self.search([('magento_product_ids', '=', False), ('magento_conf_product_ids', '=', False)])
        if unlinked_records:
            unlinked_records.log_details_ids.sudo().unlink()
            unlinked_records.sudo().unlink()


class MagentoAsyncBulkLogDetails(models.Model):
    _name = 'magento.async.bulk.log.details'
    _description = 'Log Details of Async Export data to Magento'

    bulk_log_id = fields.Many2one('magento.async.bulk.logs', string="Log bulk", ondelete='cascade')
    log_line_id = fields.Char(string="Log line id")
    sku = fields.Char(string="Product SKU")
    result_message = fields.Char(string="Result Message")
    log_status = fields.Selection([
        ('0', 'None'),
        ('1', 'Complete'),
        ('2', 'Failed but can try again'),
        ('3', 'Failed. Something needs to be fixed'),
        ('4', 'Open'),
        ('5', 'Rejected')
    ], string="Bulk Item Status")
