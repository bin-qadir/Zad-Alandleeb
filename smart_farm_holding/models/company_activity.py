from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


ACTIVITY_SELECTION = [
    ('construction',  'Construction'),
    ('agriculture',   'Agriculture'),
    ('manufacturing', 'Manufacturing'),
    ('livestock',     'Livestock'),
]


class SmartfarmCompanyActivity(models.Model):
    """
    Company Activity Configuration — the core of the holding visibility engine.

    Maps each company to its business activity, parent/child relationship,
    and controls which activity modules are enabled and visible.
    """

    _name = 'smartfarm.company.activity'
    _description = 'Company Activity Configuration'
    _rec_name = 'company_id'
    _order = 'is_holding desc, company_id'

    # ── Company Identity ──────────────────────────────────────────────────────

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        ondelete='cascade',
        index=True,
    )
    parent_company_id = fields.Many2one(
        comodel_name='res.company',
        string='Parent Company (Holding)',
        ondelete='set null',
        help='The holding company that owns this operational company.',
    )
    is_holding = fields.Boolean(
        string='Is Holding Company',
        default=False,
        help=(
            'If checked, this company is the master holding.\n'
            'Holding Managers assigned to this company see ALL data across all companies.'
        ),
    )

    # ── Business Activity ─────────────────────────────────────────────────────

    business_activity = fields.Selection(
        selection=ACTIVITY_SELECTION,
        string='Primary Business Activity',
        help=(
            'The primary activity for this company.\n'
            'Drives record filtering and menu visibility.\n'
            '(Holding companies leave this blank — they see all activities.)'
        ),
    )

    # ── Visibility Flags ──────────────────────────────────────────────────────

    show_inside_smart_farm = fields.Boolean(
        string='Show Inside Smart Farm App',
        default=True,
        help='If checked, this company\'s data appears inside the Smart Farm holding menu.',
    )
    show_as_odoo_app = fields.Boolean(
        string='Show as Separate Odoo App',
        default=True,
        help='If checked, this company\'s activity module appears as a separate Odoo app.',
    )

    # ── Activity Module Flags ─────────────────────────────────────────────────

    has_construction = fields.Boolean(
        string='Construction Module',
        default=False,
        help='This company uses the Construction module.',
    )
    has_agriculture = fields.Boolean(
        string='Agriculture Module',
        default=False,
        help='This company uses the Agriculture module.',
    )
    has_manufacturing = fields.Boolean(
        string='Manufacturing Module',
        default=False,
        help='This company uses the Manufacturing module.',
    )
    has_livestock = fields.Boolean(
        string='Livestock Module',
        default=False,
        help='This company uses the Livestock module.',
    )

    # ── Display ───────────────────────────────────────────────────────────────

    company_name = fields.Char(
        string='Company Name',
        related='company_id.name',
        readonly=True,
        store=True,
    )
    company_logo = fields.Binary(
        string='Logo',
        related='company_id.logo',
        readonly=True,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='company_id.currency_id',
        readonly=True,
    )

    # ── Statistics (computed from operational data) ────────────────────────────

    active_projects_count = fields.Integer(
        string='Active Projects',
        compute='_compute_statistics',
        store=False,
    )
    total_projects_count = fields.Integer(
        string='Total Projects',
        compute='_compute_statistics',
        store=False,
    )
    high_risk_count = fields.Integer(
        string='High Risk Records',
        compute='_compute_statistics',
        store=False,
    )

    notes = fields.Text(string='Notes')

    # ── SQL Constraints ───────────────────────────────────────────────────────

    _sql_constraints = [
        ('unique_company', 'UNIQUE(company_id)',
         'A configuration already exists for this company.'),
    ]

    # ── Validation ────────────────────────────────────────────────────────────

    @api.constrains('is_holding', 'business_activity')
    def _check_holding_activity(self):
        for rec in self:
            if rec.is_holding and rec.business_activity:
                raise ValidationError(_(
                    'A holding company should not have a specific business activity. '
                    'Leave "Primary Business Activity" empty for the holding.'
                ))

    @api.constrains('has_construction', 'has_agriculture', 'has_manufacturing', 'has_livestock',
                    'is_holding')
    def _check_module_flags(self):
        for rec in self:
            if not rec.is_holding:
                enabled_count = sum([
                    rec.has_construction, rec.has_agriculture,
                    rec.has_manufacturing, rec.has_livestock,
                ])
                if enabled_count > 1:
                    raise ValidationError(_(
                        'An operational company should be assigned to only one activity module. '
                        'Multiple modules are only allowed for the holding company.'
                    ))

    # ── Compute ───────────────────────────────────────────────────────────────

    def _compute_statistics(self):
        FarmProject = self.env['farm.project']
        ConstructionProject = self.env['construction.project']

        for rec in self:
            company = rec.company_id
            farm_projects = FarmProject.search([('company_id', '=', company.id)])
            con_projects = ConstructionProject.search([('company_id', '=', company.id)])

            all_projects = len(farm_projects) + len(con_projects)
            active_farm = len(farm_projects.filtered(lambda p: p.state == 'running'))
            active_con = len(con_projects.filtered(
                lambda p: p.state in ['planning', 'execution', 'running']))

            rec.total_projects_count = all_projects
            rec.active_projects_count = active_farm + active_con

            # High risk: farm projects with high risk score (if field exists)
            high_risk = 0
            if hasattr(farm_projects, 'risk_score'):
                high_risk += len(farm_projects.filtered(
                    lambda p: getattr(p, 'risk_score', 0) >= 70))
            rec.high_risk_count = high_risk

    # ── Auto-Set Activity Flag ────────────────────────────────────────────────

    @api.onchange('business_activity')
    def _onchange_business_activity(self):
        if self.business_activity:
            self.has_construction = self.business_activity == 'construction'
            self.has_agriculture = self.business_activity == 'agriculture'
            self.has_manufacturing = self.business_activity == 'manufacturing'
            self.has_livestock = self.business_activity == 'livestock'

    # ── Helper ────────────────────────────────────────────────────────────────

    @api.model
    def get_holding_config(self):
        """Return the holding company configuration, or None."""
        return self.search([('is_holding', '=', True)], limit=1)

    @api.model
    def get_company_config(self, company_id):
        """Return the config for a specific company."""
        return self.search([('company_id', '=', company_id)], limit=1)
