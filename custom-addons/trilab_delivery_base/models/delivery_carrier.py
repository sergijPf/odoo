from odoo import models, fields, api, exceptions, _
from odoo.tools import float_is_zero


class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    x_delivery_can_pickup = fields.Boolean(
        'Allow Delivery Pickup', compute='_x_delivery_can_pickup', store=True, readonly=False
    )
    # implemented globally, but enabling this flag depends on carrier implementation
    x_delivery_cod = fields.Boolean('X Collect on Delivery', default=False)
    x_delivery_insurance = fields.Boolean('Shipment Insurance', default=False)

    # DEFAULT VALUES used if package size is not specified or for bulk packages
    x_delivery_available_packaging_ids = fields.Many2many(
        'stock.package.type', readonly=True, compute='_x_delivery_available_packaging_ids'
    )
    x_delivery_default_package_type_id = fields.Many2one(
        'stock.package.type', string='Default Package', domain="[('id', 'in', x_delivery_available_packaging_ids)]"
    )

    x_delivery_mpk = fields.Char(string='Delivery MPK')

    x_pricing = fields.Selection(
        selection=[('fixed', 'Fixed pice'), ('grid', 'Price grid')], default='fixed', string='Pricing method'
    )

    x_delivery_currency_id = fields.Many2one(related='company_id.currency_id')
    x_delivery_minimum_insurance_value = fields.Monetary(
        string='Minimal Insurance Value', currency_field='x_delivery_currency_id', default=0.0
    )

    @api.depends('delivery_type')
    def _x_delivery_available_packaging_ids(self):
        self.x_delivery_available_packaging_ids = self.env['stock.package.type'].search(
            [('package_carrier_type', '=', self.delivery_type)]
        )

    def _compute_can_generate_return(self):
        # noinspection PyProtectedMember
        super(DeliveryCarrier, self)._compute_can_generate_return()

        for carrier in self:
            method = f'_{carrier.delivery_type}_delivery_can_generate_return'
            if not hasattr(carrier, method):
                continue

            carrier.can_generate_return = getattr(carrier, method, lambda: False)()

    @api.depends('delivery_type')
    @api.onchange('delivery_type')
    def _x_delivery_can_pickup(self):
        for carrier in self:
            carrier.x_delivery_can_pickup = getattr(
                carrier, f'_{carrier.delivery_type}_delivery_can_pickup', lambda: False
            )()

    def x_delivery_add_to_pickup(self, picking):
        picking.ensure_one()

        if not self.x_delivery_can_pickup:
            return

        if picking.x_delivery_pickup_id:
            return

        pickup = self.env['trilab.delivery.pickup'].search(
            [('state', '=', 'draft'), ('carrier_id', '=', self.id), ('warehouse_id', '=', picking.warehouse_id.id)],
            limit=1,
            order='create_date desc',
        )

        if not pickup:
            pickup = self.env['trilab.delivery.pickup'].create(
                {'carrier_id': self.id, 'warehouse_id': picking.warehouse_id.id}
            )

        picking.x_delivery_pickup_id = pickup.id

    def send_shipping(self, pickings):
        response = super(DeliveryCarrier, self).send_shipping(pickings)

        for picking in pickings:
            self.x_delivery_add_to_pickup(picking)

        return response

    # noinspection PyMethodMayBeStatic
    def x_delivery_first_nonzero(self, *values, precision_digits=3):
        for value in values:
            if value and not float_is_zero(value, precision_digits=precision_digits):
                return value
        return None

    def install_more_provider(self):
        data = super(DeliveryCarrier, self).install_more_provider()
        data['domain'] = [
            '|',
            ('name', '=like', 'delivery_%'),
            ('name', '=like', 'trilab_delivery_%'),
            ('name', '!=', 'delivery_barcode'),
        ]
        return data

    def cancel_shipment(self, pickings):
        result = super(DeliveryCarrier, self).cancel_shipment(pickings)

        for picking in pickings:
            if picking.x_delivery_pickup_id:
                picking.x_delivery_pickup_id = False
            if picking.x_delivery_label_id:
                picking.x_delivery_label_id.unlink()

        return result

    def x_normalize_weight(self, weight, weight_uom_id=None) -> float:
        # normalize to kg
        if not weight_uom_id:
            weight_uom_id = self.env['product.template']._get_weight_uom_id_from_ir_config_parameter()

        weight_kg = self.env.ref('uom.product_uom_kgm')
        return weight_uom_id._compute_quantity(weight, to_unit=weight_kg)

    def x_normalize_length(self, length, from_uom_id=None) -> float:
        # normalize to meters
        if not from_uom_id:
            from_uom_id = self.env['product.template']._get_length_uom_id_from_ir_config_parameter()
        length_m = self.env.ref('uom.product_uom_meter')
        return from_uom_id._compute_quantity(length, to_unit=length_m)

    def x_rate_shipment(self, order):
        if self.x_pricing == 'fixed':
            return self.fixed_rate_shipment(order)
        elif self.x_pricing == 'grid':
            return self.base_on_rule_rate_shipment(order)
        else:
            raise exceptions.UserError(f'Unknown pricing option "{self.x_pricing}"')

    def rate_shipment(self, order):
        self.ensure_one()

        if hasattr(self, f'{self.delivery_type}_rate_shipment'):
            return super().rate_shipment(order)
        else:
            res = self.x_rate_shipment(order)
            res['price'] = float(res['price']) * (1.0 + (self.margin / 100.0))
            res['carrier_price'] = res['price']
            if res['success'] and self.free_over and order._compute_amount_total_without_delivery() >= self.amount:
                res['warning_message'] = _('The shipping is free since the order amount exceeds %.2f.', self.amount)
                res['price'] = 0.0
            return res
