from odoo import http
from odoo.addons.website_sale.controllers.main import WebsiteSale as OriginalWebsiteSale
from odoo.http import request


class WebsiteSale(OriginalWebsiteSale):

    @http.route()
    def payment(self, **post):
        res = super(WebsiteSale, self).payment(**post)
        order = request.website.sale_get_order()
        if 'acquirers' not in res.qcontext:
            return res

        if getattr(order.carrier_id, 'x_delivery_cod', False):
            res.qcontext['acquirers'] = [
                acquirer for acquirer in res.qcontext['acquirers'] if acquirer == request.env.ref('trilab_delivery_base.payment_acquirer_cod')
            ]
        else:
            res.qcontext['acquirers'] = [
                acquirer for acquirer in res.qcontext['acquirers'] if acquirer != request.env.ref('trilab_delivery_base.payment_acquirer_cod')
            ]
        return res
