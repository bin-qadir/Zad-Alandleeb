from odoo import api, fields, models, _


QUALITY_SELECTION = [
    ('excellent', 'Excellent'),
    ('good',      'Good'),
    ('fair',      'Fair'),
    ('poor',      'Poor'),
]


class AgricultureHarvest(models.Model):
    """Harvest record — captures yield quantity and quality for a crop plan."""

    _name = 'agriculture.harvest'
    _description = 'Agriculture Harvest Record'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'harvest_date desc, name'
    _rec_name = 'name'

    name = fields.Char(string='Harvest Reference', required=True, tracking=True)

    # ── Context ───────────────────────────────────────────────────────────────

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        related='crop_plan_id.company_id',
        store=True,
        readonly=True,
    )
    crop_plan_id = fields.Many2one(
        comodel_name='agriculture.crop.plan',
        string='Crop Plan',
        required=True,
        ondelete='cascade',
        tracking=True,
    )
    season_id = fields.Many2one(
        comodel_name='agriculture.season',
        string='Season',
        related='crop_plan_id.season_id',
        store=True,
        readonly=True,
    )
    farm_field_id = fields.Many2one(
        comodel_name='farm.field',
        string='Farm Field',
        related='crop_plan_id.farm_field_id',
        store=True,
        readonly=True,
    )

    # ── Harvest Data ──────────────────────────────────────────────────────────

    harvest_date = fields.Date(string='Harvest Date', required=True, tracking=True)
    quantity_kg = fields.Float(
        string='Quantity (kg)',
        required=True,
        digits=(16, 2),
        tracking=True,
    )
    quality = fields.Selection(
        selection=QUALITY_SELECTION,
        string='Quality Grade',
        default='good',
        required=True,
        tracking=True,
    )
    moisture_pct = fields.Float(string='Moisture %', digits=(5, 2))
    rejection_kg = fields.Float(string='Rejected (kg)', digits=(16, 2), default=0.0)
    net_quantity_kg = fields.Float(
        string='Net Quantity (kg)',
        compute='_compute_net_quantity',
        store=True,
        digits=(16, 2),
    )

    # ── State ─────────────────────────────────────────────────────────────────

    state = fields.Selection(
        selection=[
            ('draft',     'Draft'),
            ('confirmed', 'Confirmed'),
            ('packed',    'Packed'),
            ('dispatched','Dispatched'),
        ],
        string='State',
        default='draft',
        required=True,
        tracking=True,
    )

    # ── Responsible ───────────────────────────────────────────────────────────

    harvested_by_id = fields.Many2one(
        comodel_name='res.users',
        string='Harvested By',
    )
    supervisor_id = fields.Many2one(
        comodel_name='res.users',
        string='Supervisor',
    )

    # ── AI Decision Layer ─────────────────────────────────────────────────────

    risk_score = fields.Float(string='Risk Score', default=0.0, digits=(5, 1))
    next_recommended_action = fields.Text(string='Next Recommended Action')

    # ── Children ──────────────────────────────────────────────────────────────

    packing_ids = fields.One2many(
        comodel_name='agriculture.packing',
        inverse_name='harvest_id',
        string='Packing Orders',
    )
    packing_count = fields.Integer(compute='_compute_packing_count', store=False)

    notes = fields.Text(string='Notes')

    # ── Compute ───────────────────────────────────────────────────────────────

    @api.depends('quantity_kg', 'rejection_kg')
    def _compute_net_quantity(self):
        for rec in self:
            rec.net_quantity_kg = rec.quantity_kg - rec.rejection_kg

    @api.depends('packing_ids')
    def _compute_packing_count(self):
        for rec in self:
            rec.packing_count = len(rec.packing_ids)

    # ── Workflow ──────────────────────────────────────────────────────────────

    def action_confirm(self):
        self.write({'state': 'confirmed'})

    def action_mark_packed(self):
        self.write({'state': 'packed'})

    def action_dispatch(self):
        self.write({'state': 'dispatched'})

    def action_reset_draft(self):
        self.write({'state': 'draft'})

    # ── Smart Button ──────────────────────────────────────────────────────────

    def action_view_packing(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Packing Orders'),
            'res_model': 'agriculture.packing',
            'view_mode': 'list,form',
            'domain': [('harvest_id', '=', self.id)],
            'context': {'default_harvest_id': self.id},
        }
