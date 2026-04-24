from odoo import api, fields, models, _


class AgriculturePacking(models.Model):
    """Packing & Dispatch record — tracks packaging and shipment of harvested produce."""

    _name = 'agriculture.packing'
    _description = 'Agriculture Packing & Dispatch'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'packing_date desc, name'
    _rec_name = 'name'

    name = fields.Char(string='Packing Reference', required=True, tracking=True)

    # ── Context ───────────────────────────────────────────────────────────────

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        related='harvest_id.company_id',
        store=True,
        readonly=True,
    )
    harvest_id = fields.Many2one(
        comodel_name='agriculture.harvest',
        string='Harvest',
        required=True,
        ondelete='cascade',
        tracking=True,
    )
    season_id = fields.Many2one(
        comodel_name='agriculture.season',
        string='Season',
        related='harvest_id.season_id',
        store=True,
        readonly=True,
    )

    # ── Packing Details ───────────────────────────────────────────────────────

    packing_date = fields.Date(string='Packing Date', tracking=True)
    dispatch_date = fields.Date(string='Dispatch Date', tracking=True)

    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Product',
        ondelete='set null',
        tracking=True,
        domain=[('type', 'in', ['consu', 'product'])],
    )
    quantity = fields.Float(string='Quantity', digits=(16, 2), tracking=True)
    uom_id = fields.Many2one(
        comodel_name='uom.uom',
        string='Unit of Measure',
        ondelete='set null',
    )
    weight_net_kg = fields.Float(string='Net Weight (kg)', digits=(16, 2))
    boxes_count = fields.Integer(string='Number of Boxes / Units')
    weight_per_box_kg = fields.Float(
        string='Weight per Box (kg)',
        compute='_compute_weight_per_box',
        store=True,
        digits=(16, 4),
    )

    # ── Customer / Destination ────────────────────────────────────────────────

    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Customer / Buyer',
        ondelete='set null',
        tracking=True,
    )
    destination = fields.Char(string='Destination')

    # ── State ─────────────────────────────────────────────────────────────────

    state = fields.Selection(
        selection=[
            ('draft',      'Draft'),
            ('packing',    'In Packing'),
            ('packed',     'Packed'),
            ('dispatched', 'Dispatched'),
            ('delivered',  'Delivered'),
        ],
        string='State',
        default='draft',
        required=True,
        tracking=True,
    )

    # ── Financials ────────────────────────────────────────────────────────────

    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='company_id.currency_id',
        store=True,
        readonly=True,
    )
    unit_price = fields.Monetary(string='Unit Price', currency_field='currency_id')
    total_amount = fields.Monetary(
        string='Total Amount',
        compute='_compute_total_amount',
        store=True,
        currency_field='currency_id',
    )

    notes = fields.Text(string='Notes')

    # ── Compute ───────────────────────────────────────────────────────────────

    @api.depends('weight_net_kg', 'boxes_count')
    def _compute_weight_per_box(self):
        for rec in self:
            if rec.boxes_count:
                rec.weight_per_box_kg = rec.weight_net_kg / rec.boxes_count
            else:
                rec.weight_per_box_kg = 0.0

    @api.depends('quantity', 'unit_price')
    def _compute_total_amount(self):
        for rec in self:
            rec.total_amount = rec.quantity * rec.unit_price

    # ── Workflow ──────────────────────────────────────────────────────────────

    def action_start_packing(self):
        self.write({'state': 'packing'})

    def action_mark_packed(self):
        self.write({'state': 'packed'})

    def action_dispatch(self):
        self.write({
            'state': 'dispatched',
            'dispatch_date': self.dispatch_date or fields.Date.today(),
        })

    def action_deliver(self):
        self.write({'state': 'delivered'})

    def action_reset_draft(self):
        self.write({'state': 'draft'})
