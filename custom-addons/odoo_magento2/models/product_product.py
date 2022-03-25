# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
from datetime import datetime
from odoo import models, fields
from odoo.exceptions import UserError

MAGENTO_PRODUCT = 'magento.product.product'


class ProductProduct(models.Model):
    _inherit = 'product.product'

    magento_product_count = fields.Integer(string='# Product Counts', compute='_compute_magento_product_count')
    magento_product_ids = fields.One2many(MAGENTO_PRODUCT, 'odoo_product_id', string='Magento Products',
                                          help='Magento Product Ids')

    def _compute_magento_product_count(self):
        """
        calculate magento product count
        :return:
        """
        magento_product_obj = self.env[MAGENTO_PRODUCT]
        for product in self:
            magento_products = magento_product_obj.search([('odoo_product_id', '=', product.id)])
            product.magento_product_count = len(magento_products) if magento_products else 0

    def write(self, vals):
        if self.magento_product_ids and ('product_variant_image_ids' in vals or 'weight' in vals) :
            self.magento_product_ids.force_update = True

        return super(ProductProduct, self).write(vals)

    def unlink(self):
        reject_configs = []

        for prod in self:
            if prod.magento_product_ids:
                reject_configs.append({c.magento_instance_id.name: c.magento_sku for c in prod.magento_product_ids})

        if reject_configs:
            raise UserError("It's not allowed to delete these product(s) as they were already added to Magento Layer "
                            "as Simple Product(s): %s\n" % (str(reject_configs)))

        return super(ProductProduct, self).unlink()

    def get_products_based_on_movement_date(self, from_datetime, company=False):
        """
        This method is give the product list from selected date
        :param from_datetime:from this date it gets the product move list
        :param company:Record of Company.
        :return:Product List
        """
        # Check MRP module is installed or not
        result = []
        module_obj = self.env['ir.module.module']
        mrp_module = module_obj.sudo().search([('name', '=', 'mrp'), ('state', '=', 'installed')])
        date = str(datetime.strftime(from_datetime, '%Y-%m-%d %H:%M:%S'))

        if mrp_module:
            mrp_qry = ("""select p.id as product_id from product_product as p
                    inner join mrp_bom as mb on mb.product_tmpl_id=p.product_tmpl_id
                    inner join mrp_bom_line as ml on ml.bom_id=mb.id
                    inner join stock_move as sm on sm.product_id=ml.product_id
                    where sm.date >= '%s' and sm.company_id = %d and sm.state in 
                    ('partially_available','assigned','done')"""%(date, company.id))
            self._cr.execute(mrp_qry)
            result = self._cr.dictfetchall()

        qry = ("""select product_id from stock_move where date >= '%s' and
                 state in ('partially_available','assigned','done')"""%(date))
        if company:
            qry += ("""and company_id = %d"""%company.id)

        self._cr.execute(qry)
        result += self._cr.dictfetchall()
        product_ids = [product_id.get('product_id') for product_id in result]

        return list(set(product_ids))

    def prepare_location_and_product_ids(self, locations, product_list):
        """
        This method prepares location and product ids from warehouse and list of product id.
        @param warehouse: Record of Warehouse
        @param product_list: Ids of Product.
        @return: Ids of locations and products in string.
        """
        # locations = self.env['stock.location'].search([('location_id', 'child_of', warehouse.lot_stock_id.ids)])
        if not len(locations):
            raise UserError("Need to specify the location(s) for each instance in Magento >> Configuration >> Settings")
        locations = locations.search([('location_id', 'child_of', locations.ids), ('usage', '!=', 'view')])

        location_ids = ','.join(str(e) for e in locations.ids)
        product_ids = ','.join(str(e) for e in product_list)
        return location_ids, product_ids

    def check_for_bom_products(self, product_ids):
        """
        This method checks if any product is BoM, then get stock for them.
        @param product_ids: Ids of Product.
        @return: Ids of BoM products.
        """
        bom_product_ids = []
        module_obj = self.env['ir.module.module']

        mrp_module = module_obj.sudo().search([('name', '=', 'mrp'), ('state', '=', 'installed')])
        if mrp_module:
            qry = ("""select p.id as product_id from product_product as p
                        inner join mrp_bom as mb on mb.product_tmpl_id=p.product_tmpl_id
                        and p.id in (%s)"""% product_ids)
            self._cr.execute(qry)
            bom_product_ids = self._cr.dictfetchall()
            bom_product_ids = [product_id.get('product_id') for product_id in bom_product_ids]

        return bom_product_ids

    def prepare_free_qty_query(self, location_ids, simple_product_list_ids):
        """
        This method prepares query for fetching the free qty.
        @param location_ids:Ids of Locations.
        @param simple_product_list_ids: Ids of products which are not BoM.
        @return: Prepared query in string.
        """
        query = """select pp.id as product_id,
                COALESCE(sum(sq.quantity)-sum(sq.reserved_quantity),0) as stock
                from product_product pp
                left join stock_quant sq on pp.id = sq.product_id and sq.location_id in (%s)
                where pp.id in (%s) group by pp.id;""" % (location_ids, simple_product_list_ids)
        return query

    def prepare_forecasted_qty_query(self, location_ids, simple_product_list_ids):
        """
        This method prepares query for fetching the forecasted qty.
        @param location_ids:Ids of Locations.
        @param simple_product_list_ids: Ids of products which are not BoM.
        @return: Prepared query in string.
        """
        query = ("""select product_id,sum(stock) as stock from (select pp.id as product_id,
                COALESCE(sum(sq.quantity)-sum(sq.reserved_quantity),0) as stock
                from product_product pp
                left join stock_quant sq on pp.id = sq.product_id and sq.location_id in (%s)
                where pp.id in (%s) group by pp.id
                union all
                select product_id as product_id, sum(product_qty) as stock from stock_move
                where state in ('assigned') and product_id in (%s) and location_dest_id in (%s)
                group by product_id) as test group by test.product_id"""%(location_ids, simple_product_list_ids,
                 simple_product_list_ids, location_ids))
        return query

    def get_free_qty(self, locations, product_list):
        """
        This method returns On hand quantity based on warehouse and product list
        :param warehouse: warehouse object
        :param product_list: list of product_ids (Not browsable record)
        :return: Dictionary as product_id : on_hand_qty
        """
        qty_on_hand = {}
        location_ids, product_ids = self.prepare_location_and_product_ids(locations, product_list)
        bom_product_ids = self.check_for_bom_products(product_ids)
        if bom_product_ids:
            bom_products = self.with_context(location=locations.ids).browse(bom_product_ids)
            for product in bom_products:
                actual_stock = getattr(product, 'free_qty')
                qty_on_hand.update({product.id:actual_stock})

        simple_product_list = list(set(product_list) - set(bom_product_ids))
        simple_product_list_ids = ','.join(str(e) for e in simple_product_list)
        if simple_product_list_ids:
            qry = self.prepare_free_qty_query(location_ids, simple_product_list_ids)
            self._cr.execute(qry)
            result = self._cr.dictfetchall()
            for i in result:
                qty_on_hand.update({i.get('product_id'):i.get('stock')})
        return qty_on_hand

    def get_forecasted_qty(self, locations, product_list):
        """
        This method is return forecasted quantity based on warehouse and product list
        :param warehouse:warehouse object
        :param product_list:list of product_ids (Not browsable records)
        :return: Forecasted Quantity
        """
        forcasted_qty = {}
        location_ids, product_ids = self.prepare_location_and_product_ids(locations, product_list)

        bom_product_ids = self.check_for_bom_products(product_ids)
        if bom_product_ids:
            bom_products = self.with_context(location=locations.ids).browse(bom_product_ids)
            for product in bom_products:
                actual_stock = getattr(product, 'free_qty') + getattr(product, 'incoming_qty')
                forcasted_qty.update({product.id:actual_stock})

        simple_product_list = list(set(product_list) - set(bom_product_ids))
        simple_product_list_ids = ','.join(str(e) for e in simple_product_list)
        if simple_product_list_ids:
            qry = self.prepare_forecasted_qty_query(location_ids, simple_product_list_ids)
            self._cr.execute(qry)
            result = self._cr.dictfetchall()
            for i in result:
                forcasted_qty.update({i.get('product_id'):i.get('stock')})
        return forcasted_qty
