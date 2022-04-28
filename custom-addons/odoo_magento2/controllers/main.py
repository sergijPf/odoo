# -*- coding: utf-8 -*-

import json
from odoo import http
from odoo.http import request


class Binary(http.Controller):
    @http.route('/web_magento_place_order', csrf=False, auth="public", type="json")
    def place_order(self):
        data = json.loads(request.httprequest.data)
        magento_url = data.get('url', False)
        magento_instance = request.env['magento.instance'].sudo().search([
            ('magento_url', '=', magento_url.rstrip('/') if magento_url else False)
        ])

        if not magento_instance or not data.get('items'):
            return 'false'
        res = request.env['sale.order'].sudo().process_sales_order_creation(magento_instance, data)

        return 'false'

        # return 'true' if res else 'false'

    @http.route('/web_magento_order_cancel', csrf=False, auth="public", type="http")
    def cancel_order(self, **kwargs):
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
