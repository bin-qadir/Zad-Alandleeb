"""
farm.construction.projects.dashboard  —  Construction Projects Portfolio Dashboard
====================================================================================

Level 1 singleton dashboard aggregating all construction farm.project records.

Displays:
  • 7 top KPI cards (count, contract value, approved, claimable, claimed,
                     over-budget count, delayed count)
  • Embedded kanban grid of all construction projects (Level 2)
  • Each kanban card is clickable → opens the project form (Level 3)

All KPI fields are non-stored.  Two raw SQL queries cover the financials for
performance (no per-record ORM loops on JOs).
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

    # ── Top KPI fields ────────────────────────────────────────────────────────
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

    # ── Project cards (Level 2) ───────────────────────────────────────────────
    project_ids = fields.Many2many(
        comodel_name='farm.project',
        compute='_compute_kpis',
        string='Construction Projects',
    )

    # ────────────────────────────────────────────────────────────────────────
    # Compute
    # ────────────────────────────────────────────────────────────────────────

    def _compute_currency(self):
        for rec in self:
            rec.currency_id = self.env.company.currency_id

    def _compute_kpis(self):
        """
        Two SQL queries then one ORM search for project records:
          Q1 — Aggregate JO financials for construction activity
          Q2 — Aggregate project-level KPIs (contract value, over-budget count)
          Q3 — Delayed projects: distinct project_ids with overdue JOs
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

        # ── Q3: Delayed projects ──────────────────────────────────────────────
        cr.execute("""
            SELECT COUNT(DISTINCT project_id)
            FROM farm_job_order
            WHERE business_activity = 'construction'
              AND project_id IS NOT NULL
              AND planned_end_date < CURRENT_DATE
              AND jo_stage NOT IN ('claimed', 'closed')
        """)
        delayed_count = cr.fetchone()[0] or 0

        # ── Project records for the kanban cards ──────────────────────────────
        projects = self.env['farm.project'].search(
            [('business_activity', '=', 'construction')],
            order='name asc',
        )

        # ── Assign ────────────────────────────────────────────────────────────
        for rec in self:
            rec.total_projects         = total_projects
            rec.total_contract_value   = total_contract_value
            rec.total_approved_amount  = approved_amt
            rec.total_claimable_amount = claimable_amt
            rec.total_claimed_amount   = claimed_amt
            rec.over_budget_count      = over_budget_count
            rec.delayed_count          = delayed_count
            rec.project_ids            = projects

    # ────────────────────────────────────────────────────────────────────────
    # Drill-down actions (KPI card clicks)
    # ────────────────────────────────────────────────────────────────────────

    def _project_action(self, name, domain):
        return {
            'type':      'ir.actions.act_window',
            'name':      _(name),
            'res_model': 'farm.project',
            'view_mode': 'list,form',
            'domain':    domain,
            'context':   {'default_business_activity': 'construction'},
        }

    def _jo_action(self, name, domain):
        return {
            'type':      'ir.actions.act_window',
            'name':      _(name),
            'res_model': 'farm.job.order',
            'view_mode': 'list,form',
            'domain':    domain,
            'context':   {'default_business_activity': 'construction'},
        }

    def action_view_all_projects(self):
        self.ensure_one()
        return self._project_action(
            'All Construction Projects',
            [('business_activity', '=', 'construction')],
        )

    def action_view_over_budget(self):
        self.ensure_one()
        return self._project_action(
            'Over Budget — Construction Projects',
            [('business_activity', '=', 'construction'), ('is_over_budget', '=', True)],
        )

    def action_view_delayed(self):
        """Open projects that have at least one overdue non-closed JO."""
        self.ensure_one()
        today = fields.Date.today()
        overdue_ids = self.env['farm.job.order'].search([
            ('business_activity', '=', 'construction'),
            ('planned_end_date',  '<', today),
            ('jo_stage', 'not in', ['claimed', 'closed']),
        ]).mapped('project_id').ids
        return self._project_action(
            'Delayed — Construction Projects',
            [('id', 'in', overdue_ids)],
        )

    def action_view_approved_jos(self):
        self.ensure_one()
        return self._jo_action(
            'Approved Amount — Construction JOs',
            [('business_activity', '=', 'construction'), ('approved_qty', '>', 0)],
        )

    def action_view_claimable_jos(self):
        self.ensure_one()
        return self._jo_action(
            'Claimable — Construction JOs',
            [('business_activity', '=', 'construction'), ('claimable_amount', '>', 0)],
        )

    def action_view_claimed_jos(self):
        self.ensure_one()
        return self._jo_action(
            'Claimed — Construction JOs',
            [('business_activity', '=', 'construction'), ('jo_stage', '=', 'claimed')],
        )

    def action_open_execution_dashboard(self):
        """Open the existing Construction Activity Execution Dashboard."""
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
