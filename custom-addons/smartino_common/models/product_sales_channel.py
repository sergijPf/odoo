# -*- coding: utf-8 -*-


from odoo import models, fields, api

class ProductSalesChannel(models.Model):
    _name = "product.sales.channel"

    color = fields.Integer(string='Color Index')
    display_name = fields.Char(string='Display Name')
    name = fields.Char(string='Name', required=True)