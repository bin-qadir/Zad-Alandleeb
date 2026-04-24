from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


BUSINESS_ACTIVITY = 'agriculture'

STATE_SELECTION = [
    ('draft',      'Draft'),
    ('running',    'Running'),
    ('done',       'Completed'),
    ('cancelled',  'Cancelled'),
]


class AgricultureSeason(models.Model):
    """Growing season — top-level container for all agriculture activities."""

    _name = 'agriculture.season'
    _description = 'Agriculture Season'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'start_date desc, name'
    _rec_name = 'name'

    # ── Identity ──────────────────────────────────────────────────────────────

    name = fields.Char(
        string='Season Name',
        required=True,
        tracking=True,
    )
    code = fields.Char(
        string='Season Code',
        required=True,
        copy=False,
        index=True,
        tracking=True,
        help='Unique season identifier, e.g. AGR-2026-S1',
    )

    # ── Company & Activity ────────────────────────────────────────────────────

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
    )
    business_activity = fields.Selection(
        selection=[
            ('construction',  'Construction'),
            ('agriculture',   'Agriculture'),
            ('manufacturing', 'Manufacturing'),
            ('livestock',     'Livestock'),
        ],
        string='Business Activity',
        default=BUSINESS_ACTIVITY,
        readonly=True,
        store=True,
    )

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    lifecycle_stage_id = fields.Many2one(
        comodel_name='activity.lifecycle.stage',
        string='Lifecycle Stage',
        domain=[('business_activity', '=', BUSINESS_ACTIVITY)],
        ondelete='set null',
        tracking=True,
    )
    state = fields.Selection(
        selection=STATE_SELECTION,
        string='State',
        default='draft',
        required=True,
        tracking=True,
    )

    # ── Links ─────────────────────────────────────────────────────────────────

    farm_project_id = fields.Many2one(
        comodel_name='farm.project',
        string='Farm Project',
        domain=[('business_activity', '=', BUSINESS_ACTIVITY)],
        ondelete='set null',
        tracking=True,
    )
    analytic_account_id = fields.Many2one(
        comodel_name='account.analytic.account',
        string='Analytic Account',
        ondelete='set null',
    )

    # ── Responsible ───────────────────────────────────────────────────────────

    responsible_id = fields.Many2one(
        comodel_name='res.users',
        string='Season Manager',
        default=lambda self: self.env.user,
        tracking=True,
    )

    # ── Schedule ──────────────────────────────────────────────────────────────

    start_date = fields.Date(string='Start Date', tracking=True)
    end_date = fields.Date(string='End Date', tracking=True)

    # ── Area ──────────────────────────────────────────────────────────────────

    total_area_ha = fields.Float(
        string='Total Area (ha)',
        digits=(16, 4),
        help='Total cultivated area in hectares for this season.',
    )

    # ── AI Decision Layer ─────────────────────────────────────────────────────

    risk_score = fields.Float(
        string='Risk Score',
        default=0.0,
        digits=(5, 1),
        help='Overall risk 0–100. Computed or manually set.',
    )
    delay_score = fields.Float(
        string='Delay Score',
        default=0.0,
        digits=(5, 1),
        help='Delay risk 0–100.',
    )
    budget_risk = fields.Float(
        string='Budget Risk',
        default=0.0,
        digits=(5, 1),
        help='Budget overrun risk 0–100.',
    )
    claim_readiness = fields.Float(
        string='Claim Readiness',
        default=0.0,
        digits=(5, 1),
        help='How ready this season is for claim/invoicing 0–100.',
    )
    next_recommended_action = fields.Text(
        string='Next Recommended Action',
        help='AI-driven suggested next action for this season.',
    )

    # ── Notes ─────────────────────────────────────────────────────────────────

    description = fields.Text(string='Description / Notes')

    # ── Children ──────────────────────────────────────────────────────────────

    crop_plan_ids = fields.One2many(
        comodel_name='agriculture.crop.plan',
        inverse_name='season_id',
        string='Crop Plan List',
    )
    operation_ids = fields.One2many(
        comodel_name='agriculture.field.operation',
        inverse_name='season_id',
        string='Field Operation List',
    )

    crop_plan_count = fields.Integer(
        string='Crop Plans',
        compute='_compute_counts',
        store=False,
    )
    operation_count = fields.Integer(
        string='Operations',
        compute='_compute_counts',
        store=False,
    )

    # ── SQL Constraints ───────────────────────────────────────────────────────

    _sql_constraints = [
        ('unique_code_company', 'UNIQUE(code, company_id)',
         'A season with this code already exists for this company.'),
    ]

    # ── Compute ───────────────────────────────────────────────────────────────

    @api.depends('crop_plan_ids', 'operation_ids')
    def _compute_counts(self):
        for rec in self:
            rec.crop_plan_count = len(rec.crop_plan_ids)
            rec.operation_count = len(rec.operation_ids)

    # ── Validation ────────────────────────────────────────────────────────────

    @api.constrains('start_date', 'end_date')
    def _check_dates(self):
        for rec in self:
            if rec.start_date and rec.end_date and rec.start_date > rec.end_date:
                raise ValidationError(_('End date must be after start date.'))

    # ── Workflow ──────────────────────────────────────────────────────────────

    def action_start(self):
        self.write({'state': 'running'})

    def action_complete(self):
        self.write({'state': 'done'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset_draft(self):
        self.write({'state': 'draft'})

    # ── Smart Buttons ─────────────────────────────────────────────────────────

    def action_view_crop_plans(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Crop Plans'),
            'res_model': 'agriculture.crop.plan',
            'view_mode': 'list,form',
            'domain': [('season_id', '=', self.id)],
            'context': {'default_season_id': self.id},
        }

    def action_view_operations(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Field Operations'),
            'res_model': 'agriculture.field.operation',
            'view_mode': 'list,form',
            'domain': [('season_id', '=', self.id)],
            'context': {'default_season_id': self.id},
        }

    # ── Name Sequence ──────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('code'):
                vals['code'] = self.env['ir.sequence'].next_by_code(
                    'agriculture.season') or '/'
        return super().create(vals_list)
