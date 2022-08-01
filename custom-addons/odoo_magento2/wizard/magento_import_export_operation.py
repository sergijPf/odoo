# -*- coding: utf-8 -*-

from odoo.exceptions import UserError
from odoo import fields, models, _

MAGENTO_DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'
IR_ACTION_ACT_WINDOW = 'ir.actions.act_window'
IR_MODEL_DATA = 'ir.model.data'
VIEW_MODE = 'tree,form'
MAGENTO_PRODUCT_PRODUCT = 'magento.product.product'


class MagentoImportExport(models.TransientModel):
    _name = 'magento.import.export'
    _description = 'Magento Import Export'

    magento_instance_ids = fields.Many2many('magento.instance', string="Magento Instances")
    magento_website_id = fields.Many2one('magento.website', string="Magento Website")
    operations = fields.Selection([
        ('export_product_extra_info', "Export Product's extra info (prices, alternatives etc.)"),
        ('export_shipment_information', 'Export Shipment Info'),
        ('export_invoice_information', 'Export Invoices'),
        ('export_product_stock', 'Export Product Stock')
    ], string='Import/ Export Operations', help='Import/ Export Operations')
    start_date = fields.Datetime(string="From Date")
    end_date = fields.Datetime("To Date")

    def execute(self):
        res = False

        if self.magento_instance_ids:
            instances = self.magento_instance_ids
        else:
            instances = self.env['magento.instance'].search([])

        if self.operations == 'export_shipment_information':
            res = self.env['stock.picking'].export_shipments_to_magento(instances, False)
        elif self.operations == 'export_invoice_information':
            res = self.env['account.move'].export_invoices_to_magento(instances, False)
        elif self.operations == 'export_product_extra_info':
            res = self.env['magento.product.product'].export_product_prices_to_magento(instances)
            if not res:
                self.env['magento.configurable.product'].export_products_extra_info_to_magento_in_bulk(instances)

        elif self.operations == 'export_product_stock':
            res = self.export_product_stock_operation(instances)

        if res:
            return res

        title = [vals for key, vals in self._fields['operations'].selection if key == self.operations]

        return {
            'effect': {
                'fadeout': 'slow',
                'message': " {} Process Completed Successfully!".format(title[0]),
                'img_url': '/web/static/img/smile.svg',
                'type': 'rainbow_man',
            }
        }

    def export_product_stock_operation(self, instances):
        res = False

        for instance in instances:
            if not self.env[MAGENTO_PRODUCT_PRODUCT].export_products_stock_to_magento(instance):
                res = True

        if res:
            return {
                'name': 'Product Stock Export Logs',
                'view_mode': 'tree,form',
                'res_model': 'magento.stock.log.book',
                'type': 'ir.actions.act_window'
            }

    def export_products_to_magento_layer_operation(self):
        active_product_ids = self._context.get("active_ids", [])
        selection = self.env["product.template"].browse(active_product_ids)
        failed_products = selection.filtered(lambda product: product.type != "product" or not product.is_magento_config)

        self.add_products_to_magento_layer(selection - failed_products)

        if failed_products:
            raise UserError(_("It seems like selected product(s) are not Storable or don't have"
                            " proper Magento Config.Product setup: %s" % str([p.name for p in failed_products])))
        else:
            return {
                'effect': {
                    'fadeout': 'slow',
                    'message': " 'Export to Magento Layer' process completed successfully! {}".format(""),
                    'img_url': '/web/static/img/smile.svg',
                    'type': 'rainbow_man',
                }
            }

    def add_products_to_magento_layer(self, odoo_products):
        magento_product_obj = self.env[MAGENTO_PRODUCT_PRODUCT]
        ptae_obj = self.env['product.template.attribute.exclusion']
        magento_sku_missing = []
        product_dict = {}

        for instance in self.magento_instance_ids:
            product_dict.update({'instance_id': instance.id})
            for odoo_prod in odoo_products:
                product_dict.update({'odoo_product_id': odoo_prod})
                self.create_or_update_configurable_product_in_magento_layer(product_dict)
                magento_sku_missing = self.create_or_update_simple_product_in_magento_layer(
                    product_dict, magento_sku_missing, magento_product_obj, ptae_obj
                )
        if magento_sku_missing:
            raise UserError(_('Missing Internal References For %s', str(magento_sku_missing)))

        return True

    def create_or_update_configurable_product_in_magento_layer(self, product_dict):
        Conf_product = self.env['magento.configurable.product']
        product = product_dict.get('odoo_product_id')
        instance_id = product_dict.get('instance_id')
        domain = [('magento_instance_id', '=', instance_id),
                  ('odoo_prod_template_id', '=', product.id)]
        conf_product = Conf_product.with_context(active_test=False).search(domain)
        if not conf_product:
            sku = self._get_conf_product_sku(Conf_product, instance_id, product.magento_sku)

            values = {
                'magento_instance_id': instance_id,
                'odoo_prod_template_id': product.id,
                'magento_sku': sku
            }
            conf_product = Conf_product.create(values)
        else:
            if not conf_product.active:
                conf_product.write({'active': True})
            conf_product.force_update = True
            conf_product.simple_product_ids.force_update = True

        product_dict.update({"conf_product_id": conf_product})

    @staticmethod
    def _get_conf_product_sku(Conf_product, instance_id, sku):
        cnt = 0

        while True:
            prod_with_same_sku = Conf_product.with_context(active_test=False).search([
                ('magento_instance_id', '=', instance_id),
                ('magento_sku', '=', (sku + str(cnt)) if cnt else sku)])

            if prod_with_same_sku:
                cnt += 1
            else:
                sku = (sku + str(cnt)) if cnt else sku
                break

        return sku

    @staticmethod
    def create_or_update_simple_product_in_magento_layer(product_dict, magento_sku_missing, magento_product_obj,
                                                         ptae_obj):
        excl_combinations = []
        product_templ = product_dict.get('odoo_product_id')
        excl_ptav = ptae_obj.search([('product_tmpl_id', '=', product_templ.id)])

        [[excl_combinations.append(
            (str(a.product_template_attribute_value_id.id), str(v.id))
        ) for v in a.value_ids] for a in excl_ptav]

        for product in product_templ.product_variant_ids:
            skip = False
            for combination in excl_combinations:
                if combination[0] in product.combination_indices and combination[1] in product.combination_indices:
                    skip = True
                    break
            if skip:
                continue

            magento_prod_sku = product.default_code
            if not magento_prod_sku:
                magento_sku_missing.append(product.name)
            else:
                product_dict.update({"prod_variant": product})
                domain = [('magento_instance_id', '=', product_dict.get('instance_id')),
                          ('magento_sku', '=', magento_prod_sku)]
                simple_prod = magento_product_obj.with_context(active_test=False).search(domain)
                if not simple_prod:
                    prod_vals = {
                        'magento_instance_id': product_dict['instance_id'],
                        'odoo_product_id': product.id,
                        'magento_sku': product.default_code,
                        'magento_conf_product_id': product_dict['conf_product_id'].id
                    }
                    magento_product_obj.create(prod_vals)

                elif not simple_prod.active:
                    simple_prod.write({'active': True})

        return magento_sku_missing
