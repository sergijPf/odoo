from odoo import fields, models


class MagentoImportExportEpt(models.TransientModel):
    """
    Describes Magento Process for import/ export operations
    """
    _inherit = 'magento.import.export.ept'

    # operations = fields.Selection([
    #     ('import_customer', 'Import Customer'),
    #     ('import_sale_order', 'Import Sale Order'),
    #     ('import_specific_order', 'Import Specific Order'),
    #     ('import_product_stock', 'Import Product Stock'),
    #     ('export_shipment_information', 'Export Shipment Information'),
    #     ('export_invoice_information', 'Export Invoice Information'),
    #     ('export_product_stock', 'Export Product Stock')
    # ], string='Import/ Export Operations')