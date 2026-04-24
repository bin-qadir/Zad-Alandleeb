"""
smart.ai.risk.score — Layer 4: Risk Engine
==========================================
Stores computed risk scores per project, enriched with rule engine results.
"""
import logging
from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class SmartAiRiskScore(models.Model):
    _name        = 'smart.ai.risk.score'
    _description = 'AI Risk Score — Layer 4 Risk Engine'
    _order       = 'computed_at desc'
    _rec_name    = 'name'

    # ── Identity ──────────────────────────────────────────────────────────────

    name = fields.Char(string='Name', required=True)
    project_id = fields.Many2one(
        'farm.project',
        string='Project',
        required=True,
        ondelete='cascade',
        index=True,
    )
    business_activity = fields.Selection(
        related='project_id.business_activity',
        store=True,
        string='Business Activity',
    )

    # ── Risk scores ───────────────────────────────────────────────────────────

    delay_risk       = fields.Float(string='Delay Risk (0-100)',       digits=(16, 1))
    cost_risk        = fields.Float(string='Cost Risk (0-100)',        digits=(16, 1))
    procurement_risk = fields.Float(string='Procurement Risk (0-100)', digits=(16, 1))
    execution_risk   = fields.Float(string='Execution Risk (0-100)',   digits=(16, 1))
    claim_risk       = fields.Float(string='Claim Risk (0-100)',       digits=(16, 1))
    overall_risk_score = fields.Float(string='Overall Risk Score',     digits=(16, 1))

    status = fields.Selection(
        selection=[
            ('healthy',  'Healthy'),
            ('warning',  'Warning'),
            ('critical', 'Critical'),
        ],
        string='Status',
        default='healthy',
        index=True,
    )

    # ── Reason texts ──────────────────────────────────────────────────────────

    delay_reason       = fields.Text(string='Delay Reason')
    cost_reason        = fields.Text(string='Cost Reason')
    procurement_reason = fields.Text(string='Procurement Reason')
    execution_reason   = fields.Text(string='Execution Reason')
    claim_reason       = fields.Text(string='Claim Reason')

    # ── Rule linkage ──────────────────────────────────────────────────────────

    triggered_rule_ids = fields.Many2many(
        comodel_name='smart.ai.rule',
        relation='sai_risk_rule_rel',
        column1='risk_id',
        column2='rule_id',
        string='Triggered Rules',
    )
    triggered_rule_count = fields.Integer(
        string='Rules Fired',
        compute='_compute_triggered_rule_count',
        store=False,
    )

    # ── Timestamps & workflow ────────────────────────────────────────────────

    computed_at = fields.Datetime(string='Last Computed')
    state = fields.Selection(
        selection=[
            ('open',         'Open'),
            ('acknowledged', 'Acknowledged'),
            ('resolved',     'Resolved'),
        ],
        string='State',
        default='open',
        index=True,
    )
    acknowledged_by = fields.Many2one('res.users', string='Acknowledged By', readonly=True)
    acknowledged_at = fields.Datetime(string='Acknowledged At',              readonly=True)
    resolved_by     = fields.Many2one('res.users', string='Resolved By',     readonly=True)
    resolved_at     = fields.Datetime(string='Resolved At',                  readonly=True)

    # ── Compute ───────────────────────────────────────────────────────────────

    def _compute_triggered_rule_count(self):
        for rec in self:
            rec.triggered_rule_count = len(rec.triggered_rule_ids)

    # ── Generator ────────────────────────────────────────────────────────────

    @api.model
    def generate_for_project(self, project):
        """Upsert risk score for a project using base insight + rule engine."""
        # Layer 4a: base scores from existing AI insight engine
        Insight = self.env['construction.ai.insight']
        base    = Insight._compute_for_project(project)

        # Layer 4b: rule engine evaluation
        rules = self.env['smart.ai.rule'].search([
            ('active',            '=', True),
            ('business_activity', '=', 'construction'),
        ])
        triggered_rule_ids = []
        for rule in rules:
            try:
                fired, _val = rule.evaluate_for_project(project)
                if fired:
                    triggered_rule_ids.append(rule.id)
            except Exception as exc:
                _logger.warning('Rule evaluation failed (rule %s, project %s): %s', rule.id, project.id, exc)

        overall   = base.get('risk_score', 0.0)
        if overall >= 71:
            status = 'critical'
        elif overall >= 41:
            status = 'warning'
        else:
            status = 'healthy'

        reason = base.get('reason', '')
        # Distribute reason fragments across dimension fields
        reason_parts = [r.strip() for r in reason.split('·') if r.strip()]
        def _pick_reason(keyword):
            for p in reason_parts:
                if keyword.lower() in p.lower():
                    return p
            return ''

        vals = {
            'name':              f"Risk: {project.name} @ {fields.Datetime.now().strftime('%Y-%m-%d %H:%M')}",
            'project_id':        project.id,
            'delay_risk':        base.get('delay_score',       0.0),
            'cost_risk':         base.get('cost_risk',         0.0),
            'procurement_risk':  base.get('procurement_risk',  0.0),
            'execution_risk':    base.get('execution_risk',    0.0),
            'claim_risk':        base.get('claim_risk',        0.0),
            'overall_risk_score': overall,
            'status':            status,
            'delay_reason':      _pick_reason('past planned end') or _pick_reason('job orders'),
            'cost_reason':       _pick_reason('cost risk'),
            'procurement_reason':_pick_reason('material requests'),
            'execution_reason':  _pick_reason('inspection'),
            'claim_reason':      _pick_reason('claimed'),
            'triggered_rule_ids':[(6, 0, triggered_rule_ids)],
            'computed_at':       fields.Datetime.now(),
        }

        existing = self.search([('project_id', '=', project.id)], order='computed_at desc', limit=1)
        if existing:
            safe_vals = {k: v for k, v in vals.items()
                         if k not in ('state', 'acknowledged_by', 'acknowledged_at',
                                      'resolved_by', 'resolved_at')}
            existing.write(safe_vals)
            return existing

        vals['state'] = 'open'
        return self.create(vals)

    # ── Workflow actions ──────────────────────────────────────────────────────

    def action_acknowledge(self):
        for rec in self.filtered(lambda r: r.state == 'open'):
            rec.write({
                'state':           'acknowledged',
                'acknowledged_by': self.env.uid,
                'acknowledged_at': fields.Datetime.now(),
            })

    def action_resolve(self):
        for rec in self.filtered(lambda r: r.state in ('open', 'acknowledged')):
            rec.write({
                'state':      'resolved',
                'resolved_by': self.env.uid,
                'resolved_at': fields.Datetime.now(),
            })

    def action_recompute(self):
        self.ensure_one()
        self.generate_for_project(self.project_id)
        return {
            'type':   'ir.actions.client',
            'tag':    'display_notification',
            'params': {
                'title':   _('Risk Score Recomputed'),
                'message': _(
                    'Risk score recomputed for %(name)s — status: %(status)s (%(score).1f%%)',
                    name=self.project_id.name,
                    status=self.status.upper(),
                    score=self.overall_risk_score,
                ),
                'type':   'success',
                'sticky': False,
            },
        }
