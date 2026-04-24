from odoo import api, fields, models, _


OPERATION_TYPE_SELECTION = [
    ('irrigation',    'Irrigation'),
    ('fertigation',   'Fertigation'),
    ('fertilization', 'Fertilization'),
    ('planting',      'Planting'),
    ('treatment',     'Pest / Disease Treatment'),
    ('pruning',       'Pruning'),
    ('soil_prep',     'Soil Preparation'),
    ('inspection',    'Inspection / Scouting'),
    ('other',         'Other'),
]


class AgricultureFieldOperation(models.Model):
    """Field operation — a discrete activity on a field within a season."""

    _name = 'agriculture.field.operation'
    _description = 'Agriculture Field Operation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'planned_date, name'
    _rec_name = 'name'

    name = fields.Char(string='Operation Name', required=True, tracking=True)

    # ── Context ───────────────────────────────────────────────────────────────

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        related='season_id.company_id',
        store=True,
        readonly=True,
    )
    season_id = fields.Many2one(
        comodel_name='agriculture.season',
        string='Season',
        required=True,
        ondelete='cascade',
        tracking=True,
    )
    crop_plan_id = fields.Many2one(
        comodel_name='agriculture.crop.plan',
        string='Crop Plan',
        ondelete='set null',
        tracking=True,
    )
    farm_field_id = fields.Many2one(
        comodel_name='farm.field',
        string='Farm Field',
        ondelete='set null',
    )

    # ── Type ──────────────────────────────────────────────────────────────────

    operation_type = fields.Selection(
        selection=OPERATION_TYPE_SELECTION,
        string='Operation Type',
        required=True,
        tracking=True,
        default='irrigation',
    )

    # ── Schedule ──────────────────────────────────────────────────────────────

    planned_date = fields.Date(string='Planned Date', tracking=True)
    actual_date = fields.Date(string='Actual Date', tracking=True)

    # ── Resources ─────────────────────────────────────────────────────────────

    operator_id = fields.Many2one(
        comodel_name='res.users',
        string='Operator',
    )
    work_type_id = fields.Many2one(
        comodel_name='farm.work.type',
        string='Work Type',
        ondelete='set null',
    )
    cost_type_id = fields.Many2one(
        comodel_name='farm.cost.type',
        string='Cost Category',
        ondelete='set null',
    )
    estimated_cost = fields.Monetary(
        string='Estimated Cost',
        currency_field='currency_id',
    )
    actual_cost = fields.Monetary(
        string='Actual Cost',
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='company_id.currency_id',
        store=True,
        readonly=True,
    )

    # ── State ─────────────────────────────────────────────────────────────────

    state = fields.Selection(
        selection=[
            ('planned',    'Planned'),
            ('in_progress','In Progress'),
            ('done',       'Done'),
            ('cancelled',  'Cancelled'),
        ],
        string='State',
        default='planned',
        required=True,
        tracking=True,
    )

    # ── Quality / Outcome ──────────────────────────────────────────────────────

    quantity = fields.Float(
        string='Quantity',
        digits=(16, 2),
        help='Quantity of input applied (water m³, fertilizer kg, etc.).',
    )
    unit = fields.Char(string='Unit', help='Unit of quantity (m³, kg, L, etc.)')
    result_notes = fields.Text(string='Result / Observation')

    # ── Notes ──────────────────────────────────────────────────────────────────

    notes = fields.Text(string='Notes')

    # ── Workflow ──────────────────────────────────────────────────────────────

    def action_start(self):
        self.write({'state': 'in_progress', 'actual_date': fields.Date.today()})

    def action_done(self):
        self.write({'state': 'done'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset(self):
        self.write({'state': 'planned'})
