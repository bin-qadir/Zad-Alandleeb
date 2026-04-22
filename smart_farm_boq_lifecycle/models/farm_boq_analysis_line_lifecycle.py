from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class FarmBoqAnalysisLineLifecycle(models.Model):
    """Lifecycle tracking extension for BOQ Analysis Lines.

    Extends farm.boq.analysis.line with 4 lifecycle groups:

      Group 1 — Contract   : item_name, contract_qty, unit_sales_price, total_sales_price
      Group 2 — Procurement: requested_qty, vendor_qty (RFQ), po_qty, vendor_bill_qty
      Group 3 — Inspection : inspected_qty (executed), approved_qty
      Group 4 — Claims     : claimed_qty, invoiced_qty, remaining_qty, extra_qty

    Lifecycle fields are only meaningful on subitem rows (display_type=False).
    Structural section rows are silently skipped in all computes.
    """

    _inherit = 'farm.boq.analysis.line'

    # ── Reverse link to Job Orders ────────────────────────────────────────────

    job_order_ids = fields.One2many(
        'farm.job.order',
        'analysis_line_id',
        string='Job Orders',
        readonly=True,
    )

    # ═════════════════════════════════════════════════════════════════════════
    # GROUP 1 — Contract
    # ═════════════════════════════════════════════════════════════════════════

    # item_name   → existing 'name'
    # contract_qty → existing 'boq_qty'

    unit_sales_price = fields.Float(
        string='Contract Unit Price',
        related='boq_line_id.unit_price',
        store=False,
        digits=(16, 2),
        help='Unit price from the approved BOQ contract (boq_line.unit_price).',
    )
    total_sales_price = fields.Float(
        string='Contract Total',
        compute='_compute_lc_contract',
        store=False,
        digits=(16, 2),
        help='contract_qty × unit_sales_price',
    )

    # ═════════════════════════════════════════════════════════════════════════
    # GROUP 2 — Procurement
    # ═════════════════════════════════════════════════════════════════════════

    lc_requested_qty = fields.Float(
        string='Requested Qty',
        compute='_compute_lc_requested',
        store=False,
        digits=(16, 2),
        help='Sum of requested_qty from all active Material Request lines '
             'linked to the same BOQ line (states: to_approve/approved/rfq/ordered/received).',
    )
    lc_vendor_qty = fields.Float(
        string='RFQ Qty',
        compute='_compute_lc_po',
        store=False,
        digits=(16, 2),
        help='Quantity on draft / sent RFQs linked to this analysis line.',
    )
    lc_po_qty = fields.Float(
        string='PO Qty',
        compute='_compute_lc_po',
        store=False,
        digits=(16, 2),
        help='Quantity on confirmed Purchase Orders linked to this analysis line.',
    )
    lc_vendor_bill_qty = fields.Float(
        string='Billed Qty',
        compute='_compute_lc_po',
        store=False,
        digits=(16, 2),
        help='Quantity on posted vendor bills linked to this analysis line.',
    )

    # ═════════════════════════════════════════════════════════════════════════
    # GROUP 3 — Inspection
    # ═════════════════════════════════════════════════════════════════════════

    lc_inspected_qty = fields.Float(
        string='Inspected Qty',
        compute='_compute_lc_inspection',
        store=False,
        digits=(16, 2),
        help='Sum of executed_qty from Job Orders linked to this analysis line.',
    )
    lc_approved_qty = fields.Float(
        string='Approved Qty',
        compute='_compute_lc_inspection',
        store=False,
        digits=(16, 2),
        help='Sum of approved_qty from Job Orders linked to this analysis line.',
    )

    # ═════════════════════════════════════════════════════════════════════════
    # GROUP 4 — Claims & Invoicing
    # ═════════════════════════════════════════════════════════════════════════

    lc_claimed_qty = fields.Float(
        string='Claimed Qty',
        compute='_compute_lc_claims',
        store=False,
        digits=(16, 2),
        help='Sum of claimed_qty from Job Orders linked to this analysis line.',
    )
    lc_invoiced_qty = fields.Float(
        string='Invoiced Qty',
        digits=(16, 2),
        default=0.0,
        help='Quantity invoiced to the client.  Enter manually or use Claimed Qty as proxy.',
    )
    lc_remaining_qty = fields.Float(
        string='Remaining (to Invoice)',
        compute='_compute_lc_claims',
        store=False,
        digits=(16, 2),
        help='approved_qty − invoiced_qty (how much can still be invoiced).',
    )
    lc_extra_qty = fields.Float(
        string='Extra / Variation Qty',
        compute='_compute_lc_claims',
        store=False,
        digits=(16, 2),
        help='approved_qty − contract_qty (positive = variation order quantity).',
    )
    lc_has_variation = fields.Boolean(
        string='Has Variation',
        compute='_compute_lc_claims',
        store=False,
        help='True when approved_qty exceeds the original contract_qty.',
    )

    # ═════════════════════════════════════════════════════════════════════════
    # Computes
    # ═════════════════════════════════════════════════════════════════════════

    @api.depends('boq_qty', 'boq_line_id', 'boq_line_id.unit_price')
    def _compute_lc_contract(self):
        for rec in self:
            if rec.display_type:
                rec.total_sales_price = 0.0
                continue
            unit_price = rec.boq_line_id.unit_price if rec.boq_line_id else rec.sale_unit_price
            rec.total_sales_price = (rec.boq_qty or 0.0) * (unit_price or 0.0)

    @api.depends('boq_line_id')
    def _compute_lc_requested(self):
        """Sum requested quantities from Material Request lines sharing the same BOQ line."""
        MRLine = self.env['farm.material.request.line']
        for rec in self:
            if rec.display_type or not rec.boq_line_id:
                rec.lc_requested_qty = 0.0
                continue
            mr_lines = MRLine.search([
                ('boq_line_id', '=', rec.boq_line_id.id),
                ('request_id.state', 'in', ('to_approve', 'approved', 'rfq', 'ordered', 'received')),
            ])
            rec.lc_requested_qty = sum(mr_lines.mapped('requested_qty'))

    @api.depends(
        'purchase_order_line_id',
        'purchase_order_line_id.product_qty',
        'purchase_order_line_id.order_id.state',
        'vendor_bill_line_id',
        'vendor_bill_line_id.quantity',
        'vendor_bill_line_id.move_id.state',
    )
    def _compute_lc_po(self):
        for rec in self:
            if rec.display_type:
                rec.lc_vendor_qty = 0.0
                rec.lc_po_qty = 0.0
                rec.lc_vendor_bill_qty = 0.0
                continue

            # RFQ / PO qty
            pol = rec.purchase_order_line_id
            if pol:
                po_state = pol.order_id.state
                if po_state in ('draft', 'sent'):
                    rec.lc_vendor_qty = pol.product_qty
                    rec.lc_po_qty = 0.0
                elif po_state in ('purchase', 'done', 'to approve'):
                    rec.lc_vendor_qty = 0.0
                    rec.lc_po_qty = pol.product_qty
                else:
                    rec.lc_vendor_qty = 0.0
                    rec.lc_po_qty = 0.0
            else:
                rec.lc_vendor_qty = 0.0
                rec.lc_po_qty = 0.0

            # Vendor bill qty (posted bills only)
            vbl = rec.vendor_bill_line_id
            if vbl and vbl.move_id.state == 'posted':
                rec.lc_vendor_bill_qty = vbl.quantity
            else:
                rec.lc_vendor_bill_qty = 0.0

    @api.depends(
        'job_order_ids',
        'job_order_ids.executed_qty',
        'job_order_ids.approved_qty',
    )
    def _compute_lc_inspection(self):
        for rec in self:
            if rec.display_type:
                rec.lc_inspected_qty = 0.0
                rec.lc_approved_qty = 0.0
                continue
            jos = rec.job_order_ids
            rec.lc_inspected_qty = sum(jos.mapped('executed_qty'))
            rec.lc_approved_qty = sum(jos.mapped('approved_qty'))

    @api.depends(
        'job_order_ids',
        'job_order_ids.claimed_qty',
        'job_order_ids.approved_qty',
        'lc_invoiced_qty',
        'boq_qty',
    )
    def _compute_lc_claims(self):
        for rec in self:
            if rec.display_type:
                rec.lc_claimed_qty = 0.0
                rec.lc_remaining_qty = 0.0
                rec.lc_extra_qty = 0.0
                rec.lc_has_variation = False
                continue
            jos = rec.job_order_ids
            claimed = sum(jos.mapped('claimed_qty'))
            approved = sum(jos.mapped('approved_qty'))
            invoiced = rec.lc_invoiced_qty or 0.0
            contract = rec.boq_qty or 0.0

            rec.lc_claimed_qty = claimed
            rec.lc_remaining_qty = max(0.0, approved - invoiced)
            rec.lc_extra_qty = approved - contract
            rec.lc_has_variation = approved > contract + 1e-9

    # ═════════════════════════════════════════════════════════════════════════
    # Constraints
    # ═════════════════════════════════════════════════════════════════════════

    @api.constrains('lc_invoiced_qty')
    def _check_invoiced_qty(self):
        """invoiced_qty must not exceed approved_qty."""
        for rec in self:
            if rec.display_type:
                continue
            approved = sum(rec.job_order_ids.mapped('approved_qty'))
            if rec.lc_invoiced_qty > approved + 1e-9:
                raise ValidationError(_(
                    'Invoiced Qty (%(inv)s) cannot exceed Approved Qty (%(app)s) '
                    'on BOQ line "%(name)s".',
                    inv=rec.lc_invoiced_qty,
                    app=approved,
                    name=rec.name,
                ))
