from odoo import fields, models, api


class InPostCarrier(models.Model):
    _name = 'inpost.carrier'
    _description = 'InPost Carrier'

    name = fields.Char('Carrier Name', index=True)
    code = fields.Char('Carrier Code', index=True)


class InPostService(models.Model):
    _name = 'inpost.service'
    _description = 'InPost Service'

    name = fields.Char('Service Level Name', index=True)
    code = fields.Char('Carrier Code', index=True)
    carrier_id = fields.Many2one('inpost.carrier')
    point_option = fields.Selection([('no', 'not needed'), ('optional', 'optional'), ('required', 'required'),
                                     ('optional_locker', 'Optional locker only'),
                                     ('required_locker', 'Require locker only')
                                     ],
                                    default='no', string='Pickup point option')

    show_point = fields.Boolean(compute='_compute_point')
    require_point = fields.Boolean(compute='_compute_point')

    @api.onchange('point_option')
    @api.depends('point_option')
    def _compute_point(self):
        for srv in self:
            srv.show_point = srv.point_option != 'no'
            srv.require_point = srv.point_option.startswith('required')


class InPostAdditionalService(models.Model):
    _name = 'inpost.service.additional'
    _description = 'InPost Additional Service'

    name = fields.Char('Service Level Name', index=True)
    code = fields.Char('Carrier Code', index=True)

    allowed_services = fields.Many2many('inpost.service')


class InPostPoint(models.Model):
    _name = 'inpost.point'
    _description = 'InPost Points'

    name = fields.Char('Point Name', index=True)
    url = fields.Char()
    type = fields.Char()  # list
    status = fields.Char()

    latitude = fields.Float(digits=(10, 7))
    longitude = fields.Float(digits=(10, 7))

    location_type = fields.Char()
    location_date = fields.Date()
    location_description = fields.Char()
    location_description_1 = fields.Char()
    location_description_2 = fields.Char()
    opening_hours = fields.Char()

    street = fields.Char()  # address_details -> street + building_number + flat_number
    street2 = fields.Char()
    zip = fields.Char(change_default=True)  # post_code
    city = fields.Char()  # city
    state_id = fields.Many2one("res.country.state", string='State', ondelete='restrict',
                               domain="[('country_id', '=?', country_id)]")  # province
    country_id = fields.Many2one('res.country', string='Country', ondelete='restrict')  # fixed PL

    phone_number = fields.Char()
    payment_point_descr = fields.Char()
    functions = fields.Char()  # list
    payment_available = fields.Boolean()
    payment_type = fields.Char()  # dict?
    virtual = fields.Char()
    recommended_low_interest_box_machines_list = fields.Char()

    @api.model
    def convert_api_data(self, rec):
        # noinspection PyPep8Naming
        State = self.env['res.country.state']
        poland = self.env.ref('base.pl')

        _location = rec.get('location', {})
        _address = rec.get('address_details', {})
        _low_interest = rec.get('recommended_low_interest_box_machines_list', [])
        _low_interest = ','.join(_low_interest) if _low_interest else None

        db_rec = {
            'url': rec.get('href'),
            'type': ','.join(rec.get('type', [])),
            'latitude': _location.get('latitude'),
            'longitude': _location.get('longitude'),
            'street': ' '.join([part for part in [_address.get('street'),
                                                  _address.get('building_number'),
                                                  _address.get('flat_number')] if part]),
            'zip': _address.get('post_code'),
            'city': _address.get('city'),
            'state_id': State.search([('country_id', '=', poland.id),
                                      ('code', 'like', _address.get('province', '').lower())],
                                     limit=1),
            'country_id': poland.id,
            'functions': ','.join(rec.get('functions', [])),
            'payment_type': ','.join(['{}:{}'.format(*vs) for vs in rec.get('payment_type', {}).items()]),
            'recommended_low_interest_box_machines_list': _low_interest
        }

        for field in ['name', 'status', 'location_type', 'location_date', 'location_description',
                      'location_description_1', 'location_description_2', 'opening_hours', 'phone_number',
                      'payment_point_descr', 'payment_available', 'virtual']:
            db_rec[field] = rec.get(field)

        return db_rec
