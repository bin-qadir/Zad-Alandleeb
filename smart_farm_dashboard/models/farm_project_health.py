"""
SMART FARM DASHBOARD — PROJECT HEALTH ENGINE
============================================

Extends farm.project with three computed fields:

  project_health:    Selection(healthy / warning / critical)
  is_over_budget:    Boolean — actual_total_cost > contract_value
  is_negative_profit: Boolean — projected_profit < 0 in execution/closing

Health logic
------------
Pre-Tender:
  Always healthy — no financial data available yet.

Tender / Contract:
  critical  → estimated_cost > contract_value (loss-making at current estimate)
  warning   → estimated_cost > contract_value × 95 % (< 5 % margin)
  healthy   → otherwise

Execution / Closing (live data):
  critical  → projected_profit < 0 (forecasting a loss)
  warning   → gross_margin_pct < 5 %
              OR total_committed_cost > contract_value × 90 %
  healthy   → otherwise
"""

from odoo import api, fields, models

# ── Thresholds ────────────────────────────────────────────────────────────────
_MARGIN_CRITICAL    = 0.0    # projected_profit < 0 → critical
_MARGIN_WARNING_PCT = 5.0    # gross_margin_pct < 5 % → warning
_COMMIT_WARNING     = 0.90   # committed > 90 % of contract → warning
_PRE_EXEC_CRITICAL  = 1.0    # estimated > 100 % of contract → critical
_PRE_EXEC_WARNING   = 0.95   # estimated > 95 % of contract → warning


class FarmProjectHealth(models.Model):
    """Adds health scoring and risk flags to farm.project."""

    _inherit = 'farm.project'

    # ── Health score ──────────────────────────────────────────────────────────

    project_health = fields.Selection(
        selection=[
            ('healthy',  'Healthy'),
            ('warning',  'Warning'),
            ('critical', 'Critical'),
        ],
        string='Health',
        compute='_compute_project_health',
        store=True,
        default='healthy',
        help=(
            'Healthy  — project on track.\n'
            'Warning  — early risk signals (low margin, high commitment).\n'
            'Critical — loss forecast or over-budget.'
        ),
    )

    # ── Risk flags ────────────────────────────────────────────────────────────

    is_over_budget = fields.Boolean(
        string='Over Budget',
        compute='_compute_risk_flags',
        store=True,
        help='True when actual_total_cost exceeds contract_value.',
    )

    is_negative_profit = fields.Boolean(
        string='Negative Profit',
        compute='_compute_risk_flags',
        store=True,
        help='True when projected_profit < 0 during Execution or Closing phase.',
    )

    # ────────────────────────────────────────────────────────────────────────
    # Computes
    # ────────────────────────────────────────────────────────────────────────

    @api.depends(
        'project_phase',
        'projected_profit',
        'gross_margin_pct',
        'total_committed_cost',
        'contract_value',
        'estimated_cost',
    )
    def _compute_project_health(self):
        for rec in self:
            phase = rec.project_phase or 'pre_tender'

            if phase in ('execution', 'closing'):
                # Live data available — use forecast metrics
                if rec.projected_profit < _MARGIN_CRITICAL:
                    rec.project_health = 'critical'
                elif (
                    rec.gross_margin_pct < _MARGIN_WARNING_PCT
                    or (
                        rec.contract_value > 0
                        and rec.total_committed_cost > rec.contract_value * _COMMIT_WARNING
                    )
                ):
                    rec.project_health = 'warning'
                else:
                    rec.project_health = 'healthy'

            elif phase in ('tender', 'contract'):
                # Pre-execution with pricing data
                if rec.contract_value > 0 and rec.estimated_cost > rec.contract_value * _PRE_EXEC_CRITICAL:
                    rec.project_health = 'critical'
                elif rec.contract_value > 0 and rec.estimated_cost > rec.contract_value * _PRE_EXEC_WARNING:
                    rec.project_health = 'warning'
                else:
                    rec.project_health = 'healthy'

            else:
                # Pre-tender — no financial basis yet
                rec.project_health = 'healthy'

    @api.depends(
        'contract_value',
        'actual_total_cost',
        'projected_profit',
        'project_phase',
    )
    def _compute_risk_flags(self):
        for rec in self:
            rec.is_over_budget = (
                rec.contract_value > 0
                and rec.actual_total_cost > rec.contract_value
            )
            rec.is_negative_profit = (
                rec.project_phase in ('execution', 'closing')
                and rec.projected_profit < 0
            )
