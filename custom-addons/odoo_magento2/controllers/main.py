# -*- coding: utf-8 -*-

import json
from odoo import http
from odoo.http import request


class Binary(http.Controller):
    @http.route('/web_magento_place_order', csrf=False, auth="public", type="json")
    def place_order(self):
        data = json.loads(request.httprequest.data)

        if not data or not data.get('items'):
            return f"Sales order - '{data.get('increment_id') if data else ''}' missed data inside."

        url = data.get('url', '').rstrip('/')
        magento_instance = request.env['magento.instance'].sudo().search([
            ('magento_url', '=', url)
        ])

        if not magento_instance:
            return f"The instance with such URL - '{url}' doesn't  exist in Odoo."

        auth = request.httprequest.headers.get("X-Access-Token", magento_instance.odoo_token) # to replace odoo_token with ''
        if not magento_instance.odoo_token or not auth or magento_instance.odoo_token != auth:
            return "Access Token doesn't match for Magento and Odoo."

        res = request.env['sale.order'].sudo().process_sales_order_creation(magento_instance, data)

        return res if res else "Error while Order processing. Please see Order Logs on Odoo side for more info."

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
