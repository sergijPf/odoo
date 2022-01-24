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

    magento_instance_id = fields.Many2one(
        'magento.instance',
        'Instance',
        ondelete='cascade',
        help="This field relocates magento instance"
    )
    magento_website_id = fields.Many2one(
        'magento.website',
        string="Website",
        help="Magento Websites",
        domain="[('magento_instance_id', '=', magento_instance_id)]"
    )
    magento_storeview_id = fields.Many2one(
        'magento.storeview',
        string="Storeviews",
        help="Magento Storeviews",
        domain="[('magento_website_id', '=', magento_website_id)]"
    )
    magento_team_id = fields.Many2one('crm.team', string='Sales Team', help="Sales Team")
    magento_sale_prefix = fields.Char(
        string="Sale Order Prefix",
        help="A prefix put before the name of imported sales orders.\n"
             "For example, if the prefix is 'mag-', the sales "
             "order 100000692 in Magento, will be named 'mag-100000692' in ERP."
    )
    magento_website_warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse',
                                                   help='Warehouse to be used to deliver an order from this website.')
    location_ids = fields.Many2many('stock.location', string="Locations",
                                     help='Locations used to compute stupdate_pricelist_in_websiteock to update on Magento.')
    catalog_price_scope = fields.Selection([
        ('global', 'Global'),
        ('website', 'Website')
    ], string="Magento Catalog Price Scope", help="Scope of Price in Magento", default='website')
    pricelist_id = fields.Many2one('product.pricelist', string="Pricelist",
                                   help="Product price will be taken/set from this pricelist if Catalog Price Scope is global")
    magento_stock_field = fields.Selection([
        ('free_qty', 'Free Quantity'),
        ('virtual_available', 'Forecast Quantity')
    ], string="Magento Stock Type", default='free_qty', help="Magento Stock Type")
    is_use_odoo_order_sequence = fields.Boolean(
        "Is Use Odoo Order Sequences?",
        default=False,
        help="If checked, Odoo Order Sequence is used when import and create orders."
    )
    invoice_done_notify_customer = fields.Boolean(
        string="Invoices Done Notify customer",
        default=False,
        help="while export invoice send email to the customer"
    )
    import_magento_order_status_ids = fields.Many2many(
        'import.magento.order.status',
        'magento_config_settings_order_status_rel',
        'magento_config_id', 'status_id',
        "Import Order Status",
        help="Select order status in which you want to import the orders from Magento to Odoo.")
    is_multi_warehouse_in_magento = fields.Boolean(
        string="Is Multi Warehouse in Magento?",
        default=False,
        help="If checked, Multi Warehouse used in Magento"
    )
    magento_website_pricelist_id = fields.Many2one(
        'product.pricelist',
        string="Magento Pricelist",
        help="Product price will be taken/set from this pricelist if Catalog Price Scope is website"
    )
    magento_version = fields.Selection([
        ('2.1', '2.1+'),
        ('2.2', '2.2+'),
        ('2.3', '2.3+'),
        ('2.4', '2.4+')
    ], string="Magento Versions", required=True, help="Version of Magento Instance", default='2.4')
    magento_url = fields.Char(string='Magento URLs', required=False, help="URL of Magento")
    dashboard_view_type = fields.Selection([('instance_level', 'Instance Level'), ('website_level', 'Website Level')],
                                           'View Dashboard Based on',
                                           config_parameter='odoo_magento2.dashboard_view_type',
                                           default='instance_level')
    tax_calculation_method = fields.Selection([
        ('excluding_tax', 'Excluding Tax'), ('including_tax', 'Including Tax')],
        string="Tax Calculation Method into Magento Website", default="including_tax",
        help="This indicates whether product prices received from Magento is including tax or excluding tax,"
             " when import sale order from Magento"
    )

    @api.onchange('magento_instance_id')
    def onchange_magento_instance_id(self):
        """
        Sets default values for configuration when change/ select Magento Instance.
        """
        magento_instance_id = self.magento_instance_id
        if magento_instance_id:
            self.write({
                'location_ids': [(6, 0, magento_instance_id.location_ids.ids)] if magento_instance_id.location_ids else False,
                'magento_stock_field': magento_instance_id.magento_stock_field,
                'magento_version': magento_instance_id.magento_version,
                'catalog_price_scope': magento_instance_id.catalog_price_scope,
                'is_multi_warehouse_in_magento': magento_instance_id.is_multi_warehouse_in_magento,
                'pricelist_id': magento_instance_id.pricelist_id.id if magento_instance_id.pricelist_id else False,
                'invoice_done_notify_customer': magento_instance_id.invoice_done_notify_customer,
                'import_magento_order_status_ids': magento_instance_id.import_magento_order_status_ids.ids,
            })
        else:
            self.magento_instance_id = False

    @api.onchange('magento_website_id')
    def onchange_magento_website_id(self):
        """
        set some Magento configurations based on changed Magento instance.
        """
        magento_website_id = self.magento_website_id
        self.magento_storeview_id = self.magento_website_warehouse_id = self.magento_website_pricelist_id = False
        if magento_website_id:
            if magento_website_id.pricelist_id.id and self.catalog_price_scope == 'website':
                self.magento_website_pricelist_id = magento_website_id.pricelist_id.id
            if magento_website_id.warehouse_id:
                self.magento_website_warehouse_id = magento_website_id.warehouse_id.id
            self.tax_calculation_method = magento_website_id.tax_calculation_method

    @api.onchange('magento_storeview_id')
    def onchange_magento_storeview_id(self):
        """
        set some Magento configurations based on changed Magento instance.
        """
        magento_storeview_id = self.magento_storeview_id
        self.is_use_odoo_order_sequence = self.magento_team_id = False
        self.magento_sale_prefix = ''
        if magento_storeview_id:
            if magento_storeview_id.team_id:
                self.magento_team_id = magento_storeview_id.team_id.id
            self.magento_sale_prefix = magento_storeview_id.sale_prefix
            self.is_use_odoo_order_sequence = magento_storeview_id.is_use_odoo_order_sequence

    def execute(self):
        """
        Save all selected Magento Instance configurations
        """
        magento_instance_id = self.magento_instance_id
        website_pricelist = self.magento_website_pricelist_id
        if website_pricelist and website_pricelist != self.magento_website_id.pricelist_id:
            self.magento_website_id.pricelist_id = website_pricelist.id

        res = super(ResConfigSettings, self).execute()

        if magento_instance_id:
            self.write_instance_vals(magento_instance_id)
        if self.magento_website_id:
            self.magento_website_id.write({
                'warehouse_id': self.magento_website_warehouse_id.id,
                'tax_calculation_method': self.tax_calculation_method,
            })
        if self.magento_storeview_id:
            self.magento_storeview_id.write({
                'team_id': self.magento_team_id,
                'sale_prefix': self.magento_sale_prefix,
                'is_use_odoo_order_sequence': self.is_use_odoo_order_sequence
            })
        return res

    def write_instance_vals(self, magento_instance_id):
        """
        Write values in the instance
        :param magento_instance_id: instance ID
        :return:
        """
        values = {}
        values.update({
            'location_ids': [(6, 0, self.location_ids.ids)] if self.location_ids else False,
            'magento_stock_field': self.magento_stock_field,
            'catalog_price_scope': magento_instance_id.catalog_price_scope if magento_instance_id else False,
            'pricelist_id': self.pricelist_id.id if self.pricelist_id else False,
            'invoice_done_notify_customer': self.invoice_done_notify_customer,
            'import_magento_order_status_ids': [(6, 0, self.import_magento_order_status_ids.ids)],
            'is_multi_warehouse_in_magento': self.is_multi_warehouse_in_magento if self.is_multi_warehouse_in_magento else False
        })
        magento_instance_id.write(values)
