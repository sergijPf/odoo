from odoo import fields, models, api, _
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    x_magento_name = fields.Char(string='Name for Magneto', translate=True)

    x_sales_channel = fields.Many2many('product.sales.channel', string='Sales Channel')
    x_pantone_code = fields.Char(string='Pantone Code')

    x_minimal_quantity = fields.Integer(default=1, string='Minimal Quantity', store=True,
                                        compute='_x_compute_x_minimal_quantity', inverse='_x_set_x_minimal_quantity')
    x_quantity_multiplicity = fields.Integer(default=1, string='Allowed Quantity Multiplicity', store=True,
                                             compute='_x_compute_x_quantity_multiplicity',
                                             inverse='_x_set_x_quantity_multiplicity')

    @api.model_create_multi
    def create(self, vals_list):
        templates = super(ProductTemplate, self).create(vals_list)
        for template, vals in zip(templates, vals_list):
            related_vals = {}
            if vals.get('x_minimal_quantity'):
                related_vals['x_minimal_quantity'] = vals['x_minimal_quantity']
            if vals.get('x_quantity_multiplicity'):
                related_vals['x_quantity_multiplicity'] = vals['x_quantity_multiplicity']
            if related_vals:
                template.write(related_vals)
        return templates

    def x_action_generate_translation(self):
        """Create website_description Translation for active languages"""
        for template in self:
            self.env['ir.translation'].x_translate_fields(self._name, template.id, 'website_description')

    @api.depends('product_variant_ids', 'product_variant_ids.x_minimal_quantity')
    def _x_compute_x_minimal_quantity(self):
        unique_variants = self.filtered(lambda x: len(x.product_variant_ids) == 1)
        for template in unique_variants:
            template.x_minimal_quantity = template.product_variant_ids.x_minimal_quantity
        for template in (self - unique_variants):
            template.x_minimal_quantity = False

    def _x_set_x_minimal_quantity(self):
        for template in self:
            if len(template.product_variant_ids) == 1:
                template.product_variant_ids.x_minimal_quantity = template.x_minimal_quantity

    @api.depends('product_variant_ids', 'product_variant_ids.x_quantity_multiplicity')
    def _x_compute_x_quantity_multiplicity(self):
        unique_variants = self.filtered(lambda x: len(x.product_variant_ids) == 1)
        for template in unique_variants:
            template.x_quantity_multiplicity = template.product_variant_ids.x_quantity_multiplicity
        for template in (self - unique_variants):
            template.x_quantity_multiplicity = False

    def _x_set_x_quantity_multiplicity(self):
        for template in self:
            if len(template.product_variant_ids) == 1:
                template.product_variant_ids.x_quantity_multiplicity = template.x_quantity_multiplicity

    def x_action_open_in_new_tab(self):
        """
            Open product.template form in new browser tab
        """
        self.ensure_one()
        form_action = self.env.ref('stock.product_template_action_product')
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web#id={self.id}&action={form_action.id}&model=product.template&view_type=form',
            'target': 'new',
        }

    def _x_check_new_combination(self, combination):
        if not self.has_dynamic_attributes():
            raise ValidationError(_('You could not create a variant for the non-dynamic product.'))

        if not self._is_combination_possible(combination):
            raise ValidationError(_('Combination is not possible for the product.'))


class PurchaseOrderTagAdditional(models.Model):
    _name = 'product.sales.channel'
    _description = 'Product Sales Channel'

    name = fields.Char(required=True)
    color = fields.Integer(string='Color Index')


class ProductProduct(models.Model):
    _inherit = 'product.product'

    x_sales_channel = fields.Many2many(related='product_tmpl_id.x_sales_channel', readonly=False)
    x_pantone_code = fields.Char(related='product_tmpl_id.x_pantone_code', readonly=False)
    x_minimal_quantity = fields.Integer(default=1, string='Minimal Quantity')
    x_quantity_multiplicity = fields.Integer(default=1, string='Allowed Quantity Multiplicity')
    x_gus_uom_id = fields.Many2one('uom.uom', string='GUS UoM')

    x_status = fields.Selection(
        selection=lambda self: self._x_get_available_product_status(),
        string='Status',
        help='w przygotowaniu - dla produktów prototypowych, niedostępne w zamówieniach,'
             ' mogą być zlecane szwalni wyszycia próbne, tworzone receptury i wyceny\n'
             'prapremiera - produkt nie wprowadzony na rynek, ale dystrybutorzy mogą zamawiać\n'
             'premiera - produkt zaprezentowany konsumentom, 6 tygodni od publikacji w '
             'B2C (ESKLEP) zmiana statusu na nowość\n'
             'nowość - produkty w pierwszym sezonie sprzedaży\n'
             'kontynuacja - produkt, który jest sprzedawany drugi lub kolejny sezon\n'
             'on hold - nie domawiamy surowców, ale nie robimy głębokich promocji, bo produkt wróci w kolejnym'
             'sezonie (w tym statusie będzie np. asortyment letni jesienią, gdy chcemy go kontynuować kolejnego lata)\n'
             'koniec serii - produkcja i zamówienia do wyczerpania surowców,'
             ' gdy surowce sie skończą automatycznie wchodzi w status wycofane\n'
             'wycofane - produkty, których juz nie planujemy w regularnej sprzedaży, ale w szczególnych warunkach po '
             'zapytaniu ofertowym dystrybutora może być wyprodukowane i zamówione specjalnie surowce, '
             'jeśli dystrybutor wykorzysta całą belkę surowca\n'
    )

    @api.model
    def _x_get_available_product_status(self):
        return [('in_preparation', _('In Preparation')),
                ('prapremiere', _('Prapremiere')),
                ('premiere', _('Premiere')),
                ('newness', _('Newness')),
                ('continuation', _('Continuation')),
                ('on_hold', _('On Hold')),
                ('end_of_series', _('End of Series')),
                ('withdrawn', _('Withdrawn'))]


class ProductPublicCategory(models.Model):
    _inherit = 'product.public.category'

    x_category_image_ids = fields.One2many('product.image', 'x_category_id', string="Extra Category Media", copy=True)
    x_show_on_www = fields.Boolean(default=True, string='Show on WWW')


class ProductImage(models.Model):
    _inherit = 'product.image'

    x_category_id = fields.Many2one('product.public.category', 'Website Product Category', index=True,
                                    ondelete='cascade')


class ProductCategory(models.Model):
    _inherit = 'product.category'

    x_gus_prodpol_id = fields.Many2one('gus.prodpol', 'GUS PRODPOL')


class GusProdpol(models.Model):
    _name = 'gus.prodpol'
    _description = 'Smartino Common GUS PRODPOL'

    name = fields.Char('Group Name', required=True)
    code = fields.Char('PKWIU / PRODPOL symbol')

    @api.constrains('code')
    def _check_unique_code(self):
        for rec in self:
            if self.search([('code', '=', rec.code)], count=True) > 1:
                raise ValidationError(_('PKWIU / PRODPOL symbol for GUS PRODPOL must be unique!'))
