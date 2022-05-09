# -*- coding: utf-8 -*-

from odoo import models, fields


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    magento_sale_order_line_ref = fields.Char(string="SO line ref.", help="Magento Sale Order Line Reference")

    def create_product_sales_order_line(self, instance, sales_order, order):
        magento_order_lines = sales_order.get('items')
        extension_attrs = sales_order.get('extension_attributes')

        for order_line in magento_order_lines:
            sale_order_line = self.prepare_product_sales_order_line_vals(order_line, instance, order, extension_attrs)

            try:
                line = self.with_context(tracking_disable=True).create(sale_order_line)
            except Exception as e:
                return str(e)

            if not line:
                return "Failed to create order line for product - %s" % order_line.get('sku')

        return ''

    def prepare_product_sales_order_line_vals(self, order_line, magento_instance, order, extension_attrs):
        sale_order_line = self.env['sale.order.line']
        so_line_ref = order_line.get('item_id')
        product_sku = order_line.get('sku')
        original_price = order_line.get('original_price', 0.0)
        discount = (original_price - order_line.get('price', 0.0)) if original_price else 0
        tax_id = self.get_account_tax_id(extension_attrs, 'product', so_line_ref)

        odoo_product = self.env['magento.product.product'].search([
            ('magento_sku', '=', product_sku),
            ('magento_instance_id', '=', magento_instance.id)
        ], limit=1).odoo_product_id

        order_line_vals = {
            'order_id': order.id,
            'product_id': odoo_product.id,
            'name': order_line.get('name'),
            'product_uom_qty': float(order_line.get('qty_ordered', 1.0)),
            'product_uom': odoo_product.uom_id.id,
            'price_unit': order_line.get('original_price', 0.0),
            'discount': round((discount / original_price) * 100, 2) if original_price and discount else 0,
            'tax_id': [(6, 0, [tax_id.id])] if tax_id else False,
            'state': 'draft',
            'magento_sale_order_line_ref': so_line_ref
        }

        new_order_line = sale_order_line.new(order_line_vals)
        # new_order_line.product_id_change()
        return sale_order_line._convert_to_write(new_order_line._cache)

    def get_account_tax_id(self, extension_attrs, type, item_id=False):
        tax_percent = self.check_tax_percent(extension_attrs, type, item_id)
        if not tax_percent:
            return False

        tax_id = self.env['account.tax'].get_tax_from_rate(rate=float(tax_percent))

        if tax_id and not tax_id.active:
            tax_id.active = True
        if not tax_id:
            name = '%s %% ' % tax_percent
            tax_id = self.env['account.tax'].sudo().create({
                'name': name,
                'description': name,
                'amount_type': 'percent',
                'price_include': False,
                'amount': float(tax_percent),
                'type_tax_use': 'sale',
            })

        return tax_id

    @staticmethod
    def check_tax_percent(extension_attributes, type, item_id=False):
        tax_percent = 0

        if extension_attributes and "item_applied_taxes" in extension_attributes:
            for tax in extension_attributes["item_applied_taxes"]:
                if tax.get('type') == type and tax.get('applied_taxes') and (
                item_id == tax.get('item_id') if item_id else True):
                    tax_percent = tax.get('applied_taxes')[0].get('percent')

        return tax_percent

    def create_shipping_sales_order_line(self, sales_order, magento_order):
        amount_net = float(sales_order.get('shipping_amount', 0.0))
        discount_amount = float(sales_order.get('shipping_discount_amount', 0.0))

        if amount_net:
            shipping_product = self.env.ref('odoo_magento2.product_product_shipping')
            tax_id = self.get_account_tax_id(sales_order.get('extension_attributes'), 'shipping')

            vals = {
                'order_id': magento_order.id,
                'product_id': shipping_product.id,
                'name': 'Shipping cost',
                'product_uom_qty': 1,
                'product_uom': self.env.ref("uom.product_uom_unit").id,
                'price_unit': amount_net,
                'discount': round((discount_amount / amount_net) * 100, 2) if amount_net and discount_amount else 0,
                'tax_id': [(6, 0, [tax_id.id])] if tax_id else False,
                'state': 'draft'
            }

            new_order_line = self.new(vals)
            # new_order_line.product_id_change()
            sale_order_line = self._convert_to_write(new_order_line._cache)

            try:
                line = self.with_context(tracking_disable=True).create(sale_order_line)
            except Exception as e:
                return 'Error creating shipping order line: ' + str(e)

            if not line:
                return "Failed to create shipping order line. "

        return ''
