# -*- coding: utf-8 -*-

from odoo import fields, models


class SaleReport(models.Model):
    _inherit = "sale.report"

    magento_instance_id = fields.Many2one('magento.instance', 'Magento Site', readonly=True)
    magento_website_id = fields.Many2one('magento.website', 'Magento Website', readonly=True)

    def _query(self, with_clause='', field=None, groupby='', from_clause=''):
        """
        Add Magento instance field in model group by
        :param with_clause:
        :param field: magento_instance_id, magento_website_id
        :param groupby:magento_instance_id, magento_website_id
        :param from_clause:
        :return:
        """
        if field is None:
            field = {}
        field['magento_instance_id'] = ", s.magento_instance_id as magento_instance_id"
        field['magento_website_id'] = ", s.magento_website_id as magento_website_id"
        groupby += ', s.magento_instance_id , s.magento_website_id'
        return super()._query(with_clause, field, groupby, from_clause)
