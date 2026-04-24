"""
smart.ai.optimization.suggestion — Layer 7: Optimization Engine
===============================================================
AI-generated suggestions for project optimization.
"""
import logging
from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)

SUGGESTION_TYPES = [
    ('manpower',    'Manpower Allocation'),
    ('procurement', 'Procurement Priority'),
    ('execution',   'Execution Priority'),
    ('claim',       'Claim Submission'),
    ('budget',      'Budget Control'),
    ('scheduling',  'Schedule Optimization'),
    ('inspection',  'Inspection Acceleration'),
]


class SmartAiOptimizationSuggestion(models.Model):
    _name        = 'smart.ai.optimization.suggestion'
    _description = 'AI Optimization Suggestion — Layer 7'
    _order       = 'priority desc, suggested_at desc'
    _rec_name    = 'name'

    name = fields.Char(string='Suggestion', required=True)
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

    suggestion_type  = fields.Selection(SUGGESTION_TYPES, string='Type',     required=True)
    title            = fields.Char(string='Title',    required=True)
    description      = fields.Text(string='Description')
    expected_impact  = fields.Text(string='Expected Impact')
    reason           = fields.Text(string='AI Reasoning')
    confidence_score = fields.Float(string='Confidence (%)', digits=(16, 0))
    priority = fields.Selection(
        selection=[('low', 'Low'), ('medium', 'Medium'), ('high', 'High')],
        string='Priority',
        default='medium',
        index=True,
    )
    state = fields.Selection(
        selection=[
            ('pending',   'Pending'),
            ('applied',   'Applied'),
            ('dismissed', 'Dismissed'),
        ],
        string='State',
        default='pending',
        index=True,
    )
    suggested_at = fields.Datetime(string='Suggested At', default=fields.Datetime.now)
    applied_by   = fields.Many2one('res.users', string='Applied By',   readonly=True)
    applied_at   = fields.Datetime(string='Applied At',                readonly=True)
    dismissed_by = fields.Many2one('res.users', string='Dismissed By', readonly=True)
    dismissed_at = fields.Datetime(string='Dismissed At',              readonly=True)
    risk_score_id = fields.Many2one(
        'smart.ai.risk.score',
        string='Source Risk Score',
        ondelete='set null',
    )

    # ── Generator ────────────────────────────────────────────────────────────

    @api.model
    def generate_for_project(self, project):
        """Generate fresh suggestions from the latest risk score."""
        score = self.env['smart.ai.risk.score'].search(
            [('project_id', '=', project.id)], order='computed_at desc', limit=1
        )

        # Clear stale pending suggestions
        self.search([('project_id', '=', project.id), ('state', '=', 'pending')]).unlink()

        suggestions = []
        now = fields.Datetime.now()

        def _priority(risk):
            if risk >= 71:
                return 'high'
            if risk >= 41:
                return 'medium'
            return 'low'

        def _confidence(risk):
            return round(min(95.0, 60.0 + risk / 100.0 * 35.0), 0)

        if score:
            if score.delay_risk >= 50:
                suggestions.append({
                    'name':            f"Manpower: {project.name}",
                    'project_id':      project.id,
                    'suggestion_type': 'manpower',
                    'title':           'Mobilise additional resources to recover schedule',
                    'description':     f"Delay risk is {score.delay_risk:.1f}%. Critical path activities are at risk.",
                    'expected_impact': 'Reduce predicted delay by up to 40% with targeted resource addition.',
                    'reason':          f"Delay risk score {score.delay_risk:.1f}% exceeds threshold of 50%.",
                    'confidence_score':_confidence(score.delay_risk),
                    'priority':        _priority(score.delay_risk),
                    'risk_score_id':   score.id,
                    'suggested_at':    now,
                })

            if score.procurement_risk >= 50:
                suggestions.append({
                    'name':            f"Procurement: {project.name}",
                    'project_id':      project.id,
                    'suggestion_type': 'procurement',
                    'title':           'Expedite pending procurement and material requests',
                    'description':     f"Procurement risk is {score.procurement_risk:.1f}%. Material supply chain is a bottleneck.",
                    'expected_impact': 'Clear procurement backlog within 5 working days.',
                    'reason':          f"Procurement risk score {score.procurement_risk:.1f}% exceeds threshold of 50%.",
                    'confidence_score':_confidence(score.procurement_risk),
                    'priority':        _priority(score.procurement_risk),
                    'risk_score_id':   score.id,
                    'suggested_at':    now,
                })

            if score.execution_risk >= 50:
                suggestions.append({
                    'name':            f"Inspection: {project.name}",
                    'project_id':      project.id,
                    'suggestion_type': 'inspection',
                    'title':           'Accelerate inspection queue to unblock execution',
                    'description':     f"Execution risk is {score.execution_risk:.1f}%. Job orders are stuck in inspection/approval.",
                    'expected_impact': 'Unblock stalled JOs and restore execution momentum.',
                    'reason':          f"Execution risk score {score.execution_risk:.1f}% exceeds threshold of 50%.",
                    'confidence_score':_confidence(score.execution_risk),
                    'priority':        _priority(score.execution_risk),
                    'risk_score_id':   score.id,
                    'suggested_at':    now,
                })

            if score.claim_risk >= 50:
                suggestions.append({
                    'name':            f"Claim: {project.name}",
                    'project_id':      project.id,
                    'suggestion_type': 'claim',
                    'title':           'Submit interim claim to recover approved value',
                    'description':     f"Claim risk is {score.claim_risk:.1f}%. Significant approved value is unclaimed.",
                    'expected_impact': 'Improve project cash flow by submitting pending claims.',
                    'reason':          f"Claim risk score {score.claim_risk:.1f}% exceeds threshold of 50%.",
                    'confidence_score':_confidence(score.claim_risk),
                    'priority':        _priority(score.claim_risk),
                    'risk_score_id':   score.id,
                    'suggested_at':    now,
                })

            if score.cost_risk >= 50:
                suggestions.append({
                    'name':            f"Budget: {project.name}",
                    'project_id':      project.id,
                    'suggestion_type': 'budget',
                    'title':           'Implement budget control measures immediately',
                    'description':     f"Cost risk is {score.cost_risk:.1f}%. Spending is trending above approved budget.",
                    'expected_impact': 'Prevent further cost overrun by freezing non-critical expenditure.',
                    'reason':          f"Cost risk score {score.cost_risk:.1f}% exceeds threshold of 50%.",
                    'confidence_score':_confidence(score.cost_risk),
                    'priority':        _priority(score.cost_risk),
                    'risk_score_id':   score.id,
                    'suggested_at':    now,
                })

        for vals in suggestions:
            self.create(vals)

    # ── Workflow actions ──────────────────────────────────────────────────────

    def action_apply(self):
        self.ensure_one()
        self.write({
            'state':      'applied',
            'applied_by': self.env.uid,
            'applied_at': fields.Datetime.now(),
        })

    def action_dismiss(self):
        self.ensure_one()
        self.write({
            'state':        'dismissed',
            'dismissed_by': self.env.uid,
            'dismissed_at': fields.Datetime.now(),
        })
