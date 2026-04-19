from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class FarmMaterialConsumption(models.Model):
    """Material consumption record for a Job Order.

    Tracks four quantity stages:
      planned_qty   → what was estimated when the job was created
      requested_qty → what was formally requested from stores
      issued_qty    → what was physically issued from stock
      consumed_qty  → what was actually consumed on site

    actual_cost = consumed_qty × unit_cost
    """

    _name = 'farm.material.consumption'
    _description = 'Farm Material Consumption'
    _order = 'job_order_id, id'

    # ── Links ─────────────────────────────────────────────────────────────────
    job_order_id = fields.Many2one(
        'farm.job.order',
        string='Job Order',
        required=True,
        ondelete='cascade',
        index=True,
    )
    project_id = fields.Many2one(
        'farm.project',
        string='Project',
        related='job_order_id.project_id',
        store=True,
        readonly=True,
    )
    boq_id = fields.Many2one(
        'farm.boq',
        string='BOQ',
        related='job_order_id.boq_id',
        store=True,
        readonly=True,
    )
    boq_line_id = fields.Many2one(
        'farm.boq.line',
        string='BOQ Subitem',
        related='job_order_id.boq_line_id',
        store=True,
        readonly=True,
    )

    # ── Product ───────────────────────────────────────────────────────────────
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        ondelete='restrict',
        domain="[('type', 'in', ['consu', 'product'])]",
    )
    description = fields.Char(string='Description')
    uom_id = fields.Many2one(
        'uom.uom',
        string='Unit of Measure',
        ondelete='set null',
    )

    # ── Quantities ────────────────────────────────────────────────────────────
    planned_qty = fields.Float(
        string='Planned Qty',
        digits=(16, 2),
        default=1.0,
    )
    requested_qty = fields.Float(
        string='Requested Qty',
        digits=(16, 2),
        default=0.0,
        help='Quantity formally requested from the store/warehouse.',
    )
    issued_qty = fields.Float(
        string='Issued Qty',
        digits=(16, 2),
        default=0.0,
        help='Quantity physically issued from stock.',
    )
    consumed_qty = fields.Float(
        string='Consumed Qty',
        digits=(16, 2),
        default=0.0,
        help='Actual quantity consumed on site.',
    )

    # ── Costing ──────────────────────────────────────────────────────────────
    unit_cost = fields.Float(
        string='Unit Cost',
        digits=(16, 4),
        default=0.0,
    )
    planned_cost = fields.Float(
        string='Planned Cost',
        compute='_compute_costs',
        store=True,
        digits=(16, 2),
    )
    actual_cost = fields.Float(
        string='Actual Cost',
        compute='_compute_costs',
        store=True,
        digits=(16, 2),
        help='consumed_qty × unit_cost',
    )

    # ── Stock integration ─────────────────────────────────────────────────────
    stock_move_id = fields.Many2one(
        'stock.move',
        string='Stock Move',
        ondelete='set null',
        copy=False,
    )
    stock_picking_id = fields.Many2one(
        'stock.picking',
        string='Stock Transfer',
        ondelete='set null',
        copy=False,
        readonly=True,
    )
    source_location_id = fields.Many2one(
        'stock.location',
        string='Source Location',
        domain="[('usage', 'in', ['internal', 'supplier'])]",
        ondelete='set null',
    )
    dest_location_id = fields.Many2one(
        'stock.location',
        string='Destination Location',
        domain="[('usage', 'in', ['internal', 'production', 'customer'])]",
        ondelete='set null',
    )

    # ── Status ────────────────────────────────────────────────────────────────
    state = fields.Selection(
        selection=[
            ('draft',     'Draft'),
            ('requested', 'Requested'),
            ('issued',    'Issued'),
            ('consumed',  'Consumed'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        index=True,
        copy=False,
    )

    # ────────────────────────────────────────────────────────────────────────
    # Computed
    # ────────────────────────────────────────────────────────────────────────

    @api.depends('planned_qty', 'consumed_qty', 'unit_cost')
    def _compute_costs(self):
        for rec in self:
            rec.planned_cost = rec.planned_qty * rec.unit_cost
            rec.actual_cost  = rec.consumed_qty * rec.unit_cost

    # ────────────────────────────────────────────────────────────────────────
    # Validation
    # ────────────────────────────────────────────────────────────────────────

    @api.constrains('job_order_id')
    def _check_job_order(self):
        for rec in self:
            if not rec.job_order_id:
                raise ValidationError(
                    _('Material consumption requires a Job Order.')
                )

    # ────────────────────────────────────────────────────────────────────────
    # ORM
    # ────────────────────────────────────────────────────────────────────────

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.description = self.description or self.product_id.name
            self.uom_id = self.uom_id or self.product_id.uom_id
            self.unit_cost = self.product_id.standard_price or self.unit_cost

    # ────────────────────────────────────────────────────────────────────────
    # State actions
    # ────────────────────────────────────────────────────────────────────────

    def action_request(self):
        self.filtered(lambda r: r.state == 'draft').write({'state': 'requested'})

    def action_issue(self):
        self.filtered(lambda r: r.state in ('draft', 'requested')).write(
            {'state': 'issued'}
        )

    def action_consume(self):
        self.filtered(
            lambda r: r.state in ('draft', 'requested', 'issued')
        ).write({'state': 'consumed'})

    def action_cancel(self):
        self.filtered(
            lambda r: r.state not in ('consumed',)
        ).write({'state': 'cancelled'})

    def action_reset_draft(self):
        self.filtered(
            lambda r: r.state not in ('consumed', 'cancelled')
        ).write({'state': 'draft'})
