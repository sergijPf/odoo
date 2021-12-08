# -*- coding: utf-8 -*-
"""
Describes methods for webhooks to create order, invoice, product and customer.
"""
import base64
import json
from odoo import http
from odoo.http import request
from odoo.addons.web.controllers.main import serialize_exception, content_disposition


class Binary(http.Controller):
    """
    Describes methods for webhooks to create order, invoice, product and customer.
    """

    @http.route('/web/binary/download_document', type='http', auth="public")
    @serialize_exception
    def download_document(self, model, id, filename=None):
        """
        Download link for files stored as binary fields.
        :param str model: name of the model to fetch the binary from
        :param str id: id of the record from which to fetch the binary
        :param str filename: field holding the file's name, if any
        :returns: :class:`werkzeug.wrappers.Response`
        """
        wizard_id = request.env[model].browse([int(id)])
        filecontent = base64.b64decode(wizard_id.datas or '')
        if not filecontent:
            return_val = request.not_found()
        else:
            if not filename:
                filename = '%s_%s' % (model.replace('.', '_'), id)
            return_val = request.make_response(
                filecontent,
                [
                    ('Content-Type', 'application/octet-stream'),
                    ('Content-Disposition', content_disposition(filename))
                ])
        return return_val

    @http.route('/web_magento_place_order', csrf=False, auth="public", type="json")
    def place_order(self):
        """
        This method will create new order in Odoo
        :return: True
        """

        print(request.db)

        data = json.loads(request.httprequest.data)
        magento_url = data.get('url', False)
        magento_instance = request.env['magento.instance'].sudo().search([
            ('magento_url', '=', magento_url.rstrip('/') if magento_url else False)
        ])

        if not magento_instance or not data.get('items'):
            return 'false'
        print(data)
        res = request.env['sale.order'].sudo().process_sales_order_creation(magento_instance, data)

        return 'true' if res else 'false'

    @http.route('/web_magento_order_cancel', csrf=False, auth="public", type="http")
    def cancel_order(self, **kwargs):
        """
        Call method while cancel order from the Magento and
        Cancel order webhook is enable from the magento configuration
        :param kwargs:
        :return: True
        """
        order_id = kwargs.get('order_id', False)
        magento_url = kwargs.get('url', False)
        magento_instance = request.env['magento.instance'].sudo().search([
            ('magento_url', '=', magento_url.rstrip('/'))
        ])
        sale_order = request.env['sale.order'].sudo().search([('magento_instance_id', '=', magento_instance.id),
                                                              ('magento_order_id', '=', int(order_id))], limit=1)
        if sale_order:
            sale_order.sudo().cancel_order_from_magento_by_webhook()
        return 'true'
