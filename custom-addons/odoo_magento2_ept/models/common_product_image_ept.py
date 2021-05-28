# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
"""
Describes methods to store images from Magento.
"""
from odoo import models, fields


class CommonProductImageEpt(models.Model):
    """
    store image from Magento
    Upload product images to Magento
    """
    _inherit = 'common.product.image.ept'

    magento_image_ids = fields.One2many(
        "magento.product.image",
        "odoo_image_id",
        'Magento Product Images',
        help="Magento Product Images"
    )
