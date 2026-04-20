from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class FarmJobOrder(models.Model):
    """Job Order — atomic unit of field execution.

    Workflow:
        draft → approved → in_progress → handover_requested
        → under_inspection → [partially_accepted | accepted]
        → ready_for_claim → claimed → closed

    Business rule (critical):
        ``approved_qty`` is the ONLY quantity that drives progress percentages
        and financial claim amounts.  ``executed_qty`` is a site measurement
        only; it does NOT generate claim entitlements.

        item_progress_percent = approved_qty / contract_qty × 100
        approved_amount       = approved_qty × unit_price
        claimable_amount      = (approved_qty − claimed_qty) × unit_price
    """

    _name        = 'farm.job.order'
    _description = 'Farm Job Order'
    _order       = 'project_id, display_code, name'
    _rec_name    = 'name'
    _inherit     = ['mail.thread', 'mail.activity.mixin']

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

    # ── BOQ hierarchy path ────────────────────────────────────────────────────
    boq_hierarchy = fields.Char(
        string='BOQ Hierarchy',
        compute='_compute_boq_hierarchy',
        store=True,
        readonly=True,
    )

    # ── Data-integrity flag ────────────────────────────────────────────────────
    is_structural_line = fields.Boolean(
        string='Structural Line?',
        compute='_compute_is_structural_line',
        store=True,
        readonly=True,
    )

    # ── Department ───────────────────────────────────────────────────────────
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
    discipline = fields.Char(string='Discipline')

    # ── Scope / planning ──────────────────────────────────────────────────────
    planned_qty = fields.Float(
        string='Contract Qty',
        digits=(16, 2),
        required=True,
        default=1.0,
    )
    unit_id = fields.Many2one('uom.uom', string='Unit', ondelete='set null')
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
    actual_start_date  = fields.Date(string='Actual Start',  readonly=True, copy=False)
    actual_end_date    = fields.Date(string='Actual End',    readonly=True, copy=False)

    # ── Execution (site measurement only — does NOT drive claims) ─────────────
    executed_qty = fields.Float(
        string='Executed Qty',
        digits=(16, 2),
        default=0.0,
        tracking=True,
        help=(
            'Physical quantity measured on site.  For information only.\n'
            'Progress % and claim amounts are driven by APPROVED QTY, not this field.'
        ),
    )
    progress_log_ids = fields.One2many(
        'farm.job.progress.log',
        'job_order_id',
        string='Progress Logs',
    )

    # ── Approval quantities (drives ALL financial / progress KPIs) ────────────
    approved_qty = fields.Float(
        string='Approved Qty',
        digits=(16, 2),
        default=0.0,
        tracking=True,
        copy=False,
        help=(
            'Quantity formally approved after inspection.\n'
            'THIS is the quantity that drives:\n'
            '  • progress_percent = approved_qty / contract_qty × 100\n'
            '  • approved_amount  = approved_qty × unit_price\n'
            '  • claimable_amount = (approved_qty − claimed_qty) × unit_price'
        ),
    )
    rejected_qty = fields.Float(
        string='Rejected Qty',
        digits=(16, 2),
        default=0.0,
        tracking=True,
        copy=False,
        help='Quantity explicitly rejected during inspection.  Item returns to In Progress for rework.',
    )

    # ── Backward-compat alias (do not use in new code) ────────────────────────
    accepted_qty = fields.Float(
        string='Accepted Qty',
        related='approved_qty',
        store=False,
        readonly=True,
    )

    # ── Progress (based on approved_qty, NOT executed_qty) ───────────────────
    progress_percent = fields.Float(
        string='Progress (%)',
        compute='_compute_progress',
        store=True,
        digits=(16, 1),
        help='approved_qty / contract_qty × 100',
    )

    # ── Workflow stages ───────────────────────────────────────────────────────
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

    jo_stage = fields.Selection(
        selection=[
            ('draft',               'Draft'),
            ('approved',            'Approved'),
            ('in_progress',         'In Progress'),
            ('handover_requested',  'Handover Requested'),
            ('under_inspection',    'Under Inspection'),
            ('partially_accepted',  'Partially Accepted'),
            ('accepted',            'Accepted'),
            ('ready_for_claim',     'Ready for Claim'),
            ('claimed',             'Claimed'),
            ('closed',              'Closed'),
        ],
        string='JO Stage',
        default='draft',
        required=True,
        index=True,
        tracking=True,
        copy=False,
        help=(
            'Draft → Approved → In Progress → Handover Requested '
            '→ Under Inspection → [Partially Accepted | Accepted] '
            '→ Ready for Claim → Claimed → Closed.'
        ),
    )

    # ── Inspection ────────────────────────────────────────────────────────────
    inspection_request_date = fields.Date(
        string='Inspection Request Date',
        tracking=True,
        copy=False,
    )
    inspection_date = fields.Date(
        string='Inspection Date',
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
    handover_status = fields.Selection(
        selection=[
            ('pending',   'Pending'),
            ('requested', 'Requested'),
            ('received',  'Received'),
            ('rejected',  'Rejected'),
        ],
        string='Handover Status',
        default='pending',
        tracking=True,
        copy=False,
    )
    handover_notes  = fields.Text(string='Handover Notes')
    inspection_notes = fields.Text(string='Inspection Notes')

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

    # All claim KPIs computed from approved_qty + claimed_qty + unit_price
    approved_amount = fields.Float(
        string='Approved Amount',
        compute='_compute_claim_fields',
        store=True,
        readonly=True,
        digits=(16, 2),
        help='approved_qty × unit_price',
    )
    claimable_qty = fields.Float(
        string='Claimable Qty',
        compute='_compute_claim_fields',
        store=True,
        readonly=True,
        digits=(16, 2),
        help='approved_qty − claimed_qty (ready to submit in next claim)',
    )
    claimable_amount = fields.Float(
        string='Claimable Amount',
        compute='_compute_claim_fields',
        store=True,
        readonly=True,
        digits=(16, 2),
        help='claimable_qty × unit_price',
    )
    claim_amount = fields.Float(
        string='Claimed Amount',
        compute='_compute_claim_fields',
        store=True,
        readonly=True,
        digits=(16, 2),
        help='claimed_qty × unit_price — total amount already submitted in claims',
    )
    remaining_qty = fields.Float(
        string='Remaining Qty',
        compute='_compute_claim_fields',
        store=True,
        readonly=True,
        digits=(16, 2),
        help='planned_qty − approved_qty — still awaiting approval',
    )
    remaining_amount = fields.Float(
        string='Remaining Amount',
        compute='_compute_claim_fields',
        store=True,
        readonly=True,
        digits=(16, 2),
        help='remaining_qty × unit_price',
    )
    # Legacy KPI aliases (kept for backward-compat views)
    claim_percent = fields.Float(
        string='Claim %',
        compute='_compute_claim_fields',
        store=True,
        readonly=True,
        digits=(16, 2),
        help='approved_qty / planned_qty × 100',
    )
    remaining_claim_qty = fields.Float(
        string='Remaining Claim Qty',
        compute='_compute_claim_fields',
        store=True,
        readonly=True,
        digits=(16, 2),
    )
    remaining_claim_amount = fields.Float(
        string='Remaining Claim Amount',
        compute='_compute_claim_fields',
        store=True,
        readonly=True,
        digits=(16, 2),
    )

    # ── Notes ─────────────────────────────────────────────────────────────────
    notes             = fields.Text(string='General Notes')
    instruction_notes = fields.Text(string='Instructions')
    tool_notes           = fields.Text(string='Tools Notes')
    equipment_notes      = fields.Text(string='Equipment / Machinery Notes')
    subcontractor_notes  = fields.Text(string='Subcontractor Notes')
    control_device_notes = fields.Text(string='Control Devices Notes')

    # ── Child lines ───────────────────────────────────────────────────────────
    material_ids = fields.One2many(
        'farm.material.consumption', 'job_order_id', string='Material Consumption',
    )
    labour_ids = fields.One2many(
        'farm.labour.entry', 'job_order_id', string='Labour Entries',
    )

    # ── Costs ─────────────────────────────────────────────────────────────────
    planned_cost = fields.Float(
        string='Planned Cost',
        compute='_compute_costs', store=True, digits=(16, 2),
    )
    planned_material_cost = fields.Float(
        string='Planned Material Cost',
        compute='_compute_costs', store=True, digits=(16, 2),
    )
    actual_material_cost = fields.Float(
        string='Actual Material Cost',
        compute='_compute_costs', store=True, digits=(16, 2),
    )
    actual_labour_cost = fields.Float(
        string='Actual Labour Cost',
        compute='_compute_costs', store=True, digits=(16, 2),
    )
    actual_subcontract_cost = fields.Float(
        string='Actual Subcontract Cost', digits=(16, 2), default=0.0, tracking=True,
    )
    actual_other_cost = fields.Float(
        string='Other Actual Cost', digits=(16, 2), default=0.0, tracking=True,
    )
    actual_total_cost = fields.Float(
        string='Actual Total Cost',
        compute='_compute_costs', store=True, digits=(16, 2),
    )
    cost_variance = fields.Float(
        string='Cost Variance',
        compute='_compute_costs', store=True, digits=(16, 2),
    )
    cost_variance_percent = fields.Float(
        string='Variance %',
        compute='_compute_costs', store=True, digits=(16, 2),
    )
    cost_variance_pct = fields.Float(
        string='Variance % (legacy)',
        related='cost_variance_percent', store=False, readonly=True,
    )

    # ── Currency ──────────────────────────────────────────────────────────────
    currency_id = fields.Many2one(
        'res.currency',
        related='analysis_id.currency_id',
        store=False,
        readonly=True,
    )

    # ── Stat-button counts ───────────────────────────────────────────────────
    material_count     = fields.Integer(compute='_compute_counts')
    labour_count       = fields.Integer(compute='_compute_counts')
    progress_log_count = fields.Integer(compute='_compute_counts')

    # ────────────────────────────────────────────────────────────────────────
    # Computed methods
    # ────────────────────────────────────────────────────────────────────────

    @api.depends('approved_qty', 'planned_qty')
    def _compute_progress(self):
        """Progress % is driven by APPROVED QTY, not executed qty."""
        for rec in self:
            rec.progress_percent = (
                rec.approved_qty / rec.planned_qty * 100.0
                if rec.planned_qty else 0.0
            )

    @api.depends('approved_qty', 'planned_qty', 'unit_price', 'claimed_qty')
    def _compute_claim_fields(self):
        """Compute all financial KPIs.

        Core formula:
          approved_amount   = approved_qty × unit_price
          claimable_qty     = max(0, approved_qty − claimed_qty)
          claimable_amount  = claimable_qty × unit_price
          claim_amount      = claimed_qty × unit_price  (already submitted)
          remaining_qty     = max(0, planned_qty − approved_qty)
          remaining_amount  = remaining_qty × unit_price
          claim_percent     = approved_qty / planned_qty × 100
        """
        for rec in self:
            planned   = rec.planned_qty  or 0.0
            approved  = rec.approved_qty or 0.0
            claimed   = rec.claimed_qty  or 0.0
            up        = rec.unit_price   or 0.0

            claimable = max(0.0, approved - claimed)
            remaining = max(0.0, planned  - approved)

            rec.approved_amount        = approved  * up
            rec.claimable_qty          = claimable
            rec.claimable_amount       = claimable * up
            rec.claim_amount           = claimed   * up
            rec.remaining_qty          = remaining
            rec.remaining_amount       = remaining * up
            rec.claim_percent          = (approved / planned * 100.0) if planned else 0.0
            # Legacy aliases
            rec.remaining_claim_qty    = claimable
            rec.remaining_claim_amount = claimable * up

    @api.depends(
        'analysis_line_id', 'analysis_line_id.cost_total',
        'material_ids.planned_cost', 'material_ids.actual_cost',
        'labour_ids.total_cost',
        'actual_subcontract_cost', 'actual_other_cost',
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
                + (rec.actual_other_cost       or 0.0)
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
            rec.material_count     = len(rec.material_ids)
            rec.labour_count       = len(rec.labour_ids)
            rec.progress_log_count = len(rec.progress_log_ids)

    @api.depends(
        'division_id', 'division_id.name',
        'subdivision_id', 'subdivision_id.name',
        'sub_subdivision_id', 'sub_subdivision_id.name',
    )
    def _compute_boq_hierarchy(self):
        for rec in self:
            parts = filter(None, [
                rec.division_id.name        if rec.division_id        else '',
                rec.subdivision_id.name     if rec.subdivision_id     else '',
                rec.sub_subdivision_id.name if rec.sub_subdivision_id else '',
            ])
            rec.boq_hierarchy = ' › '.join(parts)

    @api.depends('boq_line_id', 'boq_line_id.display_type', 'boq_line_id.parent_id')
    def _compute_is_structural_line(self):
        for rec in self:
            bl = rec.boq_line_id
            rec.is_structural_line = bool(bl and (bl.display_type or not bl.parent_id))

    # ── Onchange helpers ──────────────────────────────────────────────────────

    @api.onchange('division_id')
    def _onchange_division_id_department(self):
        if not self.division_id:
            return
        name = (self.division_id.name or '').lower()
        code = (self.division_id.code or '').upper()
        code_map = {
            'CW': 'civil', 'SW': 'structure', 'AW': 'arch',
            'MW': 'mechanical', 'EW': 'electrical', 'FW': 'arch',
        }
        if code and code in code_map:
            self.department = code_map[code]
        elif 'civil'   in name: self.department = 'civil'
        elif 'struct'  in name: self.department = 'structure'
        elif 'arch'    in name or 'finish' in name: self.department = 'arch'
        elif 'mech'    in name: self.department = 'mechanical'
        elif 'elec'    in name: self.department = 'electrical'
        else:                   self.department = 'other'

    @api.onchange('boq_line_id')
    def _onchange_boq_line_id_department(self):
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
    # Constraints
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
                    'BOQ Analysis "%s" belongs to project "%s", not "%s".',
                    rec.analysis_id.name,
                    rec.analysis_id.project_id.name,
                    rec.project_id.name,
                ))

    @api.constrains('boq_line_id')
    def _check_boq_line_is_subitem(self):
        for rec in self:
            bl = rec.boq_line_id
            if not bl:
                continue
            if bl.display_type:
                raise ValidationError(_(
                    'Job Order "%s" cannot be linked to structural BOQ row "%s".\n'
                    'Only executable subitems (no display type, with parent) are valid.',
                    rec.name or 'New', bl.name,
                ))
            if not bl.parent_id:
                raise ValidationError(_(
                    'BOQ line "%s" has no parent sub-subdivision.\n'
                    'Only subitems nested under a Sub-Subdivision are valid execution targets.',
                    bl.name,
                ))

    # ────────────────────────────────────────────────────────────────────────
    # STATE MACHINE  —  10-stage operational workflow
    #
    # Stage            jo_stage value         Legacy state
    # ─────────────────────────────────────────────────────
    # Draft            draft                  draft
    # Approved         approved               ready
    # In Progress      in_progress            in_progress
    # Handover Req.    handover_requested     in_progress
    # Under Inspect.   under_inspection       in_progress
    # Partially Acc.   partially_accepted     completed
    # Accepted         accepted               completed
    # Ready for Claim  ready_for_claim        completed
    # Claimed          claimed                completed
    # Closed           closed                 closed
    # ────────────────────────────────────────────────────────────────────────

    # ── 1. Approve JO (draft → approved) ─────────────────────────────────────
    def action_jo_approve(self):
        for rec in self.filtered(lambda r: r.jo_stage == 'draft'):
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

    # ── 2. Start Execution (approved → in_progress) ───────────────────────────
    def action_jo_start_execution(self):
        for rec in self.filtered(lambda r: r.jo_stage == 'approved'):
            rec.write({
                'jo_stage': 'in_progress',
                'state':    'in_progress',
                'actual_start_date': fields.Date.today(),
            })

    # Keep old name as alias for backward compat
    def action_jo_start(self):
        return self.action_jo_start_execution()

    # ── 3. Request Handover (in_progress → handover_requested) ───────────────
    def action_jo_request_handover(self):
        """Requires executed_qty > 0 before handover can be requested."""
        for rec in self.filtered(lambda r: r.jo_stage == 'in_progress'):
            if rec.executed_qty <= 0:
                raise UserError(_(
                    'Cannot request handover on "%s": executed quantity is still 0.\n'
                    'Enter the executed quantity on the Execution Progress tab first.',
                    rec.name,
                ))
            rec.write({
                'jo_stage':       'handover_requested',
                'handover_status': 'requested',
            })

    # Keep old name as alias
    def action_jo_request_inspection(self):
        return self.action_jo_request_handover()

    # ── 4. Start Inspection (handover_requested → under_inspection) ──────────
    def action_jo_start_inspection(self):
        for rec in self.filtered(lambda r: r.jo_stage == 'handover_requested'):
            rec.write({
                'jo_stage': 'under_inspection',
                'handover_status': 'received',
                'inspection_request_date': fields.Date.today(),
                'inspection_result': 'pending',
            })

    # ── 5a. Approve Item (under_inspection → accepted) ────────────────────────
    def action_jo_approve_item(self):
        """Full approval: sets approved_qty = executed_qty if not already set."""
        for rec in self.filtered(lambda r: r.jo_stage == 'under_inspection'):
            approved_qty = rec.approved_qty or rec.executed_qty
            if approved_qty <= 0:
                raise UserError(_(
                    'Cannot approve "%s": set Approved Qty > 0 on the Inspection tab.',
                    rec.name,
                ))
            rec.write({
                'jo_stage':         'accepted',
                'state':            'completed',
                'approval_status':  'approved',
                'inspection_result': 'passed',
                'inspection_date':  fields.Date.today(),
                'actual_end_date':  fields.Date.today(),
                'approved_qty':     approved_qty,
            })

    # Old accept alias
    def action_jo_accept(self):
        return self.action_jo_approve_item()

    # ── 5b. Partially Approve (under_inspection → partially_accepted) ─────────
    def action_jo_partially_approve(self):
        """Partial approval: approved_qty must be set manually in the form.

        approved_qty must be > 0 and < executed_qty.
        The remainder is available for re-execution.
        """
        for rec in self.filtered(lambda r: r.jo_stage == 'under_inspection'):
            if rec.approved_qty <= 0:
                raise UserError(_(
                    'Set Approved Qty > 0 on the Inspection tab '
                    'before partially approving "%s".',
                    rec.name,
                ))
            if rec.executed_qty > 0 and rec.approved_qty >= rec.executed_qty:
                raise UserError(_(
                    'For partial approval, Approved Qty (%.2f) must be '
                    'less than Executed Qty (%.2f) on "%s".\n'
                    'Use "Approve Item" for full approval.',
                    rec.approved_qty, rec.executed_qty, rec.name,
                ))
            rejected = max(0.0, rec.executed_qty - rec.approved_qty)
            rec.write({
                'jo_stage':         'partially_accepted',
                'state':            'completed',
                'approval_status':  'approved',
                'inspection_result': 'conditional',
                'inspection_date':  fields.Date.today(),
                'rejected_qty':     rejected,
            })

    # ── 5c. Reject Item (under_inspection → in_progress) ─────────────────────
    def action_jo_reject_item(self):
        """Full rejection: item returns to In Progress for rework."""
        for rec in self.filtered(lambda r: r.jo_stage == 'under_inspection'):
            rec.write({
                'jo_stage':         'in_progress',
                'state':            'in_progress',
                'approval_status':  'rejected',
                'inspection_result': 'failed',
                'rejected_qty':     rec.executed_qty,
                'approved_qty':     0.0,
                'handover_status':  'rejected',
            })

    # ── 6. Mark Ready for Claim (accepted | partially_accepted → ready_for_claim)
    def action_jo_ready_for_claim(self):
        """Requires approved_qty > 0."""
        eligible = self.filtered(
            lambda r: r.jo_stage in ('accepted', 'partially_accepted')
        )
        for rec in eligible:
            if rec.approved_qty <= 0:
                raise UserError(_(
                    'Set Approved Qty > 0 before marking "%s" Ready for Claim.',
                    rec.name,
                ))
            rec.write({'jo_stage': 'ready_for_claim'})

    # ── 7. Create Claim Entry (ready_for_claim → claimed) ─────────────────────
    def action_jo_create_claim(self):
        """Cannot claim if approved_qty <= claimed_qty (nothing left to claim)."""
        for rec in self.filtered(lambda r: r.jo_stage == 'ready_for_claim'):
            if rec.approved_qty <= rec.claimed_qty:
                raise UserError(_(
                    'Cannot create claim for "%s": '
                    'Approved Qty (%.2f) must be greater than already Claimed Qty (%.2f).',
                    rec.name, rec.approved_qty, rec.claimed_qty,
                ))
            # Claim the full approved-but-unclaimed quantity
            claim_qty = rec.approved_qty - rec.claimed_qty
            new_claimed = (rec.claimed_qty or 0.0) + claim_qty
            rec.write({
                'jo_stage':   'claimed',
                'claimed_qty': new_claimed,
            })

    # ── 8. Close Item (claimed → closed) ──────────────────────────────────────
    def action_jo_close(self):
        self.filtered(lambda r: r.jo_stage == 'claimed').write(
            {'jo_stage': 'closed', 'state': 'closed'}
        )

    # ── Manager reset ─────────────────────────────────────────────────────────
    def action_jo_reset_to_new(self):
        """Reset to Draft from any pre-acceptance stage (manager only)."""
        reversible = (
            'approved', 'in_progress', 'handover_requested',
            'under_inspection',
        )
        self.filtered(lambda r: r.jo_stage in reversible).write({
            'jo_stage':               'draft',
            'state':                  'draft',
            'actual_start_date':      False,
            'inspection_request_date': False,
            'inspection_result':      'pending',
            'handover_status':        'pending',
            'rejected_qty':           0.0,
        })

    # Legacy reset alias
    def action_reset_draft(self):
        return self.action_jo_reset_to_new()

    # ────────────────────────────────────────────────────────────────────────
    # Materials
    # ────────────────────────────────────────────────────────────────────────

    def action_request_materials(self):
        self.ensure_one()
        planned = self.material_ids.filtered(lambda m: m.state == 'draft')
        if not planned:
            raise UserError(_(
                'No material lines in "Draft" status.\n'
                'Add material lines on the Materials tab first.'
            ))
        picking_created = False
        try:
            picking_created = self._create_material_picking(planned)
        except Exception:
            pass
        if not picking_created:
            planned.write({'state': 'requested'})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Materials Requested'),
                'message': _(
                    '%d material line(s) moved to "Requested" status.', len(planned),
                ),
                'type': 'success',
                'sticky': False,
            },
        }

    def _create_material_picking(self, material_lines):
        product_lines = material_lines.filtered(lambda m: m.product_id)
        if not product_lines:
            material_lines.write({'state': 'requested'})
            return True
        picking_type = self.env['stock.picking.type'].search(
            [('code', '=', 'internal')], limit=1
        )
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
                'name':             mat.description or mat.product_id.name,
                'product_id':       mat.product_id.id,
                'product_uom_qty':  qty,
                'product_uom':      (mat.uom_id or mat.product_id.uom_id).id,
                'location_id':      (mat.source_location_id or src_loc).id,
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
        for mat in product_lines:
            mat.write({'state': 'requested', 'stock_picking_id': picking.id})
        (material_lines - product_lines).write({'state': 'requested'})
        return True

    # ────────────────────────────────────────────────────────────────────────
    # Progress logs
    # ────────────────────────────────────────────────────────────────────────

    def action_sync_progress_from_logs(self):
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
                'type': 'success', 'sticky': False,
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
    # Resource population
    # ────────────────────────────────────────────────────────────────────────

    def action_populate_resources(self):
        self.ensure_one()
        template = self.boq_line_id.template_id if self.boq_line_id else False
        if not template:
            raise UserError(_(
                'No Cost Item Template is linked to BOQ subitem "%s".\n'
                'Assign a template first, or add material lines manually.',
                self.boq_line_id.name if self.boq_line_id else _('(none)'),
            ))
        if not template.material_ids:
            raise UserError(_(
                'Template "%s" has no material lines to populate.', template.name,
            ))
        existing_products = set(self.material_ids.mapped('product_id').ids)
        Material = self.env['farm.material.consumption']
        created = skipped = 0
        for mat in template.material_ids:
            if not mat.product_id or mat.product_id.id in existing_products:
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
            message = _('%d line(s) created; %d skipped.', created, skipped)
        elif created:
            message = _('%d material line(s) created from template "%s".', created, template.name)
        else:
            message = _('No new lines — all template products already exist on this Job Order.')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Resources Populated'),
                'message': message,
                'type': msg_type, 'sticky': False,
            },
        }
