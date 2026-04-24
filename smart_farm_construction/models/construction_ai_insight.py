"""
construction.ai.insight  —  AI Decision Engine for Construction Projects
=========================================================================

One record per construction project (upsert on recompute).
All risk scores are 0–100 floats.  Status: healthy / warning / critical.

Risk weights:
  delay_score      × 0.30   (schedule risk — most impactful)
  execution_risk   × 0.25   (JO throughput bottleneck)
  procurement_risk × 0.20   (supply chain)
  cost_risk        × 0.15   (financial)
  claim_risk       × 0.10   (revenue recovery)
  ─────────────────────
  overall_risk_score  0–100

Thresholds:
  0–40  → healthy   (green)
  41–70 → warning   (orange)
  71–100 → critical  (red)
"""
from odoo import api, fields, models, _
from datetime import date
import logging

_logger = logging.getLogger(__name__)


class ConstructionAiInsight(models.Model):
    _name        = 'construction.ai.insight'
    _description = 'Construction AI Insight'
    _order       = 'date_generated desc, id desc'
    _rec_name    = 'name'

    # ── Identity ──────────────────────────────────────────────────────────────

    name = fields.Char(
        string='Insight',
        required=True,
        readonly=True,
    )
    project_id = fields.Many2one(
        'farm.project',
        string='Project',
        required=True,
        ondelete='cascade',
        index=True,
    )
    job_order_id = fields.Many2one(
        'farm.job.order',
        string='Job Order',
        ondelete='set null',
        index=True,
        help=(
            'Optional: link this insight to a specific Job Order for '
            'job-order-level AI analysis. Leave empty for project-level insights.'
        ),
    )
    business_activity = fields.Selection(
        related='project_id.business_activity',
        store=True,
        index=True,
        string='Activity',
    )
    date_generated = fields.Datetime(
        string='Generated',
        default=fields.Datetime.now,
        readonly=True,
    )

    # ── Risk Scores ───────────────────────────────────────────────────────────

    risk_score = fields.Float(
        string='Overall Risk Score',
        digits=(16, 1),
        help='Weighted composite 0–100. ≥71 = critical, 41–70 = warning, ≤40 = healthy.',
    )
    delay_score = fields.Float(
        string='Delay Risk',
        digits=(16, 1),
        help='Schedule overrun or overdue job orders.',
    )
    cost_risk = fields.Float(
        string='Cost Risk',
        digits=(16, 1),
        help='Budget overrun indicators or no BOQ in active execution.',
    )
    procurement_risk = fields.Float(
        string='Procurement Risk',
        digits=(16, 1),
        help='Pending material requests and procurement delays.',
    )
    execution_risk = fields.Float(
        string='Execution Risk',
        digits=(16, 1),
        help='Job orders stuck in inspection / approval queue.',
    )
    claim_risk = fields.Float(
        string='Claim Risk',
        digits=(16, 1),
        help='Approved value not yet claimed — revenue recovery gap.',
    )

    # ── Status ────────────────────────────────────────────────────────────────

    status = fields.Selection(
        selection=[
            ('healthy',  'Healthy'),
            ('warning',  'Warning'),
            ('critical', 'Critical'),
        ],
        string='AI Status',
        required=True,
        default='healthy',
        index=True,
    )

    # ── Insights ──────────────────────────────────────────────────────────────

    recommended_action = fields.Text(
        string='Recommended Actions',
        readonly=True,
    )
    reason = fields.Text(
        string='Risk Reasons',
        readonly=True,
    )

    # ── Workflow ──────────────────────────────────────────────────────────────

    state = fields.Selection(
        selection=[
            ('open',         'Open'),
            ('acknowledged', 'Acknowledged'),
            ('resolved',     'Resolved'),
        ],
        string='State',
        default='open',
        required=True,
        index=True,
        tracking=True,
    )
    responsible_id = fields.Many2one(
        'res.users',
        string='Responsible',
        ondelete='set null',
    )
    acknowledged_by   = fields.Many2one('res.users', string='Acknowledged By', readonly=True)
    acknowledged_date = fields.Datetime(string='Acknowledged', readonly=True)
    resolved_by       = fields.Many2one('res.users', string='Resolved By', readonly=True)
    resolved_date     = fields.Datetime(string='Resolved', readonly=True)

    # ────────────────────────────────────────────────────────────────────────
    # Core risk computation
    # ────────────────────────────────────────────────────────────────────────

    @api.model
    def _compute_for_project(self, project):
        """Return a dict of computed risk scores for the given farm.project."""
        today = date.today()

        # Collect related records once
        jos         = project.job_order_ids    if hasattr(project, 'job_order_ids')    else project.env['farm.job.order'].browse()
        mat_reqs    = project.material_request_ids if hasattr(project, 'material_request_ids') else project.env['farm.material.request'].browse()

        # ── Delay Risk ────────────────────────────────────────────────────────
        delay_score = 0.0
        if project.end_date and project.end_date < today:
            days_over  = (today - project.end_date).days
            delay_score = min(100.0, days_over * 3.5)   # 3.5 pts/day, cap 100

        if jos:
            active_jos   = [j for j in jos if j.jo_stage not in ('closed',)]
            overdue_jos  = [
                j for j in active_jos
                if j.planned_end_date and j.planned_end_date < today
                and j.jo_stage not in ('closed', 'claimed')
            ]
            if active_jos:
                jo_delay_pct = len(overdue_jos) / len(active_jos) * 100.0
                delay_score  = max(delay_score, jo_delay_pct * 0.8)

        # ── Procurement Risk ──────────────────────────────────────────────────
        procurement_risk = 0.0
        if mat_reqs:
            pending          = sum(1 for mr in mat_reqs if mr.state in ('draft', 'to_approve'))
            procurement_risk = min(100.0, pending / len(mat_reqs) * 100.0)

        # ── Execution Risk ────────────────────────────────────────────────────
        execution_risk = 0.0
        if jos:
            stuck        = [j for j in jos if j.jo_stage in ('handover_requested', 'under_inspection', 'partially_accepted')]
            active_total = [j for j in jos if j.jo_stage not in ('closed',)]
            if active_total:
                execution_risk = len(stuck) / len(active_total) * 100.0
        elif hasattr(project, 'construction_phase') and project.construction_phase == 'execution':
            execution_risk = 60.0   # active execution phase but no JOs created yet

        # ── Claim Risk ────────────────────────────────────────────────────────
        claim_risk = 0.0
        if jos:
            total_approved = sum(j.approved_amount for j in jos)
            total_claimed  = sum(j.claim_amount    for j in jos)
            if total_approved > 0:
                unclaimed_ratio = max(0.0, total_approved - total_claimed) / total_approved
                claim_risk = min(100.0, unclaimed_ratio * 80.0)

        # ── Cost Risk ─────────────────────────────────────────────────────────
        cost_risk = 0.0
        if jos:
            planned_value = sum(j.planned_qty * j.unit_price for j in jos)
            approved_val  = sum(j.approved_amount for j in jos)
            progress_pct  = getattr(project, 'execution_progress_pct', 0.0)

            if planned_value <= 0 and hasattr(project, 'construction_phase') and project.construction_phase in ('execution', 'closure'):
                cost_risk = 70.0    # execution with no cost basis
            elif planned_value > 0:
                ratio = approved_val / planned_value
                if ratio > 1.05:
                    cost_risk = min(100.0, (ratio - 1.0) * 300.0)
                # Cash-flow risk: high execution progress but claims not flowing
                total_claimed_ = sum(j.claim_amount for j in jos)
                if progress_pct > 60.0 and approved_val > 0 and total_claimed_ / approved_val < 0.25:
                    cost_risk = max(cost_risk, 55.0)
        elif hasattr(project, 'construction_phase') and project.construction_phase in ('execution', 'closure'):
            cost_risk = 45.0    # no JOs yet but execution phase active

        # ── Overall Score ─────────────────────────────────────────────────────
        risk_score = round(min(100.0, (
            delay_score      * 0.30 +
            procurement_risk * 0.20 +
            cost_risk        * 0.15 +
            execution_risk   * 0.25 +
            claim_risk       * 0.10
        )), 1)

        # ── Status ────────────────────────────────────────────────────────────
        if risk_score >= 71:
            status = 'critical'
        elif risk_score >= 41:
            status = 'warning'
        else:
            status = 'healthy'

        # ── Reason text ───────────────────────────────────────────────────────
        reasons = []
        if delay_score >= 25:
            if project.end_date and project.end_date < today:
                reasons.append(f'Project {(today - project.end_date).days}d past planned end date ({project.end_date})')
            else:
                reasons.append(f'{delay_score:.0f}% of active job orders are past their planned end date')
        if procurement_risk >= 25:
            reasons.append(f'{procurement_risk:.0f}% of material requests are still pending approval')
        if execution_risk >= 25:
            reasons.append(f'{execution_risk:.0f}% of active job orders are stuck in inspection / approval')
        if claim_risk >= 25:
            reasons.append(f'{claim_risk:.0f}% of approved value has not been claimed yet')
        if cost_risk >= 25:
            reasons.append(f'Cost risk {cost_risk:.0f}% — review BOQ margins and cash-flow position')
        if not reasons:
            reasons.append('All indicators are within normal range')
        reason = ' · '.join(reasons)

        # ── Recommendations ───────────────────────────────────────────────────
        actions = []
        if delay_score >= 50:
            actions.append('Expedite execution — mobilise additional manpower on critical-path activities')
        if procurement_risk >= 50:
            actions.append('Urgent purchase requests required — escalate delayed procurement to supply chain')
        if cost_risk >= 50:
            actions.append('Review BOQ margins — freeze non-critical spending until cost basis is confirmed')
        if execution_risk >= 50:
            actions.append('Push inspection queue — assign site engineer to resolve stuck job orders')
        if claim_risk >= 50:
            actions.append('Submit interim claim now — approved quantities are ready for billing')
        if not actions:
            actions.append('No immediate action required — continue routine monitoring')
        recommended_action = '\n'.join(f'• {a}' for a in actions)

        return {
            'risk_score':        risk_score,
            'delay_score':       round(delay_score,      1),
            'cost_risk':         round(cost_risk,         1),
            'procurement_risk':  round(procurement_risk,  1),
            'execution_risk':    round(execution_risk,    1),
            'claim_risk':        round(claim_risk,        1),
            'status':            status,
            'recommended_action': recommended_action,
            'reason':            reason,
        }

    # ────────────────────────────────────────────────────────────────────────
    # Upsert helper
    # ────────────────────────────────────────────────────────────────────────

    @api.model
    def generate_for_project(self, project):
        """Create or update (upsert) the AI insight for the given project."""
        vals = self._compute_for_project(project)
        vals.update({
            'name':              f'{project.name} — AI {fields.Datetime.now().strftime("%Y-%m-%d %H:%M")}',
            'project_id':        project.id,
            'business_activity': 'construction',
            'date_generated':    fields.Datetime.now(),
        })
        existing = self.search([('project_id', '=', project.id)], order='date_generated desc', limit=1)
        if existing:
            safe_vals = {
                k: v for k, v in vals.items()
                if k not in ('state', 'responsible_id',
                             'acknowledged_by', 'acknowledged_date',
                             'resolved_by', 'resolved_date')
            }
            existing.write(safe_vals)
            return existing
        vals['state'] = 'open'
        return self.create(vals)

    # ────────────────────────────────────────────────────────────────────────
    # Cron entrypoint
    # ────────────────────────────────────────────────────────────────────────

    @api.model
    def run_daily_construction_insights(self):
        """Cron: regenerate AI insights for all construction projects."""
        projects = self.env['farm.project'].search(
            [('business_activity', '=', 'construction')]
        )
        for proj in projects:
            try:
                self.generate_for_project(proj)
            except Exception as exc:
                _logger.warning('AI insight failed for project %s (%s): %s', proj.name, proj.id, exc)
        _logger.info('AI insights refreshed for %d construction project(s)', len(projects))

    # ────────────────────────────────────────────────────────────────────────
    # Workflow actions
    # ────────────────────────────────────────────────────────────────────────

    def action_acknowledge(self):
        for rec in self.filtered(lambda r: r.state == 'open'):
            rec.write({
                'state':            'acknowledged',
                'acknowledged_by':  self.env.uid,
                'acknowledged_date': fields.Datetime.now(),
            })

    def action_resolve(self):
        for rec in self.filtered(lambda r: r.state in ('open', 'acknowledged')):
            rec.write({
                'state':        'resolved',
                'resolved_by':  self.env.uid,
                'resolved_date': fields.Datetime.now(),
            })

    def action_recompute(self):
        """Button: recompute this insight's risk scores."""
        self.ensure_one()
        self.generate_for_project(self.project_id)
        return {
            'type': 'ir.actions.client',
            'tag':  'display_notification',
            'params': {
                'title':   _('AI Insight Updated'),
                'message': _(
                    'Risk recomputed for %(name)s — %(status)s (score: %(score)s%%)',
                    name=self.project_id.name,
                    status=self.status.upper(),
                    score=int(self.risk_score),
                ),
                'type':    'success' if self.status == 'healthy' else 'warning',
                'sticky':  False,
            },
        }
