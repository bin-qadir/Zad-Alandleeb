"""
farm.project — Super Agent extension
=====================================
Adds O2M linkage fields and computed summary fields for the AI Brain tab.
"""
from odoo import api, fields, models, _


class FarmProjectSuperAgentExt(models.Model):
    _inherit = 'farm.project'

    # ── O2M linkage ───────────────────────────────────────────────────────────

    sai_risk_score_ids = fields.One2many(
        'smart.ai.risk.score', 'project_id',
        string='Super Agent Risk Scores',
    )
    sai_prediction_ids = fields.One2many(
        'smart.ai.prediction', 'project_id',
        string='AI Predictions',
    )
    sai_suggestion_ids = fields.One2many(
        'smart.ai.optimization.suggestion', 'project_id',
        string='Optimization Suggestions',
    )
    sai_action_ids = fields.One2many(
        'smart.ai.action', 'project_id',
        string='AI Actions',
    )
    sai_knowledge_ids = fields.One2many(
        'smart.ai.knowledge.document', 'project_id',
        string='Knowledge Documents',
    )

    # ── Computed summary (store=False) ────────────────────────────────────────

    sai_latest_risk_status = fields.Selection(
        selection=[
            ('healthy',  'Healthy'),
            ('warning',  'Warning'),
            ('critical', 'Critical'),
        ],
        string='Latest AI Risk Status',
        compute='_compute_sai_summary',
        store=False,
    )
    sai_latest_risk_score = fields.Float(
        string='Latest AI Risk Score',
        digits=(16, 1),
        compute='_compute_sai_summary',
        store=False,
    )
    sai_pending_actions_count = fields.Integer(
        string='Pending AI Actions',
        compute='_compute_sai_summary',
        store=False,
    )
    sai_open_suggestions_count = fields.Integer(
        string='Open AI Suggestions',
        compute='_compute_sai_summary',
        store=False,
    )

    @api.depends('sai_risk_score_ids', 'sai_risk_score_ids.overall_risk_score',
                 'sai_action_ids', 'sai_suggestion_ids')
    def _compute_sai_summary(self):
        for rec in self:
            latest_score = self.env['smart.ai.risk.score'].search(
                [('project_id', '=', rec.id)], order='computed_at desc', limit=1
            )
            rec.sai_latest_risk_status = latest_score.status if latest_score else False
            rec.sai_latest_risk_score  = latest_score.overall_risk_score if latest_score else 0.0
            rec.sai_pending_actions_count = self.env['smart.ai.action'].search_count([
                ('project_id', '=', rec.id),
                ('state', 'in', ['draft', 'waiting_approval']),
            ])
            rec.sai_open_suggestions_count = self.env['smart.ai.optimization.suggestion'].search_count([
                ('project_id', '=', rec.id),
                ('state', '=', 'pending'),
            ])

    # ── Button action ─────────────────────────────────────────────────────────

    def action_run_super_agent_analysis(self):
        self.ensure_one()
        import logging
        _logger = logging.getLogger(__name__)
        for layer, model_name in [
            ('Context Snapshot', 'smart.ai.context.snapshot'),
            ('Risk Score',       'smart.ai.risk.score'),
            ('Prediction',       'smart.ai.prediction'),
            ('Suggestions',      'smart.ai.optimization.suggestion'),
        ]:
            try:
                self.env[model_name].generate_for_project(self) \
                    if model_name != 'smart.ai.context.snapshot' \
                    else self.env[model_name].capture_for_project(self)
            except Exception as exc:
                _logger.warning('Super Agent layer %s failed for project %s: %s', layer, self.id, exc)

        return {
            'type':   'ir.actions.client',
            'tag':    'display_notification',
            'params': {
                'title':   _('Super Agent Analysis Complete'),
                'message': _(
                    'AI analysis complete for %(name)s.',
                    name=self.name,
                ),
                'type':   'success',
                'sticky': False,
            },
        }
