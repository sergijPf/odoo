# -*- coding: utf-8 -*-

from odoo import models, fields, _
from odoo.exceptions import UserError


class ResConfigMagentoInstance(models.TransientModel):
    _name = 'res.config.magento.instance'
    _description = 'Res Config Magento Instance'

    name = fields.Char("Instance Name")
    magento_url = fields.Char(string='Magento URLs', required=True)
    access_token = fields.Char("Magento Access Token", help="Set Access token: Magento >> System >> Integrations")
    company_id = fields.Many2one('res.company', string='Magento Company')
    magento_verify_ssl = fields.Boolean(string="Verify SSL", default=False, help="Check if your Magento site is "
                                                                                 "using SSL certificate")

    def create_magento_instance(self):
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
            'magento_url': magento_url,
            'company_id': self.company_id.id,
            'magento_verify_ssl': self.magento_verify_ssl
            }

        try:
            magento_instance = magento_instance_obj.create(vals)
            magento_instance and magento_instance.synchronize_metadata()
        except Exception as error:
            raise UserError(str(error))

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
