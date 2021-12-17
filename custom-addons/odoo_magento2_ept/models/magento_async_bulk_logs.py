# -*- coding: utf-8 -*-

import json
from odoo import fields, models
from .api_request import req
from odoo.exceptions import UserError


class MagentoAsyncBulkLogs(models.Model):
    _name = 'magento.async.bulk.logs'
    _description = 'Logs of Async Export data to Magento'

    bulk_uuid = fields.Char('Bulk ID')
    magento_product_id = fields.Many2many('magento.product.product', string="Magento Product")
    magento_conf_product_id = fields.Many2many('magento.configurable.product', string="Magento Conf.Product")
    lod_details_ids = fields.One2many('magento.async.bulk.log.details', 'bulk_log_id', 'Log details')
    topic = fields.Char(string="Related topic")
    is_conf_prod = fields.Boolean("Is configurable product?", compute="_check_if_config_or_not")

    def _check_if_config_or_not(self):
        for record in self:
            record.is_conf_prod = True if len(record.magento_conf_product_id) else False if len(record.magento_product_id) else None

    def check_bulk_log_statuses(self):
        if not self.bulk_uuid:
            return

        instance = self.magento_conf_product_id.magento_instance_id or self.magento_product_id.magento_instance_id

        try:
            api_url = '/V1/bulk/%s/detailed-status' % self.bulk_uuid
            response = req(instance, api_url)
        except Exception:
            raise UserError("Error while requesting data from Magento")

        if self.lod_details_ids:
            self.lod_details_ids.sudo().unlink()

        for item in response.get('operations_list',[]):
            data = {}
            ser_data = item.get("result_serialized_data", "")
            if ser_data:
                data = json.loads(ser_data)
                if not isinstance(data, dict):
                    data = {}

            self.lod_details_ids.create({
                'bulk_log_id': self.id,
                'log_line_id': item.get('id'),
                'sku': data.get("sku", ""),
                'log_status': str(item.get('status', '0')),
                'result_message': item.get('result_message','')
            })


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
