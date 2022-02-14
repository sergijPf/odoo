from odoo import models, fields


class Website(models.Model):
    _inherit = "website"

    create_quotations_at_checkout = fields.Boolean('Create quotations at checkout',
                                                   help='''If checked, the order confirmation step of order checkout will be removed. 
                                                   Instead orders will be sent to the user as quotations.''')
