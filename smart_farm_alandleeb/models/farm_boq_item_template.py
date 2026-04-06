# -*- coding: utf-8 -*-
from odoo import models, fields, api
from .farm_cost_type import COSTING_SECTION_SELECTION


class FarmBoqItemTemplate(models.Model):
    """Master library of reusable BOQ item templates.
    Each template defines a complete BOQ item (header + component lines)
    that can be inserted into any farm.field section.
    """
    _name = 'farm.boq.item.template'
    _description = 'BOQ Item Template'
    _order = 'costing_section, name'
    _rec_name = 'name'

    name = fields.Char(string='Item Name', required=True, translate=True)
    code = fields.Char(string='Code')
    costing_section = fields.Selection(
        COSTING_SECTION_SELECTION,
        string='Default Section',
        required=True,
        default='civil',
    )
    description = fields.Text(string='Description')
    product_id = fields.Many2one(
        'product.product', string='Product', ondelete='set null',
    )
    unit_name = fields.Char(string='Unit')
    qty_item = fields.Float(string='Qty per Item', digits=(16, 3), default=1.0)
    profit_percent = fields.Float(string='Profit %', digits=(16, 2), default=0.0)
    active = fields.Boolean(string='Active', default=True)

    line_ids = fields.One2many(
        'farm.boq.item.template.line', 'template_id', string='Component Lines',
    )

    # ── Computed totals ───────────────────────────────────────────────────────
    material_total = fields.Float(
        string='Material Total', digits=(16, 2),
        compute='_compute_totals', store=True,
    )
    labor_total = fields.Float(
        string='Labor Total', digits=(16, 2),
        compute='_compute_totals', store=True,
    )
    overhead_total = fields.Float(
        string='Overhead Total', digits=(16, 2),
        compute='_compute_totals', store=True,
    )
    total_cost_per_item = fields.Float(
        string='Total Cost / Item', digits=(16, 2),
        compute='_compute_totals', store=True,
    )
    total_sales_price_qty_item = fields.Float(
        string='Total Sales Price (qty)', digits=(16, 2),
        compute='_compute_totals', store=True,
        help='Total sales price for qty_item units',
    )
    total_sales_price_per_item = fields.Float(
        string='Sales Price / Unit', digits=(16, 2),
        compute='_compute_totals', store=True,
        help='Sales price per single unit (total / qty_item)',
    )
    profit_amount = fields.Float(
        string='Profit Amount', digits=(16, 2),
        compute='_compute_totals', store=True,
    )

    @api.depends(
        'line_ids.material_amount',
        'line_ids.labor_amount',
        'line_ids.overhead_amount',
        'line_ids.display_type',
        'qty_item',
        'profit_percent',
    )
    def _compute_totals(self):
        for rec in self:
            normal = rec.line_ids.filtered(lambda l: not l.display_type)
            mat = sum(normal.mapped('material_amount'))
            lab = sum(normal.mapped('labor_amount'))
            ovh = sum(normal.mapped('overhead_amount'))
            cost = mat + lab + ovh
            sales_qty = cost * (1.0 + rec.profit_percent / 100.0)
            qty = rec.qty_item or 1.0
            rec.material_total = mat
            rec.labor_total = lab
            rec.overhead_total = ovh
            rec.total_cost_per_item = cost
            rec.total_sales_price_qty_item = sales_qty
            rec.total_sales_price_per_item = sales_qty / qty
            rec.profit_amount = sales_qty - cost


class FarmBoqItemTemplateLine(models.Model):
    """Component lines of a BOQ Item Template.
    Supports display_type (line_section, line_note) for grouping markers.
    """
    _name = 'farm.boq.item.template.line'
    _description = 'BOQ Item Template Line'
    _order = 'template_id, sequence, id'

    template_id = fields.Many2one(
        'farm.boq.item.template', string='Template',
        required=True, ondelete='cascade',
    )
    sequence = fields.Integer(string='Sequence', default=10)
    line_no = fields.Char(string='Line No.')

    display_type = fields.Selection([
        ('line_section', 'Section'),
        ('line_note', 'Note'),
    ], default=False, string='Display Type')

    description = fields.Char(string='Description')
    product_id = fields.Many2one(
        'product.product', string='Product', ondelete='restrict',
    )
    unit_name = fields.Char(string='Unit')
    qty_1 = fields.Float(string='Quantity', digits=(16, 3), default=1.0)
    cost_type_id = fields.Many2one(
        'farm.cost.type', string='Cost Type', ondelete='restrict',
    )
    cost_unit = fields.Float(string='Unit Cost', digits=(16, 2))

    # ── Computed amounts ──────────────────────────────────────────────────────
    total_line_cost = fields.Float(
        string='Total', digits=(16, 2),
        compute='_compute_amounts', store=True,
    )
    material_amount = fields.Float(
        string='Material', digits=(16, 2),
        compute='_compute_amounts', store=True,
    )
    labor_amount = fields.Float(
        string='Labor', digits=(16, 2),
        compute='_compute_amounts', store=True,
    )
    overhead_amount = fields.Float(
        string='Overhead', digits=(16, 2),
        compute='_compute_amounts', store=True,
    )
    cost_category = fields.Selection(
        related='cost_type_id.category',
        string='Category',
        store=False,
    )

    @api.depends('qty_1', 'cost_unit', 'cost_type_id', 'cost_type_id.category', 'display_type')
    def _compute_amounts(self):
        for rec in self:
            if rec.display_type:
                rec.total_line_cost = 0.0
                rec.material_amount = 0.0
                rec.labor_amount = 0.0
                rec.overhead_amount = 0.0
                continue
            total = rec.qty_1 * rec.cost_unit
            rec.total_line_cost = total
            category = rec.cost_type_id.category if rec.cost_type_id else False
            rec.material_amount = total if category == 'material' else 0.0
            rec.labor_amount = total if category == 'labor' else 0.0
            rec.overhead_amount = total if category == 'overhead' else 0.0
