"""
farm.job.order — Construction AI extension
==========================================

Adds computed AI risk panel fields to farm.job.order.
These fields pull from the parent project's latest AI insight,
making the project-level risk visible directly on each Job Order form.

All fields are store=False (read-only UI projection).
No business logic is modified.
"""
from odoo import api, fields, models


class FarmJobOrderConstructionExt(models.Model):
    _inherit = 'farm.job.order'

    # ── AI Panel fields (project-level risk projected onto the JO) ────────────

    jo_ai_risk_score = fields.Float(
        compute='_compute_jo_ai_panel',
        string='AI Risk Score',
        digits=(16, 1),
        store=False,
        help='Overall risk score from the project-level AI insight (0–100).',
    )
    jo_ai_status = fields.Selection(
        compute='_compute_jo_ai_panel',
        selection=[
            ('healthy',  'Healthy'),
            ('warning',  'Warning'),
            ('critical', 'Critical'),
        ],
        string='AI Status',
        store=False,
    )
    jo_ai_delay_score = fields.Float(
        compute='_compute_jo_ai_panel',
        string='Delay Risk',
        digits=(16, 1),
        store=False,
    )
    jo_ai_cost_risk = fields.Float(
        compute='_compute_jo_ai_panel',
        string='Cost Risk',
        digits=(16, 1),
        store=False,
    )
    jo_ai_procurement_risk = fields.Float(
        compute='_compute_jo_ai_panel',
        string='Procurement Risk',
        digits=(16, 1),
        store=False,
    )
    jo_ai_execution_risk = fields.Float(
        compute='_compute_jo_ai_panel',
        string='Execution Risk',
        digits=(16, 1),
        store=False,
    )
    jo_ai_claim_risk = fields.Float(
        compute='_compute_jo_ai_panel',
        string='Claim Risk',
        digits=(16, 1),
        store=False,
    )
    jo_ai_recommendation = fields.Text(
        compute='_compute_jo_ai_panel',
        string='AI Recommended Actions',
        store=False,
    )
    jo_ai_reason = fields.Text(
        compute='_compute_jo_ai_panel',
        string='AI Risk Reasons',
        store=False,
    )

    # ────────────────────────────────────────────────────────────────────────
    # Compute
    # ────────────────────────────────────────────────────────────────────────

    @api.depends(
        'project_id',
        'project_id.ai_insight_ids',
        'project_id.ai_insight_ids.date_generated',
        'project_id.ai_insight_ids.risk_score',
    )
    def _compute_jo_ai_panel(self):
        """Read project's latest AI insight and project values to JO fields."""
        Insight = self.env['construction.ai.insight']
        for rec in self:
            if not rec.project_id or rec.business_activity != 'construction':
                rec.jo_ai_risk_score       = 0.0
                rec.jo_ai_status           = False
                rec.jo_ai_delay_score      = 0.0
                rec.jo_ai_cost_risk        = 0.0
                rec.jo_ai_procurement_risk = 0.0
                rec.jo_ai_execution_risk   = 0.0
                rec.jo_ai_claim_risk       = 0.0
                rec.jo_ai_recommendation   = ''
                rec.jo_ai_reason           = ''
                continue

            insight = Insight.search(
                [('project_id', '=', rec.project_id.id)],
                order='date_generated desc',
                limit=1,
            )
            rec.jo_ai_risk_score       = insight.risk_score        if insight else 0.0
            rec.jo_ai_status           = insight.status            if insight else False
            rec.jo_ai_delay_score      = insight.delay_score       if insight else 0.0
            rec.jo_ai_cost_risk        = insight.cost_risk         if insight else 0.0
            rec.jo_ai_procurement_risk = insight.procurement_risk  if insight else 0.0
            rec.jo_ai_execution_risk   = insight.execution_risk    if insight else 0.0
            rec.jo_ai_claim_risk       = insight.claim_risk        if insight else 0.0
            rec.jo_ai_recommendation   = insight.recommended_action if insight else ''
            rec.jo_ai_reason           = insight.reason            if insight else ''

    # ────────────────────────────────────────────────────────────────────────
    # Action
    # ────────────────────────────────────────────────────────────────────────

    def action_open_project_ai_insight(self):
        """Button: open the project's AI insight record from the JO form."""
        self.ensure_one()
        if not self.project_id:
            return
        return self.project_id.action_open_ai_insights()
