from odoo import fields, models

class ProductCategory(models.Model):
    _inherit = "product.category"

    magento_attr_set = fields.Char(string='Magento Product Attribute Set', help='Magento Attribute set', default="Default")
    magento_assigned_attr = fields.Many2many('product.attribute', string="Magento Configurable Attribute(s)",
                                        help='Attribute(s) assigned as configurable for config.product in Magento')
    magento_export_date = fields.Datetime(string="Last Export Date to Magento", copy=False)
    # common_image = fields.Image(string="Common Image", help="Images to be used as common for Config.Products")