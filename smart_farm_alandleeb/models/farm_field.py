# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from .farm_cost_type import COSTING_SECTION_SELECTION, SECTION_COSTING_STATES

# Ordered list of all costing sections
COSTING_SECTIONS = ['civil', 'arch', 'mechanical', 'electrical', 'irrigation', 'control_system', 'other']

# Human-readable labels for error messages
SECTION_LABELS = dict(COSTING_SECTION_SELECTION)

# Map section key → state field name on farm.field
SECTION_STATE_FIELD = {s: f'{s}_costing_state' for s in COSTING_SECTIONS}

VARIANCE_STATUS_SELECTION = [
    ('no_actual', 'No Actual Data'),
    ('on_budget', 'On Budget'),
    ('under_budget', 'Under Budget'),
    ('over_budget', 'Over Budget'),
]


class FarmField(models.Model):
    _name = 'farm.field'
    _description = 'Farm Field / Plot'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'farm_id, name'

    # ── Identity ─────────────────────────────────────────────────────────────
    name = fields.Char(string='Field Name', required=True, tracking=True)
    code = fields.Char(
        string='Field Code', copy=False, readonly=True,
        default=lambda self: _('New'),
    )

    # ── Relations ─────────────────────────────────────────────────────────────
    farm_id = fields.Many2one(
        'farm.farm', string='Farm', required=True, ondelete='cascade', tracking=True,
    )
    company_id = fields.Many2one(related='farm_id.company_id', store=True)

    # ── Physical attributes ───────────────────────────────────────────────────
    area = fields.Float(string='Area (m²)', digits=(16, 2))
    area_ha = fields.Float(
        string='Area (Ha)', digits=(10, 4),
        compute='_compute_area_ha', store=True,
    )
    soil_type_id = fields.Many2one('farm.soil.type', string='Soil Type', ondelete='set null')

    irrigation_type = fields.Selection([
        ('drip', 'Drip Irrigation'), ('sprinkler', 'Sprinkler'),
        ('flood', 'Flood'), ('manual', 'Manual'), ('none', 'None'),
    ], string='Irrigation Type (Legacy)')
    irrigation_type_id = fields.Many2one(
        'farm.irrigation.type', string='Irrigation Type', ondelete='set null',
    )

    # ── Field Status ──────────────────────────────────────────────────────────
    state = fields.Selection([
        ('available', 'Available'), ('planted', 'Planted'),
        ('harvested', 'Harvested'), ('fallow', 'Fallow'),
        ('maintenance', 'Maintenance'),
    ], string='Status', default='available', tracking=True)

    # ── Crops ─────────────────────────────────────────────────────────────────
    current_crop_id = fields.Many2one('farm.crop', string='Current Crop', readonly=True)
    crop_ids = fields.One2many('farm.crop', 'field_id', string='Crop History')
    crop_count = fields.Integer(compute='_compute_crop_count', string='Crops')

    # =========================================================================
    # COST LINES — master + 7 section-filtered views
    # =========================================================================
    cost_line_ids = fields.One2many(
        'farm.cost.line', 'field_id', string='All Cost Lines',
    )
    civil_cost_line_ids = fields.One2many(
        'farm.cost.line', 'field_id',
        domain=[('costing_section', '=', 'civil')],
        string='Civil Cost Lines',
    )
    arch_cost_line_ids = fields.One2many(
        'farm.cost.line', 'field_id',
        domain=[('costing_section', '=', 'arch')],
        string='Architecture Cost Lines',
    )
    mechanical_cost_line_ids = fields.One2many(
        'farm.cost.line', 'field_id',
        domain=[('costing_section', '=', 'mechanical')],
        string='Mechanical Cost Lines',
    )
    electrical_cost_line_ids = fields.One2many(
        'farm.cost.line', 'field_id',
        domain=[('costing_section', '=', 'electrical')],
        string='Electrical Cost Lines',
    )
    irrigation_cost_line_ids = fields.One2many(
        'farm.cost.line', 'field_id',
        domain=[('costing_section', '=', 'irrigation')],
        string='Irrigation Cost Lines',
    )
    control_system_cost_line_ids = fields.One2many(
        'farm.cost.line', 'field_id',
        domain=[('costing_section', '=', 'control_system')],
        string='Control System Cost Lines',
    )
    other_cost_line_ids = fields.One2many(
        'farm.cost.line', 'field_id',
        domain=[('costing_section', '=', 'other')],
        string='Other Cost Lines',
    )

    # =========================================================================
    # BOQ ITEMS — structured items per section
    # =========================================================================
    boq_item_ids = fields.One2many(
        'farm.boq.item', 'field_id', string='All BOQ Items',
    )
    civil_boq_item_ids = fields.One2many(
        'farm.boq.item', 'field_id',
        domain=[('costing_section', '=', 'civil')],
        string='Civil BOQ Items',
    )
    arch_boq_item_ids = fields.One2many(
        'farm.boq.item', 'field_id',
        domain=[('costing_section', '=', 'arch')],
        string='Architecture BOQ Items',
    )
    mechanical_boq_item_ids = fields.One2many(
        'farm.boq.item', 'field_id',
        domain=[('costing_section', '=', 'mechanical')],
        string='Mechanical BOQ Items',
    )
    electrical_boq_item_ids = fields.One2many(
        'farm.boq.item', 'field_id',
        domain=[('costing_section', '=', 'electrical')],
        string='Electrical BOQ Items',
    )
    irrigation_boq_item_ids = fields.One2many(
        'farm.boq.item', 'field_id',
        domain=[('costing_section', '=', 'irrigation')],
        string='Irrigation BOQ Items',
    )
    control_system_boq_item_ids = fields.One2many(
        'farm.boq.item', 'field_id',
        domain=[('costing_section', '=', 'control_system')],
        string='Control System BOQ Items',
    )
    other_boq_item_ids = fields.One2many(
        'farm.boq.item', 'field_id',
        domain=[('costing_section', '=', 'other')],
        string='Other BOQ Items',
    )

    # =========================================================================
    # COST TOTALS — section grand totals
    # =========================================================================
    total_cost = fields.Float(
        string='Total Cost', digits=(16, 2), compute='_compute_cost_analysis', store=True,
    )
    civil_total = fields.Float(
        string='Civil Total', digits=(16, 2), compute='_compute_cost_analysis', store=True,
    )
    arch_total = fields.Float(
        string='Architecture Total', digits=(16, 2), compute='_compute_cost_analysis', store=True,
    )
    mechanical_total = fields.Float(
        string='Mechanical Total', digits=(16, 2), compute='_compute_cost_analysis', store=True,
    )
    electrical_total = fields.Float(
        string='Electrical Total', digits=(16, 2), compute='_compute_cost_analysis', store=True,
    )
    irrigation_total = fields.Float(
        string='Irrigation Total', digits=(16, 2), compute='_compute_cost_analysis', store=True,
    )
    control_system_total = fields.Float(
        string='Control System Total', digits=(16, 2), compute='_compute_cost_analysis', store=True,
    )
    other_total = fields.Float(
        string='Other Total', digits=(16, 2), compute='_compute_cost_analysis', store=True,
    )

    # ── Section category subtotals ────────────────────────────────────────────
    # Civil
    civil_material_total = fields.Float(
        string='Civil — Material', digits=(16, 2), compute='_compute_cost_analysis', store=True,
    )
    civil_labor_total = fields.Float(
        string='Civil — Labor', digits=(16, 2), compute='_compute_cost_analysis', store=True,
    )
    civil_overhead_total = fields.Float(
        string='Civil — Overhead', digits=(16, 2), compute='_compute_cost_analysis', store=True,
    )
    # Architecture
    arch_material_total = fields.Float(
        string='Arch — Material', digits=(16, 2), compute='_compute_cost_analysis', store=True,
    )
    arch_labor_total = fields.Float(
        string='Arch — Labor', digits=(16, 2), compute='_compute_cost_analysis', store=True,
    )
    arch_overhead_total = fields.Float(
        string='Arch — Overhead', digits=(16, 2), compute='_compute_cost_analysis', store=True,
    )
    # Mechanical
    mechanical_material_total = fields.Float(
        string='Mechanical — Material', digits=(16, 2), compute='_compute_cost_analysis', store=True,
    )
    mechanical_labor_total = fields.Float(
        string='Mechanical — Labor', digits=(16, 2), compute='_compute_cost_analysis', store=True,
    )
    mechanical_overhead_total = fields.Float(
        string='Mechanical — Overhead', digits=(16, 2), compute='_compute_cost_analysis', store=True,
    )
    # Electrical
    electrical_material_total = fields.Float(
        string='Electrical — Material', digits=(16, 2), compute='_compute_cost_analysis', store=True,
    )
    electrical_labor_total = fields.Float(
        string='Electrical — Labor', digits=(16, 2), compute='_compute_cost_analysis', store=True,
    )
    electrical_overhead_total = fields.Float(
        string='Electrical — Overhead', digits=(16, 2), compute='_compute_cost_analysis', store=True,
    )
    # Irrigation
    irrigation_material_total = fields.Float(
        string='Irrigation — Material', digits=(16, 2), compute='_compute_cost_analysis', store=True,
    )
    irrigation_labor_total = fields.Float(
        string='Irrigation — Labor', digits=(16, 2), compute='_compute_cost_analysis', store=True,
    )
    irrigation_overhead_total = fields.Float(
        string='Irrigation — Overhead', digits=(16, 2), compute='_compute_cost_analysis', store=True,
    )
    # Control System
    control_system_material_total = fields.Float(
        string='Control System — Material', digits=(16, 2), compute='_compute_cost_analysis', store=True,
    )
    control_system_labor_total = fields.Float(
        string='Control System — Labor', digits=(16, 2), compute='_compute_cost_analysis', store=True,
    )
    control_system_overhead_total = fields.Float(
        string='Control System — Overhead', digits=(16, 2), compute='_compute_cost_analysis', store=True,
    )
    # Other
    other_material_total = fields.Float(
        string='Other — Material', digits=(16, 2), compute='_compute_cost_analysis', store=True,
    )
    other_labor_total = fields.Float(
        string='Other — Labor', digits=(16, 2), compute='_compute_cost_analysis', store=True,
    )
    other_overhead_total = fields.Float(
        string='Other — Overhead', digits=(16, 2), compute='_compute_cost_analysis', store=True,
    )

    # ── Overall category totals ───────────────────────────────────────────────
    material_total = fields.Float(
        string='Material Total', digits=(16, 2), compute='_compute_cost_analysis', store=True,
    )
    labor_total = fields.Float(
        string='Labor Total', digits=(16, 2), compute='_compute_cost_analysis', store=True,
    )
    overhead_total = fields.Float(
        string='Overhead Total', digits=(16, 2), compute='_compute_cost_analysis', store=True,
    )
    cost_per_m2 = fields.Float(
        string='Cost per m²', digits=(16, 4), compute='_compute_cost_analysis', store=True,
    )
    cost_line_count = fields.Integer(
        string='Cost Lines', compute='_compute_cost_analysis', store=True,
    )
    material_line_count = fields.Integer(
        string='Material Lines', compute='_compute_cost_analysis', store=True,
    )
    labor_line_count = fields.Integer(
        string='Labor Lines', compute='_compute_cost_analysis', store=True,
    )
    overhead_line_count = fields.Integer(
        string='Overhead Lines', compute='_compute_cost_analysis', store=True,
    )

    # =========================================================================
    # PER-SECTION COSTING WORKFLOW STATES
    # =========================================================================
    civil_costing_state = fields.Selection(
        SECTION_COSTING_STATES, string='Civil Study State',
        default='draft', tracking=True,
    )
    arch_costing_state = fields.Selection(
        SECTION_COSTING_STATES, string='Arch Study State',
        default='draft', tracking=True,
    )
    mechanical_costing_state = fields.Selection(
        SECTION_COSTING_STATES, string='Mechanical Study State',
        default='draft', tracking=True,
    )
    electrical_costing_state = fields.Selection(
        SECTION_COSTING_STATES, string='Electrical Study State',
        default='draft', tracking=True,
    )
    irrigation_costing_state = fields.Selection(
        SECTION_COSTING_STATES, string='Irrigation Study State',
        default='draft', tracking=True,
    )
    control_system_costing_state = fields.Selection(
        SECTION_COSTING_STATES, string='Control System Study State',
        default='draft', tracking=True,
    )
    other_costing_state = fields.Selection(
        SECTION_COSTING_STATES, string='Other Study State',
        default='draft', tracking=True,
    )

    # ── Per-section audit fields ──────────────────────────────────────────────
    # Civil
    civil_approved_by = fields.Many2one(
        'res.users', string='Civil Approved By', readonly=True, copy=False,
    )
    civil_approved_date = fields.Datetime(
        string='Civil Approved Date', readonly=True, copy=False,
    )
    civil_analysis_note = fields.Text(string='Civil Analysis Notes')

    # Architecture
    arch_approved_by = fields.Many2one(
        'res.users', string='Arch Approved By', readonly=True, copy=False,
    )
    arch_approved_date = fields.Datetime(
        string='Arch Approved Date', readonly=True, copy=False,
    )
    arch_analysis_note = fields.Text(string='Arch Analysis Notes')

    # Mechanical
    mechanical_approved_by = fields.Many2one(
        'res.users', string='Mechanical Approved By', readonly=True, copy=False,
    )
    mechanical_approved_date = fields.Datetime(
        string='Mechanical Approved Date', readonly=True, copy=False,
    )
    mechanical_analysis_note = fields.Text(string='Mechanical Analysis Notes')

    # Electrical
    electrical_approved_by = fields.Many2one(
        'res.users', string='Electrical Approved By', readonly=True, copy=False,
    )
    electrical_approved_date = fields.Datetime(
        string='Electrical Approved Date', readonly=True, copy=False,
    )
    electrical_analysis_note = fields.Text(string='Electrical Analysis Notes')

    # Irrigation
    irrigation_approved_by = fields.Many2one(
        'res.users', string='Irrigation Approved By', readonly=True, copy=False,
    )
    irrigation_approved_date = fields.Datetime(
        string='Irrigation Approved Date', readonly=True, copy=False,
    )
    irrigation_analysis_note = fields.Text(string='Irrigation Analysis Notes')

    # Control System
    control_system_approved_by = fields.Many2one(
        'res.users', string='Control System Approved By', readonly=True, copy=False,
    )
    control_system_approved_date = fields.Datetime(
        string='Control System Approved Date', readonly=True, copy=False,
    )
    control_system_analysis_note = fields.Text(string='Control System Analysis Notes')

    # Other
    other_approved_by = fields.Many2one(
        'res.users', string='Other Approved By', readonly=True, copy=False,
    )
    other_approved_date = fields.Datetime(
        string='Other Approved Date', readonly=True, copy=False,
    )
    other_analysis_note = fields.Text(string='Other Analysis Notes')

    # =========================================================================
    # FIELD-LEVEL FINAL COSTING APPROVAL
    # =========================================================================
    field_costing_state = fields.Selection([
        ('draft', 'Draft'),
        ('under_review', 'Under Review'),
        ('partially_approved', 'Partially Approved'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string='Field Costing State', default='draft', tracking=True)
    field_costing_approved_by = fields.Many2one(
        'res.users', string='Final Costing Approved By', readonly=True, copy=False,
    )
    field_costing_approved_date = fields.Datetime(
        string='Final Costing Approved Date', readonly=True, copy=False,
    )
    field_costing_note = fields.Text(string='Final Costing Notes')

    # ── Section relevance flags ───────────────────────────────────────────────
    # True only when a section has at least one normal (non-section/note) line
    has_civil_costing = fields.Boolean(
        string='Has Civil Lines', compute='_compute_section_relevance', store=True,
    )
    has_arch_costing = fields.Boolean(
        string='Has Arch Lines', compute='_compute_section_relevance', store=True,
    )
    has_mechanical_costing = fields.Boolean(
        string='Has Mechanical Lines', compute='_compute_section_relevance', store=True,
    )
    has_electrical_costing = fields.Boolean(
        string='Has Electrical Lines', compute='_compute_section_relevance', store=True,
    )
    has_irrigation_costing = fields.Boolean(
        string='Has Irrigation Lines', compute='_compute_section_relevance', store=True,
    )
    has_control_system_costing = fields.Boolean(
        string='Has Control System Lines', compute='_compute_section_relevance', store=True,
    )
    has_other_costing = fields.Boolean(
        string='Has Other Lines', compute='_compute_section_relevance', store=True,
    )

    # ── Section summary counters ──────────────────────────────────────────────
    relevant_section_count = fields.Integer(
        string='Relevant Sections', compute='_compute_section_counts', store=True,
    )
    approved_section_count = fields.Integer(
        string='Approved Sections', compute='_compute_section_counts', store=True,
    )
    pending_section_count = fields.Integer(
        string='Pending Sections', compute='_compute_section_counts', store=True,
    )

    # =========================================================================
    # ESTIMATED vs ACTUAL VARIANCE — per section
    # =========================================================================
    # Civil
    civil_actual_total = fields.Float(string='Civil Actual', digits=(16, 2))
    civil_variance = fields.Float(
        string='Civil Variance', digits=(16, 2),
        compute='_compute_variance_analysis', store=True,
    )
    civil_variance_percent = fields.Float(
        string='Civil Variance %', digits=(16, 2),
        compute='_compute_variance_analysis', store=True,
    )
    civil_variance_status = fields.Selection(
        VARIANCE_STATUS_SELECTION, string='Civil Budget Status',
        compute='_compute_variance_analysis', store=True,
    )
    # Architecture
    arch_actual_total = fields.Float(string='Arch Actual', digits=(16, 2))
    arch_variance = fields.Float(
        string='Arch Variance', digits=(16, 2),
        compute='_compute_variance_analysis', store=True,
    )
    arch_variance_percent = fields.Float(
        string='Arch Variance %', digits=(16, 2),
        compute='_compute_variance_analysis', store=True,
    )
    arch_variance_status = fields.Selection(
        VARIANCE_STATUS_SELECTION, string='Arch Budget Status',
        compute='_compute_variance_analysis', store=True,
    )
    # Mechanical
    mechanical_actual_total = fields.Float(string='Mechanical Actual', digits=(16, 2))
    mechanical_variance = fields.Float(
        string='Mechanical Variance', digits=(16, 2),
        compute='_compute_variance_analysis', store=True,
    )
    mechanical_variance_percent = fields.Float(
        string='Mechanical Variance %', digits=(16, 2),
        compute='_compute_variance_analysis', store=True,
    )
    mechanical_variance_status = fields.Selection(
        VARIANCE_STATUS_SELECTION, string='Mechanical Budget Status',
        compute='_compute_variance_analysis', store=True,
    )
    # Electrical
    electrical_actual_total = fields.Float(string='Electrical Actual', digits=(16, 2))
    electrical_variance = fields.Float(
        string='Electrical Variance', digits=(16, 2),
        compute='_compute_variance_analysis', store=True,
    )
    electrical_variance_percent = fields.Float(
        string='Electrical Variance %', digits=(16, 2),
        compute='_compute_variance_analysis', store=True,
    )
    electrical_variance_status = fields.Selection(
        VARIANCE_STATUS_SELECTION, string='Electrical Budget Status',
        compute='_compute_variance_analysis', store=True,
    )
    # Irrigation
    irrigation_actual_total = fields.Float(string='Irrigation Actual', digits=(16, 2))
    irrigation_variance = fields.Float(
        string='Irrigation Variance', digits=(16, 2),
        compute='_compute_variance_analysis', store=True,
    )
    irrigation_variance_percent = fields.Float(
        string='Irrigation Variance %', digits=(16, 2),
        compute='_compute_variance_analysis', store=True,
    )
    irrigation_variance_status = fields.Selection(
        VARIANCE_STATUS_SELECTION, string='Irrigation Budget Status',
        compute='_compute_variance_analysis', store=True,
    )
    # Control System
    control_system_actual_total = fields.Float(string='Control System Actual', digits=(16, 2))
    control_system_variance = fields.Float(
        string='Control System Variance', digits=(16, 2),
        compute='_compute_variance_analysis', store=True,
    )
    control_system_variance_percent = fields.Float(
        string='Control System Variance %', digits=(16, 2),
        compute='_compute_variance_analysis', store=True,
    )
    control_system_variance_status = fields.Selection(
        VARIANCE_STATUS_SELECTION, string='Control System Budget Status',
        compute='_compute_variance_analysis', store=True,
    )
    # Other
    other_actual_total = fields.Float(string='Other Actual', digits=(16, 2))
    other_variance = fields.Float(
        string='Other Variance', digits=(16, 2),
        compute='_compute_variance_analysis', store=True,
    )
    other_variance_percent = fields.Float(
        string='Other Variance %', digits=(16, 2),
        compute='_compute_variance_analysis', store=True,
    )
    other_variance_status = fields.Selection(
        VARIANCE_STATUS_SELECTION, string='Other Budget Status',
        compute='_compute_variance_analysis', store=True,
    )

    # ── Overall variance totals ───────────────────────────────────────────────
    total_actual = fields.Float(
        string='Total Actual', digits=(16, 2),
        compute='_compute_variance_analysis', store=True,
    )
    total_variance = fields.Float(
        string='Total Variance', digits=(16, 2),
        compute='_compute_variance_analysis', store=True,
    )
    total_variance_percent = fields.Float(
        string='Total Variance %', digits=(16, 2),
        compute='_compute_variance_analysis', store=True,
    )
    total_variance_status = fields.Selection(
        VARIANCE_STATUS_SELECTION, string='Overall Budget Status',
        compute='_compute_variance_analysis', store=True,
    )

    # ── Overall Cost Analysis Approval ────────────────────────────────────────
    cost_analysis_state = fields.Selection([
        ('draft', 'Draft'),
        ('under_review', 'Under Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string='Cost Analysis', default='draft', tracking=True)
    cost_analysis_date = fields.Datetime(
        string='Analysis Date', readonly=True, copy=False,
    )
    cost_analysis_user_id = fields.Many2one(
        'res.users', string='Analyzed By', readonly=True, copy=False,
    )
    cost_analysis_note = fields.Text(string='Analysis Notes')

    # ── RFQ link ──────────────────────────────────────────────────────────────
    purchase_order_id = fields.Many2one(
        'purchase.order', string='RFQ / Purchase Order', copy=False, ondelete='set null',
    )

    # ── Sales Quotation integration ────────────────────────────────────────────
    partner_id = fields.Many2one(
        'res.partner', string='Customer', ondelete='set null', tracking=True,
        help='Customer used when generating a Sales Quotation from BOQ items.',
    )
    sale_order_ids = fields.Many2many(
        'sale.order', 'farm_field_sale_order_rel', 'field_id', 'sale_order_id',
        string='Quotations', copy=False,
    )
    sale_order_count = fields.Integer(
        string='Quotations', compute='_compute_sale_order_count',
    )
    include_detailed_lines = fields.Boolean(
        string='Include Detailed Lines',
        default=False,
        help='When enabled, BOQ component lines are also added under each BOQ item in the quotation.',
    )

    # ── Location / Notes ──────────────────────────────────────────────────────
    latitude = fields.Float(string='Latitude', digits=(10, 7))
    longitude = fields.Float(string='Longitude', digits=(10, 7))
    notes = fields.Html(string='Notes')

    # =========================================================================
    # SEQUENCE
    # =========================================================================
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', _('New')) == _('New'):
                vals['code'] = self.env['ir.sequence'].next_by_code('farm.field') or _('New')
        return super().create(vals_list)

    # =========================================================================
    # COMPUTED FIELDS
    # =========================================================================
    @api.depends('area')
    def _compute_area_ha(self):
        for rec in self:
            rec.area_ha = rec.area / 10000.0 if rec.area else 0.0

    @api.depends('crop_ids')
    def _compute_crop_count(self):
        for rec in self:
            rec.crop_count = len(rec.crop_ids)

    @api.depends(
        'cost_line_ids.total_cost',
        'cost_line_ids.costing_section',
        'cost_line_ids.display_type',
        'cost_line_ids.cost_type_id',
        'cost_line_ids.cost_type_id.category',
        'boq_item_ids.total_cost_per_item',
        'boq_item_ids.costing_section',
        'boq_item_ids.material_total',
        'boq_item_ids.labor_total',
        'boq_item_ids.overhead_total',
        'area',
    )
    def _compute_cost_analysis(self):
        for rec in self:
            # Normal flat cost lines only (exclude section headers and notes)
            normal = rec.cost_line_ids.filtered(lambda l: not l.display_type)

            # ── Section grand totals (flat lines + BOQ items) ─────────────────
            def _sec(section):
                lines = sum(l.total_cost for l in normal if l.costing_section == section)
                boq = sum(i.total_cost_per_item for i in rec.boq_item_ids if i.costing_section == section)
                return lines + boq

            rec.civil_total = _sec('civil')
            rec.arch_total = _sec('arch')
            rec.mechanical_total = _sec('mechanical')
            rec.electrical_total = _sec('electrical')
            rec.irrigation_total = _sec('irrigation')
            rec.control_system_total = _sec('control_system')
            rec.other_total = _sec('other')

            # ── Per-section category subtotals (flat lines + BOQ items) ───────
            def _cat(section, category):
                lines = sum(
                    l.total_cost for l in normal
                    if l.costing_section == section and l.cost_type_id.category == category
                )
                boq = sum(
                    getattr(i, f'{category}_total')
                    for i in rec.boq_item_ids
                    if i.costing_section == section
                )
                return lines + boq

            for sec in COSTING_SECTIONS:
                rec[f'{sec}_material_total'] = _cat(sec, 'material')
                rec[f'{sec}_labor_total'] = _cat(sec, 'labor')
                rec[f'{sec}_overhead_total'] = _cat(sec, 'overhead')

            # ── Overall category totals ───────────────────────────────────────
            rec.material_total = sum(
                l.total_cost for l in normal if l.cost_type_id.category == 'material'
            ) + sum(rec.boq_item_ids.mapped('material_total'))
            rec.labor_total = sum(
                l.total_cost for l in normal if l.cost_type_id.category == 'labor'
            ) + sum(rec.boq_item_ids.mapped('labor_total'))
            rec.overhead_total = sum(
                l.total_cost for l in normal if l.cost_type_id.category == 'overhead'
            ) + sum(rec.boq_item_ids.mapped('overhead_total'))

            rec.total_cost = (
                sum(normal.mapped('total_cost'))
                + sum(rec.boq_item_ids.mapped('total_cost_per_item'))
            )
            rec.cost_per_m2 = rec.total_cost / rec.area if rec.area else 0.0

            rec.cost_line_count = len(normal)
            rec.material_line_count = len(
                normal.filtered(lambda l: l.cost_type_id.category == 'material')
            )
            rec.labor_line_count = len(
                normal.filtered(lambda l: l.cost_type_id.category == 'labor')
            )
            rec.overhead_line_count = len(
                normal.filtered(lambda l: l.cost_type_id.category == 'overhead')
            )

    # ── Section relevance ─────────────────────────────────────────────────────
    @api.depends(
        'cost_line_ids.costing_section', 'cost_line_ids.display_type',
        'boq_item_ids.costing_section',
    )
    def _compute_section_relevance(self):
        for rec in self:
            normal_sections = set(
                rec.cost_line_ids.filtered(lambda l: not l.display_type).mapped('costing_section')
            )
            boq_sections = set(rec.boq_item_ids.mapped('costing_section'))
            all_sections = normal_sections | boq_sections
            rec.has_civil_costing = 'civil' in all_sections
            rec.has_arch_costing = 'arch' in all_sections
            rec.has_mechanical_costing = 'mechanical' in all_sections
            rec.has_electrical_costing = 'electrical' in all_sections
            rec.has_irrigation_costing = 'irrigation' in all_sections
            rec.has_control_system_costing = 'control_system' in all_sections
            rec.has_other_costing = 'other' in all_sections

    @api.depends(
        *[f'has_{s}_costing' for s in COSTING_SECTIONS],
        *[f'{s}_costing_state' for s in COSTING_SECTIONS],
    )
    def _compute_section_counts(self):
        for rec in self:
            relevant = [s for s in COSTING_SECTIONS if getattr(rec, f'has_{s}_costing')]
            approved = [s for s in relevant if getattr(rec, SECTION_STATE_FIELD[s]) == 'approved']
            rec.relevant_section_count = len(relevant)
            rec.approved_section_count = len(approved)
            rec.pending_section_count = len(relevant) - len(approved)

    @api.depends(
        *[f'{s}_total' for s in COSTING_SECTIONS],
        *[f'{s}_actual_total' for s in COSTING_SECTIONS],
    )
    def _compute_variance_analysis(self):
        """Compute variance = actual - estimated for every section and overall."""

        def _status(actual, variance):
            if not actual:
                return 'no_actual'
            if variance > 0:
                return 'over_budget'
            if variance < 0:
                return 'under_budget'
            return 'on_budget'

        for rec in self:
            for sec in COSTING_SECTIONS:
                estimated = getattr(rec, f'{sec}_total')
                actual = getattr(rec, f'{sec}_actual_total')
                variance = actual - estimated
                pct = (variance / estimated * 100.0) if estimated else 0.0
                rec[f'{sec}_variance'] = variance
                rec[f'{sec}_variance_percent'] = pct
                rec[f'{sec}_variance_status'] = _status(actual, variance)

            # Overall
            rec.total_actual = sum(
                getattr(rec, f'{s}_actual_total') for s in COSTING_SECTIONS
            )
            total_variance = rec.total_actual - rec.total_cost
            rec.total_variance = total_variance
            rec.total_variance_percent = (
                (total_variance / rec.total_cost * 100.0) if rec.total_cost else 0.0
            )
            rec.total_variance_status = _status(rec.total_actual, total_variance)

    # =========================================================================
    # PER-SECTION COSTING WORKFLOW
    # =========================================================================
    def action_section_state(self):
        """Generic section state updater. Called from buttons with context:
            {'section': 'civil', 'new_state': 'price_study'}
        """
        section = self.env.context.get('section')
        new_state = self.env.context.get('new_state')
        if not section or not new_state:
            return

        state_field = SECTION_STATE_FIELD.get(section)
        if not state_field:
            return

        state_labels = dict(SECTION_COSTING_STATES)
        section_label = SECTION_LABELS.get(section, section)

        for rec in self:
            vals = {state_field: new_state}
            if new_state == 'approved':
                vals[f'{section}_approved_by'] = rec.env.user.id
                vals[f'{section}_approved_date'] = fields.Datetime.now()
            rec.write(vals)
            rec.message_post(
                body=_(
                    '%s costing stage → %s',
                    section_label,
                    state_labels.get(new_state, new_state),
                )
            )
            rec._sync_field_costing_state()

    # =========================================================================
    # FIELD-LEVEL FINAL COSTING SYNC + ACTIONS
    # =========================================================================
    def _sync_field_costing_state(self):
        """Auto-advance field_costing_state based on section states.
        Called after any section state change.
        Never overrides 'rejected' (requires explicit reset).
        'approved' is set only by the explicit Approve Final Costing action.
        """
        for rec in self:
            if rec.field_costing_state == 'rejected':
                continue  # Preserve explicit rejection

            relevant = [s for s in COSTING_SECTIONS if getattr(rec, f'has_{s}_costing')]
            if not relevant:
                new_state = 'draft'
            else:
                section_states = [getattr(rec, SECTION_STATE_FIELD[s]) for s in relevant]
                n_total = len(section_states)
                n_approved = sum(1 for st in section_states if st == 'approved')
                n_draft = sum(1 for st in section_states if st == 'draft')

                if n_approved == n_total:
                    # All sections done — auto-advance unless already explicitly approved
                    if rec.field_costing_state != 'approved':
                        new_state = 'partially_approved'  # Ready for final explicit approval
                    else:
                        continue  # Keep 'approved', don't downgrade
                elif n_approved > 0:
                    new_state = 'partially_approved'
                elif n_draft == n_total:
                    new_state = 'draft'
                else:
                    new_state = 'under_review'

            if rec.field_costing_state != new_state:
                rec.field_costing_state = new_state
                # Clear audit if state regressed from approved
                if new_state != 'approved':
                    rec.field_costing_approved_by = False
                    rec.field_costing_approved_date = False

    def _get_unapproved_relevant_sections(self):
        """Return list of section labels that have lines but are not approved."""
        return [
            SECTION_LABELS.get(s, s)
            for s in COSTING_SECTIONS
            if getattr(self, f'has_{s}_costing') and getattr(self, SECTION_STATE_FIELD[s]) != 'approved'
        ]

    def action_submit_final_costing(self):
        """Submit field for final costing review."""
        for rec in self:
            rec.write({'field_costing_state': 'under_review'})
            rec.message_post(body=_('Field costing submitted for final review.'))

    def action_approve_final_costing(self):
        """Approve final field costing. All relevant sections must be approved first."""
        self.ensure_one()
        unapproved = self._get_unapproved_relevant_sections()
        if unapproved:
            raise UserError(_(
                'Cannot approve final field costing.\n'
                'The following costing sections still require approval:\n'
                '  • %s\n\n'
                'Approve all sections before proceeding.',
                '\n  • '.join(unapproved),
            ))
        self.write({
            'field_costing_state': 'approved',
            'field_costing_approved_by': self.env.user.id,
            'field_costing_approved_date': fields.Datetime.now(),
        })
        self.message_post(
            body=_('Final field costing approved by %s.', self.env.user.name)
        )

    def action_reject_final_costing(self):
        """Reject final field costing."""
        for rec in self:
            rec.write({'field_costing_state': 'rejected'})
            rec.message_post(body=_('Final field costing rejected.'))

    def action_reset_final_costing(self):
        """Reset rejected final costing back to draft."""
        for rec in self:
            rec.write({
                'field_costing_state': 'draft',
                'field_costing_approved_by': False,
                'field_costing_approved_date': False,
            })
            rec._sync_field_costing_state()
            rec.message_post(body=_('Final field costing reset to Draft.'))

    # =========================================================================
    # BOQ ITEM TEMPLATE INSERT
    # =========================================================================
    def action_insert_boq_item_template(self):
        """Open the Insert BOQ Item Template wizard for this field.
        Reads default_costing_section from context to pre-fill target section.
        """
        self.ensure_one()
        section = self.env.context.get('default_costing_section', False)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Insert BOQ Item Template'),
            'res_model': 'farm.insert.boq.item.template.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_field_id': self.id,
                'default_target_section': section or False,
            },
        }

    # =========================================================================
    # OVERALL COST ANALYSIS WORKFLOW
    # =========================================================================
    def action_create_cost_analysis(self):
        """Open the Cost Analysis summary wizard."""
        self.ensure_one()
        wizard = self.env['farm.cost.analysis.wizard'].create({'field_id': self.id})
        return {
            'type': 'ir.actions.act_window',
            'name': _('Cost Analysis — %s', self.name),
            'res_model': 'farm.cost.analysis.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_submit_cost_analysis(self):
        for rec in self:
            rec.write({'cost_analysis_state': 'under_review'})
            rec.message_post(body=_('Cost analysis submitted for review.'))

    def action_approve_cost_analysis(self):
        for rec in self:
            rec.write({
                'cost_analysis_state': 'approved',
                'cost_analysis_date': fields.Datetime.now(),
                'cost_analysis_user_id': rec.env.user.id,
            })
            rec.message_post(
                body=_('Cost analysis approved by %s.', rec.env.user.name)
            )

    def action_reject_cost_analysis(self):
        for rec in self:
            rec.write({'cost_analysis_state': 'rejected'})
            rec.message_post(body=_('Cost analysis rejected.'))

    def action_reset_cost_analysis(self):
        for rec in self:
            rec.write({'cost_analysis_state': 'draft'})
            rec.message_post(body=_('Cost analysis reset to Draft.'))

    # =========================================================================
    # RFQ GENERATION — blocked until all material sections are approved
    # =========================================================================
    def action_create_rfq(self):
        self.ensure_one()

        # ── Gate 1 (strictest): final field costing must be approved ────────────
        if self.field_costing_state != 'approved':
            raise UserError(_(
                'You must complete and approve the final field costing analysis before creating an RFQ.\n'
                'Current costing status: %s\n\n'
                'Complete section workflows → Approve all sections → Approve Final Costing.',
                dict(self._fields['field_costing_state'].selection).get(
                    self.field_costing_state, self.field_costing_state
                ),
            ))

        # ── Gate 2: all sections with material lines individually approved ────
        material_normal = self.cost_line_ids.filtered(
            lambda l: not l.display_type and l.cost_type_id.category == 'material'
        )
        unapproved_sections = self._get_unapproved_relevant_sections()
        if unapproved_sections:
            raise UserError(_(
                'The following costing sections contain material lines but are not yet approved:\n'
                '  • %s\n\n'
                'Please approve all relevant sections before creating an RFQ.',
                '\n  • '.join(unapproved_sections),
            ))

        # ── Duplicate check ───────────────────────────────────────────────────
        if self.purchase_order_id:
            raise UserError(_(
                'An RFQ already exists for this field: %s.\n'
                'Please delete or reset it before generating a new one.',
                self.purchase_order_id.name,
            ))

        # ── Collect BOQ item material lines ───────────────────────────────────
        boq_material_lines = self.boq_item_ids.mapped('line_ids').filtered(
            lambda l: not l.display_type and l.cost_type_id.category == 'material'
        )

        if not material_normal and not boq_material_lines:
            raise UserError(_(
                'No material cost lines or BOQ item material components found on this field.\n'
                'Add lines with a Cost Type of category "Material" (flat or via BOQ items) to generate an RFQ.'
            ))

        # ── Resolve vendor ────────────────────────────────────────────────────
        all_material_products = (
            [l.product_id for l in material_normal if l.product_id]
            + [l.product_id for l in boq_material_lines if l.product_id]
        )
        vendor = self.env['res.partner']
        for product in all_material_products:
            supplier_info = self.env['product.supplierinfo'].search(
                [('product_tmpl_id', '=', product.product_tmpl_id.id)],
                limit=1, order='sequence asc',
            )
            if supplier_info:
                vendor = supplier_info.partner_id
                break
        if not vendor:
            vendor = self.env['res.partner'].search(
                [('supplier_rank', '>', 0)], limit=1, order='supplier_rank desc'
            )
        if not vendor:
            raise UserError(_(
                'No supplier found. Please define a supplier on at least one product '
                'in the material cost lines, or create a supplier contact first.'
            ))

        # ── Create PO ────────────────────────────────────────────────────────
        po = self.env['purchase.order'].create({
            'partner_id': vendor.id,
            'origin': f'{self.code} - {self.name}',
            'notes': _('Auto-generated RFQ from Smart Farm field: %s', self.name),
        })
        # Flat cost line materials
        for line in material_normal:
            self.env['purchase.order.line'].create({
                'order_id': po.id,
                'product_id': line.product_id.id if line.product_id else False,
                'name': (
                    line.product_id.display_name
                    if line.product_id
                    else (line.cost_type_id.name or _('Material'))
                ),
                'product_qty': line.quantity or 1.0,
                'price_unit': line.unit_cost or 0.0,
                'date_planned': fields.Datetime.now(),
            })
        # BOQ item material lines
        for bline in boq_material_lines:
            item_name = bline.boq_item_id.name or ''
            self.env['purchase.order.line'].create({
                'order_id': po.id,
                'product_id': bline.product_id.id if bline.product_id else False,
                'name': (
                    f'[{item_name}] {bline.product_id.display_name}'
                    if bline.product_id
                    else f'[{item_name}] {bline.name or bline.cost_type_id.name or _("Material")}'
                ),
                'product_qty': bline.qty_1 or 1.0,
                'price_unit': bline.cost_unit or 0.0,
                'date_planned': fields.Datetime.now(),
            })

        self.purchase_order_id = po.id
        self.message_post(
            body=_('RFQ %s created from material cost lines and BOQ items.', po.name)
        )

        return {
            'type': 'ir.actions.act_window',
            'name': _('RFQ'),
            'res_model': 'purchase.order',
            'res_id': po.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_rfq(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('RFQ'),
            'res_model': 'purchase.order',
            'res_id': self.purchase_order_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # =========================================================================
    # SALE ORDER (QUOTATION) — generated from BOQ Items with selling prices
    # =========================================================================
    def _compute_sale_order_count(self):
        for rec in self:
            rec.sale_order_count = len(rec.sale_order_ids)

    def action_create_sale_order(self):
        self.ensure_one()

        # ── Gate: cost analysis must be approved ──────────────────────────────
        if self.cost_analysis_state != 'approved':
            raise UserError(_(
                'The cost analysis must be approved before creating a Sales Quotation.\n'
                'Current status: %s\n\n'
                'Please approve the cost analysis first.',
                dict(self._fields['cost_analysis_state'].selection).get(
                    self.cost_analysis_state, self.cost_analysis_state
                ),
            ))

        # ── Gate: customer required ────────────────────────────────────────────
        if not self.partner_id:
            raise UserError(_('Please select a customer on the field before creating a quotation.'))

        # ── Collect BOQ items in section/sequence order ────────────────────────
        boq_items = self.boq_item_ids.sorted(key=lambda i: (i.costing_section, i.sequence, i.id))
        if not boq_items:
            raise UserError(_('No BOQ items found on this field. Add BOQ items before creating a quotation.'))

        # ── Create Sale Order ─────────────────────────────────────────────────
        so = self.env['sale.order'].create({
            'partner_id': self.partner_id.id,
            'origin': f'{self.code} - {self.name}',
            'note': _('Sales Quotation auto-generated from BOQ items of field: %s', self.name),
        })

        # ── Build order lines ─────────────────────────────────────────────────
        current_section = None
        section_labels = dict(
            self.env['farm.boq.item']._fields['costing_section'].selection
        )

        for item in boq_items:
            # Insert a section header when the costing section changes
            if item.costing_section != current_section:
                current_section = item.costing_section
                self.env['sale.order.line'].create({
                    'order_id': so.id,
                    'display_type': 'line_section',
                    'name': section_labels.get(current_section, current_section),
                })

            # Normal BOQ item line
            self.env['sale.order.line'].create({
                'order_id': so.id,
                'display_type': False,
                'name': item.name,
                'product_id': item.product_id.id if item.product_id else False,
                'product_uom_qty': item.qty_item,
                'price_unit': item.total_sales_price_per_item,
            })

            # Optional: include component detail lines under the BOQ item
            if self.include_detailed_lines:
                normal_lines = item.line_ids.filtered(lambda l: not l.display_type)
                for comp in normal_lines.sorted(key=lambda l: (l.sequence, l.id)):
                    self.env['sale.order.line'].create({
                        'order_id': so.id,
                        'display_type': False,
                        'name': f'  ↳ {comp.name or comp.product_id.display_name or _("Component")}',
                        'product_id': comp.product_id.id if comp.product_id else False,
                        'product_uom_qty': comp.qty_1,
                        'price_unit': comp.cost_unit,
                    })

        # ── Link SO back to this field ────────────────────────────────────────
        self.sale_order_ids = [(4, so.id)]
        self.message_post(
            body=_('Sales Quotation %s created from BOQ items.', so.name)
        )

        return {
            'type': 'ir.actions.act_window',
            'name': _('Quotation'),
            'res_model': 'sale.order',
            'res_id': so.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_quotations(self):
        self.ensure_one()
        if self.sale_order_count == 1:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Quotation'),
                'res_model': 'sale.order',
                'res_id': self.sale_order_ids[0].id,
                'view_mode': 'form',
                'target': 'current',
            }
        return {
            'type': 'ir.actions.act_window',
            'name': _('Quotations'),
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.sale_order_ids.ids)],
            'target': 'current',
        }

    # =========================================================================
    # DISPLAY NAME
    # =========================================================================
    def name_get(self):
        result = []
        for rec in self:
            result.append((rec.id, f'{rec.farm_id.name} / {rec.name}'))
        return result
