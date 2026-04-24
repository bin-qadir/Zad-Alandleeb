from odoo import api, fields, models, _


class ManufacturingDispatch(models.Model):
    """Dispatch order — finished goods shipment from manufacturing."""

    _name = 'manufacturing.dispatch'
    _description = 'Manufacturing Dispatch Order'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'dispatch_date desc, name'
    _rec_name = 'name'

    name = fields.Char(string='Dispatch Reference', required=True, tracking=True)

    # ── Context ───────────────────────────────────────────────────────────────

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
    )
    plan_id = fields.Many2one(
        comodel_name='manufacturing.plan',
        string='Production Plan',
        ondelete='set null',
        tracking=True,
    )

    # ── Customer ──────────────────────────────────────────────────────────────

    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Customer',
        ondelete='set null',
        tracking=True,
    )
    destination = fields.Char(string='Destination')

    # ── Goods ─────────────────────────────────────────────────────────────────

    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Finished Product',
        ondelete='set null',
        tracking=True,
    )
    quantity = fields.Float(string='Quantity', digits=(16, 2), tracking=True)
    uom_id = fields.Many2one(comodel_name='uom.uom', string='Unit', ondelete='set null')
    lot_number = fields.Char(string='Lot / Batch Number')

    # ── Schedule ──────────────────────────────────────────────────────────────

    dispatch_date = fields.Date(string='Dispatch Date', tracking=True)
    delivery_date = fields.Date(string='Expected Delivery', tracking=True)

    # ── State ─────────────────────────────────────────────────────────────────

    state = fields.Selection(
        selection=[
            ('draft',      'Draft'),
            ('confirmed',  'Confirmed'),
            ('dispatched', 'Dispatched'),
            ('delivered',  'Delivered'),
            ('cancelled',  'Cancelled'),
        ],
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
        compute='_compute_total',
        store=True,
        currency_field='currency_id',
    )

    notes = fields.Text(string='Notes')

    # ── Compute ───────────────────────────────────────────────────────────────

    @api.depends('quantity', 'unit_price')
    def _compute_total(self):
        for rec in self:
            rec.total_amount = rec.quantity * rec.unit_price

    # ── Workflow ──────────────────────────────────────────────────────────────

    def action_confirm(self):
        self.write({'state': 'confirmed'})

    def action_dispatch(self):
        self.write({
            'state': 'dispatched',
            'dispatch_date': self.dispatch_date or fields.Date.today(),
        })

    def action_deliver(self):
        self.write({'state': 'delivered'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset_draft(self):
        self.write({'state': 'draft'})

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'manufacturing.dispatch') or '/'
        return super().create(vals_list)
