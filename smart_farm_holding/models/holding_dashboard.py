from odoo import api, fields, models, _


class SmartfarmHoldingDashboard(models.Model):
    """
    Holding Executive Dashboard — singleton model.

    Aggregates KPIs across ALL companies and ALL business activities.
    This is the SAP/Oracle-style control tower for the Smart Farm holding.

    All KPIs are computed from the unified Smart Farm engine:
      - farm.project  (filtered by business_activity)
      - farm.job.order (filtered by business_activity)
    NO separate activity-specific models are used.
    """

    _name = 'smartfarm.holding.dashboard'
    _description = 'Smart Farm Holding Executive Dashboard'

    # ── Singleton Pattern ─────────────────────────────────────────────────────

    name = fields.Char(string='Dashboard', default='Holding Executive Dashboard', readonly=True)

    # ── Company Overview ──────────────────────────────────────────────────────

    total_companies = fields.Integer(
        string='Total Companies',
        compute='_compute_company_kpis',
        store=False,
    )
    holding_company_name = fields.Char(
        string='Holding Company',
        compute='_compute_company_kpis',
        store=False,
    )

    # ── Project KPIs ──────────────────────────────────────────────────────────

    total_projects = fields.Integer(
        string='Total Projects',
        compute='_compute_project_kpis',
        store=False,
    )
    active_projects = fields.Integer(
        string='Active Projects',
        compute='_compute_project_kpis',
        store=False,
    )
    construction_projects = fields.Integer(
        string='Construction Projects',
        compute='_compute_project_kpis',
        store=False,
    )
    agriculture_projects = fields.Integer(
        string='Agriculture Projects',
        compute='_compute_project_kpis',
        store=False,
    )
    manufacturing_projects = fields.Integer(
        string='Manufacturing Projects',
        compute='_compute_project_kpis',
        store=False,
    )
    livestock_projects = fields.Integer(
        string='Livestock Projects',
        compute='_compute_project_kpis',
        store=False,
    )

    # ── Agriculture KPIs (computed from farm.project + farm.job.order) ───────

    total_seasons = fields.Integer(
        string='Agriculture — Total Projects',
        compute='_compute_agriculture_kpis',
        store=False,
    )
    running_seasons = fields.Integer(
        string='Agriculture — Running',
        compute='_compute_agriculture_kpis',
        store=False,
    )
    total_crop_plans = fields.Integer(
        string='Agriculture — Job Orders',
        compute='_compute_agriculture_kpis',
        store=False,
    )
    pending_harvests = fields.Integer(
        string='Agriculture — Pending Execution',
        compute='_compute_agriculture_kpis',
        store=False,
    )

    # ── Manufacturing KPIs ────────────────────────────────────────────────────

    total_production_plans = fields.Integer(
        string='Manufacturing — Total Projects',
        compute='_compute_manufacturing_kpis',
        store=False,
    )
    active_production_plans = fields.Integer(
        string='Manufacturing — Active',
        compute='_compute_manufacturing_kpis',
        store=False,
    )
    pending_dispatch = fields.Integer(
        string='Manufacturing — In Progress JOs',
        compute='_compute_manufacturing_kpis',
        store=False,
    )

    # ── Livestock KPIs ────────────────────────────────────────────────────────

    total_herds = fields.Integer(
        string='Livestock — Total Projects',
        compute='_compute_livestock_kpis',
        store=False,
    )
    active_herds = fields.Integer(
        string='Livestock — Active',
        compute='_compute_livestock_kpis',
        store=False,
    )
    total_animals = fields.Integer(
        string='Livestock — Job Orders',
        compute='_compute_livestock_kpis',
        store=False,
    )
    pending_livestock_sales = fields.Integer(
        string='Livestock — Claims Pending',
        compute='_compute_livestock_kpis',
        store=False,
    )

    # ── Construction KPIs ─────────────────────────────────────────────────────

    total_construction = fields.Integer(
        string='Construction — Total Projects',
        compute='_compute_construction_kpis',
        store=False,
    )
    active_construction = fields.Integer(
        string='Construction — Active',
        compute='_compute_construction_kpis',
        store=False,
    )

    # ── AI Risk Aggregation ────────────────────────────────────────────────────

    overall_risk_score = fields.Float(
        string='Overall Risk Score',
        compute='_compute_risk_kpis',
        store=False,
        digits=(5, 1),
        help='Average risk score across all active projects.',
    )
    high_risk_items = fields.Integer(
        string='High Risk Items (≥70)',
        compute='_compute_risk_kpis',
        store=False,
    )
    critical_risk_items = fields.Integer(
        string='Critical Risk Items (≥90)',
        compute='_compute_risk_kpis',
        store=False,
    )

    # ── Financial Overview ────────────────────────────────────────────────────

    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        compute='_compute_currency',
        store=False,
    )

    # ── Compute Methods ───────────────────────────────────────────────────────

    def _compute_currency(self):
        for rec in self:
            rec.currency_id = self.env.company.currency_id

    def _compute_company_kpis(self):
        CompanyActivity = self.env['smartfarm.company.activity']
        for rec in self:
            configs = CompanyActivity.search([])
            rec.total_companies = len(configs)
            holding = configs.filtered('is_holding')
            rec.holding_company_name = (
                holding[0].company_id.name if holding else 'Smart Farm Holding'
            )

    def _compute_project_kpis(self):
        FarmProject = self.env['farm.project']
        for rec in self:
            all_projects = FarmProject.search([])
            rec.total_projects = len(all_projects)
            rec.active_projects = len(all_projects.filtered(lambda p: p.state == 'running'))
            rec.construction_projects = len(
                all_projects.filtered(lambda p: p.business_activity == 'construction')
            )
            rec.agriculture_projects = len(
                all_projects.filtered(lambda p: p.business_activity == 'agriculture')
            )
            rec.manufacturing_projects = len(
                all_projects.filtered(lambda p: p.business_activity == 'manufacturing')
            )
            rec.livestock_projects = len(
                all_projects.filtered(lambda p: p.business_activity == 'livestock')
            )

    def _compute_agriculture_kpis(self):
        """Agriculture KPIs from farm.project + farm.job.order (filtered by activity)."""
        FarmProject = self.env['farm.project']
        JobOrder = self.env['farm.job.order']
        for rec in self:
            agr_projects = FarmProject.search([('business_activity', '=', 'agriculture')])
            rec.total_seasons = len(agr_projects)
            rec.running_seasons = len(agr_projects.filtered(lambda p: p.state == 'running'))
            rec.total_crop_plans = JobOrder.search_count(
                [('business_activity', '=', 'agriculture')]
            )
            rec.pending_harvests = JobOrder.search_count([
                ('business_activity', '=', 'agriculture'),
                ('jo_stage', 'in', ['draft', 'approved', 'in_progress']),
            ])

    def _compute_manufacturing_kpis(self):
        """Manufacturing KPIs from farm.project + farm.job.order."""
        FarmProject = self.env['farm.project']
        JobOrder = self.env['farm.job.order']
        for rec in self:
            mfg_projects = FarmProject.search([('business_activity', '=', 'manufacturing')])
            rec.total_production_plans = len(mfg_projects)
            rec.active_production_plans = len(
                mfg_projects.filtered(lambda p: p.state == 'running')
            )
            rec.pending_dispatch = JobOrder.search_count([
                ('business_activity', '=', 'manufacturing'),
                ('jo_stage', '=', 'in_progress'),
            ])

    def _compute_livestock_kpis(self):
        """Livestock KPIs from farm.project + farm.job.order."""
        FarmProject = self.env['farm.project']
        JobOrder = self.env['farm.job.order']
        for rec in self:
            ls_projects = FarmProject.search([('business_activity', '=', 'livestock')])
            rec.total_herds = len(ls_projects)
            rec.active_herds = len(ls_projects.filtered(lambda p: p.state == 'running'))
            rec.total_animals = JobOrder.search_count(
                [('business_activity', '=', 'livestock')]
            )
            rec.pending_livestock_sales = JobOrder.search_count([
                ('business_activity', '=', 'livestock'),
                ('jo_stage', 'in', ['ready_for_claim', 'claimed']),
            ])

    def _compute_construction_kpis(self):
        """Construction KPIs from farm.project (filtered by activity)."""
        FarmProject = self.env['farm.project']
        for rec in self:
            con_projects = FarmProject.search([('business_activity', '=', 'construction')])
            rec.total_construction = len(con_projects)
            rec.active_construction = len(
                con_projects.filtered(lambda p: p.state == 'running')
            )

    def _compute_risk_kpis(self):
        """Risk KPIs from farm.project (has risk_score from holding extension)."""
        FarmProject = self.env['farm.project']
        for rec in self:
            active_projects = FarmProject.search([('state', '=', 'running')])
            risk_items = active_projects.mapped('risk_score')
            if risk_items:
                rec.overall_risk_score = sum(risk_items) / len(risk_items)
                rec.high_risk_items = sum(1 for r in risk_items if r >= 70)
                rec.critical_risk_items = sum(1 for r in risk_items if r >= 90)
            else:
                rec.overall_risk_score = 0.0
                rec.high_risk_items = 0
                rec.critical_risk_items = 0

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_refresh(self):
        """Refresh dashboard — invalidate computed caches."""
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def action_view_all_projects(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('All Projects'),
            'res_model': 'farm.project',
            'view_mode': 'list,form',
            'domain': [],
        }

    def action_view_agriculture_seasons(self):
        """Agriculture — opens farm.project filtered by agriculture."""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Agriculture Projects'),
            'res_model': 'farm.project',
            'view_mode': 'list,form',
            'domain': [('business_activity', '=', 'agriculture')],
            'context': {'default_business_activity': 'agriculture'},
        }

    def action_view_manufacturing_plans(self):
        """Manufacturing — opens farm.project filtered by manufacturing."""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Manufacturing Projects'),
            'res_model': 'farm.project',
            'view_mode': 'list,form',
            'domain': [('business_activity', '=', 'manufacturing')],
            'context': {'default_business_activity': 'manufacturing'},
        }

    def action_view_livestock_herds(self):
        """Livestock — opens farm.project filtered by livestock."""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Livestock Projects'),
            'res_model': 'farm.project',
            'view_mode': 'list,form',
            'domain': [('business_activity', '=', 'livestock')],
            'context': {'default_business_activity': 'livestock'},
        }

    def action_view_construction_projects(self):
        """Construction — opens farm.project filtered by construction."""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Construction Projects'),
            'res_model': 'farm.project',
            'view_mode': 'list,form',
            'domain': [('business_activity', '=', 'construction')],
            'context': {'default_business_activity': 'construction'},
        }

    def action_view_high_risk(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('High Risk Projects'),
            'res_model': 'farm.project',
            'view_mode': 'list,form',
            'domain': [('risk_score', '>=', 70)],
        }

    def action_view_company_setup(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Company Activity Setup'),
            'res_model': 'smartfarm.company.activity',
            'view_mode': 'list,form',
            'domain': [],
        }

    # ── Singleton Accessor ────────────────────────────────────────────────────

    @api.model
    def get_dashboard(self):
        """Return (or create) the singleton dashboard record."""
        dashboard = self.search([], limit=1)
        if not dashboard:
            dashboard = self.create({'name': 'Holding Executive Dashboard'})
        return dashboard

    def action_open_dashboard(self):
        """Open the singleton dashboard form."""
        dashboard = self.get_dashboard()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Holding Executive Dashboard'),
            'res_model': 'smartfarm.holding.dashboard',
            'res_id': dashboard.id,
            'view_mode': 'form',
            'target': 'current',
        }
