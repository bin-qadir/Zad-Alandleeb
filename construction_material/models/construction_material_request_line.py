from odoo import api, fields, models


class ConstructionMaterialRequestLine(models.Model):
    _name = 'construction.material.request.line'
    _description = 'Material Request Line'
    _order = 'sequence, id'

    # ── Parent ────────────────────────────────────────────────────────────────

    request_id = fields.Many2one(
        comodel_name='construction.material.request',
        string='Material Request',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sequence = fields.Integer(string='Seq', default=10)

    # ── Source traceability ────────────────────────────────────────────────────

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
        string='Product / Material',
        required=True,
        ondelete='restrict',
        index=True,
    )
    description = fields.Char(string='Description')
    unit = fields.Char(string='Unit', size=20)

    # ── Quantities ────────────────────────────────────────────────────────────

    requested_qty = fields.Float(
        string='Requested Qty',
        required=True,
        default=1.0,
        digits=(16, 4),
    )
    available_qty = fields.Float(
        string='Available Qty',
        compute='_compute_availability',
        digits=(16, 4),
    )
    shortage_qty = fields.Float(
        string='Shortage',
        compute='_compute_availability',
        digits=(16, 4),
    )

    # ── Remarks ───────────────────────────────────────────────────────────────

    remarks = fields.Char(string='Remarks')

    # ── Computes ──────────────────────────────────────────────────────────────

    @api.depends('product_id', 'requested_qty')
    def _compute_availability(self):
        for rec in self:
            if not rec.product_id:
                rec.available_qty = 0.0
                rec.shortage_qty = 0.0
                continue
            avail = rec.product_id.qty_available
            rec.available_qty = avail
            rec.shortage_qty = max(0.0, rec.requested_qty - avail)

    # ── Onchange helpers ──────────────────────────────────────────────────────

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            if not self.description:
                self.description = self.product_id.display_name
            if self.product_id.uom_id:
                self.unit = self.product_id.uom_id.name

    @api.onchange('material_plan_id')
    def _onchange_material_plan_id(self):
        """Pull product and quantities from the linked material plan."""
        if self.material_plan_id:
            plan = self.material_plan_id
            self.product_id = plan.product_id
            self.description = plan.description or plan.product_id.display_name
            self.unit = plan.unit
            self.boq_line_id = plan.boq_line_id
            # Default requested qty to shortage (or planned if no shortage)
            self.requested_qty = (
                plan.shortage_qty if plan.shortage_qty > 0 else plan.planned_qty
            )
