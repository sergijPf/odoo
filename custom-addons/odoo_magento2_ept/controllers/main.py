# -*- coding: utf-8 -*-
"""
Describes methods for webhooks to create/cancel sales orders
"""
import json
from odoo import http
from odoo.http import request


class Binary(http.Controller):
    """
    Describes methods for webhooks to create order, invoice, product and customer.
    """
    @http.route('/web_magento_place_order', csrf=False, auth="public", type="json")
    def place_order(self):
        """
        This method will create new order in Odoo
        :return: True/False
        """
        data = json.loads(request.httprequest.data)
        magento_url = data.get('url', False)
        magento_instance = request.env['magento.instance'].sudo().search([
            ('magento_url', '=', magento_url.rstrip('/') if magento_url else False)
        ])

        if not magento_instance or not data.get('items'):
            return 'false'
        res = request.env['sale.order'].sudo().process_sales_order_creation(magento_instance, data)

        return 'true' if res else 'false'

    @http.route('/web_magento_order_cancel', csrf=False, auth="public", type="http")
    def cancel_order(self, **kwargs):
        """
        Call method while cancel order from the Magento and
        Cancel order webhook is enabled from the magento configuration
        :param kwargs:
        :return: True/False
        """
        order_id = kwargs.get('order_id', False)
        magento_url = kwargs.get('url', False)
        magento_instance = request.env['magento.instance'].sudo().search([
            ('magento_url', '=', magento_url.rstrip('/') if magento_url else False)
        ])

        if not magento_instance or not order_id:
            return 'false'

        sale_order = request.env['sale.order'].sudo().search([('magento_instance_id', '=', magento_instance.id),
                                                              ('magento_order_id', '=', int(order_id))], limit=1)
        res = False
        if sale_order:
            res = sale_order.sudo().cancel_order_from_magento_by_webhook()

        return 'true' if res else 'false'
