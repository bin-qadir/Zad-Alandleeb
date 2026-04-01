# -*- coding: utf-8 -*-
from odoo import fields, models


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    x_boq_line_id = fields.Many2one(
        'task.boq.line',
        string='BOQ Line',
        ondelete='set null',
        index=True,
    )


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    x_boq_line_id = fields.Many2one(
        'task.boq.line',
        string='BOQ Line',
        ondelete='set null',
        index=True,
    )
