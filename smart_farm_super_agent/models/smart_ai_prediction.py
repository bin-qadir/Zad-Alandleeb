"""
smart.ai.prediction — Layer 5: Prediction Engine
=================================================
Deterministic forward-looking predictions based on current project state.
"""
import logging
from datetime import date
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class SmartAiPrediction(models.Model):
    _name        = 'smart.ai.prediction'
    _description = 'AI Prediction — Layer 5 Prediction Engine'
    _order       = 'computed_at desc'
    _rec_name    = 'name'

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

    predicted_delay_days      = fields.Float(string='Predicted Delay (days)',    digits=(16, 0))
    predicted_budget_overrun  = fields.Float(string='Predicted Budget Overrun (%)', digits=(16, 1))
    predicted_material_shortage = fields.Integer(string='Predicted Material Shortages')
    predicted_claim_value     = fields.Float(string='Predicted Claim Value',     digits=(16, 2))
    confidence_score          = fields.Float(string='Confidence (%)',            digits=(16, 0))
    alert_level = fields.Selection(
        selection=[
            ('none',   'None'),
            ('low',    'Low'),
            ('medium', 'Medium'),
            ('high',   'High'),
        ],
        string='Alert Level',
        default='none',
    )
    reason      = fields.Text(string='Prediction Basis')
    method      = fields.Char(string='Method Used', default='deterministic_v1')
    computed_at = fields.Datetime(string='Computed At')

    # ── Generator ────────────────────────────────────────────────────────────

    @api.model
    def generate_for_project(self, project):
        """Upsert prediction record for a project."""
        pred = self._compute_predictions(project)
        name = f"Prediction: {project.name} @ {fields.Datetime.now().strftime('%Y-%m-%d %H:%M')}"
        pred.update({'name': name, 'project_id': project.id, 'computed_at': fields.Datetime.now()})

        existing = self.search([('project_id', '=', project.id)], order='computed_at desc', limit=1)
        if existing:
            existing.write(pred)
            return existing
        return self.create(pred)

    @api.model
    def _compute_predictions(self, project):
        """Return a dict of prediction values for the given project."""
        today = date.today()
        jos   = self.env['farm.job.order'].search([('project_id', '=', project.id)])

        # ── Delay prediction ──────────────────────────────────────────────────
        predicted_delay_days = 0.0
        end_date   = getattr(project, 'end_date',   False)
        start_date = getattr(project, 'start_date', False)
        if end_date:
            if end_date < today:
                predicted_delay_days = float((today - end_date).days)
            elif start_date:
                total_days   = (end_date - start_date).days
                elapsed_days = (today - start_date).days
                progress_pct = getattr(project, 'execution_progress_pct', 0.0) or 0.0
                if total_days > 0 and elapsed_days > 0 and progress_pct > 0:
                    expected_pct = elapsed_days / total_days * 100.0
                    if expected_pct > progress_pct + 5:
                        behind_ratio         = (expected_pct - progress_pct) / expected_pct
                        predicted_delay_days = round(behind_ratio * total_days, 0)

        # ── Budget overrun prediction ─────────────────────────────────────────
        predicted_budget_overrun = 0.0
        planned_value = sum(j.planned_qty * j.unit_price for j in jos)
        actual_cost   = sum(getattr(j, 'actual_total_cost', 0.0) or 0.0 for j in jos)
        if planned_value > 0 and actual_cost > 0:
            progress_pct = getattr(project, 'execution_progress_pct', 0.0) or 0.0
            if progress_pct > 5:
                projected_total      = actual_cost / (progress_pct / 100.0)
                overrun_pct          = (projected_total / planned_value - 1.0) * 100.0
                predicted_budget_overrun = round(max(0.0, overrun_pct), 1)

        # ── Material shortage ─────────────────────────────────────────────────
        pending_mr = self.env['farm.material.request'].search_count([
            ('project_id', '=', project.id),
            ('state', 'in', ['draft', 'to_approve']),
        ])
        predicted_material_shortage = pending_mr

        # ── Claim value ───────────────────────────────────────────────────────
        predicted_claim_value = sum(
            getattr(j, 'claimable_amount', 0.0) or 0.0 for j in jos
        )

        # ── Confidence ───────────────────────────────────────────────────────
        confidence = 30.0
        if jos:
            confidence += 20.0
        if start_date and end_date:
            confidence += 20.0
        if planned_value > 0:
            confidence += 15.0
        if actual_cost > 0:
            confidence += 15.0
        confidence = min(95.0, confidence)

        # ── Alert level ───────────────────────────────────────────────────────
        if predicted_delay_days > 30 or predicted_budget_overrun > 20:
            alert_level = 'high'
        elif predicted_delay_days > 7 or predicted_budget_overrun > 10:
            alert_level = 'medium'
        elif predicted_delay_days > 0 or predicted_budget_overrun > 0:
            alert_level = 'low'
        else:
            alert_level = 'none'

        # ── Reason ───────────────────────────────────────────────────────────
        reason_parts = [f"Based on {len(jos)} job order(s)."]
        if predicted_delay_days > 0:
            reason_parts.append(f"Delay: project is behind schedule — estimated {predicted_delay_days:.0f} day(s) late.")
        if predicted_budget_overrun > 0:
            reason_parts.append(f"Budget: cost trend projects {predicted_budget_overrun:.1f}% overrun.")
        if predicted_claim_value > 0:
            reason_parts.append(f"Claim opportunity: AED {predicted_claim_value:,.2f} claimable.")
        if pending_mr > 0:
            reason_parts.append(f"Material: {pending_mr} pending material request(s).")
        reason = ' '.join(reason_parts)

        return {
            'predicted_delay_days':       predicted_delay_days,
            'predicted_budget_overrun':   predicted_budget_overrun,
            'predicted_material_shortage':predicted_material_shortage,
            'predicted_claim_value':      predicted_claim_value,
            'confidence_score':           confidence,
            'alert_level':                alert_level,
            'reason':                     reason,
            'method':                     'deterministic_v1',
        }
