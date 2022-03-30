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
    magento_product_ids = fields.Many2many('magento.product.product', string="Magento Product")
    magento_conf_product_ids = fields.Many2many('magento.configurable.product', string="Magento Conf.Product")
    log_details_ids = fields.One2many('magento.async.bulk.log.details', 'bulk_log_id', 'Log details')
    topic = fields.Char(string="Related topic")
    is_conf_prod = fields.Boolean("Is configurable product?", compute="_check_if_config_or_not")

    def _check_if_config_or_not(self):
        for record in self:
            record.is_conf_prod = True if len(record.magento_conf_product_ids) else\
                False if len(record.magento_product_ids) else None

    def check_and_update_bulk_log_statuses(self):
        self.ensure_one()

        if (self.log_details_ids and "4" not in self.log_details_ids.mapped('log_status')) or not self.bulk_uuid:
            return True

        if self.log_details_ids:
            self.log_details_ids.sudo().unlink()

        response = self.get_detailed_status_of_log()
        print(response)

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

        self.clear_invalid_records()

        return False if '4' in self.log_details_ids.mapped('log_status') else True

    def get_detailed_status_of_log(self):
        instance = self.magento_conf_product_ids.magento_instance_id or self.magento_product_ids.magento_instance_id

        try:
            api_url = '/V1/bulk/%s/detailed-status' % self.bulk_uuid
            response = req(instance, api_url)
        except Exception:
            raise UserError("Error while Magento data requesting!")

        return response

    def clear_invalid_records(self):
        unlinked_records = self.search([('magento_product_ids', '=', False), ('magento_conf_product_ids', '=', False)])
        if unlinked_records:
            unlinked_records.log_details_ids.sudo().unlink()
            unlinked_records.sudo().unlink()


class MagentoAsyncBulkLogDetails(models.Model):
    _name = 'magento.async.bulk.log.details'
    _description = 'Log Details of Async Export data to Magento'

    bulk_log_id = fields.Many2one('magento.async.bulk.logs', string="Log bulk")
    log_line_id = fields.Char(string="Log line id")
    sku = fields.Char(string="Product SKU")
    log_status = fields.Selection([
        ('0', 'None'),
        ('1', 'Complete'),
        ('2', 'Failed but can try again'),
        ('3', 'Failed. Something needs to be fixed'),
        ('4', 'Open'),
        ('5', 'Rejected')
    ], string="Bulk Item Status")
    result_message = fields.Char(string="Result Message")
