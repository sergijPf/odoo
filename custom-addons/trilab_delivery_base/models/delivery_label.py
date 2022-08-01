from odoo import models, fields


class DownloadLabel(models.TransientModel):
    _name = 'trilab.delivery.label'
    _description = 'transient model to handle labels downloads'

    file_name = fields.Char('File name', readonly=True)
    data = fields.Binary('File data', readonly=True)
