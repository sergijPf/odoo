# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
"""
Describes Magento Inventory Locations
"""
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class MagentoInventoryLocations(models.Model):
    """
    Describes Magento Inventory Locations
    """
    _name = 'magento.inventory.locations'
    _description = "Magento Inventory Locations"
    _order = 'id ASC'

    name = fields.Char(
        string="Magento Location Name",
        required=True,
        readonly=True,
        help="Magento Inventory Location Name"
    )
    magento_location_code = fields.Char(string="Magento MSI Code", readonly=True, help="Store view Code")
    magento_instance_id = fields.Many2one(
        'magento.instance',
        'Instance',
        ondelete='cascade',
        help="This field relocates magento instance"
    )
    export_stock_warehouse_ids = fields.Many2many(
        'stock.warehouse',
        string="Warehouses",
        help='Warehouses used to compute the stock quantities.'
             'If Warehouses is not selected then it is taken from Website'
    )
    import_stock_warehouse = fields.Many2one(
        'stock.warehouse',
        string="Import Product Stock Warehouse",
        help="Warehouse for import stock from Magento to Odoo"
    )
    active = fields.Boolean(string="Status", default=True)

    @api.constrains('export_stock_warehouse_ids')
    def _check_locations_warehouse_ids(self):
        """ Do not save or update location if warehouse already set in different location with same instance.
        :return:
        @param : self
        """
        location_instance = self.magento_instance_id
        location_warehouse = self.export_stock_warehouse_ids
        locations = self.search([('magento_instance_id', '=', location_instance.id), ('id', '!=', self.id)])
        for location in locations:
            if any([location in location_warehouse.ids for location in location.export_stock_warehouse_ids.ids]):
                raise ValidationError(_("Can't set this warehouse in "
                                        "different locations with same instance."))
