from odoo import api, fields, models, _


class FarmProjectExecution(models.Model):
    """Extends Farm Project with Job Order navigation and execution KPI aggregates.

    Execution KPIs are driven by ``approved_qty`` per the business rule:
      - progress_percent  = approved_qty / planned_qty × 100  (per JO)
      - approved_amount   = approved_qty × unit_price          (per JO)
      - claimable_amount  = (approved_qty − claimed_qty) × unit_price
    """

    _inherit = 'farm.project'

    # ── Relation ──────────────────────────────────────────────────────────────

    job_order_ids = fields.One2many(
        'farm.job.order',
        'project_id',
        string='Job Order List',
    )

    # ── Counts ────────────────────────────────────────────────────────────────

    job_order_count = fields.Integer(
        string='Job Orders',
        compute='_compute_job_order_count',
        help='Total number of Job Orders on this project.',
    )

    # ── Execution financial aggregates (approved_qty driven) ──────────────────

    total_approved_amount = fields.Float(
        string='Total Approved Amount',
        compute='_compute_execution_kpis',
        digits=(16, 2),
        help='Sum of approved_amount across all Job Orders on this project.\n'
             'approved_amount = approved_qty × unit_price per JO.',
    )
    total_claimable_amount = fields.Float(
        string='Total Claimable Amount',
        compute='_compute_execution_kpis',
        digits=(16, 2),
        help='Sum of claimable_amount (approved but not yet claimed).',
    )
    total_claimed_amount = fields.Float(
        string='Total Claimed Amount',
        compute='_compute_execution_kpis',
        digits=(16, 2),
        help='Sum of claim_amount (already submitted) across all Job Orders.',
    )
    total_remaining_amount = fields.Float(
        string='Total Remaining Amount',
        compute='_compute_execution_kpis',
        digits=(16, 2),
        help='Sum of remaining_amount (not yet approved) across all Job Orders.',
    )

    # ── Progress ──────────────────────────────────────────────────────────────

    execution_progress_pct = fields.Float(
        string='Execution Progress %',
        compute='_compute_execution_kpis',
        digits=(16, 1),
        help='Weighted-average progress based on approved_qty / contract_qty '
             'across all Job Orders, weighted by planned_qty (contract qty).',
    )

    # ── Stage-based JO counts ─────────────────────────────────────────────────

    jo_count_in_progress = fields.Integer(
        string='JOs In Progress',
        compute='_compute_execution_kpis',
    )
    jo_count_under_inspection = fields.Integer(
        string='JOs Under Inspection',
        compute='_compute_execution_kpis',
    )
    jo_count_ready_for_claim = fields.Integer(
        string='JOs Ready for Claim',
        compute='_compute_execution_kpis',
    )
    jo_count_claimed = fields.Integer(
        string='JOs Claimed',
        compute='_compute_execution_kpis',
    )

    # ────────────────────────────────────────────────────────────────────────
    # Compute methods
    # ────────────────────────────────────────────────────────────────────────

    def _compute_job_order_count(self):
        JobOrder = self.env['farm.job.order']
        for rec in self:
            rec.job_order_count = JobOrder.search_count(
                [('project_id', '=', rec.id)]
            )

    def _compute_execution_kpis(self):
        """Aggregate execution KPIs across all Job Orders for this project.

        Uses a read_group for efficiency instead of iterating individual records.
        """
        JobOrder = self.env['farm.job.order']
        for rec in self:
            jos = JobOrder.search([('project_id', '=', rec.id)])

            if not jos:
                rec.total_approved_amount  = 0.0
                rec.total_claimable_amount = 0.0
                rec.total_claimed_amount   = 0.0
                rec.total_remaining_amount = 0.0
                rec.execution_progress_pct = 0.0
                rec.jo_count_in_progress       = 0
                rec.jo_count_under_inspection  = 0
                rec.jo_count_ready_for_claim   = 0
                rec.jo_count_claimed           = 0
                continue

            rec.total_approved_amount  = sum(jos.mapped('approved_amount'))
            rec.total_claimable_amount = sum(jos.mapped('claimable_amount'))
            rec.total_claimed_amount   = sum(jos.mapped('claim_amount'))
            rec.total_remaining_amount = sum(jos.mapped('remaining_amount'))

            # Weighted-average progress: Σ(approved_qty × weight) / Σ(planned_qty)
            total_planned  = sum(jos.mapped('planned_qty'))
            total_approved = sum(jos.mapped('approved_qty'))
            rec.execution_progress_pct = (
                total_approved / total_planned * 100.0
                if total_planned else 0.0
            )

            # Stage-based counts
            rec.jo_count_in_progress      = sum(1 for j in jos if j.jo_stage == 'in_progress')
            rec.jo_count_under_inspection = sum(1 for j in jos if j.jo_stage == 'under_inspection')
            rec.jo_count_ready_for_claim  = sum(1 for j in jos if j.jo_stage == 'ready_for_claim')
            rec.jo_count_claimed          = sum(1 for j in jos if j.jo_stage == 'claimed')

    # ────────────────────────────────────────────────────────────────────────
    # Actions
    # ────────────────────────────────────────────────────────────────────────

    def action_open_job_orders(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Job Orders — %s') % self.name,
            'res_model': 'farm.job.order',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
        }
