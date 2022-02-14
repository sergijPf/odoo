from odoo import models, fields


class ChangeCategoryWizard(models.TransientModel):
    _name = 'smartino.change.category.wizard'
    _description = 'Smartino change eCom category wizard'

    product_ids = fields.Many2many('product.template', default=lambda self: self.env.context.get('active_ids', []),
                                   readonly=True)
    new_category_id = fields.Many2one('product.public.category')

    def button_change_category(self):
        self.ensure_one()

        self.product_ids.write({'public_categ_ids': [(4, self.new_category_id.id)]})
