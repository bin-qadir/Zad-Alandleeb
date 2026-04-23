from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ConstructionBOQLine(models.Model):
    _name = 'construction.boq.line'
    _description = 'BOQ Line'
    _order = 'sequence, id'

    # ── Parent ────────────────────────────────────────────────────────────────

    boq_id = fields.Many2one(
        comodel_name='construction.boq',
        string='BOQ',
        required=True,
        ondelete='cascade',
        index=True,
    )
    project_id = fields.Many2one(
        comodel_name='construction.project',
        string='Project',
        related='boq_id.project_id',
        store=True,
        readonly=True,
        index=True,
    )

    # ── Structure ─────────────────────────────────────────────────────────────

    division_id = fields.Many2one(
        comodel_name='construction.division',
        string='Division',
        ondelete='set null',
        index=True,
        domain="[('project_id', '=', project_id)]",
    )
    subdivision_id = fields.Many2one(
        comodel_name='construction.subdivision',
        string='Subdivision',
        ondelete='set null',
        index=True,
        domain="[('division_id', '=', division_id)]",
    )

    # ── Identity ──────────────────────────────────────────────────────────────

    sequence = fields.Integer(string='Seq', default=10)
    item_code = fields.Char(string='Item Code', size=40)
    description = fields.Char(string='Description', required=True)
    unit = fields.Char(string='Unit', size=20)
    quantity = fields.Float(
        string='Quantity',
        required=True,
        default=1.0,
        digits=(16, 4),
    )

    # ── Cost structure lines ──────────────────────────────────────────────────

    cost_line_ids = fields.One2many(
        comodel_name='construction.cost.line',
        inverse_name='boq_line_id',
        string='Cost Structure',
    )

    # ── Cost aggregates by type (stored, depend on cost_line_ids) ─────────────

    planned_material_cost = fields.Float(
        string='Material',
        compute='_compute_cost_breakdown',
        store=True,
        digits=(16, 4),
    )
    planned_labor_cost = fields.Float(
        string='Labor',
        compute='_compute_cost_breakdown',
        store=True,
        digits=(16, 4),
    )
    planned_subcontract_cost = fields.Float(
        string='Subcontract',
        compute='_compute_cost_breakdown',
        store=True,
        digits=(16, 4),
    )
    planned_equipment_cost = fields.Float(
        string='Equipment',
        compute='_compute_cost_breakdown',
        store=True,
        digits=(16, 4),
    )
    planned_tools_cost = fields.Float(
        string='Tools',
        compute='_compute_cost_breakdown',
        store=True,
        digits=(16, 4),
    )
    planned_overhead_cost = fields.Float(
        string='Overhead',
        compute='_compute_cost_breakdown',
        store=True,
        digits=(16, 4),
    )
    planned_other_cost = fields.Float(
        string='Other',
        compute='_compute_cost_breakdown',
        store=True,
        digits=(16, 4),
    )

    # ── Pricing / totals ──────────────────────────────────────────────────────

    total_cost = fields.Float(
        string='Total Cost',
        compute='_compute_cost_breakdown',
        store=True,
        digits=(16, 4),
        help='Sum of all cost structure lines for this BOQ line.',
    )
    cost_unit = fields.Float(
        string='Cost / Unit',
        compute='_compute_cost_breakdown',
        store=True,
        digits=(16, 4),
        help='total_cost / quantity',
    )
    sale_unit_price = fields.Float(
        string='Sale Unit Price',
        digits=(16, 4),
    )
    total_sale = fields.Float(
        string='Total Sale',
        compute='_compute_pricing',
        store=True,
        digits=(16, 4),
    )
    profit_amount = fields.Float(
        string='Profit',
        compute='_compute_pricing',
        store=True,
        digits=(16, 4),
    )
    profit_margin_percent = fields.Float(
        string='Margin %',
        compute='_compute_pricing',
        store=True,
        digits=(16, 2),
    )

    # ── Currency (pass-through from BOQ) ──────────────────────────────────────

    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        related='boq_id.currency_id',
        store=True,
        readonly=True,
    )

    # ── Computes ──────────────────────────────────────────────────────────────

    @api.depends(
        'cost_line_ids.total_cost',
        'cost_line_ids.cost_type',
        'quantity',
    )
    def _compute_cost_breakdown(self):
        for rec in self:
            totals = {
                'material': 0.0,
                'labor': 0.0,
                'subcontract': 0.0,
                'equipment': 0.0,
                'tools': 0.0,
                'overhead': 0.0,
                'other': 0.0,
            }
            for cl in rec.cost_line_ids:
                key = cl.cost_type if cl.cost_type in totals else 'other'
                totals[key] += cl.total_cost

            rec.planned_material_cost = totals['material']
            rec.planned_labor_cost = totals['labor']
            rec.planned_subcontract_cost = totals['subcontract']
            rec.planned_equipment_cost = totals['equipment']
            rec.planned_tools_cost = totals['tools']
            rec.planned_overhead_cost = totals['overhead']
            rec.planned_other_cost = totals['other']

            total = sum(totals.values())
            rec.total_cost = total
            rec.cost_unit = (total / rec.quantity) if rec.quantity else 0.0

    @api.depends('quantity', 'sale_unit_price', 'total_cost')
    def _compute_pricing(self):
        for rec in self:
            sale = rec.quantity * rec.sale_unit_price
            profit = sale - rec.total_cost
            rec.total_sale = sale
            rec.profit_amount = profit
            rec.profit_margin_percent = (
                (profit / sale * 100.0) if sale else 0.0
            )

    # ── Constraints ───────────────────────────────────────────────────────────

    @api.constrains('quantity')
    def _check_quantity(self):
        for rec in self:
            if rec.quantity <= 0:
                raise ValidationError(
                    'Quantity must be greater than zero on BOQ line "%s".'
                    % rec.description
                )

    # ── Onchange ──────────────────────────────────────────────────────────────

    @api.onchange('division_id')
    def _onchange_division_id(self):
        if self.subdivision_id and self.subdivision_id.division_id != self.division_id:
            self.subdivision_id = False
