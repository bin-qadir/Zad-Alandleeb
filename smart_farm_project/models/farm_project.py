from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

# ── Default task templates per activity ──────────────────────────────────────
_DEFAULT_TASKS = {
    'construction': [
        'BOQ / Scope',
        'Execution',
        'Handover',
        'Inspection',
        'Approved Quantities',
        'Claims / Extracts',
    ],
    'agriculture': [
        'Crop Plan',
        'Daily Operations',
        'Irrigation / Fertigation',
        'Monitoring & Quality',
        'Harvest',
        'Yield / Sales',
    ],
    'manufacturing': [
        'Packing Orders',
        'Material Issue',
        'Packing Progress',
        'Quality Control',
        'Packed Output',
        'Finished Goods / Costing',
    ],
    'livestock': [
        'Herd Planning',
        'Breeding',
        'Feeding & Care',
        'Health Monitoring',
        'Fattening',
        'Sales',
    ],
}


class FarmProject(models.Model):
    _name = 'farm.project'
    _description = 'Farm Project'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    # ── Identity ──────────────────────────────────────────────────────────────
    name = fields.Char(string='Name', required=True, tracking=True)
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('running', 'Running'),
            ('done', 'Done'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
    )

    # ── Business Activity & Lifecycle ─────────────────────────────────────────
    business_activity = fields.Selection(
        selection=[
            ('construction',  'Construction'),
            ('agriculture',   'Agriculture'),
            ('manufacturing', 'Manufacturing / Packing'),
            ('livestock',     'Livestock'),
        ],
        string='Business Activity',
        tracking=True,
        index=True,
        help=(
            'Primary business activity for this project.\n'
            'Drives default task templates, dashboard isolation, and job order validation.\n'
            '• Construction — civil/MEP BOQ-driven execution workflow\n'
            '• Agriculture — crop lifecycle: planning, ops, harvest, sales\n'
            '• Manufacturing — packing cycle: orders, QC, dispatch\n'
            '• Livestock — herd: breeding, raising, fattening, sales'
        ),
    )
    lifecycle_stage = fields.Selection(
        selection=[
            ('establishment', 'Establishment'),
            ('operation',     'Operation'),
            ('packing',       'Packing'),
            ('breeding',      'Breeding'),
            ('raising',       'Raising'),
            ('fattening',     'Fattening'),
            ('sales',         'Sales'),
        ],
        string='Lifecycle Stage',
        tracking=True,
        help='Current lifecycle stage of this project.',
    )

    # ── Project Classification ─────────────────────────────────────────────────
    project_type = fields.Many2one(
        comodel_name='farm.project.type',
        string='Project Type',
        domain="[('activity', '=', business_activity)]",
        ondelete='set null',
        tracking=True,
        help=(
            'Specific project type within the selected business activity.\n'
            'The dropdown automatically filters to types valid for the current activity.\n'
            'Changing the activity will clear this field if the current type is incompatible.'
        ),
    )
    project_manager_id = fields.Many2one(
        comodel_name='res.users',
        string='Project Manager',
        ondelete='set null',
        tracking=True,
    )
    project_tag_ids = fields.Many2many(
        comodel_name='smart.farm.tag',
        relation='farm_project_tag_rel',
        column1='project_id',
        column2='tag_id',
        string='Tags',
    )
    analytic_account_id = fields.Many2one(
        comodel_name='account.analytic.account',
        string='Analytic Account',
        ondelete='set null',
        copy=False,
    )

    # ── Links ─────────────────────────────────────────────────────────────────
    odoo_project_id = fields.Many2one(
        comodel_name='project.project',
        string='Odoo Project',
        ondelete='set null',
        tracking=True,
    )

    # ── Schedule ──────────────────────────────────────────────────────────────
    start_date = fields.Date(string='Start Date', tracking=True)
    end_date = fields.Date(string='End Date', tracking=True)

    # ── Description ───────────────────────────────────────────────────────────
    description = fields.Text(string='Description')

    # ── Location ──────────────────────────────────────────────────────────────
    country_id = fields.Many2one(
        comodel_name='res.country',
        string='Country',
        ondelete='set null',
    )
    state_id = fields.Many2one(
        comodel_name='res.country.state',
        string='State / Region',
        domain="[('country_id', '=', country_id)]",
        ondelete='set null',
    )
    city = fields.Char(string='City')
    location_text = fields.Text(string='Location Details')
    latitude = fields.Float(string='Latitude', digits=(10, 7))
    longitude = fields.Float(string='Longitude', digits=(10, 7))

    # ── Area ──────────────────────────────────────────────────────────────────
    total_project_area = fields.Float(
        string='Total Area (ha)', digits=(16, 4),
    )
    cultivated_area = fields.Float(
        string='Cultivated Area (ha)', digits=(16, 4),
    )
    builtup_area = fields.Float(
        string='Built-up Area (ha)', digits=(16, 4),
    )

    # ── Consists ──────────────────────────────────────────────────────────────
    consists_notes = fields.Text(string='Project Consists of')

    # ── Documents ─────────────────────────────────────────────────────────────
    document_notes = fields.Text(string='Document Notes')

    # ── Drawings ──────────────────────────────────────────────────────────────
    drawing_notes = fields.Text(string='Drawing Notes')

    # ── Teams ─────────────────────────────────────────────────────────────────
    team_member_ids = fields.Many2many(
        comodel_name='res.users',
        relation='farm_project_team_rel',
        column1='project_id',
        column2='user_id',
        string='Team Members',
    )

    # ── Zones ─────────────────────────────────────────────────────────────────
    zone_notes = fields.Text(string='Zone Notes')

    # ── Fields relation ───────────────────────────────────────────────────────
    field_ids = fields.One2many(
        comodel_name='farm.field',
        inverse_name='project_id',
        string='Fields',
    )

    # ── Stat buttons ──────────────────────────────────────────────────────────
    field_count = fields.Integer(
        string='Field Count',
        compute='_compute_field_count',
    )
    task_count = fields.Integer(
        string='Tasks',
        compute='_compute_task_count',
    )

    @api.depends('field_ids')
    def _compute_field_count(self):
        for rec in self:
            rec.field_count = len(rec.field_ids)

    def _compute_task_count(self):
        for rec in self:
            if rec.odoo_project_id:
                rec.task_count = self.env['project.task'].search_count(
                    [('project_id', '=', rec.odoo_project_id.id)]
                )
            else:
                rec.task_count = 0

    # ────────────────────────────────────────────────────────────────────────
    # Dynamic project_type filtering
    # ────────────────────────────────────────────────────────────────────────

    @api.onchange('business_activity')
    def _onchange_business_activity_clear_type(self):
        """Clear project_type when business_activity changes to an incompatible value."""
        if self.project_type and self.project_type.activity != self.business_activity:
            self.project_type = False

    @api.constrains('project_type', 'business_activity')
    def _check_project_type_matches_activity(self):
        for rec in self:
            if not rec.project_type or not rec.business_activity:
                continue
            if rec.project_type.activity != rec.business_activity:
                raise ValidationError(_(
                    'Project type "%(type)s" (%(type_act)s) does not match the project\'s '
                    'business activity "%(proj_act)s".\n'
                    'Please select a project type that belongs to the %(proj_act)s activity.',
                    type=rec.project_type.name,
                    type_act=dict(
                        rec._fields['business_activity'].selection
                    ).get(rec.project_type.activity, rec.project_type.activity),
                    proj_act=dict(
                        rec._fields['business_activity'].selection
                    ).get(rec.business_activity, rec.business_activity),
                ))

    # ────────────────────────────────────────────────────────────────────────
    # ORM overrides
    # ────────────────────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for proj in records:
            # 1. Auto-create a linked Odoo project (project.project) if not set
            proj._ensure_odoo_project()
            # 2. Auto-create analytic account if not set
            proj._ensure_analytic_account()
            # 3. Auto-create default tasks based on business_activity
            if proj.business_activity:
                proj._create_default_tasks()
        return records

    # ────────────────────────────────────────────────────────────────────────
    # Auto-creation helpers
    # ────────────────────────────────────────────────────────────────────────

    def _ensure_odoo_project(self):
        """Auto-create a project.project if this farm project has no link yet."""
        self.ensure_one()
        if self.odoo_project_id:
            return
        create_vals = {'name': self.name}
        if self.project_manager_id:
            create_vals['user_id'] = self.project_manager_id.id
        odoo_proj = self.env['project.project'].create(create_vals)
        self.odoo_project_id = odoo_proj

    def _ensure_analytic_account(self):
        """Auto-create / link an analytic account for this farm project."""
        self.ensure_one()
        if self.analytic_account_id:
            return
        # Prefer the account from the linked Odoo project (Odoo auto-creates it)
        if self.odoo_project_id and self.odoo_project_id.account_id:
            self.analytic_account_id = self.odoo_project_id.account_id
            return
        # Fallback: create directly using the first available analytic plan
        plan = self.env['account.analytic.plan'].search(
            [('company_id', 'in', [False, self.env.company.id])],
            order='id asc',
            limit=1,
        )
        try:
            create_vals = {'name': self.name, 'company_id': self.env.company.id}
            if plan:
                create_vals['plan_id'] = plan.id
            account = self.env['account.analytic.account'].create(create_vals)
            self.analytic_account_id = account
        except Exception:
            # Analytic account creation is non-critical — silently skip
            pass

    def _create_default_tasks(self):
        """Create default project.task records based on business_activity."""
        self.ensure_one()
        task_names = _DEFAULT_TASKS.get(self.business_activity, [])
        if not task_names or not self.odoo_project_id:
            return
        Task = self.env['project.task']
        for seq, task_name in enumerate(task_names, start=1):
            Task.create({
                'name': task_name,
                'project_id': self.odoo_project_id.id,
                'sequence': seq * 10,
                'description': '',
            })

    # ────────────────────────────────────────────────────────────────────────
    # Actions
    # ────────────────────────────────────────────────────────────────────────

    def action_open_fields(self):
        """Open Farm Fields filtered to this project."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Fields — %s') % self.name,
            'res_model': 'farm.field',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
        }

    def action_open_tasks(self):
        """Open Odoo tasks for this project."""
        self.ensure_one()
        if not self.odoo_project_id:
            return {}
        return {
            'type': 'ir.actions.act_window',
            'name': _('Tasks — %s') % self.name,
            'res_model': 'project.task',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.odoo_project_id.id)],
            'context': {'default_project_id': self.odoo_project_id.id},
        }
