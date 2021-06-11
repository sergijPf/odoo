# -*- coding: utf-8 -*-
# from odoo import http


# class OdooMagentoIntegrator(http.Controller):
#     @http.route('/odoo_magento_integrator/odoo_magento_integrator/', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/odoo_magento_integrator/odoo_magento_integrator/objects/', auth='public')
#     def list(self, **kw):
#         return http.request.render('odoo_magento_integrator.listing', {
#             'root': '/odoo_magento_integrator/odoo_magento_integrator',
#             'objects': http.request.env['odoo_magento_integrator.odoo_magento_integrator'].search([]),
#         })

#     @http.route('/odoo_magento_integrator/odoo_magento_integrator/objects/<model("odoo_magento_integrator.odoo_magento_integrator"):obj>/', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('odoo_magento_integrator.object', {
#             'object': obj
#         })
