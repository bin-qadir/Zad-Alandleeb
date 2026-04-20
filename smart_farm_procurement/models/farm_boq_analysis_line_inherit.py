from odoo import api, fields, models


class FarmBoqAnalysisLineProcurement(models.Model):
    """Procurement extension for BOQ Analysis Lines.

    Adds procurement classification, vendor/product selection, estimated vs
    actual cost tracking, and a procurement state machine to each analysis line.

    Flow:
        Analysis line (approved) → Generate RFQ → purchase.order.line created
        → actual costs pulled from PO receipts / vendor bills automatically.
    """

    _inherit = 'farm.boq.analysis.line'

    # ── Procurement classification ────────────────────────────────────────────
    procurement_type = fields.Selection(
        selection=[
            ('material',    'Material'),
            ('service',     'Service'),
            ('subcontract', 'Subcontract'),
            ('labour',      'Labour (Internal)'),
        ],
        string='Procurement Type',
        default='material',
        index=True,
    )

    # ── Supplier / product ────────────────────────────────────────────────────
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        domain="[('purchase_ok', '=', True)]",
        ondelete='set null',
    )
    vendor_id = fields.Many2one(
        'res.partner',
        string='Preferred Vendor',
        domain="[('supplier_rank', '>', 0)]",
        ondelete='set null',
    )
    purchase_uom_id = fields.Many2one(
        'uom.uom',
        string='Purchase UoM',
        ondelete='set null',
    )

    # ── Estimated cost (independent of sale pricing in parent model) ──────────
    estimated_qty = fields.Float(
        string='Est. Qty',
        digits=(16, 2),
        help='Estimated purchase quantity (defaults to BOQ qty on creation).',
    )
    estimated_unit_cost = fields.Float(
        string='Est. Unit Cost',
        digits=(16, 4),
        help='Estimated unit purchase cost (defaults to cost_unit_price).',
    )
    estimated_total_cost = fields.Float(
        string='Est. Total Cost',
        compute='_compute_procurement_costs',
        store=True,
        digits=(16, 2),
    )

    # ── Actual cost — sourced from PO or vendor bill ──────────────────────────
    purchase_order_line_id = fields.Many2one(
        'purchase.order.line',
        string='PO Line',
        ondelete='set null',
        copy=False,
        index=True,
    )
    purchase_order_id = fields.Many2one(
        'purchase.order',
        string='Purchase Order',
        related='purchase_order_line_id.order_id',
        store=True,
        readonly=True,
    )
    vendor_bill_line_id = fields.Many2one(
        'account.move.line',
        string='Vendor Bill Line',
        ondelete='set null',
        copy=False,
        index=True,
        domain="[('move_id.move_type', 'in', ['in_invoice', 'in_refund'])]",
    )

    actual_qty = fields.Float(
        string='Act. Qty',
        compute='_compute_procurement_costs',
        store=True,
        digits=(16, 2),
    )
    actual_unit_cost = fields.Float(
        string='Act. Unit Cost',
        compute='_compute_procurement_costs',
        store=True,
        digits=(16, 4),
    )
    actual_total_cost = fields.Float(
        string='Act. Total Cost',
        compute='_compute_procurement_costs',
        store=True,
        digits=(16, 2),
    )
    cost_variance = fields.Float(
        string='Variance',
        compute='_compute_procurement_costs',
        store=True,
        digits=(16, 2),
        help='Actual total cost minus estimated total cost.',
    )
    cost_variance_pct = fields.Float(
        string='Variance %',
        compute='_compute_procurement_costs',
        store=True,
        digits=(16, 2),
        help='(Actual - Estimated) / Estimated × 100.',
    )

    # ── Procurement state machine ─────────────────────────────────────────────
    procurement_state = fields.Selection(
        selection=[
            ('not_requested', 'Not Requested'),
            ('rfq_sent',      'RFQ Sent'),
            ('ordered',       'PO Confirmed'),
            ('received',      'Received'),
            ('billed',        'Billed'),
        ],
        string='Procurement Status',
        default='not_requested',
        copy=False,
        index=True,
    )

    # ────────────────────────────────────────────────────────────────────────
    # Compute
    # ────────────────────────────────────────────────────────────────────────

    @api.depends(
        'estimated_qty', 'estimated_unit_cost',
        'purchase_order_line_id',
        'purchase_order_line_id.qty_received',
        'purchase_order_line_id.price_unit',
        'vendor_bill_line_id',
        'vendor_bill_line_id.price_subtotal',
    )
    def _compute_procurement_costs(self):
        for rec in self:
            # ── Estimated ──────────────────────────────────────────────────
            est_qty  = rec.estimated_qty or 0.0
            est_unit = rec.estimated_unit_cost or 0.0
            rec.estimated_total_cost = est_qty * est_unit

            # ── Actual — prefer vendor bill if linked, else PO receipt ────
            if rec.vendor_bill_line_id:
                # Bill line provides the final invoiced amount
                rec.actual_qty       = rec.vendor_bill_line_id.quantity
                rec.actual_unit_cost = rec.vendor_bill_line_id.price_unit
                rec.actual_total_cost = rec.vendor_bill_line_id.price_subtotal
            elif rec.purchase_order_line_id:
                pol = rec.purchase_order_line_id
                rec.actual_qty        = pol.qty_received
                rec.actual_unit_cost  = pol.price_unit
                rec.actual_total_cost = pol.qty_received * pol.price_unit
            else:
                rec.actual_qty        = 0.0
                rec.actual_unit_cost  = 0.0
                rec.actual_total_cost = 0.0

            # ── Variance ───────────────────────────────────────────────────
            est_total = rec.estimated_total_cost
            act_total = rec.actual_total_cost
            rec.cost_variance     = act_total - est_total
            rec.cost_variance_pct = (
                (act_total - est_total) / est_total * 100.0
                if est_total else 0.0
            )

    # ────────────────────────────────────────────────────────────────────────
    # ORM: pre-fill estimated fields from analysis pricing on create
    # ────────────────────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Pre-fill estimated fields with BOQ data when not explicitly set
            if not vals.get('estimated_qty') and vals.get('boq_qty'):
                vals['estimated_qty'] = vals['boq_qty']
            if not vals.get('estimated_unit_cost') and vals.get('cost_unit_price'):
                vals['estimated_unit_cost'] = vals['cost_unit_price']
        return super().create(vals_list)
