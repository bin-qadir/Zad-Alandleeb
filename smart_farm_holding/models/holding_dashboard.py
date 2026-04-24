from odoo import api, fields, models, _


class SmartfarmHoldingDashboard(models.Model):
    """
    Holding Executive Dashboard — singleton model.

    Aggregates KPIs across ALL companies and ALL business activities.
    This is the SAP/Oracle-style control tower for the Smart Farm holding.
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
        string='Construction (Farm Projects)',
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

    # ── Agriculture KPIs ──────────────────────────────────────────────────────

    total_seasons = fields.Integer(
        string='Agriculture Seasons',
        compute='_compute_agriculture_kpis',
        store=False,
    )
    running_seasons = fields.Integer(
        string='Running Seasons',
        compute='_compute_agriculture_kpis',
        store=False,
    )
    total_crop_plans = fields.Integer(
        string='Crop Plans',
        compute='_compute_agriculture_kpis',
        store=False,
    )
    pending_harvests = fields.Integer(
        string='Pending Harvests',
        compute='_compute_agriculture_kpis',
        store=False,
    )

    # ── Manufacturing KPIs ────────────────────────────────────────────────────

    total_production_plans = fields.Integer(
        string='Production Plans',
        compute='_compute_manufacturing_kpis',
        store=False,
    )
    active_production_plans = fields.Integer(
        string='Active Plans',
        compute='_compute_manufacturing_kpis',
        store=False,
    )
    pending_dispatch = fields.Integer(
        string='Pending Dispatches',
        compute='_compute_manufacturing_kpis',
        store=False,
    )

    # ── Livestock KPIs ────────────────────────────────────────────────────────

    total_herds = fields.Integer(
        string='Herds',
        compute='_compute_livestock_kpis',
        store=False,
    )
    active_herds = fields.Integer(
        string='Active Herds',
        compute='_compute_livestock_kpis',
        store=False,
    )
    total_animals = fields.Integer(
        string='Total Animals',
        compute='_compute_livestock_kpis',
        store=False,
    )
    pending_livestock_sales = fields.Integer(
        string='Pending Livestock Sales',
        compute='_compute_livestock_kpis',
        store=False,
    )

    # ── Construction KPIs ─────────────────────────────────────────────────────

    total_construction = fields.Integer(
        string='Construction Projects',
        compute='_compute_construction_kpis',
        store=False,
    )
    active_construction = fields.Integer(
        string='Active Construction',
        compute='_compute_construction_kpis',
        store=False,
    )

    # ── AI Risk Aggregation ────────────────────────────────────────────────────

    overall_risk_score = fields.Float(
        string='Overall Risk Score',
        compute='_compute_risk_kpis',
        store=False,
        digits=(5, 1),
        help='Average risk score across all active projects and operations.',
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
        ConstructionProject = self.env['construction.project']
        for rec in self:
            farm_projects = FarmProject.search([])
            con_projects = ConstructionProject.search([])

            rec.total_projects = len(farm_projects) + len(con_projects)
            rec.active_projects = (
                len(farm_projects.filtered(lambda p: p.state == 'running')) +
                len(con_projects.filtered(
                    lambda p: p.state in ['planning', 'execution', 'running']))
            )
            rec.construction_projects = len(
                farm_projects.filtered(lambda p: p.business_activity == 'construction')
            ) + len(con_projects)
            rec.agriculture_projects = len(
                farm_projects.filtered(lambda p: p.business_activity == 'agriculture')
            )
            rec.manufacturing_projects = len(
                farm_projects.filtered(lambda p: p.business_activity == 'manufacturing')
            )
            rec.livestock_projects = len(
                farm_projects.filtered(lambda p: p.business_activity == 'livestock')
            )

    def _compute_agriculture_kpis(self):
        Season = self.env['agriculture.season']
        CropPlan = self.env['agriculture.crop.plan']
        Harvest = self.env['agriculture.harvest']
        for rec in self:
            all_seasons = Season.search([])
            rec.total_seasons = len(all_seasons)
            rec.running_seasons = len(all_seasons.filtered(lambda s: s.state == 'running'))
            rec.total_crop_plans = CropPlan.search_count([])
            rec.pending_harvests = Harvest.search_count(
                [('state', 'in', ['draft', 'confirmed'])]
            )

    def _compute_manufacturing_kpis(self):
        Plan = self.env['manufacturing.plan']
        Dispatch = self.env['manufacturing.dispatch']
        for rec in self:
            all_plans = Plan.search([])
            rec.total_production_plans = len(all_plans)
            rec.active_production_plans = len(
                all_plans.filtered(lambda p: p.state == 'in_progress')
            )
            rec.pending_dispatch = Dispatch.search_count(
                [('state', 'in', ['draft', 'confirmed'])]
            )

    def _compute_livestock_kpis(self):
        Herd = self.env['livestock.herd']
        Animal = self.env['livestock.animal']
        Sale = self.env['livestock.sale']
        for rec in self:
            all_herds = Herd.search([])
            rec.total_herds = len(all_herds)
            rec.active_herds = len(
                all_herds.filtered(lambda h: h.state in ['active', 'fattening', 'sale_ready'])
            )
            rec.total_animals = Animal.search_count(
                [('state', 'not in', ['sold', 'dead'])]
            )
            rec.pending_livestock_sales = Sale.search_count(
                [('state', 'in', ['draft', 'confirmed'])]
            )

    def _compute_construction_kpis(self):
        ConProject = self.env['construction.project']
        for rec in self:
            all_con = ConProject.search([])
            rec.total_construction = len(all_con)
            rec.active_construction = len(
                all_con.filtered(lambda p: p.state in ['planning', 'execution', 'running'])
            )

    def _compute_risk_kpis(self):
        Season = self.env['agriculture.season']
        Herd = self.env['livestock.herd']
        Plan = self.env['manufacturing.plan']
        for rec in self:
            risk_items = []

            # Collect risk scores from agriculture
            seasons = Season.search([('state', 'not in', ['done', 'cancelled'])])
            risk_items.extend(seasons.mapped('risk_score'))

            # Livestock
            herds = Herd.search([('state', 'not in', ['sold', 'cancelled'])])
            risk_items.extend(herds.mapped('risk_score'))

            # Manufacturing
            plans = Plan.search([('state', 'not in', ['done', 'cancelled'])])
            risk_items.extend(plans.mapped('risk_score'))

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
        return {
            'type': 'ir.actions.act_window',
            'name': _('Agriculture Seasons'),
            'res_model': 'agriculture.season',
            'view_mode': 'list,form',
            'domain': [],
        }

    def action_view_manufacturing_plans(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Production Plans'),
            'res_model': 'manufacturing.plan',
            'view_mode': 'list,form',
            'domain': [],
        }

    def action_view_livestock_herds(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Herds'),
            'res_model': 'livestock.herd',
            'view_mode': 'list,form',
            'domain': [],
        }

    def action_view_construction_projects(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Construction Projects'),
            'res_model': 'construction.project',
            'view_mode': 'list,form',
            'domain': [],
        }

    def action_view_high_risk(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('High Risk — Agriculture Seasons'),
            'res_model': 'agriculture.season',
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
