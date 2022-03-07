# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
"""
Describes configuration for Magento Instance.
"""
from odoo import models, fields, api


class ResConfigSettings(models.TransientModel):
    """
    Describes Magento Instance Configurations
    """
    _inherit = 'res.config.settings'

    magento_instance_id = fields.Many2one('magento.instance', 'Instance', ondelete='cascade',
                                          help="This field relocates magento instance")
    magento_website_id = fields.Many2one('magento.website', string="Website", help="Magento Websites",
                                         domain="[('magento_instance_id', '=', magento_instance_id)]")
    magento_storeview_id = fields.Many2one('magento.storeview', string="Storeviews",  help="Magento Storeviews",
                                           domain="[('magento_website_id', '=', magento_website_id)]")
    magento_team_id = fields.Many2one('crm.team', string='Magento Sales Team')
    magento_sale_prefix = fields.Char(
        string="Sale Order Prefix", help="A prefix put before the name of imported sales orders.")
    magento_website_warehouse_id = fields.Many2one('stock.warehouse', string='Magento Warehouse',
                                                   help='Warehouse to be used to deliver an order from this website.')
    location_ids = fields.Many2many('stock.location', string="Locations",
                                    help='Locations used to compute stock quantities to be exported to Magento.')
    catalog_price_scope = fields.Selection([
        ('global', 'Global'),
        ('website', 'Website')
    ], string="Magento Catalog Price Scope", help="Scope of Price in Magento", default='website')
    pricelist_id = fields.Many2one('product.pricelist', "Pricelist", help="Product price will be taken/set from this "
                                                                          "pricelist if Catalog Price Scope is global")
    magento_stock_field = fields.Selection([
        ('free_qty', 'Free Quantity'),
        ('virtual_available', 'Forecast Quantity')
    ], string="Magento Stock Type", default='free_qty')
    is_use_odoo_order_sequence = fields.Boolean("Use Odoo Order Sequences?", default=False,
                                                help="If checked, Odoo Order Sequence is used when import and create "
                                                     "orders.")
    invoice_done_notify_customer = fields.Boolean(string="Invoices Done Notify customer", default=False,
                                                  help="while export invoice send email to the customer")
    import_magento_order_status_ids = fields.Many2many(
        'import.magento.order.status', 'magento_config_settings_order_status_rel', 'magento_config_id', 'status_id',
        "Import Order Status", help="Select order status in which you want to import the orders from Magento to Odoo."
    )
    magento_website_pricelist_id = fields.Many2one(
        'product.pricelist', string="Magento Pricelist",
        help="Product price will be taken/set from this pricelist if Catalog Price Scope is website"
    )
    magento_url = fields.Char(string='Magento URLs', required=False, help="URL of Magento")
    tax_calculation_method = fields.Selection([
        ('excluding_tax', 'Excluding Tax'),
        ('including_tax', 'Including Tax')], "Tax Calculation Method", default="including_tax",
        help="This indicates whether product prices received from Magento is including tax or excluding tax,"
             " when import sale order from Magento"
    )

    @api.onchange('magento_instance_id')
    def onchange_magento_instance_id(self):
        """
        Sets default values for configuration when change/ select Magento Instance.
        """
        instance_id = self.magento_instance_id
        if instance_id:
            self.write({
                'location_ids': [(6, 0, instance_id.location_ids.ids)] if instance_id.location_ids else False,
                'magento_stock_field': instance_id.magento_stock_field,
                'catalog_price_scope': instance_id.catalog_price_scope,
                'pricelist_id': instance_id.pricelist_id.id if instance_id.pricelist_id else False,
                'invoice_done_notify_customer': instance_id.invoice_done_notify_customer,
                'import_magento_order_status_ids': instance_id.import_magento_order_status_ids.ids,
            })
        else:
            self.magento_instance_id = False

    @api.onchange('magento_website_id')
    def onchange_magento_website_id(self):
        """
        set some Magento configurations based on changed Magento instance.
        """
        website_id = self.magento_website_id
        self.magento_storeview_id = self.magento_website_warehouse_id = self.magento_website_pricelist_id = False

        if website_id:
            if website_id.pricelist_id.id and self.catalog_price_scope == 'website':
                self.magento_website_pricelist_id = website_id.pricelist_id.id
            if website_id.warehouse_id:
                self.magento_website_warehouse_id = website_id.warehouse_id.id
            self.tax_calculation_method = website_id.tax_calculation_method

    @api.onchange('magento_storeview_id')
    def onchange_magento_storeview_id(self):
        """
        set some Magento configurations based on changed Magento instance.
        """
        storeview_id = self.magento_storeview_id
        self.is_use_odoo_order_sequence = self.magento_team_id = False
        self.magento_sale_prefix = ''

        if storeview_id:
            self.magento_team_id = storeview_id.team_id.id if storeview_id.team_id else False
            self.magento_sale_prefix = storeview_id.sale_prefix
            self.is_use_odoo_order_sequence = storeview_id.is_use_odoo_order_sequence

    def execute(self):
        """
        Save all selected Magento Instance configurations
        """
        instance = self.magento_instance_id
        website_pricelist = self.magento_website_pricelist_id

        if website_pricelist and website_pricelist != self.magento_website_id.pricelist_id:
            self.magento_website_id.pricelist_id = website_pricelist.id

        res = super(ResConfigSettings, self).execute()

        if instance:
            self.write_instance_vals(instance)

        if self.magento_website_id:
            self.magento_website_id.write({
                'warehouse_id': self.magento_website_warehouse_id.id if self.magento_website_warehouse_id else False,
                'tax_calculation_method': self.tax_calculation_method,
            })

        if self.magento_storeview_id:
            self.magento_storeview_id.write({
                'team_id': self.magento_team_id,
                'sale_prefix': self.magento_sale_prefix,
                'is_use_odoo_order_sequence': self.is_use_odoo_order_sequence
            })

        return res

    def write_instance_vals(self, magento_instance):
        values = {}
        values.update({
            'location_ids': [(6, 0, self.location_ids.ids)] if self.location_ids else False,
            'magento_stock_field': self.magento_stock_field,
            'catalog_price_scope': magento_instance.catalog_price_scope if magento_instance else False,
            'pricelist_id': self.pricelist_id.id if self.pricelist_id else False,
            'invoice_done_notify_customer': self.invoice_done_notify_customer,
            'import_magento_order_status_ids': [(6, 0, self.import_magento_order_status_ids.ids)]
        })
        magento_instance.write(values)
