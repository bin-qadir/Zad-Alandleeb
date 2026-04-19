"""
SMART FARM CONTROL — COST CONTROL + PROFIT / VARIANCE ENGINE
=============================================================

Extends farm.project with a comprehensive cost-control, profit, and
variance engine.

COST BUCKETS (project-level):
  ┌─────────────────────────────────────────────────────────────────┐
  │ Estimated Cost      = Σ approved BOQ Analysis total_cost         │
  │ Contract Value      = Σ approved SO amount_untaxed               │
  │ ─────────────────────────────────────────────────────────────── │
  │ Committed Mat.      = Σ confirmed PO amount_untaxed              │
  │ Committed Sub.      = Σ JO actual_subcontract_cost (proxy)       │
  │ Total Committed     = Committed Mat. + Committed Sub.            │
  │ ─────────────────────────────────────────────────────────────── │
  │ Actual Material     = Σ JO actual_material_cost                  │
  │ Actual Labour       = Σ JO actual_labour_cost                    │
  │ Actual Subcontract  = Σ JO actual_subcontract_cost               │
  │ Actual Other        = Σ JO actual_other_cost                     │
  │ Total Actual        = Mat + Lab + Sub + Other                    │
  │ ─────────────────────────────────────────────────────────────── │
  │ Forecast Final      = actual_total + Σ(planned × remaining%)     │
  │ Gross Margin %      = (contract − forecast) / contract × 100     │
  └─────────────────────────────────────────────────────────────────┘

PROFIT METRICS:
  estimated_profit  = contract_value − estimated_cost
  current_profit    = contract_value − actual_total_cost
  committed_profit  = contract_value − total_committed_cost
  projected_profit  = contract_value − forecast_final_cost

VARIANCE METRICS:
  contract_vs_estimate_variance = contract_value − estimated_cost
  contract_vs_actual_variance   = contract_value − actual_total_cost
  estimate_vs_actual_variance   = estimated_cost − actual_total_cost

COMMITTED COST ANTI-DOUBLE-COUNT NOTES:
  • committed_material_cost uses purchase.order.amount_untaxed for
    state = 'purchase' OR 'done'.  'done' POs may already be in stock
    valuation; this is an intentional conservative ceiling.
  • committed_subcontract_cost is a PROXY from JO actual_subcontract_cost.
    Until a dedicated subcontract PO link exists this is the best source.
  • Draft RFQs (state 'draft' or 'sent') are NOT counted.
"""
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class FarmProjectEngine(models.Model):
    """Full cost-control, profit, and variance engine for farm.project.

    This class is the authoritative compute for ALL project-level cost
    metrics.  It supersedes the partial _compute_project_costs defined
    in smart_farm_sale_contract by delegating to _compute_project_engine,
    which sets every cost/profit/variance field in one pass.
    """

    _inherit = 'farm.project'

    # ── Sales Orders one2many (for @depends on contract approval state) ─────────

    sale_order_ids = fields.One2many(
        'sale.order',
        'farm_project_id',
        string='Sale Orders',
    )

    # ── Purchase Orders one2many (for committed cost @depends) ────────────────

    purchase_order_ids = fields.One2many(
        'purchase.order',
        'farm_project_id',
        string='Purchase Orders',
    )

    # ── Contract approval gate flag (for button visibility in views) ──────────

    has_approved_contract = fields.Boolean(
        string='Has Approved Contract',
        compute='_compute_has_approved_contract',
        store=True,
        help=(
            'True when at least one farm.contract (approved/active) OR one '
            'sale.order (is_contract_approved=True) exists for this project.\n\n'
            'Used to gate Job Orders button visibility in the form view.'
        ),
    )

    @api.depends('contract_ids.state', 'sale_order_ids.is_contract_approved')
    def _compute_has_approved_contract(self):
        for rec in self:
            approved_fc = rec.contract_ids.filtered(
                lambda c: c.state in ('approved', 'active')
            )
            if approved_fc:
                rec.has_approved_contract = True
                continue
            approved_so = rec.sale_order_ids.filtered(
                lambda s: s.is_contract_approved
            )
            rec.has_approved_contract = bool(approved_so)

    # ── Additional actual cost buckets ────────────────────────────────────────
    # (actual_material_cost, actual_labour_cost already declared in
    #  smart_farm_sale_contract; we add subcontract + other here)

    actual_subcontract_cost = fields.Float(
        string='Actual Subcontract Cost',
        compute='_compute_project_engine',
        store=True,
        digits=(16, 2),
        help='Sum of actual_subcontract_cost from all Job Orders.',
    )
    actual_other_cost = fields.Float(
        string='Actual Other Cost',
        compute='_compute_project_engine',
        store=True,
        digits=(16, 2),
        help='Sum of actual_other_cost (miscellaneous) from all Job Orders.',
    )

    # Override actual_total_cost — now includes ALL four buckets
    actual_total_cost = fields.Float(
        string='Total Actual Cost',
        compute='_compute_project_engine',
        store=True,
        digits=(16, 2),
        help='Material + Labour + Subcontract + Other actual costs.',
    )
    # Override cost_variance to use the corrected actual_total_cost
    cost_variance = fields.Float(
        string='Cost Variance',
        compute='_compute_project_engine',
        store=True,
        digits=(16, 2),
        help=(
            'actual_total_cost − contract_value.\n'
            'Positive = costs exceed contract (over budget).\n'
            'Negative = costs below contract (under budget).'
        ),
    )

    # ── Committed cost ────────────────────────────────────────────────────────

    committed_material_cost = fields.Float(
        string='Committed (Materials)',
        compute='_compute_project_engine',
        store=True,
        digits=(16, 2),
        help=(
            'Sum of amount_untaxed from confirmed Purchase Orders '
            '(state = purchase or done) linked to this project.\n'
            'Draft/sent RFQs are excluded.'
        ),
    )
    committed_subcontract_cost = fields.Float(
        string='Committed (Subcontract)',
        compute='_compute_project_engine',
        store=True,
        digits=(16, 2),
        help=(
            'Proxy: sum of actual_subcontract_cost from all Job Orders.\n'
            'Used as a conservative subcontract commitment estimate.'
        ),
    )
    total_committed_cost = fields.Float(
        string='Total Committed Cost',
        compute='_compute_project_engine',
        store=True,
        digits=(16, 2),
        help='committed_material_cost + committed_subcontract_cost.',
    )

    # ── Forecast Final Cost ───────────────────────────────────────────────────

    forecast_final_cost = fields.Float(
        string='Forecast Final Cost',
        compute='_compute_project_engine',
        store=True,
        digits=(16, 2),
        help=(
            'EVM-inspired forecast:\n'
            '  forecast = actual_total + Σ(JO.planned_cost × remaining%)\n\n'
            'remaining% = max(0, 1 − progress_percent / 100)\n\n'
            'Approximates total project cost at completion based on current '
            'actuals and planned cost for remaining scope.'
        ),
    )

    gross_margin_pct = fields.Float(
        string='Gross Margin %',
        compute='_compute_project_engine',
        store=True,
        digits=(16, 1),
        help=(
            '(contract_value − forecast_final_cost) / contract_value × 100.\n'
            'Negative = trending toward a loss.'
        ),
    )

    # ── Profit metrics ────────────────────────────────────────────────────────

    estimated_profit = fields.Float(
        string='Estimated Profit',
        compute='_compute_project_engine',
        store=True,
        digits=(16, 2),
        help='contract_value − estimated_cost (original budgeted margin).',
    )
    current_profit = fields.Float(
        string='Current Profit',
        compute='_compute_project_engine',
        store=True,
        digits=(16, 2),
        help='contract_value − actual_total_cost (live margin on actuals).',
    )
    committed_profit = fields.Float(
        string='Committed Profit',
        compute='_compute_project_engine',
        store=True,
        digits=(16, 2),
        help='contract_value − total_committed_cost.',
    )
    projected_profit = fields.Float(
        string='Projected Profit',
        compute='_compute_project_engine',
        store=True,
        digits=(16, 2),
        help='contract_value − forecast_final_cost (margin at completion).',
    )

    # ── Variance metrics ──────────────────────────────────────────────────────

    contract_vs_estimate_variance = fields.Float(
        string='Contract vs Estimate',
        compute='_compute_project_engine',
        store=True,
        digits=(16, 2),
        help=(
            'contract_value − estimated_cost.\n'
            'Positive → contract exceeds estimate (commercial upside).\n'
            'Negative → contract below estimate (margin at risk).'
        ),
    )
    contract_vs_actual_variance = fields.Float(
        string='Contract vs Actual',
        compute='_compute_project_engine',
        store=True,
        digits=(16, 2),
        help=(
            'contract_value − actual_total_cost.\n'
            'Positive → actuals still under contract value.\n'
            'Negative → actuals exceed contract value (loss territory).'
        ),
    )
    estimate_vs_actual_variance = fields.Float(
        string='Estimate vs Actual',
        compute='_compute_project_engine',
        store=True,
        digits=(16, 2),
        help=(
            'estimated_cost − actual_total_cost.\n'
            'Positive → running under budget.\n'
            'Negative → running over budget.'
        ),
    )

    # ────────────────────────────────────────────────────────────────────────
    # Master compute method
    # ────────────────────────────────────────────────────────────────────────

    @api.depends(
        'job_order_ids.actual_material_cost',
        'job_order_ids.actual_labour_cost',
        'job_order_ids.actual_subcontract_cost',
        'job_order_ids.actual_other_cost',
        'job_order_ids.planned_cost',
        'job_order_ids.progress_percent',
        'purchase_order_ids.state',
        'purchase_order_ids.amount_untaxed',
        'sale_order_ids.is_contract_approved',
        'sale_order_ids.amount_untaxed',
    )
    def _compute_project_engine(self):
        """Compute ALL cost, profit, and variance metrics in one pass.

        Also sets estimated_cost, contract_value, actual_material_cost,
        actual_labour_cost so this method is self-contained and does not
        depend on smart_farm_sale_contract._compute_project_costs running
        first (avoiding potential ordering issues with stored computes).
        """
        BoqAnalysis = self.env['farm.boq.analysis']
        SaleOrder   = self.env['sale.order']

        for rec in self:

            # ── Estimated cost ────────────────────────────────────────────────
            analyses = BoqAnalysis.search([
                ('project_id', '=', rec.id),
                ('analysis_state', '=', 'approved'),
            ])
            estimated = sum(analyses.mapped('total_cost'))

            # ── Contract value ────────────────────────────────────────────────
            approved_sos = SaleOrder.search([
                ('farm_project_id', '=', rec.id),
                ('is_contract_approved', '=', True),
            ])
            contract_val = sum(approved_sos.mapped('amount_untaxed'))

            # ── Actual cost buckets from Job Orders ───────────────────────────
            jos = rec.job_order_ids
            mat  = sum(jos.mapped('actual_material_cost'))
            lab  = sum(jos.mapped('actual_labour_cost'))
            sub  = sum(jos.mapped('actual_subcontract_cost'))
            oth  = sum(jos.mapped('actual_other_cost'))
            actual_total = mat + lab + sub + oth

            # ── Committed cost from confirmed Purchase Orders ─────────────────
            # Only count state = 'purchase' (confirmed) or 'done' (received).
            # Draft RFQs ('draft', 'sent', 'to approve') are NOT committed.
            committed_po = sum(
                rec.purchase_order_ids.filtered(
                    lambda p: p.state in ('purchase', 'done')
                ).mapped('amount_untaxed')
            )
            committed_sub_proxy = sub   # JO actual subcontract as proxy

            total_committed = committed_po + committed_sub_proxy

            # ── Forecast Final Cost (EVM-inspired) ────────────────────────────
            remaining_planned = sum(
                jo.planned_cost * max(0.0, 1.0 - jo.progress_percent / 100.0)
                for jo in jos
                if jo.planned_cost > 0
            )
            forecast = actual_total + remaining_planned

            # ── Gross margin ──────────────────────────────────────────────────
            gross_margin_pct = (
                (contract_val - forecast) / contract_val * 100.0
                if contract_val else 0.0
            )

            # ── Profit ────────────────────────────────────────────────────────
            estimated_profit  = contract_val - estimated
            current_profit    = contract_val - actual_total
            committed_profit  = contract_val - total_committed
            projected_profit  = contract_val - forecast

            # ── Variances ─────────────────────────────────────────────────────
            contract_vs_estimate = contract_val - estimated       # + = contract > estimate
            contract_vs_actual   = contract_val - actual_total    # + = under spend
            estimate_vs_actual   = estimated    - actual_total    # + = under budget

            # ── Write all fields ──────────────────────────────────────────────

            # Re-write base cost fields so this method is self-contained
            rec.estimated_cost              = estimated
            rec.contract_value              = contract_val
            rec.actual_material_cost        = mat
            rec.actual_labour_cost          = lab

            # Extended actual buckets
            rec.actual_subcontract_cost     = sub
            rec.actual_other_cost           = oth
            rec.actual_total_cost           = actual_total
            rec.cost_variance               = actual_total - contract_val

            # Committed
            rec.committed_material_cost     = committed_po
            rec.committed_subcontract_cost  = committed_sub_proxy
            rec.total_committed_cost        = total_committed

            # Forecast
            rec.forecast_final_cost         = forecast
            rec.gross_margin_pct            = gross_margin_pct

            # Profit
            rec.estimated_profit            = estimated_profit
            rec.current_profit              = current_profit
            rec.committed_profit            = committed_profit
            rec.projected_profit            = projected_profit

            # Variance
            rec.contract_vs_estimate_variance  = contract_vs_estimate
            rec.contract_vs_actual_variance    = contract_vs_actual
            rec.estimate_vs_actual_variance    = estimate_vs_actual

            _logger.debug(
                'ProjectEngine [%s]: est=%.2f ctr=%.2f act=%.2f '
                'cmt=%.2f fct=%.2f margin=%.1f%%',
                rec.name, estimated, contract_val, actual_total,
                total_committed, forecast, gross_margin_pct,
            )

    # ── Delegate _compute_project_costs to the engine ─────────────────────────

    @api.depends(
        'job_order_ids.actual_material_cost',
        'job_order_ids.actual_labour_cost',
    )
    def _compute_project_costs(self):
        """Override of smart_farm_sale_contract._compute_project_costs.

        Delegates to _compute_project_engine which handles ALL fields
        (including the ones originally set by this method: estimated_cost,
        contract_value, actual_material_cost, actual_labour_cost,
        actual_total_cost, cost_variance).

        The @api.depends here must be a superset of all fields that
        _compute_project_engine needs — but since _compute_project_engine
        has its own @api.depends registered on the new fields, we only
        need to ensure the original triggers still fire this method for
        the old fields.  The engine then recomputes everything.
        """
        self._compute_project_engine()
