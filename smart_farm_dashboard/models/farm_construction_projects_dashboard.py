"""
farm.construction.projects.dashboard  —  Construction Projects Portfolio Dashboard
====================================================================================

Level 1 singleton dashboard aggregating all construction farm.project records.

Displays:
  • 7 top KPI cards (count, contract value, approved, claimable, claimed,
                     over-budget count, delayed count) — always full portfolio
  • Smart filter strip (All / Delayed / Over Budget / Claimed / Claimable)
    → Project dataset  (All | Delayed | Over Budget)
    → Job Order dataset (Claimed | Claimable)

Filter state is persisted in the singleton via `filter_type` (stored).
Clicking a filter button writes filter_type, returns False → form reloads
with new dataset.  No navigation to a new page.

Performance:
  _compute_kpis   — two raw SQL queries (portfolio totals, always unfiltered)
  _compute_datasets — one ORM search or one SQL + ORM search, filter-aware
"""
from odoo import api, fields, models, _
from datetime import date as _date


class FarmConstructionProjectsDashboard(models.Model):
    _name        = 'farm.construction.projects.dashboard'
    _description = 'Construction Projects Portfolio Dashboard'
    _rec_name    = 'id'

    # ── Currency ──────────────────────────────────────────────────────────────
    currency_id = fields.Many2one(
        'res.currency',
        compute='_compute_currency',
        string='Currency',
    )

    # ── Active filter (stored — survives page refresh) ────────────────────────
    filter_type = fields.Selection(
        selection=[
            ('all',        'All Projects'),
            ('delayed',    'Delayed Projects'),
            ('over_budget','Over Budget Projects'),
            ('claimed',    'Claimed JOs'),
            ('claimable',  'Claimable JOs'),
        ],
        string='Active Filter',
        default='all',
    )

    # ── Portfolio KPI fields (always full portfolio, unaffected by filter) ────
    total_projects         = fields.Integer(
        compute='_compute_kpis', string='Total Projects')
    total_contract_value   = fields.Monetary(
        compute='_compute_kpis', currency_field='currency_id',
        string='Total Contract Value')
    total_approved_amount  = fields.Monetary(
        compute='_compute_kpis', currency_field='currency_id',
        string='Total Approved Amount')
    total_claimable_amount = fields.Monetary(
        compute='_compute_kpis', currency_field='currency_id',
        string='Total Claimable Amount')
    total_claimed_amount   = fields.Monetary(
        compute='_compute_kpis', currency_field='currency_id',
        string='Total Claimed Amount')
    over_budget_count      = fields.Integer(
        compute='_compute_kpis', string='Over Budget Projects')
    delayed_count          = fields.Integer(
        compute='_compute_kpis', string='Delayed Projects')

    # ── Dataset fields (filter-aware) ─────────────────────────────────────────

    # Projects dataset (active for all / delayed / over_budget filters)
    project_ids = fields.Many2many(
        comodel_name='farm.project',
        compute='_compute_datasets',
        string='Construction Projects',
    )

    # Job Orders dataset (active for claimed / claimable filters)
    jo_ids = fields.Many2many(
        comodel_name='farm.job.order',
        compute='_compute_datasets',
        string='Job Orders',
    )

    # Section heading counts (reflect current filter)
    filtered_project_count = fields.Integer(
        compute='_compute_datasets', string='Filtered Projects')
    filtered_jo_count      = fields.Integer(
        compute='_compute_datasets', string='Filtered JOs')

    # ────────────────────────────────────────────────────────────────────────
    # Compute: currency
    # ────────────────────────────────────────────────────────────────────────

    def _compute_currency(self):
        for rec in self:
            rec.currency_id = self.env.company.currency_id

    # ────────────────────────────────────────────────────────────────────────
    # Compute: portfolio KPIs (always full portfolio — SQL aggregates)
    # ────────────────────────────────────────────────────────────────────────

    def _compute_kpis(self):
        """
        Two SQL queries covering the full construction portfolio.
          Q1 — Aggregate JO financials (approved, claimable, claimed)
          Q2 — Aggregate project-level KPIs (count, contract value, over-budget)
          Q3 — Delayed: distinct project_ids with overdue non-closed JOs
        Results are NOT affected by filter_type — the KPI strip always shows
        portfolio-level totals.
        """
        cr = self.env.cr

        # ── Q1: JO financial aggregates ──────────────────────────────────────
        cr.execute("""
            SELECT
                COALESCE(SUM(approved_amount),  0) AS approved,
                COALESCE(SUM(claimable_amount), 0) AS claimable,
                COALESCE(SUM(claim_amount),     0) AS claimed
            FROM farm_job_order
            WHERE business_activity = 'construction'
        """)
        row = cr.fetchone()
        approved_amt, claimable_amt, claimed_amt = row[0], row[1], row[2]

        # ── Q2: Project-level aggregates ─────────────────────────────────────
        cr.execute("""
            SELECT
                COUNT(*)                                                     AS total,
                COALESCE(SUM(contract_value), 0)                             AS contract_val,
                COALESCE(SUM(CASE WHEN is_over_budget THEN 1 ELSE 0 END), 0) AS over_budget
            FROM farm_project
            WHERE business_activity = 'construction'
        """)
        row2 = cr.fetchone()
        total_projects, total_contract_value, over_budget_count = (
            row2[0], row2[1], row2[2]
        )

        # ── Q3: Delayed projects (≥1 overdue non-closed JO) ──────────────────
        cr.execute("""
            SELECT COUNT(DISTINCT project_id)
            FROM farm_job_order
            WHERE business_activity = 'construction'
              AND project_id IS NOT NULL
              AND planned_end_date < CURRENT_DATE
              AND jo_stage NOT IN ('claimed', 'closed')
        """)
        delayed_count = cr.fetchone()[0] or 0

        # ── Assign ────────────────────────────────────────────────────────────
        for rec in self:
            rec.total_projects         = total_projects
            rec.total_contract_value   = total_contract_value
            rec.total_approved_amount  = approved_amt
            rec.total_claimable_amount = claimable_amt
            rec.total_claimed_amount   = claimed_amt
            rec.over_budget_count      = over_budget_count
            rec.delayed_count          = delayed_count

    # ────────────────────────────────────────────────────────────────────────
    # Compute: datasets (filter-aware — project_ids | jo_ids)
    # ────────────────────────────────────────────────────────────────────────

    @api.depends('filter_type')
    def _compute_datasets(self):
        """
        Builds the appropriate dataset based on filter_type:

          all        → all construction projects  (project_ids)
          delayed    → projects with overdue JOs  (project_ids)
          over_budget→ projects where is_over_budget (project_ids)
          claimed    → JOs where claimed_qty > 0  (jo_ids)
          claimable  → JOs where claimable_amount > 0  (jo_ids)

        The KPI strip is not touched — only the section dataset changes.
        """
        cr    = self.env.cr
        today = fields.Date.today()
        empty_proj = self.env['farm.project']
        empty_jo   = self.env['farm.job.order']

        for rec in self:
            ft = rec.filter_type or 'all'

            if ft == 'all':
                projects = self.env['farm.project'].search(
                    [('business_activity', '=', 'construction')],
                    order='name asc',
                )
                rec.project_ids          = projects
                rec.jo_ids               = empty_jo
                rec.filtered_project_count = len(projects)
                rec.filtered_jo_count      = 0

            elif ft == 'delayed':
                # Projects that have at least one overdue, non-closed JO
                cr.execute("""
                    SELECT DISTINCT project_id
                    FROM farm_job_order
                    WHERE business_activity = 'construction'
                      AND project_id IS NOT NULL
                      AND planned_end_date < %s
                      AND jo_stage NOT IN ('claimed', 'closed')
                """, (today,))
                delayed_ids = [r[0] for r in cr.fetchall()]
                projects = self.env['farm.project'].search(
                    [('id', 'in', delayed_ids)],
                    order='name asc',
                )
                rec.project_ids            = projects
                rec.jo_ids                 = empty_jo
                rec.filtered_project_count = len(projects)
                rec.filtered_jo_count      = 0

            elif ft == 'over_budget':
                # Domain: actual_total_cost > contract_value (is_over_budget flag)
                projects = self.env['farm.project'].search([
                    ('business_activity', '=', 'construction'),
                    ('is_over_budget',    '=', True),
                ], order='name asc')
                rec.project_ids            = projects
                rec.jo_ids                 = empty_jo
                rec.filtered_project_count = len(projects)
                rec.filtered_jo_count      = 0

            elif ft == 'claimed':
                # Domain: claimed_qty > 0
                jos = self.env['farm.job.order'].search([
                    ('business_activity', '=', 'construction'),
                    ('claimed_qty',       '>',  0),
                ], order='id asc')
                rec.project_ids            = empty_proj
                rec.jo_ids                 = jos
                rec.filtered_project_count = 0
                rec.filtered_jo_count      = len(jos)

            elif ft == 'claimable':
                # Domain: approved_qty > claimed_qty  (claimable_amount > 0)
                jos = self.env['farm.job.order'].search([
                    ('business_activity', '=', 'construction'),
                    ('claimable_amount',  '>',  0),
                ], order='id asc')
                rec.project_ids            = empty_proj
                rec.jo_ids                 = jos
                rec.filtered_project_count = 0
                rec.filtered_jo_count      = len(jos)

    # ────────────────────────────────────────────────────────────────────────
    # Filter setter methods  (called from filter pill buttons)
    # Returns False → form stays in place and reloads with new filter_type
    # ────────────────────────────────────────────────────────────────────────

    def _apply_filter(self, filter_type):
        """Write filter_type and return False to reload the current form."""
        self.ensure_one()
        self.write({'filter_type': filter_type})
        return False

    def action_filter_all(self):
        return self._apply_filter('all')

    def action_filter_delayed(self):
        return self._apply_filter('delayed')

    def action_filter_over_budget(self):
        return self._apply_filter('over_budget')

    def action_filter_claimed(self):
        return self._apply_filter('claimed')

    def action_filter_claimable(self):
        return self._apply_filter('claimable')

    # ────────────────────────────────────────────────────────────────────────
    # Navigation actions (kept — go to different views)
    # ────────────────────────────────────────────────────────────────────────

    def action_view_all_projects(self):
        """Open full construction projects list (used by Total Projects card)."""
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'name':      _('All Construction Projects'),
            'res_model': 'farm.project',
            'view_mode': 'list,form',
            'domain':    [('business_activity', '=', 'construction')],
            'context':   {'default_business_activity': 'construction'},
        }

    def action_open_execution_dashboard(self):
        """Open the Construction Activity Execution Dashboard."""
        self.ensure_one()
        return self.env['farm.activity.dashboard'].action_open_construction()

    # ────────────────────────────────────────────────────────────────────────
    # Singleton opener
    # ────────────────────────────────────────────────────────────────────────

    @api.model
    def action_open_construction_projects_dashboard(self):
        """Find-or-create singleton and return form action."""
        rec = self.search([], limit=1)
        if not rec:
            rec = self.create({})
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Construction Projects Dashboard'),
            'res_model': 'farm.construction.projects.dashboard',
            'res_id':    rec.id,
            'view_mode': 'form',
            'target':    'current',
            'context':   {'form_view_initial_mode': 'readonly'},
        }
