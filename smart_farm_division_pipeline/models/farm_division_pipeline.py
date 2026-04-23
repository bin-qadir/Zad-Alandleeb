"""
Division Workflow Pipeline
==========================
One record per (project, division) pair.

Aggregates all Job Orders under a division and computes phase KPIs across
four workflow stages:

  Pre-Execution  — planning / material_request / procurement / resources / ready
  Execution      — in_progress / completed
  Control        — inspection / approval
  Financial      — claim
"""

from odoo import api, fields, models, _


# ── Phase constants ────────────────────────────────────────────────────────────

PIPELINE_PHASES = [
    # Pre-Execution
    ('planning',            'Planning'),
    ('material_request',    'Material Request'),
    ('procurement',         'Procurement'),
    ('resources',           'Resources'),
    ('ready_for_execution', 'Ready for Execution'),
    # Execution
    ('in_progress',         'In Progress'),
    ('completed',           'Completed'),
    # Control
    ('inspection',          'Inspection'),
    ('approval',            'Approval'),
    # Financial
    ('claim',               'Claim'),
]


class FarmDivisionPipeline(models.Model):
    """Division Workflow Pipeline.

    One record per (project_id, division_id).  All KPI fields are computed
    from the underlying farm.job.order records and their linked
    farm.material.request / purchase.order records.

    Use action_refresh_kpis() to force a recompute, or let the ORM recompute
    on demand via @api.depends.
    """

    _name        = 'farm.division.pipeline'
    _description = 'Division Workflow Pipeline'
    _rec_name    = 'display_name_full'
    _order       = 'project_id, sequence, id'
    _inherit     = ['mail.thread', 'mail.activity.mixin']

    # ── Identity ───────────────────────────────────────────────────────────────
    display_name_full = fields.Char(
        string='Pipeline',
        compute='_compute_display_name_full',
        store=True,
    )
    sequence = fields.Integer(string='Sequence', default=10)
    active   = fields.Boolean(string='Active', default=True)

    # ── Core Links ─────────────────────────────────────────────────────────────
    project_id = fields.Many2one(
        'farm.project',
        string='Project',
        required=True,
        ondelete='cascade',
        index=True,
        tracking=True,
    )
    division_id = fields.Many2one(
        'farm.division.work',
        string='Division',
        required=True,
        ondelete='restrict',
        index=True,
        tracking=True,
    )

    # ── Overall Pipeline Phase ─────────────────────────────────────────────────
    pipeline_phase = fields.Selection(
        selection=PIPELINE_PHASES,
        string='Pipeline Phase',
        default='planning',
        required=True,
        tracking=True,
        help=(
            'Current overall workflow phase for this division.\n'
            'Pre-Execution: Planning → Material Request → Procurement → Resources → Ready\n'
            'Execution: In Progress → Completed\n'
            'Control: Inspection → Approval\n'
            'Financial: Claim'
        ),
    )

    notes = fields.Text(string='Notes / Remarks')

    # ── Currency (from current company) ───────────────────────────────────────
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
        readonly=True,
    )

    # ── TOTAL ──────────────────────────────────────────────────────────────────
    total_jo_count = fields.Integer(
        string='Total JOs',
        compute='_compute_all_kpis',
        store=True,
    )

    # ── Pre-Execution KPIs ─────────────────────────────────────────────────────
    planning_count = fields.Integer(
        string='In Planning',
        compute='_compute_all_kpis',
        store=True,
        help='Job Orders still in draft stage (not yet approved).',
    )
    planning_pct = fields.Float(
        string='Planning (%)',
        compute='_compute_all_kpis',
        store=True,
        digits=(16, 1),
        help='% of JOs that have both planned start and end dates set.',
    )
    material_readiness_pct = fields.Float(
        string='Material Readiness (%)',
        compute='_compute_all_kpis',
        store=True,
        digits=(16, 1),
        help='% of JOs with at least one Material Request in approved/RFQ/ordered/received state.',
    )
    procurement_pct = fields.Float(
        string='Procurement (%)',
        compute='_compute_all_kpis',
        store=True,
        digits=(16, 1),
        help='% of JOs whose Material Requests have been converted to Purchase Orders (ordered or received).',
    )
    resources_pct = fields.Float(
        string='Resources (%)',
        compute='_compute_all_kpis',
        store=True,
        digits=(16, 1),
        help='% of JOs that have at least one labour entry or material consumption record.',
    )

    # ── Execution KPIs ─────────────────────────────────────────────────────────
    in_progress_count = fields.Integer(
        string='In Progress',
        compute='_compute_all_kpis',
        store=True,
    )
    waiting_inspection_count = fields.Integer(
        string='Waiting Inspection',
        compute='_compute_all_kpis',
        store=True,
        help='JOs that have submitted a handover request and are waiting for the inspector.',
    )
    under_inspection_count = fields.Integer(
        string='Under Inspection',
        compute='_compute_all_kpis',
        store=True,
    )

    # ── Approval KPIs ──────────────────────────────────────────────────────────
    approved_count = fields.Integer(
        string='Approved',
        compute='_compute_all_kpis',
        store=True,
        help='JOs that have passed inspection (accepted or partially accepted).',
    )
    rejected_count = fields.Integer(
        string='Rejected',
        compute='_compute_all_kpis',
        store=True,
        help='JOs where inspection failed or approval was rejected.',
    )

    # ── Financial KPIs ─────────────────────────────────────────────────────────
    claimed_count = fields.Integer(
        string='Claimed JOs',
        compute='_compute_all_kpis',
        store=True,
    )
    claimed_amount_total = fields.Float(
        string='Claimed Amount',
        compute='_compute_all_kpis',
        store=True,
        digits=(16, 2),
        help='Total amount already submitted in claims for this division.',
    )
    approved_amount_total = fields.Float(
        string='Approved Amount',
        compute='_compute_all_kpis',
        store=True,
        digits=(16, 2),
        help='Total approved (invoice-eligible) amount: approved_qty × unit_price.',
    )
    contract_amount_total = fields.Float(
        string='Contract Amount',
        compute='_compute_all_kpis',
        store=True,
        digits=(16, 2),
        help='Total contract value: planned_qty × unit_price for all JOs in this division.',
    )
    remaining_claim_total = fields.Float(
        string='Remaining Claimable',
        compute='_compute_all_kpis',
        store=True,
        digits=(16, 2),
    )

    # ── SQL Constraints ────────────────────────────────────────────────────────
    _sql_constraints = [
        (
            'unique_project_division',
            'UNIQUE(project_id, division_id)',
            'A pipeline record already exists for this project / division combination.',
        ),
    ]

    # ── Compute: display name ──────────────────────────────────────────────────
    @api.depends('project_id', 'division_id')
    def _compute_display_name_full(self):
        for rec in self:
            parts = []
            if rec.project_id:
                parts.append(rec.project_id.name)
            if rec.division_id:
                parts.append(rec.division_id.name)
            rec.display_name_full = '  /  '.join(parts) if parts else _('New Pipeline')

    # ── Compute: all KPIs ─────────────────────────────────────────────────────
    @api.depends('project_id', 'division_id')
    def _compute_all_kpis(self):
        JobOrder = self.env['farm.job.order']
        MR       = self.env['farm.material.request']

        _zero = dict(
            total_jo_count=0,
            planning_count=0,
            planning_pct=0.0,
            material_readiness_pct=0.0,
            procurement_pct=0.0,
            resources_pct=0.0,
            in_progress_count=0,
            waiting_inspection_count=0,
            under_inspection_count=0,
            approved_count=0,
            rejected_count=0,
            claimed_count=0,
            claimed_amount_total=0.0,
            approved_amount_total=0.0,
            contract_amount_total=0.0,
            remaining_claim_total=0.0,
        )

        for rec in self:
            if not rec.project_id or not rec.division_id:
                rec.update(_zero)
                continue

            jos = JobOrder.search([
                ('project_id',  '=', rec.project_id.id),
                ('division_id', '=', rec.division_id.id),
            ])
            total = len(jos)
            rec.total_jo_count = total

            if not total:
                rec.update({k: v for k, v in _zero.items() if k != 'total_jo_count'})
                continue

            jo_ids = jos.ids

            # ── Pre-Execution ──────────────────────────────────────────────────

            # Planning count: JOs still in draft (not yet approved)
            rec.planning_count = sum(1 for j in jos if j.jo_stage == 'draft')

            # Planning %: JOs that have both planned dates set
            planned = sum(1 for j in jos if j.planned_start_date and j.planned_end_date)
            rec.planning_pct = round((planned / total) * 100, 1)

            # Material Readiness: JOs with at least one MR in approved+ state
            mrs_ready = MR.search([
                ('job_order_id', 'in', jo_ids),
                ('state', 'in', ['approved', 'rfq', 'ordered', 'received']),
            ])
            jo_with_mr = len(set(mrs_ready.mapped('job_order_id').ids))
            rec.material_readiness_pct = round((jo_with_mr / total) * 100, 1)

            # Procurement %: MRs that reached ordered/received (PO confirmed)
            mrs_ordered = MR.search([
                ('job_order_id', 'in', jo_ids),
                ('state', 'in', ['ordered', 'received']),
            ])
            jo_with_po = len(set(mrs_ordered.mapped('job_order_id').ids))
            rec.procurement_pct = round((jo_with_po / total) * 100, 1)

            # Resources %: JOs with at least one labour or material record
            with_resources = sum(
                1 for j in jos if j.labour_ids or j.material_ids
            )
            rec.resources_pct = round((with_resources / total) * 100, 1)

            # ── Execution ─────────────────────────────────────────────────────
            rec.in_progress_count        = sum(1 for j in jos if j.jo_stage == 'in_progress')
            rec.waiting_inspection_count = sum(1 for j in jos if j.jo_stage == 'handover_requested')
            rec.under_inspection_count   = sum(1 for j in jos if j.jo_stage == 'under_inspection')

            # ── Approval ──────────────────────────────────────────────────────
            approved_stages = {'accepted', 'partially_accepted', 'ready_for_claim', 'claimed', 'closed'}
            rec.approved_count = sum(1 for j in jos if j.jo_stage in approved_stages)
            rec.rejected_count = sum(
                1 for j in jos
                if j.inspection_result == 'failed' or j.approval_status == 'rejected'
            )

            # ── Financial ─────────────────────────────────────────────────────
            rec.claimed_count         = sum(1 for j in jos if j.jo_stage in ('claimed', 'closed'))
            rec.claimed_amount_total  = sum(j.claim_amount for j in jos)
            rec.approved_amount_total = sum(j.approved_amount for j in jos)
            rec.contract_amount_total = sum(j.planned_qty * j.unit_price for j in jos)
            rec.remaining_claim_total = sum(j.remaining_claim_amount for j in jos)

    # ── Action: Force KPI refresh ──────────────────────────────────────────────
    def action_refresh_kpis(self):
        """Manually trigger a KPI recompute for all records in self."""
        self._compute_all_kpis()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('KPIs Refreshed'),
                'message': _('Division pipeline KPIs have been recalculated.'),
                'type': 'success',
                'sticky': False,
            },
        }

    # ── Drill-down helpers ─────────────────────────────────────────────────────
    def _jo_action(self, extra_domain=None, title=None):
        self.ensure_one()
        domain = [
            ('project_id',  '=', self.project_id.id),
            ('division_id', '=', self.division_id.id),
        ]
        if extra_domain:
            domain += extra_domain
        return {
            'type':      'ir.actions.act_window',
            'name':      title or _('Job Orders'),
            'res_model': 'farm.job.order',
            'view_mode': 'list,form',
            'domain':    domain,
            'context': {
                'default_project_id':  self.project_id.id,
            },
        }

    def action_open_all_jo(self):
        return self._jo_action(
            title=_('All Job Orders — %s') % self.division_id.name,
        )

    def action_open_in_planning(self):
        return self._jo_action(
            [('jo_stage', '=', 'draft')],
            title=_('In Planning — %s') % self.division_id.name,
        )

    def action_open_in_progress(self):
        return self._jo_action(
            [('jo_stage', '=', 'in_progress')],
            title=_('In Progress — %s') % self.division_id.name,
        )

    def action_open_waiting_inspection(self):
        return self._jo_action(
            [('jo_stage', '=', 'handover_requested')],
            title=_('Waiting Inspection — %s') % self.division_id.name,
        )

    def action_open_under_inspection(self):
        return self._jo_action(
            [('jo_stage', '=', 'under_inspection')],
            title=_('Under Inspection — %s') % self.division_id.name,
        )

    def action_open_approved(self):
        return self._jo_action(
            [('jo_stage', 'in', ['accepted', 'partially_accepted',
                                  'ready_for_claim', 'claimed', 'closed'])],
            title=_('Approved — %s') % self.division_id.name,
        )

    def action_open_rejected(self):
        return self._jo_action(
            ['|',
             ('inspection_result', '=', 'failed'),
             ('approval_status', '=', 'rejected')],
            title=_('Rejected — %s') % self.division_id.name,
        )

    def action_open_claimed(self):
        return self._jo_action(
            [('jo_stage', 'in', ['claimed', 'closed'])],
            title=_('Claimed — %s') % self.division_id.name,
        )

    # ── Find or create ─────────────────────────────────────────────────────────
    @api.model
    def find_or_create(self, project_id, division_id):
        """Return the pipeline record for (project_id, division_id), creating it if needed."""
        rec = self.search([
            ('project_id',  '=', project_id),
            ('division_id', '=', division_id),
        ], limit=1)
        if not rec:
            rec = self.create({
                'project_id':  project_id,
                'division_id': division_id,
            })
        return rec
