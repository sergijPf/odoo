# -*- coding: utf-8 -*-

from odoo import models, fields


class MagentoWebsite(models.Model):
    _name = 'magento.website'
    _description = 'Magento Website'

    name = fields.Char(string="Website Name", required=True, readonly=True)
    magento_instance_id = fields.Many2one('magento.instance', 'Instance', ondelete="cascade")
    catalog_price_scope = fields.Selection(related="magento_instance_id.catalog_price_scope", readonly=True)
    magento_website_id = fields.Char(string="Magento Website Id", help="Website Id generated in Magento")
    pricelist_id = fields.Many2one('product.pricelist', string="Pricelist",
                                   help="Product Price is set in selected Pricelist if Catalog Price Scope is Website")
    store_view_ids = fields.One2many("magento.storeview", "magento_website_id", string='Magento Store Views')
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse',
                                   help='Warehouse to be used to deliver an order from this website.')
    company_id = fields.Many2one('res.company', related='magento_instance_id.company_id', string='Company',
                                 readonly=True)
    magento_base_currency = fields.Many2one('res.currency', string="Base currency", readonly=True,
                                            help="Magento Website Base Currency")
    active = fields.Boolean(string="Status", default=True)
    color = fields.Integer(string='Color Index')

    def write(self, vals):
        if 'pricelist_id' in vals and self.pricelist_id.id != vals['pricelist_id']:
            self.env['magento.product.product'].search(
                [('magento_instance_id', '=', self.magento_instance_id.id)]).write({'force_update': True})

        return super(MagentoWebsite, self).write(vals)

    def open_store_views(self):
        form_view_id = self.env.ref('odoo_magento2.view_magento_storeview_form').id
        tree_view = self.env.ref('odoo_magento2.view_magento_storeview_tree').id

        return {
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
