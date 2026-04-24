from odoo import api, fields, models, _


BUSINESS_ACTIVITY = 'livestock'

SPECIES_SELECTION = [
    ('cattle',    'Cattle'),
    ('sheep',     'Sheep'),
    ('goat',      'Goat'),
    ('camel',     'Camel'),
    ('poultry',   'Poultry'),
    ('fish',      'Fish / Aquaculture'),
    ('other',     'Other'),
]


class LivestockHerd(models.Model):
    """Herd — a managed group of animals within a livestock operation."""

    _name = 'livestock.herd'
    _description = 'Livestock Herd'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'
    _rec_name = 'name'

    name = fields.Char(string='Herd Name', required=True, tracking=True)
    reference = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        index=True,
        tracking=True,
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
        selection=[
            ('draft',      'Draft'),
            ('active',     'Active'),
            ('fattening',  'Fattening'),
            ('sale_ready', 'Ready for Sale'),
            ('sold',       'Sold / Closed'),
            ('cancelled',  'Cancelled'),
        ],
        default='draft',
        required=True,
        tracking=True,
    )

    # ── Classification ────────────────────────────────────────────────────────

    species = fields.Selection(
        selection=SPECIES_SELECTION,
        string='Species',
        required=True,
        default='cattle',
        tracking=True,
    )
    breed = fields.Char(string='Breed / Variety')

    # ── Links ─────────────────────────────────────────────────────────────────

    farm_project_id = fields.Many2one(
        comodel_name='farm.project',
        string='Livestock Project',
        domain=[('business_activity', '=', BUSINESS_ACTIVITY)],
        ondelete='set null',
        tracking=True,
    )
    analytic_account_id = fields.Many2one(
        comodel_name='account.analytic.account',
        string='Analytic Account',
        ondelete='set null',
    )
    responsible_id = fields.Many2one(
        comodel_name='res.users',
        string='Herd Manager',
        default=lambda self: self.env.user,
        tracking=True,
    )

    # ── Counts ────────────────────────────────────────────────────────────────

    total_animals = fields.Integer(
        string='Total Animals',
        compute='_compute_animal_stats',
        store=True,
    )
    male_count = fields.Integer(
        string='Male',
        compute='_compute_animal_stats',
        store=True,
    )
    female_count = fields.Integer(
        string='Female',
        compute='_compute_animal_stats',
        store=True,
    )

    # ── Schedule ──────────────────────────────────────────────────────────────

    establishment_date = fields.Date(string='Establishment Date', tracking=True)
    target_sale_date = fields.Date(string='Target Sale Date', tracking=True)

    # ── AI Decision Layer ─────────────────────────────────────────────────────

    risk_score = fields.Float(string='Risk Score', default=0.0, digits=(5, 1))
    delay_score = fields.Float(string='Delay Score', default=0.0, digits=(5, 1))
    budget_risk = fields.Float(string='Budget Risk', default=0.0, digits=(5, 1))
    next_recommended_action = fields.Text(string='Next Recommended Action')

    # ── Children ──────────────────────────────────────────────────────────────

    animal_ids = fields.One2many(
        comodel_name='livestock.animal',
        inverse_name='herd_id',
        string='Animals',
    )
    health_check_ids = fields.One2many(
        comodel_name='livestock.health.check',
        inverse_name='herd_id',
        string='Health Checks',
    )
    feeding_plan_ids = fields.One2many(
        comodel_name='livestock.feeding.plan',
        inverse_name='herd_id',
        string='Feeding Plans',
    )

    health_check_count = fields.Integer(compute='_compute_child_counts', store=False)
    feeding_plan_count = fields.Integer(compute='_compute_child_counts', store=False)

    notes = fields.Text(string='Notes')

    # ── SQL Constraints ───────────────────────────────────────────────────────

    _sql_constraints = [
        ('unique_ref_company', 'UNIQUE(reference, company_id)',
         'A herd with this reference already exists for this company.'),
    ]

    # ── Compute ───────────────────────────────────────────────────────────────

    @api.depends('animal_ids', 'animal_ids.gender')
    def _compute_animal_stats(self):
        for rec in self:
            animals = rec.animal_ids.filtered(lambda a: a.state != 'sold')
            rec.total_animals = len(animals)
            rec.male_count = len(animals.filtered(lambda a: a.gender == 'male'))
            rec.female_count = len(animals.filtered(lambda a: a.gender == 'female'))

    @api.depends('health_check_ids', 'feeding_plan_ids')
    def _compute_child_counts(self):
        for rec in self:
            rec.health_check_count = len(rec.health_check_ids)
            rec.feeding_plan_count = len(rec.feeding_plan_ids)

    # ── Workflow ──────────────────────────────────────────────────────────────

    def action_activate(self):
        self.write({'state': 'active'})

    def action_start_fattening(self):
        self.write({'state': 'fattening'})

    def action_ready_for_sale(self):
        self.write({'state': 'sale_ready'})

    def action_mark_sold(self):
        self.write({'state': 'sold'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset_draft(self):
        self.write({'state': 'draft'})

    def action_view_animals(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Animals'),
            'res_model': 'livestock.animal',
            'view_mode': 'list,form',
            'domain': [('herd_id', '=', self.id)],
            'context': {'default_herd_id': self.id},
        }

    def action_view_health_checks(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Health Checks'),
            'res_model': 'livestock.health.check',
            'view_mode': 'list,form',
            'domain': [('herd_id', '=', self.id)],
            'context': {'default_herd_id': self.id},
        }

    def action_view_feeding_plans(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Feeding Plans'),
            'res_model': 'livestock.feeding.plan',
            'view_mode': 'list,form',
            'domain': [('herd_id', '=', self.id)],
            'context': {'default_herd_id': self.id},
        }

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('reference'):
                vals['reference'] = self.env['ir.sequence'].next_by_code(
                    'livestock.herd') or '/'
        return super().create(vals_list)
