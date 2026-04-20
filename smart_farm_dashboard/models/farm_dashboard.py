"""
SMART FARM DASHBOARD — EXECUTIVE PMO SINGLETON
===============================================

farm.dashboard is a singleton model (one record per database).
All KPI fields are non-stored computed — they aggregate live project data
on every read.

Opening the dashboard:
  Menu → Executive Dashboard
  → ir.actions.server calls action_open_dashboard()
  → returns act_window for the singleton record in readonly form mode

All drill-down methods return act_window with filtered farm.project domains.
"""

from odoo import api, fields, models, _


class FarmDashboard(models.Model):
    _name        = 'farm.dashboard'
    _description = 'Smart Farm Executive Dashboard'
    _rec_name    = 'name'

    name = fields.Char(
        string='Dashboard',
        default='Executive Portfolio Dashboard',
        readonly=True,
    )

    # ── Currency passthrough ──────────────────────────────────────────────────

    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        compute='_compute_currency',
    )

    # ── Phase distribution ────────────────────────────────────────────────────

    total_projects    = fields.Integer(compute='_compute_portfolio', string='Total Projects')
    count_pre_tender  = fields.Integer(compute='_compute_portfolio', string='Pre-Tender')
    count_tender      = fields.Integer(compute='_compute_portfolio', string='Tender')
    count_contract    = fields.Integer(compute='_compute_portfolio', string='Contract')
    count_execution   = fields.Integer(compute='_compute_portfolio', string='Execution')
    count_closing     = fields.Integer(compute='_compute_portfolio', string='Closing')
    count_pre_exec    = fields.Integer(compute='_compute_portfolio', string='Pre-Execution (Locked)')
    count_with_contract = fields.Integer(compute='_compute_portfolio', string='Approved Contract')

    # ── Health distribution ───────────────────────────────────────────────────

    count_healthy  = fields.Integer(compute='_compute_portfolio', string='Healthy Projects')
    count_warning  = fields.Integer(compute='_compute_portfolio', string='Warning Projects')
    count_critical = fields.Integer(compute='_compute_portfolio', string='Critical Projects')

    # ── Portfolio financials ──────────────────────────────────────────────────

    total_contract_value  = fields.Monetary(compute='_compute_portfolio', string='Total Contract Value',  currency_field='currency_id')
    total_estimated_cost  = fields.Monetary(compute='_compute_portfolio', string='Total Estimated Cost',  currency_field='currency_id')
    total_committed_cost  = fields.Monetary(compute='_compute_portfolio', string='Total Committed Cost',  currency_field='currency_id')
    total_actual_cost     = fields.Monetary(compute='_compute_portfolio', string='Total Actual Cost',     currency_field='currency_id')
    total_forecast_final  = fields.Monetary(compute='_compute_portfolio', string='Total Forecast Final',  currency_field='currency_id')
    total_current_profit  = fields.Monetary(compute='_compute_portfolio', string='Total Current Profit',  currency_field='currency_id')
    total_projected_profit = fields.Monetary(compute='_compute_portfolio', string='Total Projected Profit', currency_field='currency_id')

    avg_gross_margin_pct  = fields.Float(
        compute='_compute_portfolio',
        string='Avg Gross Margin %',
        digits=(16, 1),
    )

    # ── Summary KPIs (derived from phase + health) ───────────────────────────

    count_active  = fields.Integer(
        compute='_compute_portfolio',
        string='Active Projects',
        help='Projects in Contract or Execution phase.',
    )
    count_at_risk = fields.Integer(
        compute='_compute_portfolio',
        string='At Risk',
        help='Projects with Warning or Critical health.',
    )

    # ── Risk indicators ───────────────────────────────────────────────────────

    count_over_budget      = fields.Integer(compute='_compute_portfolio', string='Over-Budget Projects')
    count_negative_profit  = fields.Integer(compute='_compute_portfolio', string='Negative-Profit Projects')

    # ────────────────────────────────────────────────────────────────────────
    # Compute helpers
    # ────────────────────────────────────────────────────────────────────────

    def _compute_currency(self):
        for rec in self:
            rec.currency_id = self.env.company.currency_id

    def _compute_portfolio(self):
        """Aggregate all project KPIs in a single pass."""
        Project = self.env['farm.project']
        projects = Project.search([])

        # ── Phase counts ────────────────────────────────────────────────────
        phase_map = {
            'pre_tender': 0, 'tender': 0, 'contract': 0,
            'execution': 0,  'closing': 0,
        }
        for p in projects:
            phase = p.project_phase or 'pre_tender'
            if phase in phase_map:
                phase_map[phase] += 1

        # ── Health counts ───────────────────────────────────────────────────
        health_map = {'healthy': 0, 'warning': 0, 'critical': 0}
        for p in projects:
            h = p.project_health or 'healthy'
            health_map[h] = health_map.get(h, 0) + 1

        # ── Financial aggregates ────────────────────────────────────────────
        total_contract   = sum(projects.mapped('contract_value'))
        total_estimated  = sum(projects.mapped('estimated_cost'))
        total_committed  = sum(projects.mapped('total_committed_cost'))
        total_actual     = sum(projects.mapped('actual_total_cost'))
        total_forecast   = sum(projects.mapped('forecast_final_cost'))
        total_curr_pft   = sum(projects.mapped('current_profit'))
        total_proj_pft   = sum(projects.mapped('projected_profit'))

        # Average gross margin — execution + closing projects with contract only
        exec_proj = projects.filtered(
            lambda p: p.project_phase in ('execution', 'closing') and p.contract_value > 0
        )
        avg_margin = (
            sum(exec_proj.mapped('gross_margin_pct')) / len(exec_proj)
            if exec_proj else 0.0
        )

        # ── Risk counts ─────────────────────────────────────────────────────
        over_budget = sum(
            1 for p in projects
            if p.contract_value > 0 and p.actual_total_cost > p.contract_value
        )
        neg_profit = sum(
            1 for p in projects
            if p.project_phase in ('execution', 'closing') and p.projected_profit < 0
        )
        with_contract = sum(1 for p in projects if p.has_approved_contract)

        for rec in self:
            rec.total_projects      = len(projects)
            rec.count_pre_tender    = phase_map['pre_tender']
            rec.count_tender        = phase_map['tender']
            rec.count_contract      = phase_map['contract']
            rec.count_execution     = phase_map['execution']
            rec.count_closing       = phase_map['closing']
            rec.count_pre_exec      = phase_map['pre_tender'] + phase_map['tender'] + phase_map['contract']
            rec.count_with_contract = with_contract

            rec.count_healthy  = health_map.get('healthy', 0)
            rec.count_warning  = health_map.get('warning', 0)
            rec.count_critical = health_map.get('critical', 0)

            rec.total_contract_value   = total_contract
            rec.total_estimated_cost   = total_estimated
            rec.total_committed_cost   = total_committed
            rec.total_actual_cost      = total_actual
            rec.total_forecast_final   = total_forecast
            rec.total_current_profit   = total_curr_pft
            rec.total_projected_profit = total_proj_pft
            rec.avg_gross_margin_pct   = avg_margin

            rec.count_active  = phase_map['contract'] + phase_map['execution']
            rec.count_at_risk = health_map.get('warning', 0) + health_map.get('critical', 0)

            rec.count_over_budget     = over_budget
            rec.count_negative_profit = neg_profit

    # ────────────────────────────────────────────────────────────────────────
    # Singleton accessor
    # ────────────────────────────────────────────────────────────────────────

    @api.model
    def action_open_dashboard(self):
        """Find-or-create the singleton and return a readonly form action."""
        dashboard = self.search([], limit=1)
        if not dashboard:
            dashboard = self.create({'name': 'Executive Portfolio Dashboard'})
        return {
            'type':        'ir.actions.act_window',
            'name':        _('Executive Dashboard'),
            'res_model':   'farm.dashboard',
            'res_id':      dashboard.id,
            'view_mode':   'form',
            'target':      'current',
            'context':     {'form_view_initial_mode': 'readonly'},
        }

    # ────────────────────────────────────────────────────────────────────────
    # Drill-down helpers
    # ────────────────────────────────────────────────────────────────────────

    def _project_list_action(self, name, domain, no_create=False):
        """Return an act_window for a filtered farm.project list.

        no_create=True  → uses the executive list view (create="false")
                          for the four dashboard result screens that must be
                          read-only (Approved Contract / Critical / At-Risk /
                          Active).  All other drill-downs leave no_create=False.
        """
        action = {
            'type':      'ir.actions.act_window',
            'name':      name,
            'res_model': 'farm.project',
            'view_mode': 'list,form',
            'domain':    domain,
            'target':    'current',
        }
        if no_create:
            view = self.env.ref(
                'smart_farm_dashboard.view_farm_project_executive_list',
                raise_if_not_found=False,
            )
            if view:
                action['views'] = [(view.id, 'list'), (False, 'form')]
        return action

    # ── Phase drill-down ─────────────────────────────────────────────────────

    def action_view_all(self):
        return self._project_list_action(_('All Projects'), [])

    def action_view_active(self):
        return self._project_list_action(
            _('Active Projects (Contract + Execution)'),
            [('project_phase', 'in', ['contract', 'execution'])],
            no_create=True,
        )

    def action_view_at_risk(self):
        return self._project_list_action(
            _('At-Risk Projects (Warning + Critical)'),
            [('project_health', 'in', ['warning', 'critical'])],
            no_create=True,
        )

    def action_view_pre_tender(self):
        return self._project_list_action(
            _('Pre-Tender Projects'),
            [('project_phase', '=', 'pre_tender')],
        )

    def action_view_tender(self):
        return self._project_list_action(
            _('Tender Projects'),
            [('project_phase', '=', 'tender')],
        )

    def action_view_contract(self):
        return self._project_list_action(
            _('Contract Projects'),
            [('project_phase', '=', 'contract')],
        )

    def action_view_execution(self):
        return self._project_list_action(
            _('Execution Projects'),
            [('project_phase', '=', 'execution')],
        )

    def action_view_closing(self):
        return self._project_list_action(
            _('Closing Projects'),
            [('project_phase', '=', 'closing')],
        )

    def action_view_pre_exec(self):
        return self._project_list_action(
            _('Pre-Execution Projects (Locked)'),
            [('project_phase', 'in', ['pre_tender', 'tender', 'contract'])],
        )

    def action_view_with_contract(self):
        return self._project_list_action(
            _('Projects with Approved Contract'),
            [('has_approved_contract', '=', True)],
            no_create=True,
        )

    # ── Health drill-down ────────────────────────────────────────────────────

    def action_view_healthy(self):
        return self._project_list_action(
            _('Healthy Projects'),
            [('project_health', '=', 'healthy')],
        )

    def action_view_warning(self):
        return self._project_list_action(
            _('Warning Projects'),
            [('project_health', '=', 'warning')],
        )

    def action_view_critical(self):
        return self._project_list_action(
            _('Critical Projects'),
            [('project_health', '=', 'critical')],
            no_create=True,
        )

    # ── Risk drill-down ──────────────────────────────────────────────────────

    def action_view_over_budget(self):
        return self._project_list_action(
            _('Over-Budget Projects'),
            [('is_over_budget', '=', True)],
        )

    def action_view_negative_profit(self):
        return self._project_list_action(
            _('Negative-Profit Projects'),
            [('is_negative_profit', '=', True)],
        )

    # ── Refresh ──────────────────────────────────────────────────────────────

    def action_refresh(self):
        """Reload this dashboard form (triggers fresh recompute)."""
        return {
            'type':    'ir.actions.act_window',
            'name':    _('Executive Dashboard'),
            'res_model': 'farm.dashboard',
            'res_id':  self.id,
            'view_mode': 'form',
            'target':  'current',
            'context': {'form_view_initial_mode': 'readonly'},
        }
