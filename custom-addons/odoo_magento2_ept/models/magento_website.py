# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
"""
Describes Methods for Magento Website.
"""
from odoo import models, fields


class MagentoWebsite(models.Model):
    """
    Describes Magento Website
    """
    _name = 'magento.website'
    _description = 'Magento Website'

    name = fields.Char(string="Website Name", required=True, readonly=True)
    magento_instance_id = fields.Many2one('magento.instance', 'Instance', ondelete="cascade",
                                          help="This field relocates magento instance")
    catalog_price_scope = fields.Selection(related="magento_instance_id.catalog_price_scope", store=True, readonly=True)
    magento_website_id = fields.Char(string="Magento Website Id", help="Website Id in Magento")
    pricelist_id = fields.Many2one('product.pricelist', string="Pricelist",
                                   help="Product Price is set in selected Pricelist if Catalog Price Scope is Website")
    store_view_ids = fields.One2many("magento.storeview", "magento_website_id", string='Magento Store Views',
                                     help='This relocates Magento Store Views')
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse',
                                   help='Warehouse to be used to deliver an order from this website.')
    company_id = fields.Many2one('res.company', related='magento_instance_id.company_id', string='Company',
                                 readonly=True, help="Magento Company")
    magento_base_currency = fields.Many2one('res.currency', readonly=True, help="Magento Website Base Currency")
    active = fields.Boolean(string="Status", default=True)
    color = fields.Integer(string='Color Index')
    tax_calculation_method = fields.Selection([
        ('excluding_tax', 'Excluding Tax'),
        ('including_tax', 'Including Tax')
    ], "Tax Calculation Method", help="This indicates whether product prices received from Magento is included tax or "
                                      "not, when import sale order from Magento", default="excluding_tax")

    def write(self, vals):
        if 'pricelist_id' in vals and self.pricelist_id.id != vals['pricelist_id']:
            self.env['magento.product.product'].search(
                [('magento_instance_id', '=', self.magento_instance_id.id)]).write({'force_update': True})

        return super(MagentoWebsite, self).write(vals)

    def open_store_views(self):
        """
        This method used to view all store views for website.
        """
        form_view_id = self.env.ref('odoo_magento2_ept.view_magento_storeview_form').id
        tree_view = self.env.ref('odoo_magento2_ept.view_magento_storeview_tree').id
        action = {
            'name': 'Magento Store Views',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'tree',
            'res_model': 'magento.storeview',
            'views': [(tree_view, 'tree'), (form_view_id, 'form')],
            'view_id': tree_view,
            'target': 'current',
            'domain': [('id', 'in', self.store_view_ids.ids)]
        }
        return action
