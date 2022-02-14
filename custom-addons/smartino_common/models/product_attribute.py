import logging

from odoo import models, _, fields
from odoo.tools import groupby
from odoo.exceptions import ValidationError
from itertools import product

_logger = logging.getLogger(__name__)


class ProductAttribute(models.Model):
    _inherit = 'product.attribute'

    x_website_sale_visibility = fields.Selection([('visible', 'Visible'), ('hidden', 'Hidden')],
                                                 string="eCommerce Filter Visibility", default='visible')


class ProductAttributeValue(models.Model):
    _inherit = 'product.attribute.value'

    x_image = fields.Image(string='Image')


class ProductTemplateAttributeValue(models.Model):
    _inherit = 'product.template.attribute.value'

    def x_button_create_variants(self):
        product_tmpl_id = self.product_tmpl_id and self.product_tmpl_id[0]
        new_product_ids = self.env['product.product']
        if len(self) > 1 and any(tmpl_id.id != product_tmpl_id.id for tmpl_id in self.product_tmpl_id):
            raise ValidationError(_('Create Variants is only available for one product.template'))

        multi_option_ptav_ids = self.env['product.template.attribute.value']
        one_option_ptav_ids = self.env['product.template.attribute.value']

        all_ptav_ids = self.search([('product_tmpl_id', '=', product_tmpl_id.id)])

        for attribute_id, ptav_ids in groupby(all_ptav_ids, key=lambda val: val.attribute_id):
            if len(ptav_ids) > 1:
                for ptav_id in ptav_ids:
                    multi_option_ptav_ids += ptav_id
            else:
                one_option_ptav_ids += ptav_ids[0]

        multi_option_ptav_ids = multi_option_ptav_ids.filtered(lambda x: x.id in self.ids)

        if not multi_option_ptav_ids:
            raise ValidationError(_('You need to select at least one value from each multi option attribute.'))

        # This creates combinations from e.g. [A1, A2, B1, B2] -> [(A1,B1), (A1,B2), (A2,B1), (A2, B2)]
        grouped_by_attribute_ptav_ids = [ptav_ids for attribute_id, ptav_ids in
                                         groupby(multi_option_ptav_ids, key=lambda val: val.attribute_id)]
        combinations = list(set(product(*grouped_by_attribute_ptav_ids)))

        for combination in combinations:
            new_combination = self.env['product.template.attribute.value']
            new_combination += one_option_ptav_ids
            for ptav_id in combination:
                new_combination += ptav_id

            # noinspection PyProtectedMember
            product_tmpl_id._x_check_new_combination(new_combination)
            # noinspection PyProtectedMember
            new_product_ids |= product_tmpl_id._create_product_variant(new_combination)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Created Products'),
                'message': _('Created %d new product(s)', len(new_product_ids)),
            }
        }
