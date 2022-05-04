# -*- coding: utf-8 -*-

import json
from odoo import http
from odoo.http import request


class Binary(http.Controller):
    @http.route('/web_magento_place_order', csrf=False, auth="public", type="json")
    def place_order(self):
        auth = request.httprequest.headers.get("X-Access-Token", '')
        data = json.loads(request.httprequest.data)
        magento_instance = request.env['magento.instance'].sudo().search([
            ('magento_url', '=', data.get('url', '').rstrip('/'))
        ])

        auth = '393eNsArxhD854k2dmzmkJqMjEFRFq' # to remove later

        if not magento_instance or not magento_instance.odoo_token  or not auth or \
                magento_instance.odoo_token != auth or not data.get('items'):
            return False

        return request.env['sale.order'].sudo().process_sales_order_creation(magento_instance, data)

    @http.route('/web_magento_order_cancel', csrf=False, auth="public", type="http")
    def cancel_order(self, **kwargs):
        res = False
        order_id = kwargs.get('order_id', False)
        magento_instance = request.env['magento.instance'].sudo().search([
            ('magento_url', '=', kwargs.get('url', '').rstrip('/'))
        ])

        if not magento_instance or not order_id:
            return False

        sale_order = request.env['sale.order'].sudo().search([
            ('magento_instance_id', '=', magento_instance.id),
            ('magento_order_id', '=', str(order_id))
        ], limit=1)

        if sale_order:
            res = sale_order.sudo().cancel_order_from_magento_by_webhook()

        return res
