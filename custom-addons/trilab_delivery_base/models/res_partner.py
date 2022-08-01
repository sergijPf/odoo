# noinspection PyProtectedMember
from odoo import models, fields, _
from odoo.exceptions import ValidationError


class ResPartner(models.Model):

    _inherit = 'res.partner'

    full_street = fields.Char(compute='compute_full_street', store=False, readonly=True)

    def compute_full_street(self):
        for partner in self:
            partner.full_street = ' '.join(filter(None, [partner.street, partner.street2]))

    def check_base_data(self, require: list = None):
        if require is None:
            require = []

        for addr in self:
            if not addr:
                raise ValidationError(_('Selected address does not exists'))
            name = addr.name

            if not name:
                raise ValidationError(_('Selected address is missing its name'))

            if not addr.street:
                raise ValidationError(_('Address %s is missing street info', name))

            if not self.country_id:
                raise ValidationError(_('Address %s is missing country info', name))

            if not addr.zip:
                raise ValidationError(_('Address %s is missing zip info', name))

            if not addr.city:
                raise ValidationError(_('Address %s is missing city info', name))

            for field, description in require:
                if not getattr(addr, field):
                    raise ValidationError(
                        _('Address %(name)s is missing %(field) info', {'name': name, 'field': description})
                    )
