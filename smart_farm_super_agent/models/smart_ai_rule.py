"""
smart.ai.rule — Layer 3: Rule Engine
=====================================
Configurable threshold-based rules that fire against project metrics.
"""
import logging
from datetime import date
from odoo import api, fields, models

_logger = logging.getLogger(__name__)

METRIC_SELECTION = [
    ('delay_days',              'Project Delay (days overdue)'),
    ('cost_overrun_pct',        'Cost Overrun (%)'),
    ('material_pending_count',  'Pending Material Requests'),
    ('inspection_pending_count','JOs Pending Inspection'),
    ('unclaimed_pct',           'Unclaimed Approved Value (%)'),
    ('active_jo_count',         'Active Job Orders'),
    ('overall_risk_score',      'Overall Risk Score'),
    ('progress_pct',            'Execution Progress (%)'),
    ('claimable_amount',        'Total Claimable Amount'),
    ('procurement_pending_count','Pending Procurement Docs'),
]

OPERATOR_SELECTION = [
    ('>',  'Greater Than (>)'),
    ('>=', 'Greater or Equal (>=)'),
    ('<',  'Less Than (<)'),
    ('<=', 'Less or Equal (<=)'),
    ('==', 'Equal To (==)'),
    ('!=', 'Not Equal To (!=)'),
]

SEVERITY_SELECTION = [
    ('low',      'Low'),
    ('medium',   'Medium'),
    ('high',     'High'),
    ('critical', 'Critical'),
]


class SmartAiRule(models.Model):
    _name        = 'smart.ai.rule'
    _description = 'AI Rule — Layer 3 Rule Engine'
    _order       = 'severity desc, sequence, name'
    _rec_name    = 'name'

    name = fields.Char(string='Rule Name', required=True)
    business_activity = fields.Selection(
        selection=[
            ('construction', 'Construction'),
            ('agriculture',  'Agriculture'),
            ('manufacturing','Manufacturing'),
            ('livestock',    'Livestock'),
        ],
        string='Business Activity',
        required=True,
        default='construction',
        index=True,
    )
    metric   = fields.Selection(METRIC_SELECTION,   string='Metric',   required=True)
    operator = fields.Selection(OPERATOR_SELECTION, string='Operator', required=True, default='>')
    threshold = fields.Float(
        string='Threshold Value',
        required=True,
        digits=(16, 2),
    )
    severity = fields.Selection(
        SEVERITY_SELECTION,
        string='Severity',
        required=True,
        default='medium',
    )
    recommended_action = fields.Text(string='Recommended Action')
    active   = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)

    trigger_count = fields.Integer(
        string='Times Triggered',
        compute='_compute_trigger_count',
        store=False,
    )

    # ── Compute ───────────────────────────────────────────────────────────────

    def _compute_trigger_count(self):
        for rec in self:
            rec.trigger_count = self.env['smart.ai.risk.score'].search_count([
                ('triggered_rule_ids', 'in', [rec.id])
            ])

    # ── Metric evaluation ────────────────────────────────────────────────────

    def _get_project_metric_value(self, project):
        """Return the float value of self.metric for the given project."""
        today  = date.today()
        metric = self.metric

        if metric == 'delay_days':
            end = getattr(project, 'end_date', False)
            if end and end < today:
                return float((today - end).days)
            return 0.0

        if metric == 'cost_overrun_pct':
            jos = self.env['farm.job.order'].search([('project_id', '=', project.id)])
            planned = sum(j.planned_qty * j.unit_price for j in jos)
            actual  = sum(getattr(j, 'actual_total_cost', 0) or 0 for j in jos)
            if planned > 0:
                return (actual / planned - 1) * 100.0
            return 0.0

        if metric == 'material_pending_count':
            return float(self.env['farm.material.request'].search_count([
                ('project_id', '=', project.id),
                ('state', 'in', ['draft', 'to_approve']),
            ]))

        if metric == 'inspection_pending_count':
            return float(self.env['farm.job.order'].search_count([
                ('project_id', '=', project.id),
                ('jo_stage', 'in', ['handover_requested', 'under_inspection']),
            ]))

        if metric == 'unclaimed_pct':
            jos = self.env['farm.job.order'].search([('project_id', '=', project.id)])
            total_approved = sum(getattr(j, 'approved_amount', 0) or 0 for j in jos)
            total_claimed  = sum(getattr(j, 'claim_amount',    0) or 0 for j in jos)
            if total_approved > 0:
                return (total_approved - total_claimed) / total_approved * 100.0
            return 0.0

        if metric == 'active_jo_count':
            return float(self.env['farm.job.order'].search_count([
                ('project_id', '=', project.id),
                ('jo_stage', 'not in', ['closed', 'claimed']),
            ]))

        if metric == 'overall_risk_score':
            score = self.env['smart.ai.risk.score'].search([
                ('project_id', '=', project.id),
            ], order='computed_at desc', limit=1)
            return score.overall_risk_score if score else 0.0

        if metric == 'progress_pct':
            return float(getattr(project, 'execution_progress_pct', 0.0) or 0.0)

        if metric == 'claimable_amount':
            return float(getattr(project, 'total_claimable_amount', 0.0) or 0.0)

        if metric == 'procurement_pending_count':
            return float(self.env['farm.boq.analysis'].search_count([
                ('project_id', '=', project.id),
                ('state', '=', 'draft'),
            ]))

        return 0.0

    def evaluate_for_project(self, project):
        """Return (triggered: bool, value: float) for this rule against project."""
        self.ensure_one()
        val = self._get_project_metric_value(project)
        ops = {
            '>':  lambda a, b: a > b,
            '>=': lambda a, b: a >= b,
            '<':  lambda a, b: a < b,
            '<=': lambda a, b: a <= b,
            '==': lambda a, b: a == b,
            '!=': lambda a, b: a != b,
        }
        triggered = ops.get(self.operator, lambda a, b: False)(val, self.threshold)
        return triggered, val
