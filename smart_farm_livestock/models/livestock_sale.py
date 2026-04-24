from odoo import api, fields, models, _


class LivestockSale(models.Model):
    """Livestock sale — records the sale of animals from a herd."""

    _name = 'livestock.sale'
    _description = 'Livestock Sale'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sale_date desc, name'
    _rec_name = 'name'

    name = fields.Char(string='Sale Reference', required=True, tracking=True)

    # ── Context ───────────────────────────────────────────────────────────────

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
    )
    herd_id = fields.Many2one(
        comodel_name='livestock.herd',
        string='Herd',
        required=True,
        ondelete='restrict',
        tracking=True,
    )

    # ── Buyer ─────────────────────────────────────────────────────────────────

    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Buyer',
        ondelete='set null',
        tracking=True,
    )

    # ── Sale Details ──────────────────────────────────────────────────────────

    sale_date = fields.Date(string='Sale Date', required=True, default=fields.Date.today)
    animals_count = fields.Integer(string='Animals Sold', required=True, tracking=True)
    average_weight_kg = fields.Float(string='Average Weight (kg)', digits=(10, 2))
    total_weight_kg = fields.Float(
        string='Total Weight (kg)',
        compute='_compute_total_weight',
        store=True,
        digits=(10, 2),
    )

    # ── Financials ────────────────────────────────────────────────────────────

    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='company_id.currency_id',
        store=True,
        readonly=True,
    )
    price_per_kg = fields.Monetary(string='Price per kg', currency_field='currency_id')
    price_per_head = fields.Monetary(string='Price per Head', currency_field='currency_id')
    pricing_method = fields.Selection(
        selection=[
            ('per_kg',   'Per Kilogram'),
            ('per_head', 'Per Head'),
        ],
        string='Pricing Method',
        default='per_head',
        required=True,
    )
    total_amount = fields.Monetary(
        string='Total Amount',
        compute='_compute_total_amount',
        store=True,
        currency_field='currency_id',
        tracking=True,
    )

    # ── State ─────────────────────────────────────────────────────────────────

    state = fields.Selection(
        selection=[
            ('draft',     'Draft'),
            ('confirmed', 'Confirmed'),
            ('invoiced',  'Invoiced'),
            ('done',      'Done'),
            ('cancelled', 'Cancelled'),
        ],
        default='draft',
        required=True,
        tracking=True,
    )

    # ── AI Decision Layer ─────────────────────────────────────────────────────

    risk_score = fields.Float(string='Risk Score', default=0.0, digits=(5, 1))
    next_recommended_action = fields.Text(string='Next Recommended Action')

    notes = fields.Text(string='Notes')

    # ── Compute ───────────────────────────────────────────────────────────────

    @api.depends('animals_count', 'average_weight_kg')
    def _compute_total_weight(self):
        for rec in self:
            rec.total_weight_kg = rec.animals_count * rec.average_weight_kg

    @api.depends('pricing_method', 'total_weight_kg', 'price_per_kg',
                 'animals_count', 'price_per_head')
    def _compute_total_amount(self):
        for rec in self:
            if rec.pricing_method == 'per_kg':
                rec.total_amount = rec.total_weight_kg * rec.price_per_kg
            else:
                rec.total_amount = rec.animals_count * rec.price_per_head

    # ── Workflow ──────────────────────────────────────────────────────────────

    def action_confirm(self):
        self.write({'state': 'confirmed'})

    def action_invoice(self):
        self.write({'state': 'invoiced'})

    def action_done(self):
        self.write({'state': 'done'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset_draft(self):
        self.write({'state': 'draft'})

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'livestock.sale') or '/'
        return super().create(vals_list)
