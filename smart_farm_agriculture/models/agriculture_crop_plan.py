from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class AgricultureCropPlan(models.Model):
    """Crop plan — defines what to grow in a specific field during a season."""

    _name = 'agriculture.crop.plan'
    _description = 'Agriculture Crop Plan'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'season_id, name'
    _rec_name = 'name'

    name = fields.Char(string='Plan Name', required=True, tracking=True)

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
    farm_field_id = fields.Many2one(
        comodel_name='farm.field',
        string='Farm Field',
        ondelete='set null',
        tracking=True,
    )

    # ── Crop ──────────────────────────────────────────────────────────────────

    crop_type_id = fields.Many2one(
        comodel_name='farm.crop.type',
        string='Crop Type',
        ondelete='set null',
        tracking=True,
    )
    variety = fields.Char(string='Variety / Cultivar')
    planned_area_m2 = fields.Float(string='Planned Area (m²)', digits=(16, 2))
    actual_area_m2 = fields.Float(string='Actual Area (m²)', digits=(16, 2))

    # ── Schedule ──────────────────────────────────────────────────────────────

    planting_date = fields.Date(string='Planting Date', tracking=True)
    expected_harvest_date = fields.Date(string='Expected Harvest Date', tracking=True)
    actual_harvest_date = fields.Date(string='Actual Harvest Date', tracking=True)

    # ── Yield ─────────────────────────────────────────────────────────────────

    target_yield_kg = fields.Float(string='Target Yield (kg)', digits=(16, 2))
    actual_yield_kg = fields.Float(
        string='Actual Yield (kg)',
        compute='_compute_actual_yield',
        store=True,
        digits=(16, 2),
    )

    # ── State ─────────────────────────────────────────────────────────────────

    state = fields.Selection(
        selection=[
            ('draft',     'Draft'),
            ('planting',  'Planting'),
            ('growing',   'Growing'),
            ('harvest',   'Harvest'),
            ('done',      'Completed'),
            ('cancelled', 'Cancelled'),
        ],
        string='State',
        default='draft',
        required=True,
        tracking=True,
    )
    responsible_id = fields.Many2one(
        comodel_name='res.users',
        string='Responsible',
    )

    # ── AI Decision Layer ─────────────────────────────────────────────────────

    risk_score = fields.Float(string='Risk Score', default=0.0, digits=(5, 1))
    delay_score = fields.Float(string='Delay Score', default=0.0, digits=(5, 1))
    budget_risk = fields.Float(string='Budget Risk', default=0.0, digits=(5, 1))
    next_recommended_action = fields.Text(string='Next Recommended Action')

    # ── Children ──────────────────────────────────────────────────────────────

    operation_ids = fields.One2many(
        comodel_name='agriculture.field.operation',
        inverse_name='crop_plan_id',
        string='Field Operations',
    )
    harvest_ids = fields.One2many(
        comodel_name='agriculture.harvest',
        inverse_name='crop_plan_id',
        string='Harvest Records',
    )
    operation_count = fields.Integer(compute='_compute_counts', store=False)
    harvest_count = fields.Integer(compute='_compute_counts', store=False)

    notes = fields.Text(string='Notes')

    # ── Compute ───────────────────────────────────────────────────────────────

    @api.depends('harvest_ids', 'harvest_ids.quantity_kg')
    def _compute_actual_yield(self):
        for rec in self:
            rec.actual_yield_kg = sum(rec.harvest_ids.mapped('quantity_kg'))

    @api.depends('operation_ids', 'harvest_ids')
    def _compute_counts(self):
        for rec in self:
            rec.operation_count = len(rec.operation_ids)
            rec.harvest_count = len(rec.harvest_ids)

    # ── Workflow ──────────────────────────────────────────────────────────────

    def action_start_planting(self):
        self.write({'state': 'planting'})

    def action_start_growing(self):
        self.write({'state': 'growing'})

    def action_start_harvest(self):
        self.write({'state': 'harvest'})

    def action_complete(self):
        self.write({'state': 'done'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset_draft(self):
        self.write({'state': 'draft'})

    def action_view_operations(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Field Operations'),
            'res_model': 'agriculture.field.operation',
            'view_mode': 'list,form',
            'domain': [('crop_plan_id', '=', self.id)],
            'context': {'default_crop_plan_id': self.id,
                        'default_season_id': self.season_id.id},
        }

    def action_view_harvests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Harvest Records'),
            'res_model': 'agriculture.harvest',
            'view_mode': 'list,form',
            'domain': [('crop_plan_id', '=', self.id)],
            'context': {'default_crop_plan_id': self.id},
        }
