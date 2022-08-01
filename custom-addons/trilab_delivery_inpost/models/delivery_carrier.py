import re

# noinspection PyProtectedMember
from odoo import api, models, fields, _
from odoo.exceptions import UserError, ValidationError
from .inpost_client import Client, InpostError

from odoo.addons.trilab_delivery_base.models.utils import pl_zip, slugify


class DeliveryInpost(models.Model):
    _inherit = 'delivery.carrier'

    delivery_type = fields.Selection(
        selection_add=[('inpost', "Inpost")],
        ondelete={'inpost': lambda recs: recs.write({'delivery_type': 'fixed', 'fixed_price': 0})},
    )

    inpost_token = fields.Char(string='API Token', groups="base.group_system")
    inpost_organization = fields.Char(string="Organization")
    inpost_organization_name = fields.Char(string="Organization Name")

    inpost_delivery_carrier_id = fields.Many2one('inpost.carrier', string='Inpost Carrier')
    inpost_default_service_type_id = fields.Many2one(
        "inpost.service", string="Inpost Service", domain="[('carrier_id', '=', inpost_delivery_carrier_id)]"
    )
    inpost_label_file_type = fields.Selection(
        [('pdf', 'PDF'), ('zpl', 'ZPL'), ('epl', 'EPL')], default='pdf', string="Label File Type"
    )
    inpost_label_format = fields.Selection(
        [('normal', 'Normal'), ('a6', 'A6')], default='normal', string="Label Format"
    )
    inpost_send_sender = fields.Boolean('Send Odoo Sender')
    inpost_additional_services = fields.Many2many('inpost.service.additional')

    inpost_sending_method = fields.Selection(
        [
            ('parcel_locker', 'Nadanie w Paczkomacie'),
            ('pok', 'Nadanie w POK'),
            ('pop', 'Nadanie w POP'),
            ('courier_pok', 'Nadanie w POK (kurier)'),
            ('branch', 'Nadanie w Oddziale'),
            ('dispatch_order', 'Odbiór przez Kuriera'),
            ('any_point', 'Nadanie w dowolnym punkcie'),
        ],
        default='dispatch_order',
    )
    inpost_default_sending_point_id = fields.Many2one('inpost.point', string='Default Sending Point')

    @api.onchange('inpost_token')
    def _onchange_inpost_token(self):
        self.inpost_organization = self.inpost_organization_name = self.inpost_delivery_carrier_id = None

    @api.onchange('inpost_delivery_carrier_id')
    def _onchange_inpost_delivery_carrier(self):
        self.inpost_default_service_type_id = None

    @api.onchange('inpost_default_service_type_id')
    def _onchange_inpost_default_service_type(self):
        self.x_delivery_default_package_type_id = None

    @api.onchange('inpost_token')
    def _onchange_inpost_token(self):
        if self.delivery_type == 'inpost':
            self.inpost_organization = self.inpost_organization_name = None

    @api.onchange('inpost_additional_services')
    def _onchange_inpost_additional_services(self):
        for carrier in self:
            insurance = cod = False
            for service in carrier.inpost_additional_services:
                if service.code == 'cod':
                    cod = True
                elif service.code == 'insurance':
                    insurance = True

            carrier.x_delivery_cod = cod
            carrier.x_delivery_insurance = insurance

    def inpost_get_api_client(self):
        return Client(self)

    @api.depends('inpost_sending_method')
    def _inpost_delivery_can_pickup(self):
        return self.inpost_sending_method == 'dispatch_order'

    @api.onchange('inpost_sending_method')
    def _inpost_update_x_delivery_can_pickup(self):
        self.x_delivery_can_pickup = self._inpost_delivery_can_pickup()

    # noinspection PyMethodMayBeStatic
    def _inpost_delivery_can_generate_return(self):
        return True

    @api.depends('delivery_type')
    def _x_delivery_available_packaging_ids(self):
        # noinspection PyProtectedMember
        result = super(DeliveryInpost, self)._x_delivery_available_packaging_ids()

        if result and self.delivery_type == 'inpost':
            result = result.filtered_domain([('inpost_carrier_id', '=', self.inpost_delivery_carrier_id)])

        return result

    def inpost_check_picking_data(self, picking):
        self.ensure_one()

        receiver = picking.partner_id
        sender = picking.picking_type_id.warehouse_id.partner_id

        receiver.check_base_data()
        sender.check_base_data()

        if not self.inpost_token:
            raise UserError(_("The %s carrier is missing (Missing field(s) :\n API Token)", self.name))

        elif not self.inpost_organization:
            raise UserError(_("The %s carrier is missing (Missing field(s) :\n Organization)", self.name))

        if not self.inpost_delivery_carrier_id:
            raise UserError(_("The %s carrier is missing (Missing field(s) :\n InPost Carrier)", self.name))

        if not self.x_delivery_default_package_type_id:
            raise UserError(_("The %s carrier is missing (Missing field(s) :\n Default Product Packaging)", self.name))

        # check required value for picking
        if (
            self.x_delivery_default_package_type_id.shipper_package_code == 'inpost_locker'
            and not picking.inpost_locker_code
        ):
            raise UserError(_('Selected shipping via Inpost Locker, but destination locker is missing.'))

        phone = self.inpost_cleanup_phone(receiver.mobile or receiver.phone)

        if not phone:
            raise UserError(_('Recipient phone number is missing or invalid!'))

        if picking.has_packages:
            for package in picking.package_ids:
                if not (package.package_type_id and package.package_type_id.shipper_package_code):
                    raise ValidationError(
                        _('Quant package does not specify packaging or packaging is misconfigured ' 'for Inpost')
                    )

                if (
                    self.x_delivery_first_nonzero(
                        package.shipping_weight,
                        package.weight,
                        package.package_type_id.max_weight,
                        self.x_delivery_default_package_type_id.max_weight,
                    )
                    is None
                ):
                    raise ValidationError(
                        _(
                            'Package %s shipping weight and default package weight are both equal to zero. '
                            'Make sure that one of the values will resolve to valid weight.',
                            package,
                        )
                    )

        else:
            packaging = picking.x_delivery_package_type_id or self.x_delivery_default_package_type_id
            if not (packaging and packaging.package_carrier_type):
                raise ValidationError(_('Default packaging not selected or misconfigured for Inpost'))

            if self.x_delivery_first_nonzero(picking.shipping_weight, picking.weight, packaging.max_weight) is None:
                raise ValidationError(
                    _(
                        'Package shipping weight and default package weight are both equal to zero. '
                        'Make sure that one of the values will resolve to valid weight.'
                    )
                )

    def action_get_organizations(self):
        """
        Return the list of organization configured by the customer on its inpost account.
        """
        action = None

        inpost_api = self.inpost_get_api_client()

        try:
            response = inpost_api.get_organizations()

            if response:
                action = self.env.ref('trilab_delivery_inpost.act_delivery_inpost_organization').read()[0]
                action['context'] = {
                    'organizations': response,
                    'default_organization': int(self.inpost_organization)
                    if self.inpost_organization
                    else response[0][0],
                    'default_delivery_carrier_id': self.id,
                }
        except InpostError as e:
            raise UserError(str(e))

        return action

    def action_get_points(self):
        inpost_api = self.inpost_get_api_client()
        # noinspection PyPep8Naming
        InpostPoint = self.env['inpost.point']

        page = 1
        next_page = True
        total_count = 0

        # remove all inpost points
        InpostPoint.search([]).unlink()

        while next_page:
            response = inpost_api.get_points(page, page_size=100)
            InpostPoint.create([InpostPoint.convert_api_data(rec) for rec in response['items']])
            total_count += len(response['items'])
            page += 1
            if page > response.get('total_pages'):
                next_page = False

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Imported Inpost pickup points and lockers'),
                'message': _('Import finished, added %s point(s)', total_count),
            },
        }

    # noinspection PyMethodMayBeStatic
    def inpost_cleanup_phone(self, phone_number):
        if isinstance(phone_number, str):
            return re.sub(r'\D', '', phone_number)[-9:]
        else:
            return ''

    def inpost_get_partner_data(self, partner):
        names = partner.name.split(' ', 1)

        street_address = list(filter(None, re.split(r'\s+', ' '.join(filter(None, [partner.street, partner.street2])))))

        address = {
            'address': {
                'street': ' '.join(street_address[:-1]),
                'building_number': street_address[-1],
                'city': partner.city,
                'post_code': pl_zip(partner.zip),
                'country_code': partner.country_id.code or self.env.ref('base.pl').code,
            },
            'phone': self.inpost_cleanup_phone(partner.mobile or partner.phone),
            'first_name': names[0],
            'last_name': names[1] if len(names) > 1 else names[0],
        }

        if partner.company_name:
            address['company_name'] = partner.company_name

        if partner.email:
            address['email'] = partner.email

        return address

    def _inpost_serialize_to_mm(self, value):
        mm = self.env.ref('uom.product_uom_millimeter')
        meter = self.env.ref('uom.product_uom_meter')
        return int(meter._compute_quantity(value, to_unit=mm))

    def inpost_get_parcel_data(self, picking, parcel=None):

        if parcel:
            packaging = (
                parcel.packagin_id or picking.x_delivery_package_type_id or self.x_delivery_default_package_type_id
            )
            weight = self.x_delivery_first_nonzero(parcel.shipping_weight, parcel.weight, packaging.max_weight)
        else:
            packaging = picking.x_delivery_package_type_id or self.x_delivery_default_package_type_id
            weight = self.x_delivery_first_nonzero(picking.shipping_weight, picking.weight, packaging.max_weight)

        parcel = {
            'id': (parcel and parcel.name) or picking.name,
            'dimensions': {
                'height': self._inpost_serialize_to_mm(
                    self.x_normalize_length(packaging.height, packaging.x_length_uom)
                ),
                'length': self._inpost_serialize_to_mm(
                    self.x_normalize_length(packaging.packaging_length, packaging.x_length_uom)
                ),
                'width': self._inpost_serialize_to_mm(self.x_normalize_length(packaging.width, packaging.x_length_uom)),
                'unit': 'mm',
            },
            # 'template': package.shipper_package_code,
            'weight': {'amount': self.x_normalize_weight(weight), 'unit': 'kg'},
            # 'is_non_standard': False
        }

        return parcel

    def inpost_get_package_data(self, picking):
        picking.ensure_one()

        parcels = []

        move_lines_with_package = picking.move_line_ids.filtered(lambda ml: ml.result_package_id)
        move_lines_without_package = picking.move_line_ids - move_lines_with_package

        if move_lines_without_package:
            parcels.append(self.inpost_get_parcel_data(picking))

        if picking.has_packages:
            # Generate an InPost shipment for each package in picking.
            for package in picking.package_ids:
                parcels.append(self.inpost_get_parcel_data(picking, parcel=package))

        return parcels

    def inpost_get_shipment_data(self, picking):
        order_payload = {
            'receiver': self.inpost_get_partner_data(picking.partner_id),
            'service': self.inpost_default_service_type_id.code,
            'parcels': self.inpost_get_package_data(picking),
            'custom_attributes': {
                # 'target_point': '',
                # 'dropoff_point': '',
                'sending_method': self.inpost_sending_method
            },
            'reference': picking.origin,
            # 'is_return': false,
            'additional_services': self.inpost_additional_services.mapped('code'),
            # 'external_customer_id': '',
            # 'only_choice_of_offer': false,
            'comments': picking.note or '',
        }

        if picking.inpost_locker_code:
            order_payload['custom_attributes']['target_point'] = picking.inpost_locker_code

        point_id = picking.inpost_sending_point_id or self.inpost_default_sending_point_id
        if self.inpost_sending_method != 'dispatch_order' and point_id:
            order_payload['custom_attributes']['dropoff_point'] = point_id.name

        if self.inpost_send_sender:
            order_payload['sender'] = self.inpost_get_partner_data(picking.picking_type_id.warehouse_id.partner_id)

        if self.x_delivery_cod:
            order_payload['cod'] = {
                'amount': picking.sale_id.amount_total,
                'currency': picking.partner_id.country_id.currency_id.name or self.env.company.currency_id.name,
            }

        order_payload['insurance'] = {
            'amount': max(self.x_delivery_minimum_insurance_value, picking.sale_id.amount_total),
            'currency': picking.partner_id.country_id.currency_id.name or self.env.company.currency_id.name,
        }

        if self.x_delivery_mpk:
            order_payload['mpk'] = self.x_delivery_mpk

        return order_payload

    def inpost_get_labels(self, pickings):
        for picking in pickings:
            if not picking.carrier_id or picking.carrier_id.delivery_type != 'inpost':
                # quietly ignore non-inpost pickings
                continue

            if picking.inpost_shipment_status != 'confirmed':
                raise ValidationError(
                    _(
                        'Can not fetch label for picking %s, invalid shipment status: %s',
                        picking.name,
                        picking.inpost_shipment_status,
                    )
                )

            try:
                response = self.inpost_get_api_client().get_labels(
                    [picking.inpost_shipment_id], self.inpost_label_file_type, self.inpost_label_format
                )

                # noinspection PyUnresolvedReferences
                picking.x_delivery_label_id = self.env['ir.attachment'].create(
                    {
                        'name': f'INPOST_Label_{slugify(picking.name)}.pdf',
                        'res_model': 'stock.picking',
                        'res_id': picking.id,
                        'datas': response.get('data', ''),
                    }
                )

            except InpostError as e:
                raise ValidationError(str(e))

    def inpost_send_shipping(self, pickings):
        tracking_numbers = []
        inpost_api = self.inpost_get_api_client()

        # verify data for all shipments
        for picking in pickings:
            if not picking.x_delivery_pickup_state:
                self.inpost_check_picking_data(picking)

        for picking in pickings:
            if not picking.x_delivery_pickup_id or picking.inpost_shipment_status != 'confirmed':
                try:
                    if picking.inpost_shipment_id and picking.inpost_shipment_status != 'confirmed':
                        # already registered in Inpost, try to get tracking number
                        result = inpost_api.get_shipping_info(picking.inpost_shipment_id)
                    else:
                        result = inpost_api.send_shipping(self.inpost_get_shipment_data(picking))
                        picking.inpost_shipment_id = result['id']

                        # get result again, it may change from created to order_selected
                        result = inpost_api.get_shipping_info(picking.inpost_shipment_id)

                    picking.inpost_shipment_status = result['status']
                    picking.carrier_tracking_ref = result['tracking_number']

                    if picking.inpost_shipment_status == 'confirmed':
                        try:
                            self.inpost_get_labels(picking)
                        except ValidationError:
                            # it may happen, that package is not yet paid for, so no label can be downloaded
                            pass

                except InpostError as e:
                    raise UserError(str(e))

            tracking_numbers.append(
                {
                    'exact_price': self.x_rate_shipment(picking.sale_id).get('price', 0.0),
                    'tracking_number': picking.carrier_tracking_ref,
                }
            )

        return tracking_numbers

    def inpost_get_tracking_link(self, picking):
        self.ensure_one()
        return self.inpost_get_api_client().get_tracking_link(picking.carrier_tracking_ref)

    def inpost_cancel_shipment(self, picking):
        if picking.inpost_shipment_id:
            self.inpost_get_api_client().cancel_shipment(picking.inpost_shipment_id)
            picking.message_post(body=_(u'Shipment N° %s has been cancelled', picking.carrier_tracking_ref))
            picking.write({'carrier_tracking_ref': '', 'inpost_shipment_id': ''})
        else:
            raise UserError(_('Can' 't cancel picking without Inpost shipment data!'))

    # noinspection PyUnusedLocal
    def inpost_get_return_label(self, picking, tracking_number=None, origin_date=None):
        picking.ensure_one()

        if not picking.carrier_id or picking.carrier_id.delivery_type != 'inpost':
            raise UserError(_('No Inpost shipping'))

        if not picking.inpost_shipment_id:
            raise UserError(_('Original shipment not sent via Inpost'))

        try:
            response = self.inpost_get_api_client().get_return_labels(
                [picking.inpost_shipment_id], self.inpost_label_file_type
            )

            # noinspection PyUnresolvedReferences
            picking.x_delivery_label_id = self.env['ir.attachment'].create(
                {
                    'name': f'INPOST_Label_{slugify(picking.name)}.pdf',
                    'res_model': 'stock.picking',
                    'res_id': picking.id,
                    'datas': response.get('data', ''),
                }
            )

        except InpostError as e:
            raise ValidationError(str(e))
