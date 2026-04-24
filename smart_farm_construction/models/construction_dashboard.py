"""
farm.construction.dashboard  —  Construction Executive Dashboard
================================================================

Singleton model. All KPIs are non-stored computed fields that aggregate
live data from farm.job.order and farm.project on every form open.

Sections:
  1. Portfolio KPIs     — total JOs, planned value, approved, claimable, claimed
  2. Execution Progress — weighted-average approved_qty / planned_qty %
  3. Project Phases     — Pre-Tender / Tender / Post-Tender / Execution / Closure
  4. Stage Distribution — all 10 jo_stage values + overdue
  5. Department Breakdown — Civil / Structure / Architectural / Mechanical / Electrical

Financial driver rule (preserved from Smart Farm engine):
  approved_qty is the ONLY quantity that generates revenue / progress.
  planned_value = planned_qty × unit_price  (BOQ contract value)
  approved_amount = approved_qty × unit_price
"""
from odoo import api, fields, models, _
from datetime import date


class FarmConstructionDashboard(models.Model):
    _name        = 'farm.construction.dashboard'
    _description = 'Construction Executive Dashboard'
    _rec_name    = 'name'

    ACTIVITY = 'construction'

    # ── Identity ──────────────────────────────────────────────────────────────

    name = fields.Char(
        string='Dashboard',
        default='Construction Dashboard',
        readonly=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        compute='_compute_currency',
        string='Currency',
    )

    # ── Portfolio KPIs ────────────────────────────────────────────────────────

    total_projects   = fields.Integer(compute='_compute_projects',  string='Total Projects')
    active_projects  = fields.Integer(compute='_compute_projects',  string='Active Projects')
    total_jos        = fields.Integer(compute='_compute_portfolio', string='Total Job Orders')
    planned_value    = fields.Monetary(compute='_compute_portfolio', currency_field='currency_id', string='Planned Value')
    approved_amount  = fields.Monetary(compute='_compute_portfolio', currency_field='currency_id', string='Approved Amount')
    claimable_amount = fields.Monetary(compute='_compute_portfolio', currency_field='currency_id', string='Claimable Amount')
    claimed_amount   = fields.Monetary(compute='_compute_portfolio', currency_field='currency_id', string='Claimed Amount')
    progress_pct     = fields.Float(compute='_compute_portfolio',   string='Progress %', digits=(16, 1))

    # ── Project Phases ────────────────────────────────────────────────────────

    phase_pre_tender  = fields.Integer(compute='_compute_phases', string='Pre-Tender')
    phase_tender      = fields.Integer(compute='_compute_phases', string='Tender')
    phase_post_tender = fields.Integer(compute='_compute_phases', string='Post-Tender')
    phase_execution   = fields.Integer(compute='_compute_phases', string='Execution')
    phase_closure     = fields.Integer(compute='_compute_phases', string='Closure')

    # ── JO Stage Distribution ─────────────────────────────────────────────────

    stage_draft              = fields.Integer(compute='_compute_stages', string='Draft')
    stage_approved           = fields.Integer(compute='_compute_stages', string='Approved')
    stage_in_progress        = fields.Integer(compute='_compute_stages', string='In Progress')
    stage_handover_requested = fields.Integer(compute='_compute_stages', string='Handover Req')
    stage_under_inspection   = fields.Integer(compute='_compute_stages', string='Inspection')
    stage_accepted           = fields.Integer(compute='_compute_stages', string='Accepted')
    stage_ready_for_claim    = fields.Integer(compute='_compute_stages', string='Ready to Claim')
    stage_claimed            = fields.Integer(compute='_compute_stages', string='Claimed')
    stage_closed             = fields.Integer(compute='_compute_stages', string='Closed')
    stage_overdue            = fields.Integer(compute='_compute_stages', string='Overdue')

    # ── Department Breakdown ──────────────────────────────────────────────────

    dept_civil      = fields.Integer(compute='_compute_departments', string='Civil')
    dept_structure  = fields.Integer(compute='_compute_departments', string='Structure')
    dept_arch       = fields.Integer(compute='_compute_departments', string='Architectural')
    dept_mechanical = fields.Integer(compute='_compute_departments', string='Mechanical')
    dept_electrical = fields.Integer(compute='_compute_departments', string='Electrical')
    dept_other      = fields.Integer(compute='_compute_departments', string='Other')

    # ── Smart KPI Cards — project status distribution ──────────────────────────

    status_first_ideas  = fields.Integer(compute='_compute_status_cards', string='First Ideas')
    status_new          = fields.Integer(compute='_compute_status_cards', string='New Projects')
    status_in_progress  = fields.Integer(compute='_compute_status_cards', string='In Progress')
    status_on_hold      = fields.Integer(compute='_compute_status_cards', string='On Hold')
    status_completed    = fields.Integer(compute='_compute_status_cards', string='Completed')
    status_cancelled    = fields.Integer(compute='_compute_status_cards', string='Cancelled')

    # Risk badges on status cards
    ip_critical_count   = fields.Integer(compute='_compute_status_cards', string='In Progress Critical')
    ip_warning_count    = fields.Integer(compute='_compute_status_cards', string='In Progress Warning')

    # Trend (projects created/moved in last 30 days)
    trend_first_ideas   = fields.Integer(compute='_compute_status_cards', string='New First Ideas (30d)')
    trend_new           = fields.Integer(compute='_compute_status_cards', string='New in Tender (30d)')
    trend_in_progress   = fields.Integer(compute='_compute_status_cards', string='Newly In Progress (30d)')

    # ── AI Decision Center ────────────────────────────────────────────────────

    ai_critical_count         = fields.Integer(compute='_compute_ai_center', string='Critical Projects')
    ai_warning_count          = fields.Integer(compute='_compute_ai_center', string='Warning Projects')
    ai_procurement_risk_count = fields.Integer(compute='_compute_ai_center', string='Procurement Risks')
    ai_cost_risk_count        = fields.Integer(compute='_compute_ai_center', string='Cost Overruns')
    ai_delay_count            = fields.Integer(compute='_compute_ai_center', string='Delayed Execution')
    ai_claim_ready_count      = fields.Integer(compute='_compute_ai_center', string='Claim Ready')

    # ────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ────────────────────────────────────────────────────────────────────────

    def _jos(self, include_closed=False):
        """Return all construction job orders."""
        domain = [('business_activity', '=', self.ACTIVITY)]
        if not include_closed:
            domain.append(('jo_stage', '!=', 'closed'))
        return self.env['farm.job.order'].search(domain)

    def _projects(self):
        """Return all construction farm projects."""
        return self.env['farm.project'].search(
            [('business_activity', '=', self.ACTIVITY)]
        )

    # ────────────────────────────────────────────────────────────────────────
    # Compute methods
    # ────────────────────────────────────────────────────────────────────────

    def _compute_currency(self):
        for rec in self:
            rec.currency_id = rec.env.company.currency_id

    def _compute_projects(self):
        for rec in self:
            projects = rec._projects()
            rec.total_projects  = len(projects)
            rec.active_projects = sum(1 for p in projects if p.state == 'running')

    def _compute_portfolio(self):
        for rec in self:
            jos = rec._jos()
            if not jos:
                rec.total_jos        = 0
                rec.planned_value    = 0.0
                rec.approved_amount  = 0.0
                rec.claimable_amount = 0.0
                rec.claimed_amount   = 0.0
                rec.progress_pct     = 0.0
                continue
            rec.total_jos        = len(jos)
            rec.planned_value    = sum(j.planned_qty * j.unit_price for j in jos)
            rec.approved_amount  = sum(jos.mapped('approved_amount'))
            rec.claimable_amount = sum(jos.mapped('claimable_amount'))
            rec.claimed_amount   = sum(jos.mapped('claim_amount'))
            total_planned  = sum(jos.mapped('planned_qty'))
            total_approved = sum(jos.mapped('approved_qty'))
            rec.progress_pct = (
                total_approved / total_planned * 100.0
                if total_planned else 0.0
            )

    def _compute_phases(self):
        for rec in self:
            projects = rec._projects()
            rec.phase_pre_tender  = sum(1 for p in projects if p.construction_phase == 'pre_tender')
            rec.phase_tender      = sum(1 for p in projects if p.construction_phase == 'tender')
            rec.phase_post_tender = sum(1 for p in projects if p.construction_phase == 'post_tender')
            rec.phase_execution   = sum(1 for p in projects if p.construction_phase == 'execution')
            rec.phase_closure     = sum(1 for p in projects if p.construction_phase == 'closure')

    def _compute_stages(self):
        today = date.today()
        for rec in self:
            jos      = rec._jos()
            all_jos  = rec._jos(include_closed=True)
            rec.stage_draft              = sum(1 for j in jos if j.jo_stage == 'draft')
            rec.stage_approved           = sum(1 for j in jos if j.jo_stage == 'approved')
            rec.stage_in_progress        = sum(1 for j in jos if j.jo_stage == 'in_progress')
            rec.stage_handover_requested = sum(1 for j in jos if j.jo_stage == 'handover_requested')
            rec.stage_under_inspection   = sum(1 for j in jos if j.jo_stage == 'under_inspection')
            rec.stage_accepted           = sum(1 for j in jos if j.jo_stage in ['partially_accepted', 'accepted'])
            rec.stage_ready_for_claim    = sum(1 for j in jos if j.jo_stage == 'ready_for_claim')
            rec.stage_claimed            = sum(1 for j in jos if j.jo_stage == 'claimed')
            rec.stage_closed             = sum(1 for j in all_jos if j.jo_stage == 'closed')
            rec.stage_overdue            = sum(
                1 for j in jos
                if j.planned_end_date
                and j.planned_end_date < today
                and j.jo_stage not in ('closed', 'claimed')
            )

    def _compute_departments(self):
        for rec in self:
            jos = rec._jos()
            rec.dept_civil      = sum(1 for j in jos if j.department == 'civil')
            rec.dept_structure  = sum(1 for j in jos if j.department == 'structure')
            rec.dept_arch       = sum(1 for j in jos if j.department == 'arch')
            rec.dept_mechanical = sum(1 for j in jos if j.department == 'mechanical')
            rec.dept_electrical = sum(1 for j in jos if j.department == 'electrical')
            rec.dept_other      = sum(
                1 for j in jos
                if not j.department or j.department == 'other'
            )

    def _compute_status_cards(self):
        from datetime import timedelta
        cutoff = date.today() - timedelta(days=30)
        for rec in self:
            projects = rec._projects()
            rec.status_first_ideas = sum(1 for p in projects if p.construction_status == 'first_ideas')
            rec.status_new         = sum(1 for p in projects if p.construction_status == 'new')
            rec.status_in_progress = sum(1 for p in projects if p.construction_status == 'in_progress')
            rec.status_on_hold     = sum(1 for p in projects if p.construction_status == 'on_hold')
            rec.status_completed   = sum(1 for p in projects if p.construction_status == 'completed')
            rec.status_cancelled   = sum(1 for p in projects if p.construction_status == 'cancelled')

            # Trend — created in last 30 days
            rec.trend_first_ideas  = sum(1 for p in projects if p.construction_status == 'first_ideas'  and p.create_date and p.create_date.date() >= cutoff)
            rec.trend_new          = sum(1 for p in projects if p.construction_status == 'new'           and p.create_date and p.create_date.date() >= cutoff)
            rec.trend_in_progress  = sum(1 for p in projects if p.construction_status == 'in_progress'  and p.create_date and p.create_date.date() >= cutoff)

            # Risk badges for In Progress
            ip_ids = [p.id for p in projects if p.construction_status == 'in_progress']
            if ip_ids:
                insights = self.env['construction.ai.insight'].search([
                    ('project_id', 'in', ip_ids),
                    ('state', '!=', 'resolved'),
                ])
                rec.ip_critical_count = sum(1 for i in insights if i.status == 'critical')
                rec.ip_warning_count  = sum(1 for i in insights if i.status == 'warning')
            else:
                rec.ip_critical_count = 0
                rec.ip_warning_count  = 0

    def _compute_ai_center(self):
        for rec in self:
            proj_ids = rec._projects().ids
            if not proj_ids:
                rec.ai_critical_count         = 0
                rec.ai_warning_count          = 0
                rec.ai_procurement_risk_count = 0
                rec.ai_cost_risk_count        = 0
                rec.ai_delay_count            = 0
                rec.ai_claim_ready_count      = 0
                continue
            insights = self.env['construction.ai.insight'].search([
                ('project_id', 'in', proj_ids),
                ('state', '!=', 'resolved'),
            ])
            rec.ai_critical_count         = sum(1 for i in insights if i.status == 'critical')
            rec.ai_warning_count          = sum(1 for i in insights if i.status == 'warning')
            rec.ai_procurement_risk_count = sum(1 for i in insights if i.procurement_risk >= 50)
            rec.ai_cost_risk_count        = sum(1 for i in insights if i.cost_risk >= 50)
            rec.ai_delay_count            = sum(1 for i in insights if i.delay_score >= 50)
            rec.ai_claim_ready_count      = sum(1 for i in insights if i.claim_risk >= 30)

    # ────────────────────────────────────────────────────────────────────────
    # UI Actions — refresh
    # ────────────────────────────────────────────────────────────────────────

    def action_refresh(self):
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'res_model': 'farm.construction.dashboard',
            'res_id':    self.id,
            'view_mode': 'form',
            'target':    'current',
            'context':   {'form_view_initial_mode': 'readonly'},
        }

    # ────────────────────────────────────────────────────────────────────────
    # Drill-down helpers
    # ────────────────────────────────────────────────────────────────────────

    def _open_projects(self, name='Construction Projects', extra_domain=None):
        domain = [('business_activity', '=', self.ACTIVITY)]
        if extra_domain:
            domain += extra_domain
        return {
            'type':      'ir.actions.act_window',
            'name':      _(name),
            'res_model': 'farm.project',
            'view_mode': 'list,form,kanban',
            'domain':    domain,
            'context':   {'default_business_activity': 'construction'},
        }

    def _open_jos(self, name, extra_domain=None):
        domain = [('business_activity', '=', self.ACTIVITY)]
        if extra_domain:
            domain += extra_domain
        return {
            'type':      'ir.actions.act_window',
            'name':      _(name),
            'res_model': 'farm.job.order',
            'view_mode': 'list,form',
            'domain':    domain,
            'context':   {'default_business_activity': 'construction'},
        }

    # ── Portfolio drill-downs ─────────────────────────────────────────────────

    def action_view_all_projects(self):
        return self._open_projects()

    def action_view_active_projects(self):
        return self._open_projects('Active Construction Projects', [('state', '=', 'running')])

    def action_view_all_jos(self):
        return self._open_jos('All Construction Job Orders')

    # ── Phase drill-downs ─────────────────────────────────────────────────────

    def action_view_pre_tender(self):
        return self._open_projects('Pre-Tender Projects', [('construction_phase', '=', 'pre_tender')])

    def action_view_tender(self):
        return self._open_projects('Tender Projects', [('construction_phase', '=', 'tender')])

    def action_view_post_tender(self):
        return self._open_projects('Post-Tender Projects', [('construction_phase', '=', 'post_tender')])

    def action_view_execution_phase(self):
        return self._open_projects('Execution Phase Projects', [('construction_phase', '=', 'execution')])

    def action_view_closure_phase(self):
        return self._open_projects('Closure Phase Projects', [('construction_phase', '=', 'closure')])

    # ── Stage drill-downs ─────────────────────────────────────────────────────

    def action_view_draft_jos(self):
        return self._open_jos('Draft Job Orders', [('jo_stage', '=', 'draft')])

    def action_view_approved_jos(self):
        return self._open_jos('Approved Job Orders', [('jo_stage', '=', 'approved')])

    def action_view_in_progress_jos(self):
        return self._open_jos('In Progress Job Orders', [('jo_stage', '=', 'in_progress')])

    def action_view_handover_jos(self):
        return self._open_jos('Handover Requested', [('jo_stage', '=', 'handover_requested')])

    def action_view_inspection_jos(self):
        return self._open_jos('Under Inspection', [('jo_stage', '=', 'under_inspection')])

    def action_view_accepted_jos(self):
        return self._open_jos('Accepted Job Orders', [('jo_stage', 'in', ['partially_accepted', 'accepted'])])

    def action_view_ready_claim_jos(self):
        return self._open_jos('Ready for Claim', [('jo_stage', '=', 'ready_for_claim')])

    def action_view_claimed_jos(self):
        return self._open_jos('Claimed Job Orders', [('jo_stage', '=', 'claimed')])

    def action_view_closed_jos(self):
        return self._open_jos('Closed Job Orders', [('jo_stage', '=', 'closed')])

    def action_view_overdue_jos(self):
        today_str = date.today().isoformat()
        return self._open_jos('Overdue Job Orders', [
            ('planned_end_date', '<', today_str),
            ('jo_stage', 'not in', ['closed', 'claimed']),
        ])

    # ── Department drill-downs ────────────────────────────────────────────────

    def action_view_civil_jos(self):
        return self._open_jos('Civil Job Orders', [('department', '=', 'civil')])

    def action_view_structure_jos(self):
        return self._open_jos('Structure Job Orders', [('department', '=', 'structure')])

    def action_view_arch_jos(self):
        return self._open_jos('Architectural Job Orders', [('department', '=', 'arch')])

    def action_view_mech_jos(self):
        return self._open_jos('Mechanical Job Orders', [('department', '=', 'mechanical')])

    def action_view_elec_jos(self):
        return self._open_jos('Electrical Job Orders', [('department', '=', 'electrical')])

    # ── Smart KPI status card drill-downs ────────────────────────────────────

    def action_view_first_ideas(self):
        return self._open_projects('First Ideas', [('construction_status', '=', 'first_ideas')])

    def action_view_new_projects(self):
        return self._open_projects('New Projects', [('construction_status', '=', 'new')])

    def action_view_in_progress_projects(self):
        return self._open_projects('In Progress Projects', [('construction_status', '=', 'in_progress')])

    def action_view_on_hold_projects(self):
        return self._open_projects('On Hold Projects', [('construction_status', '=', 'on_hold')])

    def action_view_completed_projects(self):
        return self._open_projects('Completed Projects', [('construction_status', '=', 'completed')])

    def action_view_cancelled_projects(self):
        return self._open_projects('Cancelled Projects', [('construction_status', '=', 'cancelled')])

    # ── AI Decision Center drill-downs ────────────────────────────────────────

    def _open_ai_insights(self, name, extra_domain=None):
        """Open AI insights list filtered to construction + extra_domain."""
        proj_ids = self._projects().ids
        domain   = [('project_id', 'in', proj_ids), ('state', '!=', 'resolved')]
        if extra_domain:
            domain += extra_domain
        return {
            'type':      'ir.actions.act_window',
            'name':      _(name),
            'res_model': 'construction.ai.insight',
            'view_mode': 'list,form',
            'domain':    domain,
        }

    def action_view_critical_projects(self):
        return self._open_ai_insights('Critical Projects', [('status', '=', 'critical')])

    def action_view_warning_projects(self):
        return self._open_ai_insights('Warning Projects', [('status', '=', 'warning')])

    def action_view_procurement_risks(self):
        return self._open_ai_insights('Procurement Risks', [('procurement_risk', '>=', 50)])

    def action_view_cost_overruns(self):
        return self._open_ai_insights('Cost Overruns', [('cost_risk', '>=', 50)])

    def action_view_delayed_execution(self):
        return self._open_ai_insights('Delayed Execution', [('delay_score', '>=', 50)])

    def action_view_claim_ready(self):
        return self._open_ai_insights('Claim Ready', [('claim_risk', '>=', 30)])

    def action_run_ai_all(self):
        """Refresh AI insights for all construction projects from dashboard."""
        self.env['construction.ai.insight'].run_daily_construction_insights()
        return self.action_refresh()
