# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
"""
Describes configuration for Magento Instance.
"""
from odoo import models, fields, _
from odoo.exceptions import UserError


class ResConfigMagentoInstance(models.TransientModel):
    """
    Describes configuration for Magento instance
    """
    _name = 'res.config.magento.instance'
    _description = 'Res Config Magento Instance'

    name = fields.Char("Instance Name")
    magento_version = fields.Selection([
        ('2.1', '2.1+'),
        ('2.2', '2.2+'),
        ('2.3', '2.3+'),
        ('2.4', '2.4+')
    ], string="Magento Versions", required=True, help="Version of Magento Instance", default='2.4')
    magento_url = fields.Char(string='Magento URLs', required=True, help="URL of Magento")
    access_token = fields.Char(
        string="Magento Access Token",
        help="Set Access token: Magento >> System >> Integrations"
    )
    company_id = fields.Many2one(
        'res.company',
        string='Magento Company',
        help="Magento Company"
    )
    is_use_odoo_order_sequence = fields.Boolean(
        "Is Use Odoo Order Sequences?",
        default=False,
        help="If checked, Odoo Order Sequence is used"
    )
    is_multi_warehouse_in_magento = fields.Boolean(
        string="Is Multi Inventory Sources in Magento?",
        default=False,
        help="If checked, Multi Inventory Sources used in Magento"
    )
    magento_verify_ssl = fields.Boolean(
        string="Verify SSL", default=False,
        help="Check this if your Magento site is using SSL certificate")

    def create_magento_instance(self):
        """
        Creates Magento Instance.
        """
        magento_instance_obj = self.env['magento.instance']
        magento_url = self.magento_url.rstrip('/')
        magento_instance_exist = magento_instance_obj.with_context(active_test=False).search([
            ('magento_url', '=', magento_url), ('access_token', '=', self.access_token)
        ])
        if magento_instance_exist:
            raise UserError(_('The instance already exists for the given Hostname. '
                              'The Hostname must be unique, for instance. '
                              'Please check the existing instance; '
                              'if you cannot find the instance, '
                              'please check whether the instance is archived.'))
        vals = {
            'name': self.name,
            'access_token': self.access_token,
            'magento_version': self.magento_version,
            'magento_url': magento_url,
            'company_id': self.company_id.id,
            'is_multi_warehouse_in_magento': self.is_multi_warehouse_in_magento,
            'magento_verify_ssl': self.magento_verify_ssl
            }
        magento_instance = magento_instance_obj
        try:
            magento_instance = magento_instance.create(vals)
            magento_instance and magento_instance.synchronize_metadata()
        except Exception as error:
            magento_instance.sudo().unlink()
            raise UserError(str(error))
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
