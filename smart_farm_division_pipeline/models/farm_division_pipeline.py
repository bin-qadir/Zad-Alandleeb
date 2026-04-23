"""
Division Workflow Pipeline  —  Interactive Execution Dashboard
==============================================================
One record per (project, division).

Computes KPIs across four pipeline groups from the underlying Job Orders,
Material Requests and Purchase Orders:

  Pre-Execution  — planning / material readiness / procurement / resources
  Execution      — in_progress / waiting inspection / under inspection / completed
  Control        — pending approval / approved / rejected / rework
  Financial      — eligible for claim / claimed / under review / approved / rejected

Also computes alert counts (delayed JOs, overdue inspections, over-budget, unpaid).
"""

from datetime import date
from odoo import api, fields, models, _


# ── Pipeline phase list ────────────────────────────────────────────────────────

PIPELINE_PHASES = [
    ('planning',            'Planning'),
    ('material_request',    'Material Request'),
    ('procurement',         'Procurement'),
    ('resources',           'Resources'),
    ('ready_for_execution', 'Ready for Execution'),
    ('in_progress',         'In Progress'),
    ('completed',           'Completed'),
    ('inspection',          'Inspection'),
    ('approval',            'Approval'),
    ('claim',               'Claim'),
]

# Stages that are "done" (no longer active work)
_DONE_STAGES = frozenset(['closed', 'claimed'])


def _pct(num, denom):
    """Return rounded percentage, safe against zero division."""
    return round((num / denom) * 100, 1) if denom else 0.0


def _bar_html(pct, color_class='dp-bar-teal'):
    """Return a Bootstrap-style progress bar HTML snippet."""
    w = min(max(int(pct), 0), 100)
    return (
        f'<div class="dp-progressbar">'
        f'<div class="dp-progressbar-fill {color_class}" style="width:{w}%"></div>'
        f'</div>'
        f'<span class="dp-bar-pct">{pct:.1f}%</span>'
    )


class FarmDivisionPipeline(models.Model):
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

    # ── Core links ─────────────────────────────────────────────────────────────
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

    # ── Pipeline phase ─────────────────────────────────────────────────────────
    pipeline_phase = fields.Selection(
        selection=PIPELINE_PHASES,
        string='Pipeline Phase',
        default='planning',
        required=True,
        tracking=True,
    )
    notes = fields.Text(string='Notes / Remarks')

    # ── Currency ───────────────────────────────────────────────────────────────
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
        readonly=True,
    )

    # ══ KPI fields — all computed & stored ════════════════════════════════════

    # ── Totals ────────────────────────────────────────────────────────────────
    total_jo_count       = fields.Integer(string='Total JOs',         compute='_compute_all_kpis', store=True)
    contract_amount_total= fields.Float(  string='Contract Amount',   compute='_compute_all_kpis', store=True, digits=(16, 2))
    approved_amount_total= fields.Float(  string='Approved Amount',   compute='_compute_all_kpis', store=True, digits=(16, 2))
    remaining_claim_total= fields.Float(  string='Remaining Claimable',compute='_compute_all_kpis',store=True, digits=(16, 2))

    # ── Pre-Execution ─────────────────────────────────────────────────────────
    planning_count          = fields.Integer(string='In Planning',         compute='_compute_all_kpis', store=True)
    planning_pct            = fields.Float(  string='Planning (%)',         compute='_compute_all_kpis', store=True, digits=(16, 1))
    material_readiness_pct  = fields.Float(  string='Material Readiness (%)',compute='_compute_all_kpis',store=True, digits=(16, 1))
    procurement_pct         = fields.Float(  string='Procurement (%)',      compute='_compute_all_kpis', store=True, digits=(16, 1))
    resources_pct           = fields.Float(  string='Resources (%)',        compute='_compute_all_kpis', store=True, digits=(16, 1))

    # Progress bar HTML (rendered from pct values)
    planning_bar_html         = fields.Html(string='Planning Bar',    compute='_compute_html_bars', sanitize=False)
    material_bar_html         = fields.Html(string='Material Bar',    compute='_compute_html_bars', sanitize=False)
    procurement_bar_html      = fields.Html(string='Procurement Bar', compute='_compute_html_bars', sanitize=False)
    resources_bar_html        = fields.Html(string='Resources Bar',   compute='_compute_html_bars', sanitize=False)

    # ── Execution ─────────────────────────────────────────────────────────────
    in_progress_count        = fields.Integer(string='In Progress',       compute='_compute_all_kpis', store=True)
    waiting_inspection_count = fields.Integer(string='Waiting Inspection',compute='_compute_all_kpis', store=True)
    under_inspection_count   = fields.Integer(string='Under Inspection',  compute='_compute_all_kpis', store=True)
    completed_count          = fields.Integer(string='Completed',         compute='_compute_all_kpis', store=True)

    # ── Control ───────────────────────────────────────────────────────────────
    pending_approval_count = fields.Integer(string='Pending Approval', compute='_compute_all_kpis', store=True,
        help='JOs submitted for inspection and awaiting inspector decision.')
    approved_count         = fields.Integer(string='Approved',         compute='_compute_all_kpis', store=True)
    rejected_count         = fields.Integer(string='Rejected',         compute='_compute_all_kpis', store=True)
    rework_count           = fields.Integer(string='Rework',           compute='_compute_all_kpis', store=True,
        help='JOs where inspection failed and have been returned to In Progress for rework.')

    # ── Financial ─────────────────────────────────────────────────────────────
    eligible_for_claim_count  = fields.Integer(string='Eligible for Claim', compute='_compute_all_kpis', store=True)
    eligible_for_claim_amount = fields.Float(  string='Eligible Amount',    compute='_compute_all_kpis', store=True, digits=(16, 2))
    claimed_count             = fields.Integer(string='Claimed',            compute='_compute_all_kpis', store=True)
    claimed_amount_total      = fields.Float(  string='Claimed Amount',     compute='_compute_all_kpis', store=True, digits=(16, 2))
    under_review_count        = fields.Integer(string='Under Review',       compute='_compute_all_kpis', store=True,
        help='Claims submitted and currently under client review.')
    under_review_amount       = fields.Float(  string='Under Review Amount',compute='_compute_all_kpis', store=True, digits=(16, 2))
    approved_claim_count      = fields.Integer(string='Approved Claims',    compute='_compute_all_kpis', store=True)
    approved_claim_amount     = fields.Float(  string='Approved Claim Amt', compute='_compute_all_kpis', store=True, digits=(16, 2))
    rejected_claim_count      = fields.Integer(string='Rejected Claims',    compute='_compute_all_kpis', store=True)

    # ── Alerts ────────────────────────────────────────────────────────────────
    delayed_count             = fields.Integer(string='Delayed JOs',           compute='_compute_all_kpis', store=True)
    overdue_inspection_count  = fields.Integer(string='Overdue Inspections',   compute='_compute_all_kpis', store=True)
    over_budget_count         = fields.Integer(string='Over Budget JOs',       compute='_compute_all_kpis', store=True)
    unpaid_count              = fields.Integer(string='Unpaid (Pending)',       compute='_compute_all_kpis', store=True)
    has_alerts                = fields.Boolean(string='Has Alerts',             compute='_compute_all_kpis', store=True)

    # ── SQL constraint ─────────────────────────────────────────────────────────
    _sql_constraints = [
        (
            'unique_project_division',
            'UNIQUE(project_id, division_id)',
            'A pipeline record already exists for this project / division combination.',
        ),
    ]

    # ══ Compute methods ═══════════════════════════════════════════════════════

    @api.depends('project_id', 'division_id')
    def _compute_display_name_full(self):
        for rec in self:
            parts = []
            if rec.project_id:
                parts.append(rec.project_id.name)
            if rec.division_id:
                parts.append(rec.division_id.name)
            rec.display_name_full = '  /  '.join(parts) if parts else _('New Pipeline')

    @api.depends('project_id', 'division_id')
    def _compute_all_kpis(self):
        JobOrder = self.env['farm.job.order']
        MR       = self.env['farm.material.request']
        today    = date.today()

        _zero = dict(
            total_jo_count=0,
            contract_amount_total=0.0, approved_amount_total=0.0, remaining_claim_total=0.0,
            # Pre-execution
            planning_count=0, planning_pct=0.0,
            material_readiness_pct=0.0, procurement_pct=0.0, resources_pct=0.0,
            # Execution
            in_progress_count=0, waiting_inspection_count=0,
            under_inspection_count=0, completed_count=0,
            # Control
            pending_approval_count=0, approved_count=0, rejected_count=0, rework_count=0,
            # Financial
            eligible_for_claim_count=0, eligible_for_claim_amount=0.0,
            claimed_count=0, claimed_amount_total=0.0,
            under_review_count=0, under_review_amount=0.0,
            approved_claim_count=0, approved_claim_amount=0.0,
            rejected_claim_count=0,
            # Alerts
            delayed_count=0, overdue_inspection_count=0,
            over_budget_count=0, unpaid_count=0, has_alerts=False,
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
            rec.planning_count = sum(1 for j in jos if j.jo_stage == 'draft')
            planned = sum(1 for j in jos if j.planned_start_date and j.planned_end_date)
            rec.planning_pct = _pct(planned, total)

            mrs_ready = MR.search([
                ('job_order_id', 'in', jo_ids),
                ('state', 'in', ['approved', 'rfq', 'ordered', 'received']),
            ])
            jo_with_mr = len(set(mrs_ready.mapped('job_order_id').ids))
            rec.material_readiness_pct = _pct(jo_with_mr, total)

            mrs_ordered = MR.search([
                ('job_order_id', 'in', jo_ids),
                ('state', 'in', ['ordered', 'received']),
            ])
            jo_with_po = len(set(mrs_ordered.mapped('job_order_id').ids))
            rec.procurement_pct = _pct(jo_with_po, total)

            with_resources = sum(1 for j in jos if j.labour_ids or j.material_ids)
            rec.resources_pct = _pct(with_resources, total)

            # ── Execution ─────────────────────────────────────────────────────
            rec.in_progress_count        = sum(1 for j in jos if j.jo_stage == 'in_progress')
            rec.waiting_inspection_count = sum(1 for j in jos if j.jo_stage == 'handover_requested')
            rec.under_inspection_count   = sum(1 for j in jos if j.jo_stage == 'under_inspection')
            rec.completed_count          = sum(1 for j in jos if j.jo_stage == 'closed')

            # ── Control ───────────────────────────────────────────────────────
            # pending_approval: under inspection (inspector has not yet decided)
            rec.pending_approval_count = rec.under_inspection_count

            # approved: passed inspection (accepted, partially accepted, or beyond)
            approved_stages = {'accepted', 'partially_accepted', 'ready_for_claim', 'claimed', 'closed'}
            rec.approved_count = sum(1 for j in jos if j.jo_stage in approved_stages)

            # rejected: inspection failed or approval formally rejected
            rec.rejected_count = sum(
                1 for j in jos
                if j.inspection_result == 'failed' or j.approval_status == 'rejected'
            )

            # rework: inspection failed AND back in in_progress
            rec.rework_count = sum(
                1 for j in jos
                if j.inspection_result == 'failed' and j.jo_stage == 'in_progress'
            )

            # ── Financial ─────────────────────────────────────────────────────
            eligible = [j for j in jos if j.jo_stage == 'ready_for_claim']
            rec.eligible_for_claim_count  = len(eligible)
            rec.eligible_for_claim_amount = sum(j.remaining_claim_amount for j in eligible)

            rec.claimed_count        = sum(1 for j in jos if j.jo_stage in ('claimed', 'closed'))
            rec.claimed_amount_total = sum(j.claim_amount for j in jos)

            under_review = [j for j in jos if j.jo_stage == 'claimed']
            rec.under_review_count  = len(under_review)
            rec.under_review_amount = sum(j.claim_amount for j in under_review)

            closed_jos = [j for j in jos if j.jo_stage == 'closed']
            rec.approved_claim_count  = len(closed_jos)
            rec.approved_claim_amount = sum(j.claim_amount for j in closed_jos)

            rec.rejected_claim_count = sum(1 for j in jos if j.approval_status == 'rejected')

            rec.approved_amount_total = sum(j.approved_amount for j in jos)
            rec.contract_amount_total = sum(j.planned_qty * j.unit_price for j in jos)
            rec.remaining_claim_total = sum(j.remaining_claim_amount for j in jos)

            # ── Alerts ────────────────────────────────────────────────────────
            active_stages = frozenset(['draft', 'approved', 'in_progress',
                                       'handover_requested', 'under_inspection',
                                       'partially_accepted', 'accepted', 'ready_for_claim'])

            rec.delayed_count = sum(
                1 for j in jos
                if j.planned_end_date
                and j.planned_end_date < today
                and j.jo_stage in active_stages
            )
            rec.overdue_inspection_count = rec.waiting_inspection_count
            rec.over_budget_count = sum(
                1 for j in jos
                if j.planned_cost and j.actual_total_cost > j.planned_cost
            )
            rec.unpaid_count = rec.under_review_count

            rec.has_alerts = bool(
                rec.delayed_count
                or rec.overdue_inspection_count
                or rec.over_budget_count
                or rec.unpaid_count
            )

    @api.depends('planning_pct', 'material_readiness_pct', 'procurement_pct', 'resources_pct')
    def _compute_html_bars(self):
        for rec in self:
            rec.planning_bar_html    = _bar_html(rec.planning_pct,           'dp-bar-teal')
            rec.material_bar_html    = _bar_html(rec.material_readiness_pct, 'dp-bar-blue')
            rec.procurement_bar_html = _bar_html(rec.procurement_pct,        'dp-bar-purple')
            rec.resources_bar_html   = _bar_html(rec.resources_pct,          'dp-bar-amber')

    # ══ Actions ══════════════════════════════════════════════════════════════

    def action_refresh_kpis(self):
        self._compute_all_kpis()
        self._compute_html_bars()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title':   _('KPIs Refreshed'),
                'message': _('Division pipeline KPIs have been recalculated.'),
                'type':    'success',
                'sticky':  False,
            },
        }

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
            'context':   {'default_project_id': self.project_id.id},
        }

    def action_open_all_jo(self):
        return self._jo_action(title=_('All Job Orders — %s') % self.division_id.name)

    def action_open_in_planning(self):
        return self._jo_action([('jo_stage', '=', 'draft')],
                               title=_('In Planning — %s') % self.division_id.name)

    def action_open_in_progress(self):
        return self._jo_action([('jo_stage', '=', 'in_progress')],
                               title=_('In Progress — %s') % self.division_id.name)

    def action_open_waiting_inspection(self):
        return self._jo_action([('jo_stage', '=', 'handover_requested')],
                               title=_('Waiting Inspection — %s') % self.division_id.name)

    def action_open_under_inspection(self):
        return self._jo_action([('jo_stage', '=', 'under_inspection')],
                               title=_('Under Inspection — %s') % self.division_id.name)

    def action_open_completed(self):
        return self._jo_action([('jo_stage', '=', 'closed')],
                               title=_('Completed — %s') % self.division_id.name)

    def action_open_pending_approval(self):
        return self._jo_action([('jo_stage', '=', 'under_inspection')],
                               title=_('Pending Approval — %s') % self.division_id.name)

    def action_open_approved(self):
        return self._jo_action(
            [('jo_stage', 'in', ['accepted', 'partially_accepted',
                                  'ready_for_claim', 'claimed', 'closed'])],
            title=_('Approved — %s') % self.division_id.name,
        )

    def action_open_rejected(self):
        return self._jo_action(
            ['|', ('inspection_result', '=', 'failed'), ('approval_status', '=', 'rejected')],
            title=_('Rejected — %s') % self.division_id.name,
        )

    def action_open_rework(self):
        return self._jo_action(
            ['&', ('inspection_result', '=', 'failed'), ('jo_stage', '=', 'in_progress')],
            title=_('Rework — %s') % self.division_id.name,
        )

    def action_open_eligible_for_claim(self):
        return self._jo_action([('jo_stage', '=', 'ready_for_claim')],
                               title=_('Eligible for Claim — %s') % self.division_id.name)

    def action_open_under_review(self):
        return self._jo_action([('jo_stage', '=', 'claimed')],
                               title=_('Under Review — %s') % self.division_id.name)

    def action_open_approved_claims(self):
        return self._jo_action([('jo_stage', '=', 'closed')],
                               title=_('Approved Claims — %s') % self.division_id.name)

    def action_open_rejected_claims(self):
        return self._jo_action([('approval_status', '=', 'rejected')],
                               title=_('Rejected Claims — %s') % self.division_id.name)

    def action_open_delayed(self):
        return self._jo_action(
            ['&',
             ('planned_end_date', '<', str(date.today())),
             ('jo_stage', 'in', ['draft', 'approved', 'in_progress',
                                  'handover_requested', 'under_inspection',
                                  'partially_accepted', 'accepted', 'ready_for_claim'])],
            title=_('Delayed — %s') % self.division_id.name,
        )

    def action_open_over_budget(self):
        return self._jo_action(
            [('actual_total_cost', '>', 0)],
            title=_('Over Budget — %s') % self.division_id.name,
        )

    def action_open_claimed(self):
        return self._jo_action([('jo_stage', 'in', ['claimed', 'closed'])],
                               title=_('Claimed — %s') % self.division_id.name)

    @api.model
    def find_or_create(self, project_id, division_id):
        rec = self.search([
            ('project_id',  '=', project_id),
            ('division_id', '=', division_id),
        ], limit=1)
        if not rec:
            rec = self.create({'project_id': project_id, 'division_id': division_id})
        return rec
