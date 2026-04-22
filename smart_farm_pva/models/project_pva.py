"""
SMART FARM PVA — PROJECT LEVEL
================================

Extends farm.project with the revenue-side Planned vs Actual engine and
two additional risk flags not yet present in smart_farm_dashboard.

ALREADY on farm.project (do NOT redefine — from smart_farm_control):
  estimated_cost, contract_value
  actual_material_cost, actual_labour_cost, actual_subcontract_cost,
  actual_other_cost, actual_total_cost
  committed_material_cost, committed_subcontract_cost, total_committed_cost
  forecast_final_cost, gross_margin_pct
  estimated_profit, current_profit, committed_profit, projected_profit
  contract_vs_estimate_variance, contract_vs_actual_variance,
  estimate_vs_actual_variance
  revenue, vendor_bill_cost, realized_profit

ALREADY on farm.project (from smart_farm_dashboard):
  is_over_budget, is_negative_profit, project_health

NEW fields added here:

  JO-based planned revenue
  ------------------------
  jo_planned_revenue   = Σ (JO.planned_qty × JO.unit_price)
                         What we planned to bill according to the BOQ contract
                         quantities.  Differs from contract_value (which is the
                         approved SO amount).

  jo_actual_revenue    = Σ JO.claim_amount
                         Total revenue earned from submitted claims.
                         Same source as revenue fallback in smart_farm_control,
                         but here it is ALWAYS from claims (not invoice-preferred)
                         to give a consistent JO-scope comparison.

  jo_revenue_variance  = jo_actual_revenue − jo_planned_revenue

  JO-based profitability
  ----------------------
  jo_planned_profit    = jo_planned_revenue − estimated_cost
  jo_actual_profit     = jo_actual_revenue  − actual_total_cost
  jo_profit_variance   = jo_actual_profit   − jo_planned_profit
  jo_planned_margin    = jo_planned_profit  / jo_planned_revenue × 100
  jo_actual_margin     = jo_actual_profit   / jo_actual_revenue  × 100

  Additional risk flags
  ---------------------
  is_low_margin    = jo_actual_margin > 0 AND jo_actual_margin < threshold
  has_qty_overrun  = any JO has approved_qty > planned_qty
"""
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# Threshold: margin below this % raises the low-margin flag
_LOW_MARGIN_THRESHOLD = 10.0


class FarmProjectPva(models.Model):
    """Revenue-side PVA and additional risk flags for farm.project."""

    _inherit = 'farm.project'

    # ── JO-based planned revenue ──────────────────────────────────────────────

    jo_planned_revenue = fields.Float(
        string='Planned Revenue (BOQ)',
        compute='_compute_project_pva',
        store=True,
        digits=(16, 2),
        help=(
            'Sum of (planned_qty × unit_price) across all Job Orders.\n\n'
            'This is the BOQ-contract revenue basis: the total expected billing '
            'if every JO is executed exactly at its planned quantity and BOQ price.\n\n'
            'Compare with contract_value (approved SO amount) for commercial gap.'
        ),
    )

    jo_actual_revenue = fields.Float(
        string='Actual Revenue (Claims)',
        compute='_compute_project_pva',
        store=True,
        digits=(16, 2),
        help=(
            'Sum of claim_amount across all Job Orders.\n\n'
            'Represents earned revenue from submitted claims '
            '(claimed_qty × unit_price per JO).\n\n'
            'Always JO-claim based — use revenue (smart_farm_control) '
            'for the invoice-preferred version.'
        ),
    )

    jo_revenue_variance = fields.Float(
        string='Revenue Variance',
        compute='_compute_project_pva',
        store=True,
        digits=(16, 2),
        help=(
            'jo_actual_revenue − jo_planned_revenue.\n'
            'Negative = behind billing plan.'
        ),
    )

    # ── JO-based profitability ────────────────────────────────────────────────

    jo_planned_profit = fields.Float(
        string='Planned Profit (BOQ)',
        compute='_compute_project_pva',
        store=True,
        digits=(16, 2),
        help='jo_planned_revenue − estimated_cost.',
    )
    jo_actual_profit = fields.Float(
        string='Actual Profit (Claims)',
        compute='_compute_project_pva',
        store=True,
        digits=(16, 2),
        help='jo_actual_revenue − actual_total_cost.',
    )
    jo_profit_variance = fields.Float(
        string='Profit Variance',
        compute='_compute_project_pva',
        store=True,
        digits=(16, 2),
        help='jo_actual_profit − jo_planned_profit.',
    )
    jo_planned_margin = fields.Float(
        string='Planned Margin %',
        compute='_compute_project_pva',
        store=True,
        digits=(16, 1),
        help='jo_planned_profit / jo_planned_revenue × 100',
    )
    jo_actual_margin = fields.Float(
        string='Actual Margin %',
        compute='_compute_project_pva',
        store=True,
        digits=(16, 1),
        help='jo_actual_profit / jo_actual_revenue × 100',
    )

    # ── Additional risk flags ─────────────────────────────────────────────────

    is_low_margin = fields.Boolean(
        string='Low Margin',
        compute='_compute_pva_flags',
        store=True,
        help=(
            f'True when jo_actual_margin is between 0 % and {_LOW_MARGIN_THRESHOLD} %.\n'
            'Indicates work is ongoing and margin is thin but not yet negative.'
        ),
    )
    has_qty_overrun = fields.Boolean(
        string='Qty Overrun',
        compute='_compute_pva_flags',
        store=True,
        help=(
            'True when at least one Job Order has approved_qty > planned_qty.\n'
            'Signals scope creep or over-execution against the BOQ contract qty.'
        ),
    )

    # ────────────────────────────────────────────────────────────────────────
    # Computes
    # ────────────────────────────────────────────────────────────────────────

    @api.depends(
        'job_order_ids.planned_qty',
        'job_order_ids.unit_price',
        'job_order_ids.claimed_qty',
        'job_order_ids.claim_amount',
        'estimated_cost',
        'actual_total_cost',
    )
    def _compute_project_pva(self):
        for rec in self:
            jos = rec.job_order_ids

            # Revenue (BOQ price basis)
            planned_rev = sum(jo.planned_qty * jo.unit_price for jo in jos)
            actual_rev  = sum(jos.mapped('claim_amount'))

            # Cost (from smart_farm_control's full-bucket actual)
            planned_cost = rec.estimated_cost   # from approved BOQ analyses
            actual_cost  = rec.actual_total_cost  # mat+lab+sub+other (4 buckets)

            # Store revenue fields
            rec.jo_planned_revenue  = planned_rev
            rec.jo_actual_revenue   = actual_rev
            rec.jo_revenue_variance = actual_rev - planned_rev

            # Profitability
            planned_profit = planned_rev - planned_cost
            actual_profit  = actual_rev  - actual_cost

            rec.jo_planned_profit  = planned_profit
            rec.jo_actual_profit   = actual_profit
            rec.jo_profit_variance = actual_profit - planned_profit

            rec.jo_planned_margin = (
                planned_profit / planned_rev * 100.0
                if planned_rev else 0.0
            )
            rec.jo_actual_margin = (
                actual_profit / actual_rev * 100.0
                if actual_rev else 0.0
            )

    @api.depends(
        'jo_actual_margin',
        'job_order_ids.approved_qty',
        'job_order_ids.planned_qty',
    )
    def _compute_pva_flags(self):
        for rec in self:
            # Low margin: earning but thin margin
            margin = rec.jo_actual_margin
            rec.is_low_margin = bool(
                rec.jo_actual_revenue
                and 0.0 < margin < _LOW_MARGIN_THRESHOLD
            )

            # Quantity overrun: any JO executed beyond planned scope
            rec.has_qty_overrun = any(
                jo.approved_qty > jo.planned_qty
                for jo in rec.job_order_ids
                if jo.planned_qty > 0
            )
