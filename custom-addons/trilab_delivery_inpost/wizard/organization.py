from odoo import models, fields


class Organization(models.TransientModel):
    _name = "inpost.organization"
    _description = "InPost Organizations"

    organization = fields.Selection(selection="_get_organizations")
    delivery_carrier_id = fields.Many2one('delivery.carrier')

    def _get_organizations(self):
        if self.env.context.get('organizations'):
            return self.env.context.get('organizations')
        else:
            return []

    def action_validate(self):
        values = self.fields_get()['organization']['selection']

        self.delivery_carrier_id.inpost_organization = self.organization
        self.delivery_carrier_id.inpost_organization_name = \
            ''.join([x[1] for x in values if str(x[0]) == self.organization])

        return {'type': 'ir.actions.act_window_close'}
