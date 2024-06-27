# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    product_image = fields.Binary(string="Product Image", related="sale_order_template_id.product_image")
    room_concept_pdf = fields.Binary(string="Room Concept PDF")
