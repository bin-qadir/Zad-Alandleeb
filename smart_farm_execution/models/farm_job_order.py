from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class FarmJobOrder(models.Model):
    """Job Order — the atomic unit of field execution.

    Each Job Order maps to ONE approved BOQ subitem from an approved BOQ
    Analysis document.  It carries:

    - planned scope (qty, unit, dates from BOQ)
    - real-time progress (executed_qty → progress_percent)
    - actual resource consumption via material, labour, subcontract lines
    - cost summary: planned cost (from analysis) vs actual (all sources)
    - full site notes: general / instructions / inspection

    State machine:
        draft → ready → in_progress → completed → closed

    Rules:
    - project_id, boq_id, boq_line_id are required (enforced by constraint)
    - analysis_id must be 'approved' before going in_progress
    - Cannot complete if executed_qty == 0
    - Cannot close if progress_percent < 100 (manager can override)
    """

    _name = 'farm.job.order'
    _description = 'Farm Job Order'
    # Primary sort: BOQ code (zero-padded → string sort == numeric sort),
    # secondary: sequence name so duplicate codes still have a stable order.
    _order = 'project_id, display_code, name'
    _rec_name = 'name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # ── Identity ──────────────────────────────────────────────────────────────
    name = fields.Char(
        string='Job Order',
        required=True,
        copy=False,
        default=lambda self: _('New'),
        tracking=True,
    )

    # ── Project / BOQ traceability ────────────────────────────────────────────
    project_id = fields.Many2one(
        'farm.project',
        string='Farm Project',
        required=True,
        ondelete='restrict',
        index=True,
        tracking=True,
    )
    boq_id = fields.Many2one(
        'farm.boq',
        string='BOQ Document',
        related='analysis_id.boq_id',
        store=True,
        readonly=True,
        index=True,
    )
    analysis_id = fields.Many2one(
        'farm.boq.analysis',
        string='BOQ Analysis',
        required=True,
        ondelete='restrict',
        index=True,
        domain="[('project_id', '=', project_id), ('analysis_state', '=', 'approved')]",
        tracking=True,
    )
    boq_line_id = fields.Many2one(
        'farm.boq.line',
        string='BOQ Subitem',
        required=True,
        ondelete='restrict',
        index=True,
        domain="[('boq_id', '=', boq_id), ('display_type', '=', False)]",
    )
    analysis_line_id = fields.Many2one(
        'farm.boq.analysis.line',
        string='Analysis Line',
        ondelete='set null',
        index=True,
        domain="[('analysis_id', '=', analysis_id)]",
    )

    # ── Classification (mirrored from BOQ line) ───────────────────────────────
    display_code = fields.Char(
        string='BOQ Code',
        related='boq_line_id.display_code',
        store=True,
        readonly=True,
    )
    division_id = fields.Many2one(
        'farm.division.work',
        string='Division',
        related='boq_line_id.division_id',
        store=True,
        readonly=True,
    )
    subdivision_id = fields.Many2one(
        'farm.subdivision.work',
        string='Subdivision',
        related='boq_line_id.subdivision_id',
        store=True,
        readonly=True,
    )
    sub_subdivision_id = fields.Many2one(
        'farm.sub_subdivision.work',
        string='Sub-Subdivision',
        related='boq_line_id.sub_subdivision_id',
        store=True,
        readonly=True,
    )

    # ── BOQ hierarchy path (computed display) ─────────────────────────────────
    # e.g. "Civil Works › Site Preparation › Site Clearing"
    boq_hierarchy = fields.Char(
        string='BOQ Hierarchy',
        compute='_compute_boq_hierarchy',
        store=True,
        readonly=True,
    )

    # ── Data-integrity flag ────────────────────────────────────────────────────
    # True when this JO's boq_line_id is a structural row (section / subsection)
    # instead of a real executable subitem.  Shown as a danger badge in the UI.
    is_structural_line = fields.Boolean(
        string='Structural Line?',
        compute='_compute_is_structural_line',
        store=True,
        readonly=True,
        help=(
            'True when the linked BOQ line is a section/subdivision header '
            'instead of a real executable subitem.  Job Orders in this state '
            'cannot be executed and should be regenerated from valid subitems.'
        ),
    )

    # ── Department (auto-populated from division, overridable) ───────────────
    department = fields.Selection(
        selection=[
            ('civil',       'Civil'),
            ('structure',   'Structure'),
            ('arch',        'Architectural'),
            ('mechanical',  'Mechanical'),
            ('electrical',  'Electrical'),
            ('other',       'Other'),
        ],
        string='Department',
        index=True,
        tracking=True,
    )

    # ── Work classification ───────────────────────────────────────────────────
    work_type_id = fields.Many2one(
        'farm.work.type',
        string='Work Type',
        ondelete='set null',
        tracking=True,
    )
    discipline = fields.Char(
        string='Discipline',
        help='e.g. Civil, Mechanical, Electrical, Agricultural…',
    )

    # ── Scope / planning ──────────────────────────────────────────────────────
    planned_qty = fields.Float(
        string='Planned Qty',
        digits=(16, 2),
        required=True,
        default=1.0,
    )
    unit_id = fields.Many2one(
        'uom.uom',
        string='Unit',
        ondelete='set null',
    )
    unit_price = fields.Float(
        string='Unit Price',
        related='boq_line_id.unit_price',
        store=True,
        readonly=True,
        digits=(16, 2),
    )

    # ── Planning dates ────────────────────────────────────────────────────────
    planned_start_date = fields.Date(string='Planned Start', tracking=True)
    planned_end_date   = fields.Date(string='Planned End',   tracking=True)

    # ── Actual dates (set by workflow) ────────────────────────────────────────
    actual_start_date = fields.Date(string='Actual Start', readonly=True, copy=False)
    actual_end_date   = fields.Date(string='Actual End',   readonly=True, copy=False)

    # ── Progress ──────────────────────────────────────────────────────────────
    executed_qty = fields.Float(
        string='Executed Qty',
        digits=(16, 2),
        default=0.0,
        tracking=True,
    )
    progress_percent = fields.Float(
        string='Progress (%)',
        compute='_compute_progress',
        store=True,
        digits=(16, 1),
    )
    progress_log_ids = fields.One2many(
        'farm.job.progress.log',
        'job_order_id',
        string='Progress Logs',
    )

    # ── Workflow state ────────────────────────────────────────────────────────
    state = fields.Selection(
        selection=[
            ('draft',       'Draft'),
            ('ready',       'Ready'),
            ('in_progress', 'In Progress'),
            ('completed',   'Completed'),
            ('closed',      'Closed'),
        ],
        string='Status',
        default='draft',
        required=True,
        index=True,
        tracking=True,
        copy=False,
    )

    # ── Operational stage (primary UI stage, shown in statusbar) ─────────────
    jo_stage = fields.Selection(
        selection=[
            ('new',               'New'),
            ('approved',          'Approved'),
            ('in_progress',       'In Progress'),
            ('under_inspection',  'Under Inspection'),
            ('accepted',          'Accepted'),
            ('ready_for_claim',   'Ready for Claim'),
            ('claimed',           'Claimed'),
            ('closed',            'Closed'),
        ],
        string='JO Stage',
        default='new',
        required=True,
        index=True,
        tracking=True,
        copy=False,
        help=(
            'Operational stage: New → Approved → In Progress → Under Inspection '
            '→ Accepted → Ready for Claim → Claimed → Closed.\n'
            'Drives the execution → inspection → acceptance → claim flow.'
        ),
    )

    # ── Notes ─────────────────────────────────────────────────────────────────
    notes             = fields.Text(string='General Notes')
    instruction_notes = fields.Text(string='Instructions')
    inspection_notes  = fields.Text(string='Inspection Notes')

    # ── Inspection & Handover ─────────────────────────────────────────────────
    inspection_request_date = fields.Date(
        string='Inspection Request Date',
        tracking=True,
        copy=False,
    )
    inspection_result = fields.Selection(
        selection=[
            ('pending',      'Pending'),
            ('passed',       'Passed'),
            ('failed',       'Failed'),
            ('conditional',  'Conditional'),
        ],
        string='Inspection Result',
        default='pending',
        tracking=True,
        copy=False,
    )
    accepted_qty = fields.Float(
        string='Accepted Qty',
        digits=(16, 2),
        default=0.0,
        tracking=True,
        copy=False,
        help='Quantity accepted after inspection — drives claim calculation.',
    )
    handover_status = fields.Selection(
        selection=[
            ('pending',   'Pending'),
            ('received',  'Received'),
            ('rejected',  'Rejected'),
        ],
        string='Handover Status',
        default='pending',
        tracking=True,
        copy=False,
    )
    handover_notes = fields.Text(string='Handover Notes')

    # ── Approvals / Awarding ──────────────────────────────────────────────────
    approval_status = fields.Selection(
        selection=[
            ('pending',   'Pending'),
            ('approved',  'Approved'),
            ('rejected',  'Rejected'),
        ],
        string='Approval Status',
        default='pending',
        tracking=True,
        copy=False,
    )
    awarding_status = fields.Selection(
        selection=[
            ('not_awarded',   'Not Awarded'),
            ('direct',        'Direct'),
            ('subcontracted', 'Subcontracted'),
        ],
        string='Awarding Status',
        default='not_awarded',
        tracking=True,
    )
    approval_notes = fields.Text(string='Approval Notes')

    # ── Claims / Extracts ─────────────────────────────────────────────────────
    claimed_qty = fields.Float(
        string='Claimed Qty',
        digits=(16, 2),
        default=0.0,
        tracking=True,
        copy=False,
    )
    remaining_claim_qty = fields.Float(
        string='Remaining Claim Qty',
        compute='_compute_claim_fields',
        store=True,
        readonly=True,
        digits=(16, 2),
    )
    claim_percent = fields.Float(
        string='Claim %',
        compute='_compute_claim_fields',
        store=True,
        readonly=True,
        digits=(16, 2),
        help='accepted_qty / planned_qty × 100',
    )
    claim_amount = fields.Float(
        string='Claim Amount',
        compute='_compute_claim_fields',
        store=True,
        readonly=True,
        digits=(16, 2),
        help='accepted_qty × unit_price',
    )
    remaining_claim_amount = fields.Float(
        string='Remaining Claim Amount',
        compute='_compute_claim_fields',
        store=True,
        readonly=True,
        digits=(16, 2),
        help='(planned_qty − claimed_qty) × unit_price',
    )

    # ── Resource Notes ────────────────────────────────────────────────────────
    tool_notes           = fields.Text(string='Tools Notes')
    equipment_notes      = fields.Text(string='Equipment / Machinery Notes')
    subcontractor_notes  = fields.Text(string='Subcontractor Notes')
    control_device_notes = fields.Text(string='Control Devices Notes')

    # ── Child lines ───────────────────────────────────────────────────────────
    material_ids = fields.One2many(
        'farm.material.consumption',
        'job_order_id',
        string='Material Consumption',
    )
    labour_ids = fields.One2many(
        'farm.labour.entry',
        'job_order_id',
        string='Labour Entries',
    )

    # ── Planned cost (from analysis line) ─────────────────────────────────────
    planned_cost = fields.Float(
        string='Planned Cost',
        compute='_compute_costs',
        store=True,
        digits=(16, 2),
        help='Cost total from the linked BOQ Analysis line.',
    )
    planned_material_cost = fields.Float(
        string='Planned Material Cost',
        compute='_compute_costs',
        store=True,
        digits=(16, 2),
        help='Sum of planned_cost from all material consumption lines.',
    )

    # ── Actual costs ─────────────────────────────────────────────────────────
    actual_material_cost = fields.Float(
        string='Actual Material Cost',
        compute='_compute_costs',
        store=True,
        digits=(16, 2),
    )
    actual_labour_cost = fields.Float(
        string='Actual Labour Cost',
        compute='_compute_costs',
        store=True,
        digits=(16, 2),
    )
    # Manual entry for subcontract and other costs not covered by lines
    actual_subcontract_cost = fields.Float(
        string='Actual Subcontract Cost',
        digits=(16, 2),
        default=0.0,
        tracking=True,
    )
    actual_other_cost = fields.Float(
        string='Other Actual Cost',
        digits=(16, 2),
        default=0.0,
        tracking=True,
        help='Any other actual cost not covered by materials or labour.',
    )
    actual_total_cost = fields.Float(
        string='Actual Total Cost',
        compute='_compute_costs',
        store=True,
        digits=(16, 2),
    )
    cost_variance = fields.Float(
        string='Cost Variance',
        compute='_compute_costs',
        store=True,
        digits=(16, 2),
        help='Actual total cost minus planned cost (positive = over budget).',
    )
    cost_variance_percent = fields.Float(
        string='Variance %',
        compute='_compute_costs',
        store=True,
        digits=(16, 2),
    )
    # Keep backward-compat alias
    cost_variance_pct = fields.Float(
        string='Variance % (legacy)',
        related='cost_variance_percent',
        store=False,
        readonly=True,
    )

    # ── Currency (for monetary widgets) ──────────────────────────────────────
    currency_id = fields.Many2one(
        'res.currency',
        related='analysis_id.currency_id',
        store=False,
        readonly=True,
    )

    # ── Counts for stat buttons ───────────────────────────────────────────────
    material_count = fields.Integer(
        string='# Materials',
        compute='_compute_counts',
    )
    labour_count = fields.Integer(
        string='# Labour',
        compute='_compute_counts',
    )
    progress_log_count = fields.Integer(
        string='# Progress Logs',
        compute='_compute_counts',
    )

    # ────────────────────────────────────────────────────────────────────────
    # Computed
    # ────────────────────────────────────────────────────────────────────────

    @api.depends('executed_qty', 'planned_qty')
    def _compute_progress(self):
        for rec in self:
            rec.progress_percent = (
                rec.executed_qty / rec.planned_qty * 100.0
                if rec.planned_qty else 0.0
            )

    @api.depends(
        'analysis_line_id', 'analysis_line_id.cost_total',
        'material_ids.planned_cost', 'material_ids.actual_cost',
        'labour_ids.total_cost',
        'actual_subcontract_cost',
        'actual_other_cost',
    )
    def _compute_costs(self):
        for rec in self:
            rec.planned_cost          = rec.analysis_line_id.cost_total if rec.analysis_line_id else 0.0
            rec.planned_material_cost = sum(rec.material_ids.mapped('planned_cost'))
            rec.actual_material_cost  = sum(rec.material_ids.mapped('actual_cost'))
            rec.actual_labour_cost    = sum(rec.labour_ids.mapped('total_cost'))
            rec.actual_total_cost     = (
                rec.actual_material_cost
                + rec.actual_labour_cost
                + (rec.actual_subcontract_cost or 0.0)
                + (rec.actual_other_cost or 0.0)
            )
            planned = rec.planned_cost
            actual  = rec.actual_total_cost
            rec.cost_variance         = actual - planned
            rec.cost_variance_percent = (
                (actual - planned) / planned * 100.0 if planned else 0.0
            )

    @api.depends('material_ids', 'labour_ids', 'progress_log_ids')
    def _compute_counts(self):
        for rec in self:
            rec.material_count    = len(rec.material_ids)
            rec.labour_count      = len(rec.labour_ids)
            rec.progress_log_count = len(rec.progress_log_ids)

    @api.depends(
        'division_id', 'division_id.name',
        'subdivision_id', 'subdivision_id.name',
        'sub_subdivision_id', 'sub_subdivision_id.name',
    )
    def _compute_boq_hierarchy(self):
        """Build a readable breadcrumb: Division › Subdivision › Sub-Subdivision."""
        for rec in self:
            parts = []
            if rec.division_id:
                parts.append(rec.division_id.name)
            if rec.subdivision_id:
                parts.append(rec.subdivision_id.name)
            if rec.sub_subdivision_id:
                parts.append(rec.sub_subdivision_id.name)
            rec.boq_hierarchy = ' › '.join(parts) if parts else ''

    @api.depends('boq_line_id', 'boq_line_id.display_type', 'boq_line_id.parent_id')
    def _compute_is_structural_line(self):
        """Flag JOs whose BOQ line is a structural header, not a real subitem.

        A valid executable subitem has display_type=False AND parent_id set.
        Any other combination means the JO was created from a section/header row
        and cannot represent real work.
        """
        for rec in self:
            bl = rec.boq_line_id
            if bl:
                rec.is_structural_line = bool(bl.display_type) or not bl.parent_id
            else:
                rec.is_structural_line = False

    @api.depends('accepted_qty', 'planned_qty', 'unit_price', 'claimed_qty')
    def _compute_claim_fields(self):
        """Compute all claim/extract KPIs from accepted qty and contract qty.

        Formulas:
          claim_percent        = accepted_qty / planned_qty × 100
          claim_amount         = accepted_qty × unit_price
          remaining_claim_qty  = planned_qty − claimed_qty
          remaining_claim_amount = remaining_claim_qty × unit_price
        """
        for rec in self:
            planned   = rec.planned_qty or 0.0
            accepted  = rec.accepted_qty or 0.0
            claimed   = rec.claimed_qty or 0.0
            up        = rec.unit_price or 0.0

            rec.claim_percent         = (accepted / planned * 100.0) if planned else 0.0
            rec.claim_amount          = accepted * up
            rec.remaining_claim_qty   = planned - claimed
            rec.remaining_claim_amount = (planned - claimed) * up

    @api.onchange('division_id')
    def _onchange_division_id_department(self):
        """Auto-populate department from division name when user changes division."""
        if not self.division_id:
            return
        name = (self.division_id.name or '').lower()
        code = (self.division_id.code or '').upper()
        # Check code first (more stable), fall back to name substring
        code_map = {
            'CW': 'civil',   'SW': 'structure', 'AW': 'arch',
            'MW': 'mechanical', 'EW': 'electrical',
            'FW': 'arch',    # Finishing Works → Architectural
        }
        if code and code in code_map:
            self.department = code_map[code]
        elif 'civil' in name:
            self.department = 'civil'
        elif 'struct' in name:
            self.department = 'structure'
        elif 'arch' in name or 'finish' in name:
            self.department = 'arch'
        elif 'mech' in name:
            self.department = 'mechanical'
        elif 'elec' in name:
            self.department = 'electrical'
        else:
            self.department = 'other'

    @api.onchange('boq_line_id')
    def _onchange_boq_line_id_department(self):
        """When BOQ line changes, re-trigger department computation via division."""
        # division_id is a related stored field so it updates synchronously
        # after boq_line_id changes; call the division onchange to set department.
        self._onchange_division_id_department()

    # ────────────────────────────────────────────────────────────────────────
    # ORM overrides
    # ────────────────────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env['ir.sequence']
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = seq.next_by_code('farm.job.order') or _('New')
        return super().create(vals_list)

    # ────────────────────────────────────────────────────────────────────────
    # Validation
    # ────────────────────────────────────────────────────────────────────────

    @api.constrains('project_id', 'boq_line_id', 'analysis_id')
    def _check_traceability(self):
        for rec in self:
            if not rec.project_id:
                raise ValidationError(_('Job Order requires a Farm Project.'))
            if not rec.boq_line_id:
                raise ValidationError(_('Job Order requires a BOQ Subitem.'))
            if rec.analysis_id and rec.analysis_id.project_id != rec.project_id:
                raise ValidationError(_(
                    'The selected BOQ Analysis belongs to project "%s", '
                    'not "%s".',
                    rec.analysis_id.project_id.name,
                    rec.project_id.name,
                ))

    @api.constrains('boq_line_id')
    def _check_boq_line_is_subitem(self):
        """Block Job Orders linked to structural section/header rows.

        Only real executable subitems (display_type=False AND parent_id set)
        are valid targets for Job Orders.  Sections, subdivisions, and
        sub-subdivision headers carry no quantity or costing data and must
        never be used as Job Order source lines.
        """
        for rec in self:
            bl = rec.boq_line_id
            if not bl:
                continue
            if bl.display_type:
                raise ValidationError(_(
                    'Job Order "%s" cannot be linked to structural BOQ row '
                    '"%s" (type: %s).\n\n'
                    'Job Orders can only be generated from executable subitems '
                    '(BOQ lines with no display type and a parent sub-subdivision).',
                    rec.name or 'New',
                    bl.name,
                    dict(bl._fields['display_type'].selection).get(
                        bl.display_type, bl.display_type
                    ),
                ))
            if not bl.parent_id:
                raise ValidationError(_(
                    'Job Order "%s" is linked to BOQ line "%s" which has no '
                    'parent sub-subdivision row.\n\n'
                    'Only subitems nested under a Sub-Subdivision are '
                    'valid execution targets.',
                    rec.name or 'New',
                    bl.name,
                ))

    # ────────────────────────────────────────────────────────────────────────
    # State machine
    # ────────────────────────────────────────────────────────────────────────

    def action_set_ready(self):
        """Draft → Ready.  Validates that an approved analysis is linked."""
        for rec in self.filtered(lambda r: r.state == 'draft'):
            if not rec.analysis_id:
                raise UserError(_(
                    'Cannot set Job Order "%s" to Ready: no BOQ Analysis is linked.',
                    rec.name,
                ))
            if rec.analysis_id.analysis_state != 'approved':
                raise UserError(_(
                    'Cannot set Job Order "%s" to Ready: BOQ Analysis "%s" '
                    'is not yet approved.',
                    rec.name, rec.analysis_id.name,
                ))
            rec.state = 'ready'

    def action_start(self):
        """Ready → In Progress.  Records actual start date."""
        for rec in self.filtered(lambda r: r.state == 'ready'):
            rec.write({
                'state': 'in_progress',
                'actual_start_date': fields.Date.today(),
            })

    def action_complete(self):
        """In Progress → Completed.  Requires at least some executed qty."""
        for rec in self.filtered(lambda r: r.state == 'in_progress'):
            if rec.executed_qty <= 0:
                raise UserError(_(
                    'Cannot complete Job Order "%s": executed quantity is still 0. '
                    'Please enter the executed quantity on the Progress tab.',
                    rec.name,
                ))
            rec.write({
                'state': 'completed',
                'actual_end_date': fields.Date.today(),
            })

    def action_close(self):
        """Completed → Closed.  Enforces 100 % progress."""
        for rec in self.filtered(lambda r: r.state == 'completed'):
            if rec.progress_percent < 100.0:
                raise UserError(_(
                    'Job Order "%s" is only %.1f%% complete. '
                    'Set executed qty to planned qty before closing.',
                    rec.name, rec.progress_percent,
                ))
            rec.state = 'closed'

    def action_reset_draft(self):
        """Ready / In Progress → Draft (manager correction)."""
        self.filtered(
            lambda r: r.state in ('ready', 'in_progress')
        ).write({
            'state': 'draft',
            'actual_start_date': False,
        })

    # ────────────────────────────────────────────────────────────────────────
    # jo_stage progression (primary operational workflow)
    #
    # Each action advances jo_stage AND syncs the legacy state field so
    # existing server actions, BOQ analysis summaries, and reports remain
    # consistent without code changes.
    #
    # Stage parity:
    #   new               → draft
    #   approved          → ready
    #   in_progress       → in_progress
    #   under_inspection  → in_progress   (still executing, awaiting result)
    #   accepted          → completed
    #   ready_for_claim   → completed
    #   claimed           → completed
    #   closed            → closed
    # ────────────────────────────────────────────────────────────────────────

    def action_jo_approve(self):
        """new → approved.  Validates analysis is approved."""
        for rec in self.filtered(lambda r: r.jo_stage == 'new'):
            if not rec.analysis_id:
                raise UserError(_(
                    'Cannot approve "%s": no BOQ Analysis is linked.', rec.name,
                ))
            if rec.analysis_id.analysis_state != 'approved':
                raise UserError(_(
                    'Cannot approve "%s": BOQ Analysis "%s" is not yet approved.',
                    rec.name, rec.analysis_id.name,
                ))
            rec.write({'jo_stage': 'approved', 'state': 'ready'})

    def action_jo_start(self):
        """approved → in_progress.  Records actual start date."""
        for rec in self.filtered(lambda r: r.jo_stage == 'approved'):
            rec.write({
                'jo_stage': 'in_progress',
                'state': 'in_progress',
                'actual_start_date': fields.Date.today(),
            })

    def action_jo_request_inspection(self):
        """in_progress → under_inspection.  Requires executed qty > 0."""
        for rec in self.filtered(lambda r: r.jo_stage == 'in_progress'):
            if rec.executed_qty <= 0:
                raise UserError(_(
                    'Cannot request inspection on "%s": executed quantity is still 0.',
                    rec.name,
                ))
            rec.write({
                'jo_stage': 'under_inspection',
                # state stays in_progress — execution continues until accepted
                'inspection_request_date': fields.Date.today(),
                'inspection_result': 'pending',
            })

    def action_jo_accept(self):
        """under_inspection → accepted.  Requires inspection result is Pass or Conditional."""
        for rec in self.filtered(lambda r: r.jo_stage == 'under_inspection'):
            if rec.inspection_result not in ('passed', 'conditional'):
                raise UserError(_(
                    'Cannot accept "%s": inspection result must be Passed or Conditional.',
                    rec.name,
                ))
            rec.write({
                'jo_stage': 'accepted',
                'state': 'completed',
                'actual_end_date': fields.Date.today(),
            })

    def action_jo_ready_for_claim(self):
        """accepted → ready_for_claim.  Requires accepted_qty > 0."""
        for rec in self.filtered(lambda r: r.jo_stage == 'accepted'):
            if rec.accepted_qty <= 0:
                raise UserError(_(
                    'Set Accepted Qty > 0 on the Inspection tab before marking '
                    '"%s" as Ready for Claim.',
                    rec.name,
                ))
            rec.write({'jo_stage': 'ready_for_claim'})

    def action_jo_create_claim(self):
        """ready_for_claim → claimed.  Auto-fills claimed_qty from accepted_qty."""
        for rec in self.filtered(lambda r: r.jo_stage == 'ready_for_claim'):
            claim_qty = rec.claimed_qty or rec.accepted_qty
            rec.write({
                'jo_stage': 'claimed',
                'claimed_qty': claim_qty,
            })

    def action_jo_close(self):
        """claimed → closed."""
        self.filtered(lambda r: r.jo_stage == 'claimed').write(
            {'jo_stage': 'closed', 'state': 'closed'}
        )

    def action_jo_reset_to_new(self):
        """Manager override: revert to New from any pre-accepted stage."""
        reversible = ('approved', 'in_progress', 'under_inspection')
        self.filtered(lambda r: r.jo_stage in reversible).write({
            'jo_stage': 'new',
            'state': 'draft',
            'actual_start_date': False,
            'inspection_request_date': False,
            'inspection_result': 'pending',
        })

    # ────────────────────────────────────────────────────────────────────────
    # Materials
    # ────────────────────────────────────────────────────────────────────────

    def action_request_materials(self):
        """Change all planned (draft) material lines to 'requested' and optionally
        create an internal stock picking for physical issuance tracking.
        """
        self.ensure_one()
        planned = self.material_ids.filtered(
            lambda m: m.state == 'draft'
        )
        if not planned:
            raise UserError(_(
                'No material lines in "Draft" status to request.\n'
                'Add material consumption lines on the Materials tab first.\n'
                'Tip: Use "Populate Resources" if a BOQ template is linked.'
            ))

        # Attempt to create a stock picking — wrapped in try/except so the
        # method does not fail if stock data is incomplete.
        picking_created = False
        try:
            picking_created = self._create_material_picking(planned)
        except Exception:
            # Stock picking creation failed — fall back to state update only.
            pass

        if not picking_created:
            planned.write({'state': 'requested'})

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Materials Requested'),
                'message': _(
                    '%d material line(s) moved to "Requested" status.',
                    len(planned),
                ),
                'type': 'success',
                'sticky': False,
            },
        }

    def _create_material_picking(self, material_lines):
        """Create an internal stock.picking for the given material lines.

        Returns True if a picking was created and the lines were linked;
        False if creation was skipped (no picking type, no products etc.)
        """
        # Only handle lines with a product set
        product_lines = material_lines.filtered(lambda m: m.product_id)
        if not product_lines:
            material_lines.write({'state': 'requested'})
            return True

        # Find an active internal picking type
        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'internal'),
        ], limit=1)
        if not picking_type:
            material_lines.write({'state': 'requested'})
            return True

        src_loc = (
            picking_type.default_location_src_id
            or self.env.ref('stock.stock_location_stock', raise_if_not_found=False)
        )
        dst_loc = (
            picking_type.default_location_dest_id
            or self.env.ref('stock.stock_location_output', raise_if_not_found=False)
        )
        if not src_loc or not dst_loc:
            material_lines.write({'state': 'requested'})
            return True

        move_vals = []
        for mat in product_lines:
            qty = mat.requested_qty or mat.planned_qty or 1.0
            move_vals.append((0, 0, {
                'name':            mat.description or mat.product_id.name,
                'product_id':      mat.product_id.id,
                'product_uom_qty': qty,
                'product_uom':     (mat.uom_id or mat.product_id.uom_id).id,
                'location_id':     (mat.source_location_id or src_loc).id,
                'location_dest_id': (mat.dest_location_id or dst_loc).id,
            }))

        if not move_vals:
            material_lines.write({'state': 'requested'})
            return True

        picking = self.env['stock.picking'].create({
            'picking_type_id':  picking_type.id,
            'location_id':      src_loc.id,
            'location_dest_id': dst_loc.id,
            'move_ids':         move_vals,
            'origin':           self.name,
        })

        # Link picking back to lines; lines without product just get state update
        for mat in product_lines:
            mat.write({
                'state':            'requested',
                'stock_picking_id': picking.id,
            })
        non_product = material_lines - product_lines
        non_product.write({'state': 'requested'})
        return True

    # ────────────────────────────────────────────────────────────────────────
    # Progress logs
    # ────────────────────────────────────────────────────────────────────────

    def action_sync_progress_from_logs(self):
        """Set executed_qty = sum of all progress log increments."""
        self.ensure_one()
        total = sum(self.progress_log_ids.mapped('executed_increment'))
        self.executed_qty = total
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Progress Synced'),
                'message': _(
                    'Executed qty set to %.2f from %d log entries.',
                    total, len(self.progress_log_ids),
                ),
                'type': 'success',
                'sticky': False,
            },
        }

    # ────────────────────────────────────────────────────────────────────────
    # Stat button actions
    # ────────────────────────────────────────────────────────────────────────

    def action_view_materials(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Materials — %s') % self.name,
            'res_model': 'farm.material.consumption',
            'view_mode': 'list,form',
            'domain': [('job_order_id', '=', self.id)],
            'context': {'default_job_order_id': self.id},
        }

    def action_view_labour(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Labour — %s') % self.name,
            'res_model': 'farm.labour.entry',
            'view_mode': 'list,form',
            'domain': [('job_order_id', '=', self.id)],
            'context': {'default_job_order_id': self.id},
        }

    def action_view_analysis(self):
        self.ensure_one()
        if not self.analysis_id:
            raise UserError(_('No BOQ Analysis linked to this Job Order.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('BOQ Analysis'),
            'res_model': 'farm.boq.analysis',
            'view_mode': 'form',
            'res_id': self.analysis_id.id,
        }

    def action_view_progress_logs(self):
        """Open progress log entries for this Job Order."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Progress Logs — %s') % self.name,
            'res_model': 'farm.job.progress.log',
            'view_mode': 'list,form',
            'domain': [('job_order_id', '=', self.id)],
            'context': {'default_job_order_id': self.id},
        }

    # ────────────────────────────────────────────────────────────────────────
    # Resource population from template
    # ────────────────────────────────────────────────────────────────────────

    def action_populate_resources(self):
        """Populate planned material consumption lines from the BOQ line template.

        Safe rules:
        - Only runs if a template is linked to the BOQ subitem.
        - Skips products that are already present on existing material lines
          (idempotent: running twice does not create duplicates).
        - Does NOT overwrite existing lines.
        """
        self.ensure_one()
        template = self.boq_line_id.template_id if self.boq_line_id else False
        if not template:
            raise UserError(_(
                'No Cost Item Template is linked to BOQ subitem "%s".\n\n'
                'Assign a template to the BOQ subitem first, or add material '
                'lines manually on the Materials tab.',
                self.boq_line_id.name if self.boq_line_id else _('(none)'),
            ))

        if not template.material_ids:
            raise UserError(_(
                'The linked template "%s" has no material lines to populate.',
                template.name,
            ))

        # Determine which products already have a line (idempotency)
        existing_products = set(self.material_ids.mapped('product_id').ids)

        Material = self.env['farm.material.consumption']
        created = 0
        skipped = 0
        for mat in template.material_ids:
            if not mat.product_id:
                skipped += 1
                continue
            if mat.product_id.id in existing_products:
                skipped += 1
                continue
            Material.create({
                'job_order_id': self.id,
                'product_id':   mat.product_id.id,
                'description':  mat.description or mat.product_id.name,
                'uom_id':       (mat.uom_id or mat.product_id.uom_id).id,
                'planned_qty':  mat.quantity or 1.0,
                'unit_cost':    mat.unit_price or 0.0,
            })
            created += 1

        msg_type = 'success' if created else 'warning'
        if created and skipped:
            message = _('%d material line(s) created; %d skipped (already present or no product).', created, skipped)
        elif created:
            message = _('%d material line(s) created from template "%s".', created, template.name)
        else:
            message = _('No new material lines created — all template products already exist on this Job Order.')

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Resources Populated'),
                'message': message,
                'type': msg_type,
                'sticky': False,
            },
        }
