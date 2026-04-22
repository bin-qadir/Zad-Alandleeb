"""
SMART FARM PVA — JOB ORDER LEVEL
=================================

Extends farm.job.order with Planned vs Actual fields that are NOT yet
present on the model.

ALREADY on farm.job.order (do NOT redefine):
  planned_qty, planned_cost, unit_price
  approved_qty, claimed_qty, claim_amount
  actual_material_cost, actual_labour_cost, actual_subcontract_cost,
  actual_other_cost, actual_total_cost
  cost_variance, cost_variance_percent
  progress_percent, approved_amount, claimable_amount

NEW fields added here:

  Quantity variance
  -----------------
  qty_variance        = approved_qty − planned_qty
  qty_variance_pct    = qty_variance / planned_qty × 100

  Revenue (BOQ price basis)
  -------------------------
  planned_sales_amount  = planned_qty × unit_price   (what we planned to bill)
  sales_variance        = claim_amount − planned_sales_amount

  Profitability (per JO)
  ----------------------
  jo_planned_profit     = planned_sales_amount − planned_cost
  jo_actual_profit      = claim_amount − actual_total_cost
  jo_profit_variance    = jo_actual_profit − jo_planned_profit
  planned_margin_pct    = jo_planned_profit / planned_sales_amount × 100
  actual_margin_pct     = jo_actual_profit  / claim_amount × 100

  Status flags
  ------------
  pva_qty_overrun   = approved_qty > planned_qty (over-executed scope)
"""
from odoo import api, fields, models


class FarmJobOrderPva(models.Model):
    """PVA extension for farm.job.order."""

    _inherit = 'farm.job.order'

    # ── Quantity variance ─────────────────────────────────────────────────────

    qty_variance = fields.Float(
        string='Qty Variance',
        compute='_compute_jo_qty_pva',
        digits=(16, 2),
        help='Approved Qty − Planned Qty.\nNegative = under-executed.',
    )
    qty_variance_pct = fields.Float(
        string='Qty Var %',
        compute='_compute_jo_qty_pva',
        digits=(16, 1),
        help='(approved_qty − planned_qty) / planned_qty × 100',
    )

    # ── Revenue (BOQ price basis) ─────────────────────────────────────────────

    planned_sales_amount = fields.Float(
        string='Planned Revenue',
        compute='_compute_jo_revenue_pva',
        digits=(16, 2),
        help=(
            'planned_qty × unit_price.\n'
            'The total revenue expected if this JO is executed as planned.'
        ),
    )
    # actual_sales_amount = claim_amount (already on the model)
    sales_variance = fields.Float(
        string='Revenue Variance',
        compute='_compute_jo_revenue_pva',
        digits=(16, 2),
        help='Claimed Amount − Planned Revenue.\nNegative = under-claimed vs plan.',
    )

    # ── Profitability (per JO) ────────────────────────────────────────────────

    jo_planned_profit = fields.Float(
        string='Planned Profit',
        compute='_compute_jo_profit_pva',
        digits=(16, 2),
        help='Planned Revenue − Planned Cost (from analysis line).',
    )
    jo_actual_profit = fields.Float(
        string='Actual Profit',
        compute='_compute_jo_profit_pva',
        digits=(16, 2),
        help='Claimed Amount − Actual Total Cost.',
    )
    jo_profit_variance = fields.Float(
        string='Profit Variance',
        compute='_compute_jo_profit_pva',
        digits=(16, 2),
        help='Actual Profit − Planned Profit.',
    )
    planned_margin_pct = fields.Float(
        string='Planned Margin %',
        compute='_compute_jo_profit_pva',
        digits=(16, 1),
        help='jo_planned_profit / planned_sales_amount × 100',
    )
    actual_margin_pct = fields.Float(
        string='Actual Margin %',
        compute='_compute_jo_profit_pva',
        digits=(16, 1),
        help='jo_actual_profit / claim_amount × 100',
    )

    # ── Status flags ──────────────────────────────────────────────────────────

    pva_qty_overrun = fields.Boolean(
        string='Qty Overrun',
        compute='_compute_jo_pva_flags',
        help='True when approved_qty exceeds planned_qty (scope over-run).',
    )

    # ── Computes ──────────────────────────────────────────────────────────────

    @api.depends('approved_qty', 'planned_qty')
    def _compute_jo_qty_pva(self):
        for rec in self:
            rec.qty_variance = rec.approved_qty - rec.planned_qty
            rec.qty_variance_pct = (
                rec.qty_variance / rec.planned_qty * 100.0
                if rec.planned_qty else 0.0
            )

    @api.depends('planned_qty', 'unit_price', 'claim_amount')
    def _compute_jo_revenue_pva(self):
        for rec in self:
            rec.planned_sales_amount = rec.planned_qty * rec.unit_price
            rec.sales_variance = rec.claim_amount - rec.planned_sales_amount

    @api.depends('planned_sales_amount', 'planned_cost',
                 'claim_amount', 'actual_total_cost')
    def _compute_jo_profit_pva(self):
        for rec in self:
            planned_rev  = rec.planned_sales_amount
            planned_cost = rec.planned_cost
            actual_rev   = rec.claim_amount
            actual_cost  = rec.actual_total_cost

            rec.jo_planned_profit  = planned_rev  - planned_cost
            rec.jo_actual_profit   = actual_rev   - actual_cost
            rec.jo_profit_variance = rec.jo_actual_profit - rec.jo_planned_profit

            rec.planned_margin_pct = (
                rec.jo_planned_profit / planned_rev * 100.0
                if planned_rev else 0.0
            )
            rec.actual_margin_pct = (
                rec.jo_actual_profit / actual_rev * 100.0
                if actual_rev else 0.0
            )

    @api.depends('approved_qty', 'planned_qty')
    def _compute_jo_pva_flags(self):
        for rec in self:
            rec.pva_qty_overrun = (
                rec.planned_qty > 0 and rec.approved_qty > rec.planned_qty
            )
