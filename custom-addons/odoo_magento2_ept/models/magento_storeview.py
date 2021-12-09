# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
"""
Describes Magento Store View
"""
from odoo import models, fields


class MagentoStoreview(models.Model):
    """
    Describes Magento Store View
    """
    _name = 'magento.storeview'
    _description = "Magento Storeview"
    _order = 'sort_order ASC, id ASC'

    name = fields.Char("Store view Name", required=True, readonly=True)
    sort_order = fields.Integer('Website Sort Order', readonly=True)
    magento_website_id = fields.Many2one('magento.website', string="Magento Website")
    lang_id = fields.Many2one('res.lang', string='Language', help="Language Name")
    team_id = fields.Many2one('crm.team', string='Sales Team')
    magento_storeview_id = fields.Char(string="Magento Store View")
    magento_storeview_code = fields.Char(string="Magento Store Code")
    magento_instance_id = fields.Many2one('magento.instance', related='magento_website_id.magento_instance_id',
                                          ondelete="cascade", string='Magento Instance', store=True, readonly=True,
                                          required=False)
    active = fields.Boolean(string="Status", default=True)
    sale_prefix = fields.Char("Sale Order Prefix", help="A prefix put before the name of imported sales orders.\n "
                                                        "For example, if the prefix is 'mag-', the sales order"
                                                        " 100000692 in Magento, will be named 'mag-100000692' in ERP.")
    is_use_odoo_order_sequence = fields.Boolean("Is Use Odoo Order Sequences?", default=False,
                                                help="If checked, Odoo Order Sequence is used")
