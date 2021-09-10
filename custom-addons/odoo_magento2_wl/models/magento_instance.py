from odoo import models, fields


class MagentoInstance(models.Model):
    _inherit = 'magento.instance'

    user_ids = fields.Many2many('res.users', string="Allowed magento users",
                                help="Users who have access to this magento instance",
                                domain=[('groups_id.full_name', '=', 'Magento / User')])