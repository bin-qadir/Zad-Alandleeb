from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


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
    lifecycle_stage_id = fields.Many2one(
        comodel_name='activity.lifecycle.stage',
        string='Lifecycle Stage',
        domain="[('business_activity', '=', business_activity)]",
        ondelete='set null',
        tracking=True,
        help='Current lifecycle stage of this project. Filtered by the selected business activity.',
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

    # ── Master Project (parent-child hierarchy) ───────────────────────────────

    master_project_id = fields.Many2one(
        comodel_name='farm.project',
        string='Master Project',
        ondelete='set null',
        index=True,
        tracking=True,
        help=(
            'Parent / umbrella project that this Activity Project belongs to.\n'
            'Example: a "Site A Development" master project can have separate\n'
            'Construction, Agriculture, Manufacturing, and Livestock sub-projects.'
        ),
    )
    activity_project_ids = fields.One2many(
        comodel_name='farm.project',
        inverse_name='master_project_id',
        string='Activity Projects',
        help='Activity-specific sub-projects linked to this master project.',
    )

    # ── Activity sub-project counts ───────────────────────────────────────────

    construction_project_count = fields.Integer(
        string='Construction Projects',
        compute='_compute_activity_project_counts',
    )
    agriculture_project_count = fields.Integer(
        string='Agriculture Projects',
        compute='_compute_activity_project_counts',
    )
    manufacturing_project_count = fields.Integer(
        string='Manufacturing Projects',
        compute='_compute_activity_project_counts',
    )
    livestock_project_count = fields.Integer(
        string='Livestock Projects',
        compute='_compute_activity_project_counts',
    )

    # ── Stat buttons ──────────────────────────────────────────────────────────
    field_count = fields.Integer(
        string='Field Count',
        compute='_compute_field_count',
    )
    task_count = fields.Integer(
        string='Tasks',
        compute='_compute_task_count',
        help='Count of operational tasks in the linked Odoo project.',
    )

    @api.depends('field_ids')
    def _compute_field_count(self):
        for rec in self:
            rec.field_count = len(rec.field_ids)

    @api.depends('odoo_project_id')
    def _compute_task_count(self):
        for rec in self:
            if rec.odoo_project_id:
                # Exclude milestones; count only real user-created tasks
                rec.task_count = self.env['project.task'].search_count([
                    ('project_id', '=', rec.odoo_project_id.id),
                ])
            else:
                rec.task_count = 0

    @api.depends('activity_project_ids', 'activity_project_ids.business_activity')
    def _compute_activity_project_counts(self):
        for rec in self:
            sub = rec.activity_project_ids
            rec.construction_project_count  = sum(1 for p in sub if p.business_activity == 'construction')
            rec.agriculture_project_count   = sum(1 for p in sub if p.business_activity == 'agriculture')
            rec.manufacturing_project_count = sum(1 for p in sub if p.business_activity == 'manufacturing')
            rec.livestock_project_count     = sum(1 for p in sub if p.business_activity == 'livestock')

    # ────────────────────────────────────────────────────────────────────────
    # Dynamic project_type filtering
    # ────────────────────────────────────────────────────────────────────────

    @api.onchange('project_type')
    def _onchange_project_type_sync_activity(self):
        """
        Auto-sync business_activity from project_type when the type is selected.

        This enables the "type-first" workflow:
          1. User picks Project Type  → business_activity auto-fills from type.activity
          2. lifecycle_stage_id is cleared if it no longer matches the new activity
        The reverse (activity-first) is handled by _onchange_business_activity_clear_type.
        """
        if self.project_type:
            new_activity = self.project_type.activity
            if self.business_activity != new_activity:
                self.business_activity = new_activity
                if (self.lifecycle_stage_id
                        and self.lifecycle_stage_id.business_activity != new_activity):
                    self.lifecycle_stage_id = False

    @api.onchange('business_activity')
    def _onchange_business_activity_clear_type(self):
        """Clear project_type and lifecycle_stage_id when business_activity changes."""
        if self.project_type and self.project_type.activity != self.business_activity:
            self.project_type = False
        if (self.lifecycle_stage_id
                and self.lifecycle_stage_id.business_activity != self.business_activity):
            self.lifecycle_stage_id = False

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
    # Master Project onchange + constraint
    # ────────────────────────────────────────────────────────────────────────

    @api.onchange('master_project_id')
    def _onchange_master_project_id(self):
        """Warn the user if the master project has an incompatible business activity."""
        if (self.master_project_id
                and self.business_activity
                and self.master_project_id.business_activity
                and self.master_project_id.business_activity == self.business_activity
                and self.master_project_id.id != self._origin.id):
            # Same activity type — unusual but not blocked; just a UI nudge
            return {
                'warning': {
                    'title':   _('Activity Match'),
                    'message': _(
                        'The selected Master Project has the same business activity (%s).\n'
                        'Typically a master project has no specific activity or a different one.',
                        dict(self._fields['business_activity'].selection).get(
                            self.business_activity, self.business_activity
                        ),
                    ),
                }
            }

    @api.constrains('master_project_id')
    def _check_master_project_id(self):
        """Prevent circular references (project linking to itself or its descendants)."""
        for rec in self:
            if not rec.master_project_id:
                continue
            if rec.master_project_id.id == rec.id:
                raise ValidationError(_(
                    'A project cannot be its own master project.'
                ))
            # Walk up the ancestor chain to detect cycles
            ancestor = rec.master_project_id.master_project_id
            visited = {rec.id, rec.master_project_id.id}
            while ancestor:
                if ancestor.id in visited:
                    raise ValidationError(_(
                        'Circular reference detected in the Master Project hierarchy.\n'
                        'Project "%s" is already an ancestor of this project.',
                        ancestor.name,
                    ))
                visited.add(ancestor.id)
                ancestor = ancestor.master_project_id

    # ────────────────────────────────────────────────────────────────────────
    # ORM overrides
    # ────────────────────────────────────────────────────────────────────────

    # ────────────────────────────────────────────────────────────────────────
    # Bidirectional project_type ↔ business_activity sync (ORM level)
    # ────────────────────────────────────────────────────────────────────────

    def _sync_project_type_and_activity(self, vals):
        """
        Derive business_activity from project_type when project_type is being set.

        Called from create() and write() before the ORM super() call so that
        database records are always consistent.

        Rules:
          • project_type is set (>0)    → business_activity = type.activity  (type wins)
          • project_type is cleared (0) → business_activity left unchanged
          • project_type absent in vals → no change
        The existing _check_project_type_matches_activity constraint validates
        the final state and blocks any remaining mismatches.
        """
        ptype_id = vals.get('project_type')
        if ptype_id:
            ptype = self.env['farm.project.type'].browse(ptype_id)
            if ptype.exists():
                vals['business_activity'] = ptype.activity
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._sync_project_type_and_activity(vals)
        records = super().create(vals_list)
        for proj in records:
            # 1. Auto-create a linked Odoo project (project.project) if not set
            proj._ensure_odoo_project()
            # 2. Auto-create analytic account if not set
            proj._ensure_analytic_account()
        return records

    def write(self, vals):
        self._sync_project_type_and_activity(vals)
        return super().write(vals)

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

    # ── Activity sub-project navigation ──────────────────────────────────────

    def _action_view_activity_projects(self, activity):
        """Open Activity Projects filtered by business_activity under this master."""
        self.ensure_one()
        activity_labels = {
            'construction':  _('Construction Projects'),
            'agriculture':   _('Agriculture Projects'),
            'manufacturing': _('Manufacturing Projects'),
            'livestock':     _('Livestock Projects'),
        }
        return {
            'type': 'ir.actions.act_window',
            'name': '%s — %s' % (activity_labels.get(activity, activity), self.name),
            'res_model': 'farm.project',
            'view_mode': 'list,form',
            'domain': [
                ('master_project_id', '=', self.id),
                ('business_activity', '=', activity),
            ],
            'context': {
                'default_master_project_id': self.id,
                'default_business_activity': activity,
            },
        }

    def action_view_construction_projects(self):
        return self._action_view_activity_projects('construction')

    def action_view_agriculture_projects(self):
        return self._action_view_activity_projects('agriculture')

    def action_view_manufacturing_projects(self):
        return self._action_view_activity_projects('manufacturing')

    def action_view_livestock_projects(self):
        return self._action_view_activity_projects('livestock')
