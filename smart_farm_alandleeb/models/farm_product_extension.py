# -*- coding: utf-8 -*-
from odoo import models, fields


class ProductTemplate(models.Model):
    """Extend product.template with a default Cost Type for Smart Farm costing lines."""
    _inherit = 'product.template'

    cost_type_id = fields.Many2one(
        'farm.cost.type',
        string='Default Cost Type',
        ondelete='set null',
        help='Default cost type used when this product is added to a farm costing line.',
    )


class ProductProduct(models.Model):
    """Expose cost_type_id on product.product via related field."""
    _inherit = 'product.product'

    cost_type_id = fields.Many2one(
        related='product_tmpl_id.cost_type_id',
        string='Default Cost Type',
        store=False,
    )
