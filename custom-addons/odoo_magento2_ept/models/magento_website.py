# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
"""
Describes Methods for Magento Website.
"""
import json
from datetime import date
from odoo import models, fields, api, _


class MagentoWebsite(models.Model):
    """
    Describes Magento Website.
    """
    _name = 'magento.website'
    _description = 'Magento Website'
    _order = 'sort_order ASC, id ASC'

    name = fields.Char(string="Website Name", required=True, readonly=True, help="Website Name")
    sort_order = fields.Integer(
        string='Website Sort Order',
        readonly=True,
        help='Website Sort Order'
    )
    magento_instance_id = fields.Many2one(
        'magento.instance',
        'Instance',
        ondelete="cascade",
        help="This field relocates magento instance"
    )
    magento_website_id = fields.Char(string="Magento Website", help="Magento Website Id")
    import_partners_from_date = fields.Datetime(
        string='Last partner import date',
        help='Date when partner last imported'
    )
    pricelist_ids = fields.Many2many(
        'product.pricelist',
        string="Pricelist",
        help="Product Price is set in selected Pricelist if Catalog Price Scope is Website"
    )
    pricelist_id = fields.Many2one(
        'product.pricelist',
        string="Pricelist Id",
        help="Product Price is set in selected Pricelist if Catalog Price Scope is Website"
    )
    store_view_ids = fields.One2many(
        "magento.storeview",
        inverse_name="magento_website_id",
        string='Magento Store Views',
        help='This relocates Magento Store Views'
    )
    warehouse_id = fields.Many2one(
        comodel_name='stock.warehouse',
        string='Warehouse',
        help='Warehouse to be used to deliver an order from this website.'
    )
    company_id = fields.Many2one(
        'res.company',
        related='magento_instance_id.company_id',
        string='Company',
        readonly=True,
        help="Magento Company"
    )
    currency_id = fields.Many2one(
        "res.currency",
        related='pricelist_id.currency_id',
        readonly=True,
        help="Currency"
    )
    magento_base_currency = fields.Many2one(
        "res.currency",
        readonly=True,
        help="Magento Website Base Currency"
    )
    active = fields.Boolean(string="Status", default=True)
    color = fields.Integer(string='Color Index')
    magento_order_data = fields.Text(compute="_compute_kanban_magento_order_data")
    website_display_currency = fields.Many2one("res.currency",
                                               readonly=True,
                                               help="Display currency of the magento website.")


    def _compute_kanban_magento_order_data(self):
        if not self._context.get('sort'):
            context = dict(self.env.context)
            context.update({'sort': 'week'})
            self.env.context = context
        for record in self:
            # Prepare values for Graph
            values = record.get_graph_data(record)
            data_type, comparison_value = record.get_compare_data(record)
            # Total sales
            total_sales = round(sum([key['y'] for key in values]), 2)
            # Product count query
            exported = 'All'
            product_data = record.get_total_products(record, exported)
            # Customer count query
            customer_data = record.get_customers(record)
            # Order count query
            order_data = record.get_total_orders(record)
            # Order shipped count query
            order_shipped = record.get_shipped_orders(record)
            # # refund count query
            # refund_data = record.get_refund(record)
            record.magento_order_data = json.dumps({
                "values": values,
                "title": "",
                "key": "Order: Untaxed amount",
                "area": True,
                "color": "#875A7B",
                "is_sample_data": False,
                "total_sales": total_sales,
                "order_data": order_data,
                "product_date": product_data,
                "customer_data": customer_data,
                "order_shipped": order_shipped,
                "sort_on": self._context.get('sort'),
                "currency_symbol": record.magento_base_currency.symbol or '', # remove currency symbol and make it same as odoo
                "graph_sale_percentage": {'type': data_type, 'value': comparison_value}
            })

    @staticmethod
    def prepare_action(view, domain):
        """
        Use: To prepare action dictionary
        :return: action details
        """
        action = {
            'name': view.get('name'),
            'type': view.get('type'),
            'domain': domain,
            'view_mode': view.get('view_mode'),
            'view_id': view.get('view_id')[0] if view.get('view_id') else False,
            'views': view.get('views'),
            'res_model': view.get('res_model'),
            'target': view.get('target'),
        }

        if 'tree' in action['views'][0]:
            action['views'][0] = (action['view_id'], 'list')
        return action

    def get_total_products(self, record, exported, product_type=False):
        """
        Use: To get the list of products exported from Magento instance
        Here if exported = True, then only get those record which having sync_product_with_magento= true
        if exported = False, then only get those record which having sync_product_with_magento= false
        if exported = All, then get all those records which having sync_product_with_magento = true and false
        :param record: magento website object
        :param exported: exported is one of the "True" or "False" or "All"
        :return: total number of Magento products ids and action for products
        """
        product_data = {}
        main_sql = """select count(id) as total_count from magento_product_template
        inner join magento_product_template_magento_website_rel on
        magento_product_template_magento_website_rel.magento_product_template_id = magento_product_template.id  
        where magento_product_template_magento_website_rel.magento_website_id = %s and
        magento_product_template.magento_instance_id = %s""" % (record.id, record.magento_instance_id.id)
        domain = []
        if exported != 'All' and exported:
            main_sql = main_sql + " and magento_product_template.sync_product_with_magento = True"
            domain.append(('sync_product_with_magento', '=', True))
        elif not exported:
            main_sql = main_sql + " and magento_product_template.sync_product_with_magento = False"
            domain.append(('sync_product_with_magento', '=', False))
        elif exported == 'All':
            #main_sql = main_sql + " and magento_product_template.sync_product_with_magento in (False,True)"
            domain.append(('sync_product_with_magento', 'in', (False, True)))

        if product_type:
            domain.append(('product_type', '=', product_type))
        self._cr.execute(main_sql)
        result = self._cr.dictfetchall()
        total_count = 0
        if result:
            total_count = result[0].get('total_count')
        view = self.env.ref('odoo_magento2_ept.action_magento_product_exported_ept').sudo().read()[0]
        domain.append(('magento_instance_id', '=', record.magento_instance_id.id))
        domain.append(('magento_website_ids', '=', record.name))
        action = record.prepare_action(view, domain)
        product_data.update({'product_count': total_count, 'product_action': action})
        return product_data

    def get_customers(self, record):
        """
        Use: To get the list of customers with Magento instance for current Magento instance
        :return: total number of customer ids and action for customers
        """
        customer_data = {}
        main_sql = """select count(id) as total_count from res_partner
                where magento_website_id = %s and
                magento_instance_id = %s""" % (record.id, record.magento_instance_id.id)
        view = self.env.ref('base.action_partner_form').sudo().read()[0]
        action = record.prepare_action(view, [('active', 'in', [True, False]),
                                              ('magento_instance_id', '=', record.magento_instance_id.id),
                                              ('magento_website_id', '=', record.id)
                                              ])
        self._cr.execute(main_sql)
        result = self._cr.dictfetchall()
        total_count = 0
        if result:
            total_count = result[0].get('total_count')
        customer_data.update({'customer_count': total_count, 'customer_action': action})
        return customer_data

    def get_total_orders(self, record, state=False):
        """
        Use: To get the list of Magento sale orders month wise or year wise
        :return: total number of Magento sale orders ids and action for sale orders of current instance
        """
        if not state:
            state = ('sale', 'done')
        def orders_of_current_week(record):
            self._cr.execute("""select id from sale_order where date(date_order)
                                >= (select date_trunc('week', date(current_date)))
                                and magento_instance_id= %s and state in %s 
                                and magento_website_id = %s 
                                order by date(date_order)
                        """ % (record.magento_instance_id.id, state, record.id))
            return self._cr.dictfetchall()

        def orders_of_current_month(record):
            self._cr.execute("""select id from sale_order where date(date_order) >=
                                (select date_trunc('month', date(current_date)))
                                and magento_instance_id= %s and state in %s 
                                and magento_website_id = %s
                                order by date(date_order)
                        """ % (record.magento_instance_id.id, state, record.id))
            return self._cr.dictfetchall()

        def orders_of_current_year(record):
            self._cr.execute("""select id from sale_order where date(date_order) >=
                                (select date_trunc('year', date(current_date))) 
                                and magento_instance_id= %s and state in %s  
                                and magento_website_id = %s
                                order by date(date_order)
                             """ % (record.magento_instance_id.id, state, record.id))
            return self._cr.dictfetchall()

        def orders_of_all_time(record):
            self._cr.execute(
                """select id from sale_order where magento_instance_id = %s
                and state in %s
                and magento_website_id = %s""" % (record.magento_instance_id.id, state, record.id))
            return self._cr.dictfetchall()

        order_data = {}
        order_ids = []
        if self._context.get('sort') == "week":
            result = orders_of_current_week(record)
        elif self._context.get('sort') == "month":
            result = orders_of_current_month(record)
        elif self._context.get('sort') == "year":
            result = orders_of_current_year(record)
        else:
            result = orders_of_all_time(record)
        if result:
            for data in result:
                order_ids.append(data.get('id'))
        view = self.env.ref('odoo_magento2_ept.magento_action_sales_order_ept').sudo().read()[0]
        action = record.prepare_action(view, [('id', 'in', order_ids)])
        order_data.update({'order_count': len(order_ids), 'order_action': action})
        return order_data

    def get_shipped_orders(self, record):
        """
        Use: To get the list of Magento shipped orders month wise or year wise
        :return: total number of Magento shipped orders ids and action for shipped orders of current instance
        """
        shipped_query = """select distinct(so.id) from stock_picking sp
                             inner join sale_order so on so.procurement_group_id=sp.group_id inner 
                             join stock_location on stock_location.id=sp.location_dest_id and stock_location.usage='customer' 
                             where sp.is_magento_picking = True and sp.state = 'done' and 
                             so.magento_instance_id=%s and so.magento_website_id=%s""" % \
                        (record.magento_instance_id.id, record.id)

        def shipped_order_of_current_week(shipped_query):
            qry = shipped_query + " and date(so.date_order) >= (select date_trunc('week', date(current_date)))"
            self._cr.execute(qry)
            return self._cr.dictfetchall()

        def shipped_order_of_current_month(shipped_query):
            qry = shipped_query + " and date(so.date_order) >= (select date_trunc('month', date(current_date)))"
            self._cr.execute(qry)
            return self._cr.dictfetchall()

        def shipped_order_of_current_year(shipped_query):
            qry = shipped_query + " and date(so.date_order) >= (select date_trunc('year', date(current_date)))"
            self._cr.execute(qry)
            return self._cr.dictfetchall()

        def shipped_order_of_all_time(shipped_query):
            self._cr.execute(shipped_query)
            return self._cr.dictfetchall()

        order_data = {}
        order_ids = []
        if self._context.get('sort') == "week":
            result = shipped_order_of_current_week(shipped_query)
        elif self._context.get('sort') == "month":
            result = shipped_order_of_current_month(shipped_query)
        elif self._context.get('sort') == "year":
            result = shipped_order_of_current_year(shipped_query)
        else:
            result = shipped_order_of_all_time(shipped_query)
        if result:
            for data in result:
                order_ids.append(data.get('id'))
        view = self.env.ref('odoo_magento2_ept.magento_action_sales_order_ept').sudo().read()[0]
        action = record.prepare_action(view, [('id', 'in', order_ids)])
        order_data.update({'order_count': len(order_ids), 'order_action': action})
        return order_data

    def magento_product_exported_ept(self):
        """
        get exported as true product action
        :return:
        """
        exported = True
        product_data = self.get_total_products(self, exported)
        return product_data.get('product_action')


    def action_magento_simple_product_type(self):
        """
        get magento simple product type
        :return:
        """
        product_type = "simple"
        exported = "All"
        product_data = self.get_total_products(self, exported, product_type)
        return product_data.get('product_action')

    def action_magento_configurable_product_type(self):
        """
        get magento configurable product type
        :return:
        """
        product_type = "configurable"
        exported = "All"
        product_data = self.get_total_products(self, exported, product_type)
        return product_data.get('product_action')

    def magento_action_sales_quotations_ept(self):
        """
        get quotations action
        :return:
        """
        state = ('draft', 'sent')
        order_data = self.get_total_orders(self, state)
        return order_data.get('order_action')

    def magento_action_sales_order_ept(self):
        """
        get sales order action
        :return:
        """
        state = ('sale', 'done')
        order_data = self.get_total_orders(self, state)
        return order_data.get('order_action')

    def get_magento_invoice_records(self, state):
        """
        To get instance wise magento invoice
        :param state: state of the invoice
        :return: invoice_data dict with total count and action
        """
        invoice_data = {}
        invoice_ids = []
        invoice_query = """select account_move.id
        from sale_order_line_invoice_rel
        inner join sale_order_line on sale_order_line.id=sale_order_line_invoice_rel.order_line_id 
        inner join sale_order on sale_order.id=sale_order_line.order_id
        inner join account_move_line on account_move_line.id=sale_order_line_invoice_rel.invoice_line_id 
        inner join account_move on account_move.id=account_move_line.move_id
        where sale_order.magento_website_id=%s
        and sale_order.magento_instance_id=%s
        and account_move.state in ('%s')
        and account_move.move_type in ('out_invoice','out_refund')""" % \
                        (self.id, self.magento_instance_id.id, state)
        self._cr.execute(invoice_query)
        result = self._cr.dictfetchall()
        view = self.env.ref('odoo_magento2_ept.action_magento_invoice_tree1_ept').sudo().read()[0]
        if result:
            for data in result:
                invoice_ids.append(data.get('id'))
        action = self.prepare_action(view, [('id', 'in', invoice_ids)])
        invoice_data.update({'order_count': len(invoice_ids), 'order_action': action})
        return invoice_data

    def get_magento_picking_records(self, state):
        """
        To get instance wise magento picking
        :param state: state of the picking
        :return: picking_data dict with total count and action
        """
        picking_data = {}
        picking_ids = []
        invoice_query = """SELECT SP.id FROM stock_picking as SP
        inner join sale_order as SO on SP.sale_id = SO.id
        inner join stock_location as SL on SL.id = SP.location_dest_id 
        WHERE SP.magento_instance_id = %s
        and SO.magento_website_id = %s
        and SL.usage = 'customer'
        and SP.state in ('%s')
        """ % (self.magento_instance_id.id, self.id, state)
        self._cr.execute(invoice_query)
        result = self._cr.dictfetchall()
        view = self.env.ref('odoo_magento2_ept.action_magento_stock_picking_tree_ept').sudo().read()[0]
        if result:
            for data in result:
                picking_ids.append(data.get('id'))
        action = self.prepare_action(view, [('id', 'in', picking_ids)])
        picking_data.update({'order_count': len(picking_ids), 'order_action': action})
        return picking_data

    def magento_invoice_invoices_open(self):
        """
        get draft state invoice action
        :return:
        """
        state = 'draft'
        invoice_data = self.get_magento_invoice_records(state)
        return invoice_data.get('order_action')

    def magento_invoice_invoices_paid(self):
        """
        get posted state invoice action
        :return:
        """
        state = 'posted'
        invoice_data = self.get_magento_invoice_records(state)
        return invoice_data.get('order_action')

    def magento_waiting_stock_picking_ept(self):
        """
        get confirmed state picking action
        :return:
        """
        state = 'confirmed'
        picking_data = self.get_magento_picking_records(state)
        return picking_data.get('order_action')

    def magento_partially_available_stock_picking_ept(self):
        """
        get partially_available state picking action
        :return:
        """
        state = 'partially_available'
        picking_data = self.get_magento_picking_records(state)
        return picking_data.get('order_action')

    def magento_ready_stock_picking_ept(self):
        """
        get assigned state picking action
        :return:
        """
        state = 'assigned'
        picking_data = self.get_magento_picking_records(state)
        return picking_data.get('order_action')

    def magento_transferred_stock_picking_ept(self):
        """
        get done state picking action
        :return:
        """
        state = 'done'
        picking_data = self.get_magento_picking_records(state)
        return picking_data.get('order_action')


    @api.model
    def perform_operation(self, record_id):
        """
        Use: To prepare Magento operation action
        :return: Magento operation action details
        """
        view = self.env.ref('odoo_magento2_ept.'
                            'action_wizard_magento_instance_import_export_operations').sudo().read()[0]
        action = self.prepare_action(view, [])
        website = self.browse(record_id)
        action.update({'context': {'default_magento_instance_ids': website.magento_instance_id.ids}})
        return action

    @api.model
    def open_logs(self, record_id):
        """
        Use: To prepare Magento logs action
        :return: Magento logs action details
        """
        website = self.browse(record_id)
        view = self.env.ref('odoo_magento2_ept.action_common_log_book_ept_magento').sudo().read()[0]
        return self.prepare_action(view, [('magento_instance_id', '=', website.magento_instance_id.id)])

    @api.model
    def open_report(self, record_id):
        """
        Use: To prepare Magento report action
        :return: Magento report action details
        """
        view = self.env.ref('sale.action_order_report_all').sudo().read()[0]
        website = self.browse(record_id)
        action = self.prepare_action(view, [('magento_instance_id', '=', website.magento_instance_id.id),
                                            ('magento_website_id', '=', record_id)])
        return action

    def get_graph_data(self, record):
        """
        Use: To get the details of Magento sale orders and total amount month wise or year wise to prepare the graph
        :return: Magento sale order date or month and sum of sale orders amount of current instance
        """
        def get_current_week_date(record):
            self._cr.execute("""SELECT to_char(date(d.day),'DAY'), t.amount_untaxed as sum
                                FROM  (
                                   SELECT day
                                   FROM generate_series(date(date_trunc('week', (current_date)))
                                    , date(date_trunc('week', (current_date)) + interval '6 days')
                                    , interval  '1 day') day
                                   ) d
                                LEFT   JOIN 
                                (SELECT date(date_order)::date AS day, sum(amount_untaxed) as amount_untaxed
                                   FROM   sale_order
                                   WHERE  date(date_order) >= (select date_trunc('week', date(current_date)))
                                   AND    date(date_order) <= (select date_trunc('week', date(current_date)) 
                                   + interval '6 days')
                                   AND magento_instance_id=%s and state in ('sale','done') 
                                    AND magento_website_id = %s 
                                   GROUP  BY 1
                                   ) t USING (day)
                                ORDER  BY day""" % (record.magento_instance_id.id, record.id))
            return self._cr.dictfetchall()

        def graph_of_current_month(record):
            self._cr.execute("""select EXTRACT(DAY from date(date_day)) :: integer,sum(amount_untaxed) from (
                        SELECT 
                          day::date as date_day,
                          0 as amount_untaxed
                        FROM generate_series(date(date_trunc('month', (current_date)))
                            , date(date_trunc('month', (current_date)) + interval '1 MONTH - 1 day')
                            , interval  '1 day') day
                        union all
                        SELECT date(date_order)::date AS date_day,
                        sum(amount_untaxed) as amount_untaxed
                          FROM   sale_order
                        WHERE  date(date_order) >= (select date_trunc('month', date(current_date)))
                        AND date(date_order)::date <= (select date_trunc('month', date(current_date)) 
                        + '1 MONTH - 1 day')
                        and magento_instance_id = %s and state in ('sale','done') 
                        and magento_website_id = %s 
                        group by 1
                        )foo 
                        GROUP  BY 1
                        ORDER  BY 1""" % (record.magento_instance_id.id, record.id))
            return self._cr.dictfetchall()

        def graph_of_current_year(record):
            self._cr.execute("""select TRIM(TO_CHAR(DATE_TRUNC('month',month),'MONTH')),sum(amount_untaxed) from
                                (SELECT DATE_TRUNC('month',date(day)) as month,
                                  0 as amount_untaxed
                                FROM generate_series(date(date_trunc('year', (current_date)))
                                , date(date_trunc('year', (current_date)) + interval '1 YEAR - 1 day')
                                , interval  '1 MONTH') day
                                union all
                                SELECT DATE_TRUNC('month',date(date_order)) as month,
                                sum(amount_untaxed) as amount_untaxed
                                  FROM   sale_order
                                WHERE  date(date_order) >= (select date_trunc('year', date(current_date))) AND 
                                date(date_order)::date <= (select date_trunc('year', date(current_date)) 
                                + '1 YEAR - 1 day')
                                and magento_instance_id = %s and state in ('sale','done') 
                                and magento_website_id = %s 
                                group by DATE_TRUNC('month',date(date_order))
                                order by month
                                )foo 
                                GROUP  BY foo.month
                                order by foo.month""" % (record.magento_instance_id.id, record.id))
            return self._cr.dictfetchall()

        def graph_of_all_time(record):
            self._cr.execute("""select TRIM(TO_CHAR(DATE_TRUNC('month',date_order),'YYYY-MM')),sum(amount_untaxed)
                                from sale_order where magento_instance_id = %s and state in ('sale','done') 
                                and magento_website_id = %s 
                                group by DATE_TRUNC('month',date_order) 
                                order by DATE_TRUNC('month',date_order)""" % (record.magento_instance_id.id, record.id))
            return self._cr.dictfetchall()

        # Prepare values for Graph
        values = []
        if self._context.get('sort') == 'week':
            result = get_current_week_date(record)
        elif self._context.get('sort') == "month":
            result = graph_of_current_month(record)
        elif self._context.get('sort') == "year":
            result = graph_of_current_year(record)
        else:
            result = graph_of_all_time(record)
        if result:
            for data in result:
                values.append({"x": ("{}".format(data.get(list(data.keys())[0]))), "y": data.get('sum') or 0.0})
        return values

    def get_compare_data(self, record):
        """
        :param record: Magento instance
        :return: Comparison ratio of orders (weekly,monthly and yearly based on selection)
        """
        data_type = False
        total_percentage = 0.0

        def get_compared_week_data(record):
            current_total = 0.0
            previous_total = 0.0
            day_of_week = date.weekday(date.today())
            self._cr.execute("""select sum(amount_untaxed) as current_week from sale_order
                                where date(date_order) >= (select date_trunc('week', date(current_date))) and
                                magento_instance_id=%s and magento_website_id = %s and state in ('sale','done')""" %
                             (record.magento_instance_id.id, record.id))
            current_week_data = self._cr.dictfetchone()
            if current_week_data:
                current_total = current_week_data.get('current_week') if current_week_data.get('current_week') else 0
            # Previous week data
            self._cr.execute("""select sum(amount_untaxed) as previous_week from sale_order
                            where date(date_order) between (select date_trunc('week', current_date) - interval '7 day') 
                            and (select date_trunc('week', (select date_trunc('week', current_date) - interval '7
                            day')) + interval '%s day')
                            and magento_instance_id=%s and magento_website_id = %s and state in ('sale','done')
                            """ % (day_of_week, record.magento_instance_id.id, record.id))
            previous_week_data = self._cr.dictfetchone()
            if previous_week_data:
                previous_total = previous_week_data.get('previous_week') if previous_week_data.get(
                    'previous_week') else 0
            return current_total, previous_total

        def get_compared_month_data(record):
            current_total = 0.0
            previous_total = 0.0
            day_of_month = date.today().day - 1
            self._cr.execute("""select sum(amount_untaxed) as current_month from sale_order
                                where date(date_order) >= (select date_trunc('month', date(current_date)))
                                and magento_instance_id=%s and magento_website_id = %s and state in ('sale','done')""" %
                             (record.magento_instance_id.id, record.id))
            current_data = self._cr.dictfetchone()
            if current_data:
                current_total = current_data.get('current_month') if current_data.get('current_month') else 0
            # Previous week data
            self._cr.execute("""select sum(amount_untaxed) as previous_month from sale_order where date(date_order)
                            between (select date_trunc('month', current_date) - interval '1 month') and
                            (select date_trunc('month', (select date_trunc('month', current_date) - interval
                            '1 month')) + interval '%s days')
                            and magento_instance_id=%s and magento_website_id = %s and state in ('sale','done')
                            """ % (day_of_month, record.magento_instance_id.id, record.id))
            previous_data = self._cr.dictfetchone()
            if previous_data:
                previous_total = previous_data.get('previous_month') if previous_data.get('previous_month') else 0
            return current_total, previous_total

        def get_compared_year_data(record):
            current_total = 0.0
            previous_total = 0.0
            year_begin = date.today().replace(month=1, day=1)
            year_end = date.today()
            delta = (year_end - year_begin).days - 1
            self._cr.execute("""select sum(amount_untaxed) as current_year from sale_order
                                where date(date_order) >= (select date_trunc('year', date(current_date)))
                                and magento_instance_id=%s and magento_website_id = %s and state in ('sale','done')""" %
                             (record.magento_instance_id.id, record.id))
            current_data = self._cr.dictfetchone()
            if current_data:
                current_total = current_data.get('current_year') if current_data.get('current_year') else 0
            # Previous week data
            self._cr.execute("""select sum(amount_untaxed) as previous_year from sale_order where date(date_order)
                            between (select date_trunc('year', date(current_date) - interval '1 year')) and 
                            (select date_trunc('year', date(current_date) - interval '1 year') + interval '%s days') 
                            and magento_instance_id=%s and magento_website_id = %s and state in ('sale','done')
                            """ % (delta, record.magento_instance_id.id, record.id))
            previous_data = self._cr.dictfetchone()
            if previous_data:
                previous_total = previous_data.get('previous_year') if previous_data.get('previous_year') else 0
            return current_total, previous_total

        if self._context.get('sort') == 'week':
            current_total, previous_total = get_compared_week_data(record)
        elif self._context.get('sort') == "month":
            current_total, previous_total = get_compared_month_data(record)
        elif self._context.get('sort') == "year":
            current_total, previous_total = get_compared_year_data(record)
        else:
            current_total, previous_total = 0.0, 0.0
        if current_total > 0.0:
            if current_total >= previous_total:
                data_type = 'positive'
                total_percentage = (current_total - previous_total) * 100 / current_total
            if previous_total > current_total:
                data_type = 'negative'
                total_percentage = (previous_total - current_total) * 100 / current_total
        return data_type, round(total_percentage, 2)

    def open_store_views(self):
        """
        This method used to view all store views for website.
        """
        form_view_id = self.env.ref('odoo_magento2_ept.view_magento_storeview_form').id
        tree_view = self.env.ref('odoo_magento2_ept.view_magento_storeview_tree').id
        action = {
            'name': 'Magento Store Views',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'tree',
            'res_model': 'magento.storeview',
            'views': [(tree_view, 'tree'), (form_view_id, 'form')],
            'view_id': tree_view,
            'target': 'current',
            'domain': [('id', 'in', self.store_view_ids.ids)]
        }
        return action
    @staticmethod
    def show_instace(self):
        """
        Use: To prepare Magento Instance action
        :return: Magento Instance action details
        """
        view_ref = self.env['ir.model.data'].get_object_reference('odoo_magento2_ept',
                                                                  'view_magento_instance_form')
        view_id = view_ref[1] if view_ref else False
        return {
            'name': _('Magento Instance'),
            'res_model': 'magento.instance',
            'type': 'ir.actions.act_window',
            'views': [(view_id, 'form')],
            'view_mode': 'form',
            'view_id': view_id,
            'res_id': self.magento_instance_id.id,
            'target': 'current'
        }

    @staticmethod
    def show_storeview(self):
        """
        Use: To prepare Magento Store View action
        :return: Magento Store View action details
        """
        view = self.env.ref('odoo_magento2_ept.action_magento_storeview').sudo().read()[0]
        action = self.prepare_action(view, [('id','in',self.store_view_ids.ids)])
        action.update({'context': {'default_id': self.magento_instance_id.id}})
        return action


