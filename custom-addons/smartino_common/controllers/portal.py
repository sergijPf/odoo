from odoo.addons.sale_management.controllers.portal import CustomerPortal
from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError, MissingError


class SmartinoCustomerPortal(CustomerPortal):

    @http.route(["/my/orders/<int:so_line_id>/x_set_partner_choice/<string:choice>"],
                type='json', auth="public", website=True)
    def x_set_partner_choice(self, so_line_id, choice, access_token=None, **post):
        try:
            line_sudo = self._document_check_access('sale.order.line', so_line_id, access_token=access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')

        line_sudo.x_partner_choice = choice

        if choice == 'cancel':
            line_sudo.product_uom_qty = 0

        return True
