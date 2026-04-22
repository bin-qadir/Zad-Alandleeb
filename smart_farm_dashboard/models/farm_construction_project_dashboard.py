"""
farm.construction.project.dashboard  —  Construction Project Dashboard (Level 2)
==================================================================================

Per-project dashboard. One record per farm.project with
business_activity='construction'.  All KPI and stage fields are non-stored
computed fields that aggregate live data from farm.job.order filtered to
the specific project.

Navigation:
  Level 1  farm.construction.projects.dashboard  (portfolio)
      ↓  click project card
  Level 2  farm.construction.project.dashboard    (this model)
      ↓  click department card
  Level 3  farm.civil.dashboard (civil) or JO list (other depts)
"""
from odoo import api, fields, models, _


class FarmConstructionProjectDashboard(models.Model):
    _name        = 'farm.construction.project.dashboard'
    _description = 'Construction Project Dashboard'
    _rec_name    = 'project_id'
    _order       = 'project_id'

    # ── Identity ──────────────────────────────────────────────────────────────
    project_id = fields.Many2one(
        'farm.project',
        string='Project',
        required=True,
        ondelete='cascade',
        index=True,
    )

    currency_id = fields.Many2one(
        'res.currency',
        compute='_compute_currency',
        string='Currency',
    )

    # ── Project-level KPIs (computed from JOs + project record) ──────────────
    contract_value   = fields.Monetary(
        compute='_compute_kpis', currency_field='currency_id',
        string='Contract Value')
    total_jos        = fields.Integer(
        compute='_compute_kpis', string='Total Job Orders')
    approved_amount  = fields.Monetary(
        compute='_compute_kpis', currency_field='currency_id',
        string='Approved Amount')
    claimable_amount = fields.Monetary(
        compute='_compute_kpis', currency_field='currency_id',
        string='Claimable Amount')
    claimed_amount   = fields.Monetary(
        compute='_compute_kpis', currency_field='currency_id',
        string='Claimed Amount')
    overdue_count    = fields.Integer(
        compute='_compute_kpis', string='Overdue JOs')
    is_over_budget   = fields.Boolean(
        related='project_id.is_over_budget', string='Over Budget')

    # ── Stage distribution ────────────────────────────────────────────────────
    jo_count_draft       = fields.Integer(compute='_compute_kpis', string='Draft')
    jo_count_approved    = fields.Integer(compute='_compute_kpis', string='Approved')
    jo_count_in_progress = fields.Integer(compute='_compute_kpis', string='In Progress')
    jo_count_handover    = fields.Integer(compute='_compute_kpis', string='Handover Req.')
    jo_count_inspection  = fields.Integer(compute='_compute_kpis', string='Under Inspection')
    jo_count_accepted    = fields.Integer(compute='_compute_kpis', string='Accepted')
    jo_count_ready_claim = fields.Integer(compute='_compute_kpis', string='Ready for Claim')
    jo_count_claimed     = fields.Integer(compute='_compute_kpis', string='Claimed')
    jo_count_closed      = fields.Integer(compute='_compute_kpis', string='Closed')

    # ── Department breakdown ──────────────────────────────────────────────────
    dept_civil      = fields.Integer(compute='_compute_kpis', string='Civil')
    dept_structure  = fields.Integer(compute='_compute_kpis', string='Structure')
    dept_arch       = fields.Integer(compute='_compute_kpis', string='Architectural')
    dept_mechanical = fields.Integer(compute='_compute_kpis', string='Mechanical')
    dept_electrical = fields.Integer(compute='_compute_kpis', string='Electrical')

    # ────────────────────────────────────────────────────────────────────────
    # Compute
    # ────────────────────────────────────────────────────────────────────────

    def _compute_currency(self):
        for rec in self:
            rec.currency_id = self.env.company.currency_id

    def _compute_kpis(self):
        cr   = self.env.cr
        today = fields.Date.today()

        for rec in self:
            pid = rec.project_id.id
            if not pid:
                # zero out
                for fname in (
                    'contract_value', 'approved_amount', 'claimable_amount',
                    'claimed_amount',
                ):
                    setattr(rec, fname, 0.0)
                for fname in (
                    'total_jos', 'overdue_count',
                    'jo_count_draft', 'jo_count_approved', 'jo_count_in_progress',
                    'jo_count_handover', 'jo_count_inspection', 'jo_count_accepted',
                    'jo_count_ready_claim', 'jo_count_claimed', 'jo_count_closed',
                    'dept_civil', 'dept_structure', 'dept_arch',
                    'dept_mechanical', 'dept_electrical',
                ):
                    setattr(rec, fname, 0)
                continue

            # ── Q1: aggregate JO financials for this project ──────────────
            cr.execute("""
                SELECT
                    COUNT(*)                               AS total,
                    COALESCE(SUM(approved_amount),  0)    AS approved,
                    COALESCE(SUM(claimable_amount), 0)    AS claimable,
                    COALESCE(SUM(claim_amount),     0)    AS claimed,
                    COALESCE(SUM(
                        CASE WHEN planned_end_date < %s
                             AND jo_stage NOT IN ('claimed','closed')
                             THEN 1 ELSE 0 END
                    ), 0)                                 AS overdue
                FROM farm_job_order
                WHERE business_activity = 'construction'
                  AND project_id = %s
            """, (today, pid))
            row = cr.fetchone()
            total_jos, approved, claimable, claimed, overdue = (
                row[0], row[1], row[2], row[3], row[4])

            # ── Q2: stage distribution ────────────────────────────────────
            cr.execute("""
                SELECT jo_stage, COUNT(*)
                FROM farm_job_order
                WHERE business_activity = 'construction'
                  AND project_id = %s
                GROUP BY jo_stage
            """, (pid,))
            stages = dict(cr.fetchall())

            # ── Q3: department distribution ───────────────────────────────
            cr.execute("""
                SELECT department, COUNT(*)
                FROM farm_job_order
                WHERE business_activity = 'construction'
                  AND project_id = %s
                GROUP BY department
            """, (pid,))
            depts = dict(cr.fetchall())

            # Contract value comes from the project record itself
            contract_val = rec.project_id.contract_value or 0.0

            # ── Assign ────────────────────────────────────────────────────
            rec.contract_value   = contract_val
            rec.total_jos        = total_jos
            rec.approved_amount  = approved
            rec.claimable_amount = claimable
            rec.claimed_amount   = claimed
            rec.overdue_count    = overdue

            rec.jo_count_draft       = stages.get('draft', 0)
            rec.jo_count_approved    = stages.get('approved', 0)
            rec.jo_count_in_progress = stages.get('in_progress', 0)
            rec.jo_count_handover    = stages.get('handover_requested', 0)
            rec.jo_count_inspection  = stages.get('under_inspection', 0)
            rec.jo_count_accepted    = (stages.get('accepted', 0)
                                        + stages.get('partially_accepted', 0))
            rec.jo_count_ready_claim = stages.get('ready_for_claim', 0)
            rec.jo_count_claimed     = stages.get('claimed', 0)
            rec.jo_count_closed      = stages.get('closed', 0)

            rec.dept_civil      = depts.get('civil', 0)
            rec.dept_structure  = depts.get('structure', 0)
            rec.dept_arch       = depts.get('arch', 0)
            rec.dept_mechanical = depts.get('mechanical', 0)
            rec.dept_electrical = depts.get('electrical', 0)

    # ────────────────────────────────────────────────────────────────────────
    # Internal helper — every action scoped to this project
    # ────────────────────────────────────────────────────────────────────────

    def _jo_action(self, label, extra_domain=None):
        """Return an act_window for job orders, always filtered to this project."""
        self.ensure_one()
        domain = [
            ('business_activity', '=', 'construction'),
            ('project_id',        '=', self.project_id.id),
        ]
        if extra_domain:
            domain += extra_domain
        return {
            'type':      'ir.actions.act_window',
            'name':      _('%(label)s — %(project)s') % {
                'label': label, 'project': self.project_id.name},
            'res_model': 'farm.job.order',
            'view_mode': 'list,form',
            'domain':    domain,
            'context': {
                'default_business_activity': 'construction',
                'default_project_id':        self.project_id.id,
            },
        }

    # ────────────────────────────────────────────────────────────────────────
    # KPI card actions  (Part 3)
    # ────────────────────────────────────────────────────────────────────────

    def action_view_contract(self):
        """Open the project form (contract value source)."""
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'name':      self.project_id.name,
            'res_model': 'farm.project',
            'res_id':    self.project_id.id,
            'view_mode': 'form',
            'target':    'current',
        }

    def action_view_approved_jos(self):
        return self._jo_action('Approved JOs', [('approved_qty', '>', 0)])

    def action_view_claimable_jos(self):
        return self._jo_action('Claimable JOs', [('claimable_amount', '>', 0)])

    def action_view_claimed_jos(self):
        return self._jo_action('Claimed JOs', [('jo_stage', '=', 'claimed')])

    # ────────────────────────────────────────────────────────────────────────
    # Stage box actions  (Part 2)
    # ────────────────────────────────────────────────────────────────────────

    def action_stage_draft(self):
        return self._jo_action('Draft', [('jo_stage', '=', 'draft')])

    def action_stage_approved(self):
        return self._jo_action('Approved', [('jo_stage', '=', 'approved')])

    def action_stage_in_progress(self):
        return self._jo_action('In Progress', [('jo_stage', '=', 'in_progress')])

    def action_stage_handover(self):
        return self._jo_action(
            'Handover Requested', [('jo_stage', '=', 'handover_requested')])

    def action_stage_inspection(self):
        return self._jo_action(
            'Under Inspection', [('jo_stage', '=', 'under_inspection')])

    def action_stage_accepted(self):
        return self._jo_action(
            'Accepted', [('jo_stage', 'in', ('accepted', 'partially_accepted'))])

    def action_stage_ready_claim(self):
        return self._jo_action('Ready for Claim', [('jo_stage', '=', 'ready_for_claim')])

    def action_stage_claimed(self):
        return self._jo_action('Claimed', [('jo_stage', '=', 'claimed')])

    def action_stage_closed(self):
        return self._jo_action('Closed', [('jo_stage', '=', 'closed')])

    # ────────────────────────────────────────────────────────────────────────
    # Department drill-down actions  (Level 2 → Level 3)
    # ────────────────────────────────────────────────────────────────────────

    def action_open_civil(self):
        """Level 3 — Civil Division Dashboard filtered to this project."""
        self.ensure_one()
        return self.env['farm.civil.dashboard'].action_open_for_project(
            self.project_id.id)

    def action_open_structure(self):
        """Level 3 — Structure Division Dashboard filtered to this project."""
        self.ensure_one()
        return self.env['farm.structure.dashboard'].action_open_for_project(
            self.project_id.id)

    def action_open_arch(self):
        """Level 3 — Architectural Division Dashboard filtered to this project."""
        self.ensure_one()
        return self.env['farm.arch.dashboard'].action_open_for_project(
            self.project_id.id)

    def action_open_mechanical(self):
        """Level 3 — Mechanical Division Dashboard filtered to this project."""
        self.ensure_one()
        return self.env['farm.mech.dashboard'].action_open_for_project(
            self.project_id.id)

    def action_open_electrical(self):
        """Level 3 — Electrical Division Dashboard filtered to this project."""
        self.ensure_one()
        return self.env['farm.elec.dashboard'].action_open_for_project(
            self.project_id.id)

    def _dept_jo_action(self, label, dept_code):
        return {
            'type':      'ir.actions.act_window',
            'name':      _('%(dept)s — %(project)s') % {
                'dept': label, 'project': self.project_id.name},
            'res_model': 'farm.job.order',
            'view_mode': 'list,form',
            'domain':    [
                ('business_activity', '=', 'construction'),
                ('project_id',        '=', self.project_id.id),
                ('department',        '=', dept_code),
            ],
            'context': {
                'default_business_activity': 'construction',
                'default_project_id':        self.project_id.id,
                'default_department':        dept_code,
            },
        }

    # ── All JOs for this project ─────────────────────────────────────────────
    def action_view_all_jos(self):
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'name':      _('All JOs — %s') % self.project_id.name,
            'res_model': 'farm.job.order',
            'view_mode': 'list,form',
            'domain':    [
                ('business_activity', '=', 'construction'),
                ('project_id',        '=', self.project_id.id),
            ],
            'context': {
                'default_business_activity': 'construction',
                'default_project_id':        self.project_id.id,
            },
        }

    # ── Overdue JOs ──────────────────────────────────────────────────────────
    def action_view_overdue(self):
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Overdue JOs — %s') % self.project_id.name,
            'res_model': 'farm.job.order',
            'view_mode': 'list,form',
            'domain':    [
                ('business_activity', '=', 'construction'),
                ('project_id',        '=', self.project_id.id),
                ('planned_end_date',  '<', fields.Date.today()),
                ('jo_stage', 'not in', ('claimed', 'closed')),
            ],
        }

    # ── Back to portfolio ────────────────────────────────────────────────────
    def action_back_to_portfolio(self):
        """Return to Level 1 Construction Projects Dashboard."""
        self.ensure_one()
        return (
            self.env['farm.construction.projects.dashboard']
            .action_open_construction_projects_dashboard()
        )

    # ────────────────────────────────────────────────────────────────────────
    # Opener  (called from Level 1 kanban card via farm.project method)
    # ────────────────────────────────────────────────────────────────────────

    @api.model
    def action_open_for_project(self, project_id):
        """Find-or-create dashboard record for the given project and open it."""
        rec = self.search([('project_id', '=', project_id)], limit=1)
        if not rec:
            rec = self.create({'project_id': project_id})
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Construction Dashboard'),
            'res_model': 'farm.construction.project.dashboard',
            'res_id':    rec.id,
            'view_mode': 'form',
            'target':    'current',
            'context':   {'form_view_initial_mode': 'readonly'},
        }
