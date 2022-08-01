import base64
from datetime import date

# noinspection PyProtectedMember
from odoo import api, models, fields, _
from odoo.exceptions import ValidationError, UserError


class DeliveryPickup(models.Model):
    _name = 'trilab.delivery.pickup'
    _description = 'Delivery Pickup'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    carrier_id = fields.Many2one('delivery.carrier', string='Carrier', check_company=True)

    delivery_type = fields.Selection(related='carrier_id.delivery_type', string='Delivery Type')

    company_id = fields.Many2one('res.company', string='Company', related='carrier_id.company_id', store=True,
                                 readonly=True)

    pickup_date = fields.Date(required=True, tracking=True)
    pickup_hour_from = fields.Integer(required=True, tracking=True)
    pickup_hour_to = fields.Integer(required=True, tracking=True)
    picking_ids = fields.One2many('stock.picking', 'x_delivery_pickup_id', copy=False)
    protocol_id = fields.Many2one('ir.attachment', readonly=True, copy=False)
    warehouse_id = fields.Many2one('stock.warehouse', required=True)

    state = fields.Selection([('draft', 'Draft'),
                              ('created', 'Created'),
                              ('scheduled', 'Scheduled')],
                             required=True, default='draft', copy=False, tracking=True)

    comments = fields.Text(string='Courier Instructions')

    show_create_protocol_btn = fields.Boolean(compute='compute_show_create_protocol')
    show_schedule_pickup_btn = fields.Boolean(compute='compute_show_schedule_protocol')
    show_cancel_pickup_btn = fields.Boolean(compute='compute_show_cancel_pickup')

    # noinspection PyShadowingNames
    @api.model
    def default_get(self, fields):
        res = super(DeliveryPickup, self).default_get(fields)
        res['pickup_date'] = date.today()
        res['pickup_hour_from'] = 8
        res['pickup_hour_to'] = 16
        return res

    def name_get(self):
        return [(record.id, f'{record.carrier_id.name} {record.pickup_date} ({record.id})') for record in self]

    @api.onchange('carrier_id', 'warehouse_id')
    def _onchange_carrier_id(self):
        self.picking_ids = False

    @api.constrains('pickup_hour_from', 'pickup_hour_to')
    def constrains_hours(self):
        for pickup in self:
            for hour in [pickup.pickup_hour_from, pickup.pickup_hour_to]:
                if hour < 0 or hour > 23:
                    raise ValidationError(_('Valid hour from 0 to 23'))

            if pickup.pickup_hour_from > pickup.pickup_hour_to:
                raise ValidationError(_('Wrong hour range'))

    def download_protocol(self):
        if self.protocol_id:
            return {
                'type': 'ir.actions.act_url',
                'url': f'/web/content/ir.attachment/{ self.protocol_id.id }/datas?download=True',
                'target': 'self',
            }

    def create_protocol_file(self, data, filename=None):
        return self.env['ir.attachment'].create({
            'name': filename or f'Pickup_Protocol_{self.id}.pdf',
            'res_model': 'trilab.delivery.pickup',
            'res_id': self.id,
            'datas': base64.b64encode(data)
        })

    @api.depends('state')
    def compute_show_create_protocol(self):
        for pickup in self:
            if hasattr(pickup, f'{pickup.delivery_type}_show_create_protocol'):
                pickup.show_create_protocol_btn = getattr(pickup, f'{pickup.delivery_type}_show_create_protocol')()
            else:
                pickup.show_create_protocol_btn = self.state == 'draft'

    def create_protocol_validation(self):
        if not self.picking_ids:
            raise ValidationError(_('Select some Stock Pickings first'))

        if hasattr(self, f'{self.delivery_type}_create_protocol_validation'):
            getattr(self, f'{self.delivery_type}_create_protocol_validation')()

    def create_protocol(self):
        self.ensure_one()

        self.create_protocol_validation()

        if hasattr(self, f'{self.delivery_type}_create_protocol'):
            data = getattr(self, f'{self.delivery_type}_create_protocol')()
        else:
            report = self.env.ref('trilab_delivery_base.delivery_pickup_protocol')
            data = {
                'protocol_id': self.create_protocol_file(report.sudo()._render_qweb_pdf([self.id])[0])
            }
        self.write({
            'state': 'created',
            **data
        })

    @api.depends('state')
    def compute_show_schedule_protocol(self):
        for pickup in self:
            if hasattr(pickup, f'{pickup.delivery_type}_show_schedule_pickup'):
                self.show_schedule_pickup_btn = getattr(pickup, f'{pickup.delivery_type}_show_schedule_pickup')()
            else:
                self.show_schedule_pickup_btn = pickup.state in ['draft', 'created']

    def schedule_pickup_validation(self):
        if self.pickup_date < fields.Date.today():
            raise ValidationError(_('Pickup date is in the past.'))

        if hasattr(self, f'{self.delivery_type}_schedule_pickup_validation'):
            getattr(self, f'{self.delivery_type}_schedule_pickup_validation')()

    # noinspection PyUnresolvedReferences
    def schedule_pickup(self):
        self.ensure_one()

        self.schedule_pickup_validation()

        self.write({
            'state': 'scheduled',
            **getattr(self, f'{self.delivery_type}_schedule_pickup', lambda: {})()
        })

    def compute_show_cancel_pickup(self):
        for pickup in self:
            if hasattr(pickup, f'{pickup.delivery_type}_show_cancel_pickup'):
                pickup.show_cancel_pickup_btn = getattr(pickup, f'{pickup.delivery_type}_show_cancel_pickup')()
            else:
                pickup.show_cancel_pickup_btn = pickup.state in ['scheduled', 'created']

    def cancel_pickup_validation(self):
        if self.state not in ('created', 'scheduled'):
            raise UserError(_("Can't cancel pickup in this state"))

        if hasattr(self, f'{self.delivery_type}_cancel_pickup_validation'):
            getattr(self, f'{self.delivery_type}_cancel_pickup_validation')()

    def cancel_pickup(self):
        self.cancel_pickup_validation()

        if self.protocol_id:
            self.protocol_id.unlink()

        self.write({
            'state': 'draft',
            'protocol_id': False,
            **getattr(self, f'{self.delivery_type}_cancel_pickup', lambda: {})()
        })
