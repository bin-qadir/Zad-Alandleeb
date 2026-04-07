# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from .farm_cost_type import COSTING_SECTION_SELECTION

LINE_TYPE_SELECTION = [
    ('division', 'Works Division'),
    ('subdivision', 'Sub-division Works'),
    ('boq_item', 'B.O.Q Item Work'),
]


class ProjectCostAnalysisLine(models.Model):
    """Project Costing Analysis Line.

    Three-level hierarchy:
      division   (01, 02, …)        ← Works Division
      subdivision (02.01, 02.02, …)  ← Sub-division Works
      boq_item   (02.01.01, …)       ← B.O.Q Item Work

    Division and subdivision lines roll up their children's totals.
    B.O.Q item lines fill from a selected B.O.Q Item Template × quantity.
    """
    _name = 'project.cost.analysis.line'
    _description = 'Project Costing Analysis Line'
    _order = 'project_id, sequence, id'
    _parent_name = 'parent_id'

    # ── Core relations ────────────────────────────────────────────────────────
    project_id = fields.Many2one(
        'project.project', string='Project',
        required=True, ondelete='cascade', index=True,
    )
    parent_id = fields.Many2one(
        'project.cost.analysis.line', string='Parent Line',
        ondelete='cascade', index=True,
        domain="[('project_id', '=', project_id), ('line_type', 'in', ['division', 'subdivision'])]",
    )
    child_ids = fields.One2many(
        'project.cost.analysis.line', 'parent_id', string='Child Lines',
    )

    # ── Line type & numbering ─────────────────────────────────────────────────
    line_type = fields.Selection(
        LINE_TYPE_SELECTION, string='Line Type',
        required=True, default='division',
    )
    sequence = fields.Integer(string='Sequence', default=10)
    sequence_no = fields.Char(
        string='No.', compute='_compute_sequence_no', store=True,
        help='Auto-generated hierarchical position number (01, 02.01, 02.01.03).',
    )
    name = fields.Char(string='Description', required=True)
    active = fields.Boolean(string='Active', default=True)

    # ── Classification ────────────────────────────────────────────────────────
    costing_section = fields.Selection(
        COSTING_SECTION_SELECTION, string='Works Division',
    )
    work_type_id = fields.Many2one(
        'farm.boq.work.type', string='Sub-division Works',
        ondelete='set null',
        domain="[('costing_section', '=', costing_section), ('active', '=', True)]",
    )
    boq_item_template_id = fields.Many2one(
        'farm.boq.item.template', string='B.O.Q Item Template',
        ondelete='set null',
        domain="[('active', '=', True)]",
    )

    # ── BOQ item data ─────────────────────────────────────────────────────────
    product_id = fields.Many2one(
        'product.product', string='Product', ondelete='restrict',
    )
    uom_name = fields.Char(string='Unit of Measure')
    quantity = fields.Float(string='Quantity', digits=(16, 3), default=1.0)

    # ── Cost totals (stored computed) ─────────────────────────────────────────
    material_total = fields.Float(
        string='Total Material Cost', digits=(16, 2),
        compute='_compute_totals', store=True,
    )
    labor_total = fields.Float(
        string='Total Labor Cost', digits=(16, 2),
        compute='_compute_totals', store=True,
    )
    overhead_total = fields.Float(
        string='Total Overhead Cost', digits=(16, 2),
        compute='_compute_totals', store=True,
    )
    total_cost = fields.Float(
        string='Total Cost', digits=(16, 2),
        compute='_compute_totals', store=True,
    )

    # ── Profitability ─────────────────────────────────────────────────────────
    suggested_profit_percent = fields.Float(
        string='Suggested Profit %', digits=(16, 2),
    )
    profit_amount = fields.Float(
        string='Profit Amount', digits=(16, 2),
        compute='_compute_totals', store=True,
    )
    sale_total = fields.Float(
        string='Total Sale Price', digits=(16, 2),
        compute='_compute_totals', store=True,
    )

    # =========================================================================
    # SEQUENCE NUMBER — hierarchical auto-numbering (01, 02.01, 02.01.03)
    # =========================================================================
    @api.depends(
        'sequence', 'parent_id', 'parent_id.sequence_no',
        'project_id.analysis_line_ids.sequence',
        'project_id.analysis_line_ids.parent_id',
    )
    def _compute_sequence_no(self):
        for rec in self:
            rec.sequence_no = rec._get_position_no()

    def _get_position_no(self):
        """Return hierarchical position string for this line."""
        if not self.parent_id:
            siblings = self.project_id.analysis_line_ids.filtered(
                lambda l: not l.parent_id
            ).sorted(lambda l: (l.sequence, l.id))
        else:
            siblings = self.parent_id.child_ids.sorted(lambda l: (l.sequence, l.id))

        ids = list(siblings.ids)
        if self.id and self.id in ids:
            idx = ids.index(self.id) + 1
        else:
            idx = len(ids) + 1  # new unsaved record: place at end

        parent_no = self.parent_id.sequence_no if self.parent_id else ''
        return f'{parent_no}.{idx:02d}' if parent_no else f'{idx:02d}'

    # =========================================================================
    # TOTALS — rollup for division/subdivision; template×qty for boq_item
    # =========================================================================
    @api.depends(
        'line_type',
        'child_ids.material_total',
        'child_ids.labor_total',
        'child_ids.overhead_total',
        'child_ids.total_cost',
        'child_ids.profit_amount',
        'child_ids.sale_total',
        'boq_item_template_id',
        'boq_item_template_id.material_total',
        'boq_item_template_id.labor_total',
        'boq_item_template_id.overhead_total',
        'quantity',
        'suggested_profit_percent',
    )
    def _compute_totals(self):
        for rec in self:
            if rec.line_type in ('division', 'subdivision'):
                # Rollup from children
                rec.material_total = sum(rec.child_ids.mapped('material_total'))
                rec.labor_total = sum(rec.child_ids.mapped('labor_total'))
                rec.overhead_total = sum(rec.child_ids.mapped('overhead_total'))
                rec.total_cost = sum(rec.child_ids.mapped('total_cost'))
                rec.profit_amount = sum(rec.child_ids.mapped('profit_amount'))
                rec.sale_total = sum(rec.child_ids.mapped('sale_total'))
            else:
                # boq_item: derive from template × quantity
                tmpl = rec.boq_item_template_id
                qty = rec.quantity or 1.0
                if tmpl:
                    mat = tmpl.material_total * qty
                    lab = tmpl.labor_total * qty
                    ovh = tmpl.overhead_total * qty
                else:
                    mat = lab = ovh = 0.0
                cost = mat + lab + ovh
                profit_pct = rec.suggested_profit_percent or 0.0
                profit = cost * (profit_pct / 100.0)
                rec.material_total = mat
                rec.labor_total = lab
                rec.overhead_total = ovh
                rec.total_cost = cost
                rec.profit_amount = profit
                rec.sale_total = cost + profit

    # =========================================================================
    # ONCHANGES
    # =========================================================================
    @api.onchange('costing_section')
    def _onchange_costing_section(self):
        """Clear sub-fields that belong to the old section."""
        if self.work_type_id and self.work_type_id.costing_section != self.costing_section:
            self.work_type_id = False
        if self.boq_item_template_id and \
                self.boq_item_template_id.costing_section != self.costing_section:
            self.boq_item_template_id = False

    @api.onchange('work_type_id')
    def _onchange_work_type_id(self):
        """Clear template when work type changes and template no longer matches."""
        if not self.work_type_id:
            self.boq_item_template_id = False
            return
        if self.boq_item_template_id and \
                self.boq_item_template_id.costing_section != self.work_type_id.costing_section:
            self.boq_item_template_id = False
        # Auto-fill costing_section from work type
        if self.work_type_id.costing_section and not self.costing_section:
            self.costing_section = self.work_type_id.costing_section

    @api.onchange('boq_item_template_id')
    def _onchange_boq_item_template(self):
        """Auto-fill BOQ item fields from the selected template."""
        tmpl = self.boq_item_template_id
        if not tmpl:
            return
        self.name = tmpl.name
        self.product_id = tmpl.product_id
        self.uom_name = tmpl.unit_name or ''
        self.quantity = tmpl.qty_item or 1.0
        self.suggested_profit_percent = tmpl.profit_percent
        # Auto-fill section from template if not yet set
        if not self.costing_section and tmpl.costing_section:
            self.costing_section = tmpl.costing_section

    @api.onchange('line_type')
    def _onchange_line_type(self):
        """Reset item-specific fields when type is not boq_item."""
        if self.line_type != 'boq_item':
            self.boq_item_template_id = False
            self.product_id = False
            self.uom_name = False
            self.quantity = 1.0

    # =========================================================================
    # DEFAULTS
    # =========================================================================
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        ctx = self.env.context
        if 'line_type' not in res and ctx.get('default_line_type'):
            res['line_type'] = ctx['default_line_type']
        if 'project_id' not in res and ctx.get('default_project_id'):
            res['project_id'] = ctx['default_project_id']
        return res


class ProjectProject(models.Model):
    """Extend project.project with a Costing Analysis workspace."""
    _inherit = 'project.project'

    analysis_line_ids = fields.One2many(
        'project.cost.analysis.line', 'project_id',
        string='Costing Analysis Lines',
    )

    # ── Project-level analysis totals ─────────────────────────────────────────
    analysis_material_total = fields.Float(
        string='Analysis Material Total', digits=(16, 2),
        compute='_compute_analysis_totals',
    )
    analysis_labor_total = fields.Float(
        string='Analysis Labor Total', digits=(16, 2),
        compute='_compute_analysis_totals',
    )
    analysis_overhead_total = fields.Float(
        string='Analysis Overhead Total', digits=(16, 2),
        compute='_compute_analysis_totals',
    )
    analysis_total_cost = fields.Float(
        string='Analysis Total Cost', digits=(16, 2),
        compute='_compute_analysis_totals',
    )
    analysis_total_profit = fields.Float(
        string='Analysis Total Profit', digits=(16, 2),
        compute='_compute_analysis_totals',
    )
    analysis_total_sale = fields.Float(
        string='Analysis Total Sale', digits=(16, 2),
        compute='_compute_analysis_totals',
    )

    @api.depends(
        'analysis_line_ids.material_total',
        'analysis_line_ids.labor_total',
        'analysis_line_ids.overhead_total',
        'analysis_line_ids.total_cost',
        'analysis_line_ids.profit_amount',
        'analysis_line_ids.sale_total',
        'analysis_line_ids.parent_id',
    )
    def _compute_analysis_totals(self):
        """Sum only top-level lines (divisions) to avoid double-counting."""
        for rec in self:
            top = rec.analysis_line_ids.filtered(lambda l: not l.parent_id)
            rec.analysis_material_total = sum(top.mapped('material_total'))
            rec.analysis_labor_total = sum(top.mapped('labor_total'))
            rec.analysis_overhead_total = sum(top.mapped('overhead_total'))
            rec.analysis_total_cost = sum(top.mapped('total_cost'))
            rec.analysis_total_profit = sum(top.mapped('profit_amount'))
            rec.analysis_total_sale = sum(top.mapped('sale_total'))
