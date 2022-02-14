from odoo import models, fields


class ChangePickingTypeWizard(models.TransientModel):
    _name = 'smartino.change.picking.type.wizard'
    _description = 'Smartino change picking type wizard'

    production_ids = fields.Many2many('mrp.production', default=lambda self: self.env.context.get('active_ids', []),
                                      readonly=True)
    new_picking_type_id = fields.Many2one('stock.picking.type',
                                          domain="[('code', '=', 'mrp_operation'), ('company_id', '=', company_id)]")
    company_id = fields.Many2one('res.company', 'Company', default=lambda self: self.env.company, readonly=True)

    def button_change_picking_type(self):
        self.ensure_one()

        todo_production_ids = self.production_ids.filtered(lambda prod: prod.state in ('confirmed', 'draft'))
        for production_id in todo_production_ids:
            if production_id.picking_type_id.id == self.new_picking_type_id.id:
                continue
            production_id.action_cancel()
            new_production_id = production_id.copy({'picking_type_id': self.new_picking_type_id.id,
                                                    'origin': production_id.origin,
                                                    'procurement_group_id': production_id.procurement_group_id.id})
            production_id.procurement_group_id.name = new_production_id.name
            new_production_id.onchange_picking_type()

            # noinspection PyProtectedMember
            new_production_id._onchange_location()
            # noinspection PyProtectedMember
            new_production_id._onchange_location_dest()
