from odoo import api, fields, models

RECEIPT_STATUS = [
    ('not_received',       'Not Received'),
    ('partially_received', 'Partial'),
    ('fully_received',     'Fully Received'),
]

LINE_STATE = [
    ('draft',              'Draft'),
    ('rfq',                'RFQ Sent'),
    ('ordered',            'Ordered'),
    ('partially_received', 'Partially Received'),
    ('fully_received',     'Fully Received'),
    ('cancelled',          'Cancelled'),
]


class ConstructionProcurementLine(models.Model):
    _name = 'construction.procurement.line'
    _description = 'Construction Procurement Line'
    _order = 'sequence, id'

    # ── Parent ────────────────────────────────────────────────────────────────

    procurement_id = fields.Many2one(
        comodel_name='construction.procurement',
        string='Procurement',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sequence = fields.Integer(string='Seq', default=10)

    # ── Stored project/division context (for grouping) ────────────────────────

    project_id = fields.Many2one(
        comodel_name='construction.project',
        string='Project',
        related='procurement_id.project_id',
        store=True,
        readonly=True,
        index=True,
    )
    division_id = fields.Many2one(
        comodel_name='construction.division',
        string='Division',
        related='procurement_id.division_id',
        store=True,
        readonly=True,
        index=True,
    )

    # ── Traceability links ────────────────────────────────────────────────────

    material_request_line_id = fields.Many2one(
        comodel_name='construction.material.request.line',
        string='Request Line',
        ondelete='set null',
        index=True,
    )
    boq_line_id = fields.Many2one(
        comodel_name='construction.boq.line',
        string='BOQ Line',
        ondelete='set null',
        index=True,
    )
    material_plan_id = fields.Many2one(
        comodel_name='construction.material.plan',
        string='Material Plan',
        ondelete='set null',
        index=True,
    )

    # ── Product ───────────────────────────────────────────────────────────────

    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Product',
        required=True,
        ondelete='restrict',
        index=True,
    )
    description = fields.Char(string='Description')
    unit = fields.Char(string='Unit', size=20)

    # ── Quantities ────────────────────────────────────────────────────────────

    requested_qty = fields.Float(
        string='Requested',
        digits=(16, 4),
    )
    ordered_qty = fields.Float(
        string='Ordered',
        digits=(16, 4),
        default=1.0,
    )
    received_qty = fields.Float(
        string='Received',
        compute='_compute_received_qty',
        store=True,
        digits=(16, 4),
    )
    remaining_qty = fields.Float(
        string='Remaining',
        compute='_compute_remaining_qty',
        store=True,
        digits=(16, 4),
    )

    # ── Pricing ───────────────────────────────────────────────────────────────

    unit_price = fields.Float(
        string='Unit Price',
        digits=(16, 4),
    )
    total_price = fields.Float(
        string='Total Price',
        compute='_compute_total_price',
        store=True,
        digits=(16, 4),
    )

    # ── PO linkage ────────────────────────────────────────────────────────────

    purchase_order_line_id = fields.Many2one(
        comodel_name='purchase.order.line',
        string='PO Line',
        ondelete='set null',
        copy=False,
        index=True,
    )

    # ── State ─────────────────────────────────────────────────────────────────

    state = fields.Selection(
        selection=LINE_STATE,
        string='Status',
        default='draft',
        index=True,
    )
    receipt_status = fields.Selection(
        selection=RECEIPT_STATUS,
        string='Receipt',
        compute='_compute_receipt_status',
        store=True,
    )

    # ── Computes ──────────────────────────────────────────────────────────────

    @api.depends('purchase_order_line_id', 'purchase_order_line_id.qty_received')
    def _compute_received_qty(self):
        for rec in self:
            if rec.purchase_order_line_id:
                rec.received_qty = rec.purchase_order_line_id.qty_received
            else:
                rec.received_qty = 0.0

    @api.depends('ordered_qty', 'received_qty')
    def _compute_remaining_qty(self):
        for rec in self:
            rec.remaining_qty = max(0.0, rec.ordered_qty - rec.received_qty)

    @api.depends('ordered_qty', 'unit_price')
    def _compute_total_price(self):
        for rec in self:
            rec.total_price = rec.ordered_qty * rec.unit_price

    @api.depends('ordered_qty', 'received_qty')
    def _compute_receipt_status(self):
        for rec in self:
            if rec.received_qty <= 0:
                rec.receipt_status = 'not_received'
            elif rec.received_qty < rec.ordered_qty:
                rec.receipt_status = 'partially_received'
            else:
                rec.receipt_status = 'fully_received'

    # ── Onchange helpers ──────────────────────────────────────────────────────

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            if not self.description:
                self.description = self.product_id.display_name
            if self.product_id.uom_id:
                self.unit = self.product_id.uom_id.name
            if not self.unit_price and self.product_id.standard_price:
                self.unit_price = self.product_id.standard_price

    @api.onchange('material_request_line_id')
    def _onchange_request_line(self):
        """Pull product / qty / links from the source request line."""
        rl = self.material_request_line_id
        if not rl:
            return
        self.product_id = rl.product_id
        self.description = rl.description or rl.product_id.display_name
        self.unit = rl.unit
        self.requested_qty = rl.requested_qty
        self.ordered_qty = rl.requested_qty
        if rl.material_plan_id:
            self.material_plan_id = rl.material_plan_id
        if rl.boq_line_id:
            self.boq_line_id = rl.boq_line_id
