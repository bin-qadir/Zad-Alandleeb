from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class FarmMaterialRequestLine(models.Model):
    """One line of a Material Request.

    Contract qty context:
        contract_qty          = BOQ line boq_qty (the full planned quantity)
        previously_requested  = Σ requested_qty on all other approved/ordered/received
                                 MR lines for the same boq_line_id
        remaining_qty         = contract_qty − previously_requested
        requested_qty         ≤ remaining_qty  (validation enforced on save)

    Cost tracking:
        estimated_cost  = requested_qty × unit_cost
        actual_cost     = received_qty  × unit_cost  (updated from PO receipt)
    """

    _name        = 'farm.material.request.line'
    _description = 'Material Request Line'
    _order       = 'sequence, id'

    # ── Parent ────────────────────────────────────────────────────────────────
    request_id = fields.Many2one(
        'farm.material.request',
        string='Material Request',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sequence = fields.Integer(string='Sequence', default=10)

    # ── Product ───────────────────────────────────────────────────────────────
    product_id = fields.Many2one(
        'product.product',
        string='Product / Material',
        required=True,
        domain="[('purchase_ok', '=', True)]",
        index=True,
    )
    product_description = fields.Char(string='Description')
    uom_id = fields.Many2one(
        'uom.uom',
        string='Unit',
        domain="[('category_id', '=', product_uom_category_id)]",
    )
    product_uom_category_id = fields.Many2one(
        related='product_id.uom_id.category_id',
        string='UoM Category',
    )

    # ── BOQ context ───────────────────────────────────────────────────────────
    boq_line_id = fields.Many2one(
        'farm.boq.line',
        string='BOQ Subitem',
        ondelete='set null',
        index=True,
        domain="[('boq_id.project_id', '=', parent.project_id),"
               " ('display_type', '=', False)]",
        help='Link to BOQ line for contract-qty validation and cost traceability.',
    )
    contract_qty = fields.Float(
        string='BOQ Contract Qty',
        compute='_compute_contract_qty',
        store=True,
        digits=(16, 3),
        help='Planned quantity from the linked BOQ line.',
    )
    previously_requested_qty = fields.Float(
        string='Previously Requested',
        compute='_compute_previously_requested',
        digits=(16, 3),
        help='Total qty already requested (approved/ordered/received) on '
             'other MR lines for the same BOQ line.',
    )
    remaining_qty = fields.Float(
        string='Remaining Qty',
        compute='_compute_previously_requested',
        digits=(16, 3),
        help='contract_qty − previously_requested_qty. '
             'requested_qty must not exceed this.',
    )

    # ── Quantities ────────────────────────────────────────────────────────────
    requested_qty = fields.Float(
        string='Requested Qty',
        required=True,
        digits=(16, 3),
        default=1.0,
    )
    received_qty = fields.Float(
        string='Received Qty',
        digits=(16, 3),
        default=0.0,
        copy=False,
        help='Updated automatically when the linked PO line is received.',
    )

    # ── Cost ──────────────────────────────────────────────────────────────────
    unit_cost = fields.Float(
        string='Unit Cost',
        digits=(16, 4),
        help='Estimated unit purchase cost. Defaults from product standard price.',
    )
    estimated_cost = fields.Float(
        string='Estimated Cost',
        compute='_compute_costs',
        store=True,
        digits=(16, 2),
    )
    actual_cost = fields.Float(
        string='Actual Cost',
        compute='_compute_costs',
        store=True,
        digits=(16, 2),
        help='received_qty × unit_cost (synced from PO receipt).',
    )

    # ── Vendor ────────────────────────────────────────────────────────────────
    vendor_id = fields.Many2one(
        'res.partner',
        string='Preferred Vendor',
        domain="[('supplier_rank', '>', 0)]",
        help='Vendor for this line; POs are grouped by vendor.',
    )

    # ── PO link (set after approval) ──────────────────────────────────────────
    purchase_order_line_id = fields.Many2one(
        'purchase.order.line',
        string='PO Line',
        readonly=True,
        copy=False,
        ondelete='set null',
        index=True,
    )
    purchase_order_id = fields.Many2one(
        'purchase.order',
        string='Purchase Order',
        related='purchase_order_line_id.order_id',
        readonly=True,
        store=True,
    )

    # ────────────────────────────────────────────────────────────────────────
    # Onchange helpers
    # ────────────────────────────────────────────────────────────────────────

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.uom_id       = self.product_id.uom_po_id or self.product_id.uom_id
            self.unit_cost    = self.product_id.standard_price
            if not self.product_description:
                self.product_description = self.product_id.display_name
            # Suggest vendor from product supplierinfo
            supplier = self.product_id.seller_ids[:1]
            if supplier and not self.vendor_id:
                self.vendor_id = supplier.partner_id

    @api.onchange('boq_line_id')
    def _onchange_boq_line_id(self):
        if self.boq_line_id and not self.requested_qty:
            # Suggest the full contract qty as default
            self.requested_qty = self.boq_line_id.boq_qty

    # ────────────────────────────────────────────────────────────────────────
    # Computed
    # ────────────────────────────────────────────────────────────────────────

    @api.depends('boq_line_id', 'boq_line_id.boq_qty')
    def _compute_contract_qty(self):
        for line in self:
            line.contract_qty = line.boq_line_id.boq_qty if line.boq_line_id else 0.0

    @api.depends(
        'boq_line_id',
        'request_id.state',
    )
    def _compute_previously_requested(self):
        """Sum qty from OTHER approved/ordered/received MR lines for same BOQ line."""
        for line in self:
            if not line.boq_line_id:
                line.previously_requested_qty = 0.0
                line.remaining_qty = 0.0
                continue
            domain = [
                ('boq_line_id', '=', line.boq_line_id.id),
                ('request_id.state', 'in', ('approved', 'rfq', 'ordered', 'received')),
            ]
            if line.id:
                domain.append(('id', '!=', line.id))
            other_lines = self.env['farm.material.request.line'].search(domain)
            prev = sum(other_lines.mapped('requested_qty'))
            contract = line.contract_qty
            line.previously_requested_qty = prev
            line.remaining_qty = max(0.0, contract - prev) if contract else 0.0

    @api.depends('requested_qty', 'received_qty', 'unit_cost')
    def _compute_costs(self):
        for line in self:
            line.estimated_cost = line.requested_qty * line.unit_cost
            line.actual_cost    = line.received_qty  * line.unit_cost

    # ────────────────────────────────────────────────────────────────────────
    # Validation
    # ────────────────────────────────────────────────────────────────────────

    @api.constrains('requested_qty', 'boq_line_id')
    def _check_requested_qty(self):
        """Block saving if requested_qty exceeds remaining_qty on the BOQ line."""
        for line in self:
            if not line.boq_line_id:
                continue
            if line.contract_qty <= 0:
                continue   # No contract qty set — allow freely
            # Compute remaining including this line
            other_domain = [
                ('boq_line_id', '=', line.boq_line_id.id),
                ('request_id.state', 'in', ('approved', 'rfq', 'ordered', 'received')),
                ('id', '!=', line.id),
            ]
            prev = sum(
                self.env['farm.material.request.line']
                .search(other_domain)
                .mapped('requested_qty')
            )
            remaining = max(0.0, line.contract_qty - prev)
            if line.requested_qty > remaining + 1e-9:
                raise ValidationError(_(
                    'Line "%(prod)s": requested qty %(req).3f exceeds remaining '
                    'BOQ quantity %(rem).3f (contract: %(ctr).3f, already requested: %(prev).3f).\n'
                    'Reduce the requested qty or review the BOQ.',
                    prod=line.product_id.display_name,
                    req=line.requested_qty,
                    rem=remaining,
                    ctr=line.contract_qty,
                    prev=prev,
                ))
