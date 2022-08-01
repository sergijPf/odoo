import base64
import io
from zipfile import ZipFile

# noinspection PyProtectedMember
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class StockPicking(models.Model):

    _inherit = 'stock.picking'

    x_delivery_label_id = fields.Many2one('ir.attachment', string='Label', ondelete='set null', copy=False)
    x_delivery_pickup_id = fields.Many2one('trilab.delivery.pickup', ondelete='set null', copy=False)
    x_delivery_pickup_state = fields.Selection(related='x_delivery_pickup_id.state', store=True, readonly=True)
    x_delivery_package_type_id = fields.Many2one('stock.package.type', 'Package Type', index=True, check_company=True)
    x_delivery_can_show_cancel_btn = fields.Boolean(string='Delivery Can Show Cancel Button',
                                                    compute='_x_delivery_can_show_cancel_btn')
    x_delivery_cmr_code = fields.Char('CMR Code')

    warehouse_id = fields.Many2one('stock.warehouse', related='picking_type_id.warehouse_id')

    @api.onchange('carrier_id')
    def _x_delivery_onchange_carrier_id(self):
        for picking in self:
            picking.x_delivery_package_type_id = picking.carrier_id.x_delivery_default_package_type_id

    @api.depends('carrier_id')
    def _x_delivery_can_show_cancel_btn(self):
        for picking in self:
            result = (picking.carrier_tracking_ref
                      and picking.delivery_type not in ['fixed', 'base_on_rule', False]
                      and hasattr(picking.carrier_id, f'{picking.delivery_type}_cancel_shipment'))

            if hasattr(picking, f'{picking.delivery_type}_can_show_cancel_btn'):
                result = getattr(picking, f'{picking.delivery_type}_can_show_cancel_btn')(result)

            picking.x_delivery_can_show_cancel_btn = result

    def x_delivery_pickup_btn(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Delivery Pickup'),
            'res_model': 'trilab.delivery.pickup',
            'view_mode': 'form',
            'res_id': self.x_delivery_pickup_id.id,
        }

    def x_delivery_download_label(self):
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/ir.attachment/{ self.x_delivery_label_id.id }/datas?download=True',
            'target': 'self',
        }

    def x_get_content_description(self):
        moves = self.move_line_ids.filtered(lambda m: m.product_id and not m.result_package_id)
        desc = ', '.join(f'{move.product_id.name} [{move.qty_done} {move.product_uom_id.name}]' for move in moves)
        return desc or self.name

    def x_get_delivery_labels(self):
        # generate missing labels, but group calls by carrier
        grouped = {}
        for picking in self.filtered_domain([('x_delivery_label_id', '=', False)]):
            grouped.setdefault(picking.carrier_id.delivery_type,
                               {'carrier': picking.carrier_id,
                                'pickings': self.env['stock.picking']})
            grouped[picking.carrier_id.delivery_type]['pickings'] |= picking

        for carrier_type, group in grouped.items():
            if hasattr(group['carrier'], f'{carrier_type}_get_labels'):
                getattr(group['carrier'], f'{carrier_type}_get_labels')(group['pickings'])

        labels = self.filtered_domain([('x_delivery_label_id', '!=', False)]).mapped('x_delivery_label_id')

        if labels:
            zip_data = io.BytesIO()

            with ZipFile(zip_data, 'w') as _zip:
                for label in labels:
                    _zip.writestr(label.name, base64.decodebytes(label.datas))

            zip_data.seek(0)

            download = self.env['trilab.delivery.label'].create({
                'file_name': 'delivery_labels.zip',
                'data': base64.encodebytes(zip_data.read())
            })

            return {
                'type': 'ir.actions.act_window',
                'name': _('Download File'),
                'view_mode': 'form',
                'res_model': 'trilab.delivery.label',
                'res_id': download.id,
                'target': 'new',
                'view_id': self.env.ref('trilab_delivery_base.label_save_done').id,
            }

        else:
            raise UserError('No labels found')
