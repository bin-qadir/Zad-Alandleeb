from odoo import api, fields, models


class FarmBoqAnalysisLineExecution(models.Model):
    """Execution extension for BOQ Analysis Lines.

    Adds a reverse link to Job Orders and aggregates execution actuals
    (qty executed, cost incurred, progress) back onto the analysis line
    for direct comparison with estimated values.

    Keeps a strict boundary:
    - `execution_actual_*` fields come from Job Orders (execution layer)
    - `actual_total_cost` / `actual_qty` on the base model come from
      Procurement (PO/bill) — not touched here.
    """

    _inherit = 'farm.boq.analysis.line'

    # ── Reverse link to job orders ────────────────────────────────────────────
    job_order_ids = fields.One2many(
        'farm.job.order',
        'analysis_line_id',
        string='Job Orders',
        readonly=True,
    )
    # Non-stored count — separate compute to avoid store/compute_sudo mismatch
    job_order_count = fields.Integer(
        string='# Job Orders',
        compute='_compute_job_order_count',
    )

    # ── Execution actuals (source: job orders) ────────────────────────────────
    execution_actual_qty = fields.Float(
        string='Executed Qty',
        compute='_compute_execution_actuals',
        store=True,
        digits=(16, 2),
        help='Sum of executed_qty from all linked Job Orders.',
    )
    execution_actual_cost = fields.Float(
        string='Execution Actual Cost',
        compute='_compute_execution_actuals',
        store=True,
        digits=(16, 2),
        help='Total actual cost (material + labour + subcontract + other) '
             'from all linked Job Orders.',
    )
    execution_progress = fields.Float(
        string='Execution Progress (%)',
        compute='_compute_execution_actuals',
        store=True,
        digits=(16, 1),
        help='Average progress % across all linked Job Orders.',
    )
    execution_cost_variance = fields.Float(
        string='Execution Variance',
        compute='_compute_execution_actuals',
        store=True,
        digits=(16, 2),
        help='Execution actual cost minus the analysis estimated cost_total.',
    )

    # ────────────────────────────────────────────────────────────────────────
    # Computed
    # ────────────────────────────────────────────────────────────────────────

    @api.depends('job_order_ids')
    def _compute_job_order_count(self):
        """Non-stored count — kept separate from stored actuals."""
        for rec in self:
            rec.job_order_count = len(rec.job_order_ids)

    @api.depends(
        'job_order_ids.executed_qty',
        'job_order_ids.actual_total_cost',
        'job_order_ids.progress_percent',
        'cost_total',
    )
    def _compute_execution_actuals(self):
        """Stored aggregates from linked Job Orders."""
        for rec in self:
            jobs = rec.job_order_ids
            rec.execution_actual_qty   = sum(jobs.mapped('executed_qty'))
            rec.execution_actual_cost  = sum(jobs.mapped('actual_total_cost'))
            rec.execution_progress     = (
                sum(jobs.mapped('progress_percent')) / len(jobs)
                if jobs else 0.0
            )
            rec.execution_cost_variance = (
                rec.execution_actual_cost - (rec.cost_total or 0.0)
            )
