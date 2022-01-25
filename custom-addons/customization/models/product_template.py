# -*- coding: utf-8 -*-


from odoo import models, fields

class ProductTemplate(models.Model):
    _inherit = "product.template"

    # x_magento_name = fields.Char(string='Name for Magento')
    x_status = fields.Selection([
        ('in_preparation', 'In Preparation'),
        ('prapremiere', 'Prapremiere'),
        ('premiere', 'Premiere'),
        ('newness', 'Newness'),
        ('continuation', 'Continuation'),
        ('on_hold', 'On Hold'),
        ('end_of_series', 'End of Series'),
        ('withdrawn', 'Withdrawn')
    ], string='Status')

    x_sales_channel = fields.Many2many('product.sales.channel', string='Sales Channel')