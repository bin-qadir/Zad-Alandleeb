from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

# Default divisions created automatically for each new project
DEFAULT_DIVISIONS = [
    ('civil',          'Civil',          'CIV', 10),
    ('structural',     'Structural',     'STR', 20),
    ('architectural',  'Architectural',  'ARC', 30),
    ('mechanical',     'Mechanical',     'MEC', 40),
    ('electrical',     'Electrical',     'ELE', 50),
]


class ConstructionProject(models.Model):
    _name = 'construction.project'
    _description = 'Construction Project'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'project_code, name'
    _rec_name = 'name'

    # ── Identity ──────────────────────────────────────────────────────────────

    name = fields.Char(
        string='Project Name',
        required=True,
        tracking=True,
    )
    project_code = fields.Char(
        string='Project Code',
        required=True,
        copy=False,
        index=True,
        tracking=True,
    )

    # ── Parties ───────────────────────────────────────────────────────────────

    client_id = fields.Many2one(
        comodel_name='res.partner',
        string='Client',
        ondelete='set null',
        tracking=True,
        domain=[('is_company', '=', True)],
    )
    consultant_id = fields.Many2one(
        comodel_name='res.partner',
        string='Consultant',
        ondelete='set null',
        tracking=True,
    )

    # ── Company / Currency ────────────────────────────────────────────────────

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        related='company_id.currency_id',
        store=True,
        readonly=True,
    )

    # ── Classification ────────────────────────────────────────────────────────

    project_type = fields.Selection(
        selection=[
            ('residential',   'Residential'),
            ('commercial',    'Commercial'),
            ('industrial',    'Industrial'),
            ('infrastructure','Infrastructure'),
            ('mixed_use',     'Mixed Use'),
            ('renovation',    'Renovation'),
            ('other',         'Other'),
        ],
        string='Project Type',
        tracking=True,
    )

    # ── Schedule ──────────────────────────────────────────────────────────────

    start_date = fields.Date(string='Start Date', tracking=True)
    end_date = fields.Date(string='End Date', tracking=True)

    # ── State & Phase ─────────────────────────────────────────────────────────

    state = fields.Selection(
        selection=[
            ('draft',     'Draft'),
            ('active',    'Active'),
            ('on_hold',   'On Hold'),
            ('closed',    'Closed'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
        copy=False,
    )
    phase = fields.Selection(
        selection=[
            ('feasibility', 'Feasibility'),
            ('design',      'Design'),
            ('boq',         'BOQ'),
            ('costing',     'Costing'),
            ('tender',      'Tender'),
            ('contract',    'Contract'),
            ('execution',   'Execution'),
            ('inspection',  'Inspection'),
            ('handover',    'Handover'),
            ('closure',     'Closure'),
        ],
        string='Phase',
        tracking=True,
    )

    # ── Links ─────────────────────────────────────────────────────────────────

    analytic_account_id = fields.Many2one(
        comodel_name='account.analytic.account',
        string='Analytic Account',
        ondelete='set null',
        copy=False,
        tracking=True,
    )
    odoo_project_id = fields.Many2one(
        comodel_name='project.project',
        string='Odoo Project',
        ondelete='set null',
        copy=False,
        tracking=True,
    )

    # ── Notes ─────────────────────────────────────────────────────────────────

    notes = fields.Html(string='Notes')

    # ── Structure (computed counts) ───────────────────────────────────────────

    division_ids = fields.One2many(
        comodel_name='construction.division',
        inverse_name='project_id',
        string='Division List',
    )
    division_count = fields.Integer(
        string='Divisions',
        compute='_compute_division_count',
    )
    subdivision_ids = fields.One2many(
        comodel_name='construction.subdivision',
        inverse_name='project_id',
        string='Subdivision List',
    )
    subdivision_count = fields.Integer(
        string='Subdivisions',
        compute='_compute_subdivision_count',
    )

    # ── Computes ──────────────────────────────────────────────────────────────

    @api.depends('division_ids')
    def _compute_division_count(self):
        for rec in self:
            rec.division_count = len(rec.division_ids)

    @api.depends('subdivision_ids')
    def _compute_subdivision_count(self):
        for rec in self:
            rec.subdivision_count = len(rec.subdivision_ids)

    # ── Constraints ───────────────────────────────────────────────────────────

    _sql_constraints = [
        (
            'project_code_uniq',
            'unique(project_code)',
            'Project code must be unique across all projects.',
        ),
    ]

    @api.constrains('start_date', 'end_date')
    def _check_dates(self):
        for rec in self:
            if rec.start_date and rec.end_date and rec.end_date < rec.start_date:
                raise ValidationError(_(
                    'End Date cannot be before Start Date on project "%s".',
                    rec.name,
                ))

    # ── ORM overrides ─────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for proj in records:
            proj._ensure_odoo_project()
            proj._ensure_analytic_account()
            proj._create_default_divisions()
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'name' in vals:
            for proj in self:
                if proj.odoo_project_id:
                    proj.odoo_project_id.sudo().write({'name': vals['name']})
        return res

    # ── Auto-creation helpers ─────────────────────────────────────────────────

    def _ensure_odoo_project(self):
        """Auto-create a linked project.project if not already set."""
        self.ensure_one()
        if self.odoo_project_id:
            return
        create_vals = {
            'name': self.name,
            'company_id': self.company_id.id,
        }
        odoo_proj = self.env['project.project'].sudo().create(create_vals)
        self.odoo_project_id = odoo_proj

    def _ensure_analytic_account(self):
        """Auto-create or link an analytic account for this project."""
        self.ensure_one()
        if self.analytic_account_id:
            return
        # Prefer the account automatically created by Odoo for project.project
        if self.odoo_project_id and self.odoo_project_id.account_id:
            self.analytic_account_id = self.odoo_project_id.account_id
            return
        # Fallback: create directly under the first available plan
        plan = self.env['account.analytic.plan'].sudo().search(
            [('company_id', 'in', [False, self.company_id.id])],
            order='id asc',
            limit=1,
        )
        try:
            create_vals = {
                'name': self.name,
                'company_id': self.company_id.id,
            }
            if plan:
                create_vals['plan_id'] = plan.id
            account = self.env['account.analytic.account'].sudo().create(create_vals)
            self.analytic_account_id = account
        except Exception:
            # Non-critical — skip silently
            pass

    def _create_default_divisions(self):
        """Create the five standard construction divisions for this project."""
        self.ensure_one()
        if self.division_ids:
            return
        Division = self.env['construction.division']
        for _key, name, code, seq in DEFAULT_DIVISIONS:
            Division.create({
                'name': name,
                'code': code,
                'sequence': seq,
                'project_id': self.id,
            })

    # ── State transitions ─────────────────────────────────────────────────────

    def action_activate(self):
        self.write({'state': 'active'})

    def action_hold(self):
        self.write({'state': 'on_hold'})

    def action_close(self):
        self.write({'state': 'closed'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset_draft(self):
        self.write({'state': 'draft'})

    # ── Smart button actions ──────────────────────────────────────────────────

    def action_open_divisions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Divisions — %s') % self.name,
            'res_model': 'construction.division',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
        }

    def action_open_subdivisions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Subdivisions — %s') % self.name,
            'res_model': 'construction.subdivision',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
        }

    def action_open_odoo_project(self):
        self.ensure_one()
        if not self.odoo_project_id:
            return {}
        return {
            'type': 'ir.actions.act_window',
            'name': _('Odoo Project'),
            'res_model': 'project.project',
            'view_mode': 'form',
            'res_id': self.odoo_project_id.id,
        }
