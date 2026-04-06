# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class FarmCostAnalysisWizard(models.TransientModel):
    """Cost Analysis wizard — shows full BOQ breakdown and drives approval workflow."""

    _name = 'farm.cost.analysis.wizard'
    _description = 'Farm Cost Analysis Wizard'

    # ── Source field ──────────────────────────────────────────────────────────
    field_id = fields.Many2one(
        'farm.field', string='Field', required=True, readonly=True, ondelete='cascade'
    )

    # ── BOQ Summary (related, read-only display) ──────────────────────────────
    field_name = fields.Char(related='field_id.name', string='Field Name')
    farm_name = fields.Char(related='field_id.farm_id.name', string='Farm')
    area = fields.Float(related='field_id.area', string='Area (m²)')
    area_ha = fields.Float(related='field_id.area_ha', string='Area (Ha)')
    soil_type = fields.Char(related='field_id.soil_type_id.name', string='Soil Type')
    irrigation_type = fields.Char(
        related='field_id.irrigation_type_id.name', string='Irrigation Type'
    )

    # ── Section Totals ────────────────────────────────────────────────────────
    civil_total = fields.Float(related='field_id.civil_total', string='Civil Total')
    arch_total = fields.Float(related='field_id.arch_total', string='Architecture Total')
    mechanical_total = fields.Float(
        related='field_id.mechanical_total', string='Mechanical Total'
    )
    electrical_total = fields.Float(
        related='field_id.electrical_total', string='Electrical Total'
    )
    irrigation_cost_total = fields.Float(
        related='field_id.irrigation_total', string='Irrigation Total'
    )
    control_system_total = fields.Float(
        related='field_id.control_system_total', string='Control System Total'
    )
    other_total = fields.Float(related='field_id.other_total', string='Other Total')

    # ── Section Category Subtotals ────────────────────────────────────────────
    # Civil
    civil_material_total = fields.Float(
        related='field_id.civil_material_total', string='Civil — Material'
    )
    civil_labor_total = fields.Float(
        related='field_id.civil_labor_total', string='Civil — Labor'
    )
    civil_overhead_total = fields.Float(
        related='field_id.civil_overhead_total', string='Civil — Overhead'
    )
    # Architecture
    arch_material_total = fields.Float(
        related='field_id.arch_material_total', string='Arch — Material'
    )
    arch_labor_total = fields.Float(
        related='field_id.arch_labor_total', string='Arch — Labor'
    )
    arch_overhead_total = fields.Float(
        related='field_id.arch_overhead_total', string='Arch — Overhead'
    )
    # Mechanical
    mechanical_material_total = fields.Float(
        related='field_id.mechanical_material_total', string='Mechanical — Material'
    )
    mechanical_labor_total = fields.Float(
        related='field_id.mechanical_labor_total', string='Mechanical — Labor'
    )
    mechanical_overhead_total = fields.Float(
        related='field_id.mechanical_overhead_total', string='Mechanical — Overhead'
    )
    # Electrical
    electrical_material_total = fields.Float(
        related='field_id.electrical_material_total', string='Electrical — Material'
    )
    electrical_labor_total = fields.Float(
        related='field_id.electrical_labor_total', string='Electrical — Labor'
    )
    electrical_overhead_total = fields.Float(
        related='field_id.electrical_overhead_total', string='Electrical — Overhead'
    )
    # Irrigation
    irrigation_material_total = fields.Float(
        related='field_id.irrigation_material_total', string='Irrigation — Material'
    )
    irrigation_labor_total = fields.Float(
        related='field_id.irrigation_labor_total', string='Irrigation — Labor'
    )
    irrigation_overhead_total = fields.Float(
        related='field_id.irrigation_overhead_total', string='Irrigation — Overhead'
    )
    # Control System
    control_system_material_total = fields.Float(
        related='field_id.control_system_material_total', string='Control System — Material'
    )
    control_system_labor_total = fields.Float(
        related='field_id.control_system_labor_total', string='Control System — Labor'
    )
    control_system_overhead_total = fields.Float(
        related='field_id.control_system_overhead_total', string='Control System — Overhead'
    )
    # Other
    other_material_total = fields.Float(
        related='field_id.other_material_total', string='Other — Material'
    )
    other_labor_total = fields.Float(
        related='field_id.other_labor_total', string='Other — Labor'
    )
    other_overhead_total = fields.Float(
        related='field_id.other_overhead_total', string='Other — Overhead'
    )

    # ── Section Cost Lines — for detailed breakdown display ───────────────────
    civil_cost_line_ids = fields.One2many(
        related='field_id.civil_cost_line_ids',
        string='Civil Lines',
        readonly=True,
    )
    arch_cost_line_ids = fields.One2many(
        related='field_id.arch_cost_line_ids',
        string='Architecture Lines',
        readonly=True,
    )
    mechanical_cost_line_ids = fields.One2many(
        related='field_id.mechanical_cost_line_ids',
        string='Mechanical Lines',
        readonly=True,
    )
    electrical_cost_line_ids = fields.One2many(
        related='field_id.electrical_cost_line_ids',
        string='Electrical Lines',
        readonly=True,
    )
    irrigation_cost_line_ids = fields.One2many(
        related='field_id.irrigation_cost_line_ids',
        string='Irrigation Lines',
        readonly=True,
    )
    control_system_cost_line_ids = fields.One2many(
        related='field_id.control_system_cost_line_ids',
        string='Control System Lines',
        readonly=True,
    )
    other_cost_line_ids = fields.One2many(
        related='field_id.other_cost_line_ids',
        string='Other Lines',
        readonly=True,
    )

    # ── Section BOQ Items — structured items per section ──────────────────────
    civil_boq_item_ids = fields.One2many(
        related='field_id.civil_boq_item_ids',
        string='Civil BOQ Items',
        readonly=True,
    )
    arch_boq_item_ids = fields.One2many(
        related='field_id.arch_boq_item_ids',
        string='Architecture BOQ Items',
        readonly=True,
    )
    mechanical_boq_item_ids = fields.One2many(
        related='field_id.mechanical_boq_item_ids',
        string='Mechanical BOQ Items',
        readonly=True,
    )
    electrical_boq_item_ids = fields.One2many(
        related='field_id.electrical_boq_item_ids',
        string='Electrical BOQ Items',
        readonly=True,
    )
    irrigation_boq_item_ids = fields.One2many(
        related='field_id.irrigation_boq_item_ids',
        string='Irrigation BOQ Items',
        readonly=True,
    )
    control_system_boq_item_ids = fields.One2many(
        related='field_id.control_system_boq_item_ids',
        string='Control System BOQ Items',
        readonly=True,
    )
    other_boq_item_ids = fields.One2many(
        related='field_id.other_boq_item_ids',
        string='Other BOQ Items',
        readonly=True,
    )

    # ── BOQ count flags ───────────────────────────────────────────────────────
    has_civil_boq = fields.Boolean(compute='_compute_boq_flags')
    has_arch_boq = fields.Boolean(compute='_compute_boq_flags')
    has_mechanical_boq = fields.Boolean(compute='_compute_boq_flags')
    has_electrical_boq = fields.Boolean(compute='_compute_boq_flags')
    has_irrigation_boq = fields.Boolean(compute='_compute_boq_flags')
    has_control_system_boq = fields.Boolean(compute='_compute_boq_flags')
    has_other_boq = fields.Boolean(compute='_compute_boq_flags')

    def _compute_boq_flags(self):
        for rec in self:
            rec.has_civil_boq = bool(rec.civil_boq_item_ids)
            rec.has_arch_boq = bool(rec.arch_boq_item_ids)
            rec.has_mechanical_boq = bool(rec.mechanical_boq_item_ids)
            rec.has_electrical_boq = bool(rec.electrical_boq_item_ids)
            rec.has_irrigation_boq = bool(rec.irrigation_boq_item_ids)
            rec.has_control_system_boq = bool(rec.control_system_boq_item_ids)
            rec.has_other_boq = bool(rec.other_boq_item_ids)

    # ── Section relevance flags ───────────────────────────────────────────────
    has_civil_costing = fields.Boolean(
        related='field_id.has_civil_costing', string='Has Civil'
    )
    has_arch_costing = fields.Boolean(
        related='field_id.has_arch_costing', string='Has Arch'
    )
    has_mechanical_costing = fields.Boolean(
        related='field_id.has_mechanical_costing', string='Has Mechanical'
    )
    has_electrical_costing = fields.Boolean(
        related='field_id.has_electrical_costing', string='Has Electrical'
    )
    has_irrigation_costing = fields.Boolean(
        related='field_id.has_irrigation_costing', string='Has Irrigation'
    )
    has_control_system_costing = fields.Boolean(
        related='field_id.has_control_system_costing', string='Has Control System'
    )
    has_other_costing = fields.Boolean(
        related='field_id.has_other_costing', string='Has Other'
    )

    # ── Overall Category Totals ───────────────────────────────────────────────
    material_total = fields.Float(
        related='field_id.material_total', string='Material Total'
    )
    labor_total = fields.Float(related='field_id.labor_total', string='Labor Total')
    overhead_total = fields.Float(
        related='field_id.overhead_total', string='Overhead Total'
    )

    # ── Analysis Indicators ───────────────────────────────────────────────────
    cost_per_m2 = fields.Float(related='field_id.cost_per_m2', string='Cost per m²')
    grand_total = fields.Float(related='field_id.total_cost', string='Grand Total')
    cost_line_count = fields.Integer(
        related='field_id.cost_line_count', string='Costing Lines'
    )
    material_line_count = fields.Integer(
        related='field_id.material_line_count', string='Material Lines'
    )
    labor_line_count = fields.Integer(
        related='field_id.labor_line_count', string='Labor Lines'
    )
    overhead_line_count = fields.Integer(
        related='field_id.overhead_line_count', string='Overhead Lines'
    )

    # ── Approval state (display) ──────────────────────────────────────────────
    cost_analysis_state = fields.Selection(
        related='field_id.cost_analysis_state', string='Current Status'
    )

    # ── Analysis note (editable in wizard) ───────────────────────────────────
    analysis_note = fields.Text(string='Analysis Notes / Comments')

    # =========================================================================
    # WIZARD ACTIONS
    # =========================================================================
    def _apply_note(self):
        if self.analysis_note:
            self.field_id.cost_analysis_note = self.analysis_note

    def action_submit(self):
        """Submit analysis for manager review."""
        self.ensure_one()
        self._apply_note()
        self.field_id.action_submit_cost_analysis()
        return {'type': 'ir.actions.act_window_close'}

    def action_approve(self):
        """Approve cost analysis (manager/admin only)."""
        self.ensure_one()
        self._apply_note()
        self.field_id.action_approve_cost_analysis()
        return {'type': 'ir.actions.act_window_close'}

    def action_reject(self):
        """Reject cost analysis."""
        self.ensure_one()
        self._apply_note()
        self.field_id.action_reject_cost_analysis()
        return {'type': 'ir.actions.act_window_close'}
