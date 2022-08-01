# noinspection PyProtectedMember
from odoo import models, fields, _
from odoo.exceptions import UserError
from .inpost_client import InpostError


class DeliveryPickup(models.Model):
    _inherit = 'trilab.delivery.pickup'

    inpost_order_number = fields.Char(tracking=True, readonly=1)

    def inpost_show_create_protocol(self):
        return self.state == 'created'

    def inpost_create_protocol_validation(self):
        if not all(p.inpost_shipment_id for p in self.picking_ids):
            raise UserError(_('Some pickings are not registered with Inpost'))

        if not all(p.inpost_shipment_status == 'confirmed' for p in self.picking_ids):
            raise UserError(_('Some of prepared packages are not confirmed with Inpost'))

    def inpost_schedule_pickup_validation(self):
        self.inpost_create_protocol_validation()

    def inpost_create_protocol(self):
        self.ensure_one()

        if not self.inpost_order_number:
            return {}

        try:
            response = self.carrier_id.inpost_get_api_client().printout_order(self.inpost_order_number)

            return {'protocol_id': self.create_protocol_file(response, filename=f'Inpost_Protocol_{self.id}.pdf')}

        except InpostError as e:
            raise UserError(str(e))

    def inpost_show_schedule_pickup(self):
        return self.state == 'draft'

    # noinspection PyUnresolvedReferences
    def inpost_schedule_pickup(self):
        sender = self.warehouse_id.partner_id
        parcels = self.picking_ids.mapped('inpost_shipment_id')

        parcel_data = {
            # 'dispatch_point_id': 0,
            'shipments': parcels,
            'address': self.carrier_id.inpost_get_partner_data(sender)['address'],
            'name': sender.commercial_company_name or sender.name,
            'phone': self.carrier_id.inpost_cleanup_phone(sender.phone or sender.mobile),
        }

        if self.comments:
            parcel_data['comment'] = self.comments

        # if dispatch_point:
        #     parcel_data['dispatch_point_id'] = dispatch_point

        try:
            response = self.carrier_id.inpost_get_api_client().dispatch_orders(parcel_data)
        except InpostError as e:
            raise UserError(str(e))

        return {'inpost_order_number': response['id'], 'state': 'created'}

    def inpost_show_cancel_pickup(self):
        return bool(self.inpost_order_number)

    def inpost_cancel_pickup(self):
        try:
            if self.inpost_order_number:
                self.carrier_id.inpost_get_api_client().cancel_order(self.inpost_order_number)

            return {'inpost_order_number': False}

        except InpostError as e:
            raise UserError(str(e))
