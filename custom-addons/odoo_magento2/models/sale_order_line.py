# -*- coding: utf-8 -*-

from odoo import models, fields


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    magento_sale_order_line_ref = fields.Char(string="SO line ref.", help="Magento Sale Order Line Reference")

    def create_product_sales_order_line(self, instance, sales_order, order_rec):
        magento_order_lines = sales_order.get('items')

        for order_line in magento_order_lines:
            so_line_ref = order_line.get('item_id')
            so_line_vals = self.prepare_product_sales_order_line_vals(order_line, instance, order_rec)

            if isinstance(so_line_vals, str):
                return so_line_vals

            try:
                line = order_rec.order_line.filtered(lambda x: x.magento_sale_order_line_ref == str(so_line_ref))
                if line:
                    line.with_context(tracking_disable=True).write(so_line_vals)
                else:
                    line = self.with_context(tracking_disable=True).create(so_line_vals)
            except Exception as e:
                return f"Error creating/updating sales order line with following sku {order_line.get('sku')}: {str(e)}"

            if not line:
                return f"Failed to create order line for product - {order_line.get('sku')}"

        return ''

    def prepare_product_sales_order_line_vals(self, order_line, instance, order_rec):
        sale_order_line_obj = self.env['sale.order.line']
        so_line_ref = order_line.get('item_id')
        product_sku = order_line.get('sku')
        original_price = order_line.get('original_price', 0.0)
        discount = (original_price - order_line.get('price_incl_tax', 0.0)) if original_price else 0
        discount += order_line.get('discount_amount', 0.0) / order_line.get('qty_ordered', 1.0)

        odoo_product = self.env['magento.product.product'].search([
            ('magento_sku', '=', product_sku),
            ('magento_instance_id', '=', instance.id)
        ], limit=1).odoo_product_id

        res = self.check_vat_is_in_fiscal_positions_tax_list(order_rec, odoo_product)
        if res:
            return res

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
            'magento_sale_order_line_ref': str(so_line_ref)
        })

        return order_line_vals

    @staticmethod
    def check_vat_is_in_fiscal_positions_tax_list(order_rec, odoo_product):
        if not odoo_product.taxes_id:
            return f"Product {odoo_product.default_code} missed 'Customer Taxes' field to be used while VAT % calculation."

        for tax in odoo_product.taxes_id:
            if tax.id not in order_rec.fiscal_position_id.tax_ids.tax_src_id.mapped('id'):
                return f"Fiscal position - '{order_rec.fiscal_position_id.name}' missed Sales Tax - '{tax.name}'" \
                       f" applied for product '{odoo_product.default_code}'"

    def create_shipping_sales_order_line(self, sales_order, order_rec):
        ship_amount = float(sales_order.get('shipping_amount', 0.0))
        discount_amount = sales_order.get('shipping_discount_amount', 0.0)
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
            'price_unit': ship_amount,
            'discount': round((discount_amount / ship_amount) * 100, 2) if ship_amount and discount_amount else 0,
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
