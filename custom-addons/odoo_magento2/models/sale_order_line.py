# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.

from odoo import models, fields


class SaleOrderLine(models.Model):
    """
    Describes Sale order line
    """
    _inherit = 'sale.order.line'

    magento_sale_order_line_ref = fields.Char(
        string="Magento Sale Order Line Reference",
        help="Magento Sale Order Line Reference"
    )

    def create_sale_order_line(self, vals):
        """
        Pass dictionary
        vals = {'order_id':order_id, 'product_id':product_id, 'company_id':company_id, 'description':product_name,
        'order_qty':qty, 'price_unit':price, 'discount':discount}
        Required data in dictionary :- order_id, name, product_id.
        """
        sale_order_line = self.env['sale.order.line']
        order_line = {
            'order_id':vals.get('order_id', False),
            'product_id':vals.get('product_id', False),
            'company_id':vals.get('company_id', False),
            'name':vals.get('description', ''),
            'product_uom':vals.get('product_uom')
        }

        new_order_line = sale_order_line.new(order_line)
        new_order_line.product_id_change()
        order_line = sale_order_line._convert_to_write({name:new_order_line[name] for name in new_order_line._cache})

        order_line.update({
            'order_id':vals.get('order_id', False),
            'product_uom_qty':vals.get('order_qty', 0.0),
            'price_unit':vals.get('price_unit', 0.0),
            'discount':vals.get('discount', 0.0),
            'state':'draft',
        })
        return order_line

    @staticmethod
    def calculate_order_item_price(tax_calculation_method, item):
        """
        Calculate order item price based on tax calculation method configurations
        :param tax_calculation_method: Tax calculation method (Including/ Excluding)
        :param item: order item received from Magento
        :return: order item price
        """
        if tax_calculation_method == 'including_tax':
            price = item.get('parent_item').get('price_incl_tax') if "parent_item" in item else item.get(
                'price_incl_tax')
        else:
            price = item.get('parent_item').get('price') if "parent_item" in item else item.get('price')
        original_price = item.get('parent_item').get('original_price') if "parent_item" in item else item.get(
            'original_price')
        item_price = price if price != original_price else original_price
        return item_price

    def create_sale_order_line_vals(self, order_line_dict, price_unit, odoo_product, magento_order):
        """
        Create Sale Order Line Values
        :param order_line_dict:  Magento sale order line object
        :param price_unit: price unit object
        :param odoo_product: odoo product object
        :param magento_order: Magento order object
        :return:
        """
        order_qty = float(order_line_dict.get('qty_ordered', 1.0))
        magento_sale_order_line_ref = order_line_dict.get('parent_item_id') or order_line_dict.get('item_id')
        order_line_vals = {
            'order_id': magento_order.id,
            'product_id': odoo_product.id,
            'company_id': magento_order.company_id.id,
            'name': order_line_dict.get('name'),
            'description': odoo_product.name or magento_order.name,
            'product_uom': odoo_product.uom_id.id,
            'order_qty': order_qty,
            'price_unit': price_unit,
        }
        order_line_vals = self.create_sale_order_line(order_line_vals)
        order_line_vals.update({
            'magento_sale_order_line_ref': magento_sale_order_line_ref
        })
        return order_line_vals

    def magento_create_sale_order_line_adj(self, magento_instance, sales_order, magento_order):
        magento_product = self.env['magento.product.product']
        magento_order_lines = sales_order.get('items')
        store_id = sales_order.get('store_id')
        store_view = magento_instance.magento_website_ids.store_view_ids.filtered(
            lambda x: x.magento_storeview_id == str(store_id)
        )
        tax_calculation_method = store_view and store_view.magento_website_id.tax_calculation_method

        for item in magento_order_lines:
            product_sku = item.get('sku')
            item_price = self.calculate_order_item_price(tax_calculation_method, item)
            magento_product = magento_product.search([
                ('magento_sku', '=', product_sku),
                ('magento_instance_id', '=', magento_instance.id)
            ], limit=1)
            sale_order_line = self.create_sale_order_line_vals(item, item_price, magento_product.odoo_product_id,
                                                               magento_order)
            try:
                line = self.create(sale_order_line)
            except Exception:
                return False

            if not line:
                return False

        return True
