from odoo import api, fields, models


class PackageType(models.Model):
    _inherit = 'stock.package.type'

    def _x_get_default_length_uom(self):
        return self.env['product.template']._get_length_uom_id_from_ir_config_parameter()

    def _x_get_default_weight_uom(self):
        return self.env['product.template']._get_weight_uom_id_from_ir_config_parameter()

    def _x_compute_length_uom(self):
        for packaging in self:
            packaging.x_length_uom = self.env['product.template']._get_length_uom_id_from_ir_config_parameter()

    def _x_compute_weight_uom(self):
        for packaging in self:
            packaging.x_weight_uom = self.env['product.template']._get_weight_uom_id_from_ir_config_parameter()

    @api.depends('x_length_uom')
    def _compute_length_uom_name(self):
        for packaging in self:
            if packaging.x_length_uom:
                packaging.length_uom_name = packaging.x_length_uom.display_name
            else:
                super()._compute_length_uom_name()

    @api.depends('x_weight_uom')
    def _compute_weight_uom_name(self):
        for packaging in self:
            if packaging.x_weight_uom:
                packaging.weight_uom_name = packaging.x_weight_uom.display_name
            else:
                super()._compute_weight_uom_name()

    def _get_default_length_uom(self):
        if 'default_x_length_uom' in self.env.context:
            return self.env['uom.uom'].browse(self.env.context['default_x_length_uom'])
        else:
            return super()._get_default_length_uom()

    def _get_default_weight_uom(self):
        if 'default_x_weight_uom' in self.env.context:
            return self.env['uom.uom'].browse(self.env.context['default_x_weight_uom'])
        else:
            return super()._get_default_weight_uom()

    x_length_uom = fields.Many2one('uom.uom', string='Length unit of measure', compute=_x_compute_length_uom,
                                   default=_x_get_default_length_uom, readonly=False, store=True)

    x_weight_uom = fields.Many2one('uom.uom', string='Weight unit of measure', compute=_x_compute_weight_uom,
                                   default=_x_get_default_weight_uom, readonly=False, store=True)

    length_uom_name = fields.Char(string='Length unit of measure label', compute='_compute_length_uom_name',
                                  default=_get_default_length_uom)
    weight_uom_name = fields.Char(string='Weight unit of measure label', compute='_compute_weight_uom_name',
                                  default=_get_default_weight_uom)
