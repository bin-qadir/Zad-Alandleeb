from odoo import api, fields, models, _


class LivestockFeedingPlan(models.Model):
    """Feeding plan — nutritional program for a herd over a period."""

    _name = 'livestock.feeding.plan'
    _description = 'Livestock Feeding Plan'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'start_date desc, name'
    _rec_name = 'name'

    name = fields.Char(string='Plan Name', required=True, tracking=True)

    # ── Context ───────────────────────────────────────────────────────────────

    company_id = fields.Many2one(
        comodel_name='res.company',
        related='herd_id.company_id',
        store=True,
        readonly=True,
    )
    herd_id = fields.Many2one(
        comodel_name='livestock.herd',
        string='Herd',
        required=True,
        ondelete='cascade',
        tracking=True,
    )

    # ── Feed Details ──────────────────────────────────────────────────────────

    start_date = fields.Date(string='Start Date', tracking=True)
    end_date = fields.Date(string='End Date', tracking=True)
    feed_type = fields.Char(string='Feed Type / Mix')
    feed_source_id = fields.Many2one(
        comodel_name='res.partner',
        string='Feed Supplier',
        ondelete='set null',
    )

    daily_qty_per_animal_kg = fields.Float(
        string='Daily Qty per Animal (kg)',
        digits=(8, 3),
    )
    total_animals = fields.Integer(
        string='Animals in Plan',
        related='herd_id.total_animals',
        readonly=True,
    )
    daily_total_kg = fields.Float(
        string='Daily Total (kg)',
        compute='_compute_daily_total',
        store=True,
        digits=(10, 2),
    )

    # ── Cost ──────────────────────────────────────────────────────────────────

    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='company_id.currency_id',
        store=True,
        readonly=True,
    )
    cost_per_kg = fields.Monetary(string='Cost per kg', currency_field='currency_id')
    estimated_total_cost = fields.Monetary(
        string='Estimated Total Cost',
        compute='_compute_estimated_cost',
        store=True,
        currency_field='currency_id',
    )

    # ── State ─────────────────────────────────────────────────────────────────

    state = fields.Selection(
        selection=[
            ('draft',    'Draft'),
            ('active',   'Active'),
            ('done',     'Completed'),
            ('cancelled','Cancelled'),
        ],
        default='draft',
        required=True,
        tracking=True,
    )
    notes = fields.Text(string='Notes')

    # ── Compute ───────────────────────────────────────────────────────────────

    @api.depends('daily_qty_per_animal_kg', 'total_animals')
    def _compute_daily_total(self):
        for rec in self:
            rec.daily_total_kg = rec.daily_qty_per_animal_kg * rec.total_animals

    @api.depends('daily_total_kg', 'cost_per_kg', 'start_date', 'end_date')
    def _compute_estimated_cost(self):
        for rec in self:
            if rec.start_date and rec.end_date:
                days = (rec.end_date - rec.start_date).days + 1
            else:
                days = 0
            rec.estimated_total_cost = rec.daily_total_kg * rec.cost_per_kg * days

    # ── Workflow ──────────────────────────────────────────────────────────────

    def action_activate(self):
        self.write({'state': 'active'})

    def action_complete(self):
        self.write({'state': 'done'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset_draft(self):
        self.write({'state': 'draft'})
