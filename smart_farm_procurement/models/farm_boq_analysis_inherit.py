from odoo import api, fields, models, _
from odoo.exceptions import UserError


class FarmBoqAnalysisProcurement(models.Model):
    """Procurement extension for BOQ Analysis Documents.

    Adds:
    - purchase_count stat button
    - action_generate_rfq(): groups approved lines by vendor → creates POs
    - action_view_purchases(): opens related Purchase Orders
    """

    _inherit = 'farm.boq.analysis'

    # ── Smart button count ────────────────────────────────────────────────────
    purchase_count = fields.Integer(
        string='Purchase Orders',
        compute='_compute_purchase_count',
    )

    # ────────────────────────────────────────────────────────────────────────
    # Compute
    # ────────────────────────────────────────────────────────────────────────

    @api.depends('line_ids.purchase_order_id')
    def _compute_purchase_count(self):
        for rec in self:
            rec.purchase_count = len(
                rec.line_ids.mapped('purchase_order_id').filtered('id')
            )

    # ────────────────────────────────────────────────────────────────────────
    # Actions
    # ────────────────────────────────────────────────────────────────────────

    def action_generate_rfq(self):
        """Generate RFQ(s) from approved analysis lines that have a vendor set.

        Rules:
        - Analysis document must be in 'approved' state.
        - Only lines where:
            * analysis_state == 'approved'
            * vendor_id is set
            * procurement_state == 'not_requested'
            * procurement_type != 'labour' (internal labour doesn't get a PO)
        - Lines are grouped by vendor_id → one PO per vendor.
        - Each PO line is linked back to the analysis line via
          farm_analysis_line_id (on purchase.order.line).
        - After creation: procurement_state → 'rfq_sent'.

        Returns an action to view all created POs.
        """
        self.ensure_one()

        if self.analysis_state != 'approved':
            raise UserError(_(
                'The Analysis document must be approved before generating RFQs.\n'
                'Current status: %s', dict(
                    self._fields['analysis_state'].selection
                ).get(self.analysis_state, self.analysis_state)
            ))

        eligible_lines = self.line_ids.filtered(
            lambda l: (
                l.analysis_state == 'approved'
                and l.vendor_id
                and l.procurement_state == 'not_requested'
                and l.procurement_type != 'labour'
            )
        )

        if not eligible_lines:
            raise UserError(_(
                'No eligible lines found.\n\n'
                'To generate RFQs, lines must:\n'
                '- Be in "Approved" analysis status\n'
                '- Have a Preferred Vendor assigned\n'
                '- Be in "Not Requested" procurement status\n'
                '- Not be of type "Labour (Internal)"'
            ))

        # Group lines by vendor
        vendors = eligible_lines.mapped('vendor_id')
        created_po_ids = []

        PurchaseOrder = self.env['purchase.order']

        for vendor in vendors:
            vendor_lines = eligible_lines.filtered(
                lambda l: l.vendor_id == vendor
            )

            # Build PO line vals
            po_line_vals = []
            for al in vendor_lines:
                product = al.product_id
                uom = al.purchase_uom_id or al.unit_id

                pol_vals = {
                    'product_id':          product.id if product else False,
                    'name':                al.name or al.display_code or '',
                    'product_qty':         al.estimated_qty or al.boq_qty or 1.0,
                    'product_uom':         uom.id if uom else False,
                    'price_unit':          al.estimated_unit_cost or 0.0,
                    'date_planned':        fields.Date.today(),
                    'farm_analysis_line_id': al.id,
                }
                po_line_vals.append((0, 0, pol_vals))

            # Create the PO
            po = PurchaseOrder.create({
                'partner_id':        vendor.id,
                'farm_project_id':   self.project_id.id or False,
                'farm_boq_id':       self.boq_id.id or False,
                'farm_analysis_id':  self.id,
                'order_line':        po_line_vals,
                'notes':             _(
                    'Generated from BOQ Analysis: %s\n'
                    'BOQ: %s\nProject: %s'
                ) % (
                    self.name,
                    self.boq_id.name or '',
                    self.project_id.name or '',
                ),
            })
            created_po_ids.append(po.id)

            # Link analysis lines back to their PO lines
            for al in vendor_lines:
                matching_pol = po.order_line.filtered(
                    lambda l: l.farm_analysis_line_id == al
                )
                if matching_pol:
                    al.write({
                        'purchase_order_line_id': matching_pol[0].id,
                        'procurement_state':      'rfq_sent',
                    })

        return {
            'type': 'ir.actions.act_window',
            'name': _('Purchase Orders'),
            'res_model': 'purchase.order',
            'view_mode': 'list,form',
            'domain': [('id', 'in', created_po_ids)],
        }

    def action_view_purchases(self):
        """Open all Purchase Orders linked to this analysis."""
        self.ensure_one()
        po_ids = self.line_ids.mapped('purchase_order_id').filtered('id').ids
        return {
            'type': 'ir.actions.act_window',
            'name': _('Purchases — %s') % self.name,
            'res_model': 'purchase.order',
            'view_mode': 'list,form',
            'domain': [('id', 'in', po_ids)],
            'context': {'default_farm_analysis_id': self.id},
        }
