# -*- coding: utf-8 -*-

from odoo import models, fields


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    magento_sale_order_line_ref = fields.Char(string="SO line ref.", help="Magento Sale Order Line Reference")

    def create_product_sales_order_line(self, instance, sales_order, order_rec):
        magento_order_lines = sales_order.get('items')
        extens_attrs = sales_order.get('extension_attributes')

        for order_line in magento_order_lines:
            so_line_ref = order_line.get('item_id')
            so_line_vals = self.prepare_product_sales_order_line_vals(order_line, instance, order_rec, extens_attrs)

            if isinstance(so_line_vals, str):
                return so_line_vals

            try:
                line = order_rec.order_line.filtered(lambda x: x.magento_sale_order_line_ref == so_line_ref)
                if line:
                    line.with_context(tracking_disable=True).write(so_line_vals)
                else:
                    line = self.with_context(tracking_disable=True).create(so_line_vals)
            except Exception as e:
                return f"Error creating/updating sales order line with following sku {order_line.get('sku')}: {str(e)}"

            if not line:
                return f"Failed to create order line for product - {order_line.get('sku')}"

        return ''

    def prepare_product_sales_order_line_vals(self, order_line, instance, order_rec, extension_attrs):
        sale_order_line_obj = self.env['sale.order.line']
        so_line_ref = order_line.get('item_id')
        product_sku = order_line.get('sku')
        original_price = order_line.get('original_price', 0.0)
        discount = (original_price - order_line.get('price', 0.0)) if original_price else 0

        tax_id = self.get_account_tax_id(extension_attrs, 'product', order_rec, order_line.get('sku'), so_line_ref)
        if isinstance(tax_id, str):
            return tax_id

        odoo_product = self.env['magento.product.product'].search([
            ('magento_sku', '=', product_sku),
            ('magento_instance_id', '=', instance.id)
        ], limit=1).odoo_product_id

        order_line_vals = {
            'order_id': order_rec.id,
            'product_id': odoo_product.id
        }

        new_order_line = sale_order_line_obj.new(order_line_vals)
        new_order_line.product_id_change()
        order_line_vals = sale_order_line_obj._convert_to_write(new_order_line._cache)

        order_line_vals.update({
            'name': order_line.get('name'),
            'product_uom_qty': float(order_line.get('qty_ordered', 1.0)),
            'price_unit': original_price,
            'discount': round((discount / original_price) * 100, 2) if original_price and discount else 0,
            'tax_id': [(6, 0, [tax_id.id])],
            'magento_sale_order_line_ref': so_line_ref
        })

        return order_line_vals

    def get_account_tax_id(self, extension_attrs, type, order_rec, item, item_id):
        tax_percent = self.check_tax_percent(extension_attrs, type, item_id)
        if tax_percent is False:
            return f"Unable to get tax percentage from order data for {item}"

        tax_id = order_rec.fiscal_position_id.tax_ids.with_context(active_test=False).tax_src_id.filtered(
            lambda x: x.type_tax_use == 'sale' and (True if tax_percent == 0 else x.price_include) and
                      (x.amount >= tax_percent - 0.001 and x.amount <= tax_percent + 0.001)
        )

        if tax_id:
            tax_id = tax_id[0]
            if not tax_id.active:
                tax_id.active = True
            return tax_id
        else:
            return f"Missed '{tax_percent}'% tax (brutto) within '{order_rec.fiscal_position_id.name}' Fiscal Position"

    @staticmethod
    def check_tax_percent(extension_attributes, type, item_id):
        tax_percent = False

        if extension_attributes and "item_applied_taxes" in extension_attributes:
            if extension_attributes["item_applied_taxes"] == []:
                tax_percent = 0
            else:
                for tax in extension_attributes["item_applied_taxes"]:
                    if tax.get('type') == type and tax.get('applied_taxes') and item_id == tax.get('item_id'):
                        tax_percent = tax.get('applied_taxes')[0].get('percent')

        return tax_percent

    def create_shipping_sales_order_line(self, sales_order, order_rec):
        amount_net = float(sales_order.get('shipping_amount', 0.0))
        discount_amount = float(sales_order.get('shipping_discount_amount', 0.0))
        shipping_product = self.env.ref('odoo_magento2.product_product_shipping')

        if not shipping_product:
            return "Failed to find Magento Shipping product within Odoo products."

        vals = {
            'order_id': order_rec.id,
            'product_id': shipping_product.id
        }

        new_order_line = self.new(vals)
        new_order_line.product_id_change()
        vals = self._convert_to_write(new_order_line._cache)

        vals.update({
            'name': 'Shipping cost',
            'product_uom_qty': 1,
            'price_unit': amount_net,
            'discount': round((discount_amount / amount_net) * 100, 2) if amount_net and discount_amount else 0,
            'tax_id': False,
            'magento_sale_order_line_ref': 'shipping'
        })

        try:
            line = order_rec.order_line.filtered(lambda x: x.magento_sale_order_line_ref == 'shipping')
            if line:
                line.with_context(tracking_disable=True).write(vals)
            else:
                line = self.with_context(tracking_disable=True).create(vals)
        except Exception as e:
            return 'Error creating/updating shipping order line: ' + str(e)

        if not line:
            return "Failed to create shipping order line. "

        return ''
