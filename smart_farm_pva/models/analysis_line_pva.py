"""
SMART FARM PVA — BOQ ANALYSIS LINE LEVEL
==========================================

Extends farm.boq.analysis.line with execution-side actuals pulled from
Job Orders that reference this analysis line.

The link is farm.job.order.analysis_line_id (Many2one → farm.boq.analysis.line).
Not all JOs carry this link (it is optional), so the 'actual' figures
represent only the JOs that are explicitly traced back to this line.

ALREADY on farm.boq.analysis.line (do NOT redefine):
  boq_qty           — planned quantity (from BOQ)
  cost_unit_price   — planned cost price per unit
  sale_unit_price   — planned sale price per unit
  cost_total        — boq_qty × cost_unit_price  (planned cost)
  sale_total        — boq_qty × sale_unit_price  (planned revenue)
  profit            — sale_total − cost_total
  margin            — profit / cost_total × 100

NEW fields added here:

  jo_ids             — back-relation to JOs linked to this analysis line
  actual_approved_qty  = Σ jo.approved_qty
  actual_claimed_qty   = Σ jo.claimed_qty
  qty_variance         = actual_approved_qty − boq_qty
  qty_variance_pct     = qty_variance / boq_qty × 100
  actual_claimed_rev   = Σ jo.claim_amount  (actual earned revenue from claims)
  actual_cost_jos      = Σ jo.actual_total_cost
"""
from odoo import api, fields, models


class FarmBoqAnalysisLinePva(models.Model):
    """PVA extension for farm.boq.analysis.line."""

    _inherit = 'farm.boq.analysis.line'

    # ── Back-relation to Job Orders ───────────────────────────────────────────

    jo_ids = fields.One2many(
        comodel_name='farm.job.order',
        inverse_name='analysis_line_id',
        string='Linked Job Orders',
    )

    # ── Actual quantities (from JOs) ──────────────────────────────────────────

    actual_approved_qty = fields.Float(
        string='Actual Approved Qty',
        compute='_compute_line_pva',
        digits=(16, 2),
        help='Sum of approved_qty from all Job Orders linked to this line.',
    )
    actual_claimed_qty = fields.Float(
        string='Actual Claimed Qty',
        compute='_compute_line_pva',
        digits=(16, 2),
        help='Sum of claimed_qty from all Job Orders linked to this line.',
    )

    # ── Quantity variance ─────────────────────────────────────────────────────

    qty_variance = fields.Float(
        string='Qty Variance',
        compute='_compute_line_pva',
        digits=(16, 2),
        help='actual_approved_qty − boq_qty.\nNegative = under-executed vs BOQ.',
    )
    qty_variance_pct = fields.Float(
        string='Qty Var %',
        compute='_compute_line_pva',
        digits=(16, 1),
        help='qty_variance / boq_qty × 100',
    )

    # ── Actual revenue & cost (from JOs) ─────────────────────────────────────

    actual_claimed_rev = fields.Float(
        string='Actual Claimed Revenue',
        compute='_compute_line_pva',
        digits=(16, 2),
        help='Sum of claim_amount from all Job Orders linked to this line.',
    )
    actual_cost_jos = fields.Float(
        string='Actual Cost (JOs)',
        compute='_compute_line_pva',
        digits=(16, 2),
        help=(
            'Sum of actual_total_cost from all Job Orders linked to this line.\n'
            'Includes: material + labour + subcontract + other.'
        ),
    )

    # ── Compute ───────────────────────────────────────────────────────────────

    @api.depends(
        'jo_ids.approved_qty',
        'jo_ids.claimed_qty',
        'jo_ids.claim_amount',
        'jo_ids.actual_total_cost',
        'boq_qty',
    )
    def _compute_line_pva(self):
        for rec in self:
            jos = rec.jo_ids.filtered(
                lambda j: j.business_activity == 'construction'
            )

            app_qty    = sum(jos.mapped('approved_qty'))
            claim_qty  = sum(jos.mapped('claimed_qty'))
            claim_rev  = sum(jos.mapped('claim_amount'))
            actual_cost = sum(jos.mapped('actual_total_cost'))

            rec.actual_approved_qty = app_qty
            rec.actual_claimed_qty  = claim_qty
            rec.actual_claimed_rev  = claim_rev
            rec.actual_cost_jos     = actual_cost

            rec.qty_variance = app_qty - rec.boq_qty
            rec.qty_variance_pct = (
                rec.qty_variance / rec.boq_qty * 100.0
                if rec.boq_qty else 0.0
            )
