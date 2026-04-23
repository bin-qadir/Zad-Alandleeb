from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ConstructionMaterialPlan(models.Model):
    _name = 'construction.material.plan'
    _description = 'Construction Material Plan Line'
    _order = 'boq_line_id, sequence, id'

    # ── Parent BOQ line ────────────────────────────────────────────────────────

    boq_line_id = fields.Many2one(
        comodel_name='construction.boq.line',
        string='BOQ Line',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sequence = fields.Integer(string='Seq', default=10)

    # ── Derived location fields (stored for filtering / grouping) ─────────────

    project_id = fields.Many2one(
        comodel_name='construction.project',
        string='Project',
        related='boq_line_id.project_id',
        store=True,
        readonly=True,
        index=True,
    )
    division_id = fields.Many2one(
        comodel_name='construction.division',
        string='Division',
        related='boq_line_id.division_id',
        store=True,
        readonly=True,
        index=True,
    )
    subdivision_id = fields.Many2one(
        comodel_name='construction.subdivision',
        string='Subdivision',
        related='boq_line_id.subdivision_id',
        store=True,
        readonly=True,
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

    planned_qty = fields.Float(
        string='Planned Qty',
        required=True,
        default=1.0,
        digits=(16, 4),
    )
    available_qty = fields.Float(
        string='Available Qty',
        compute='_compute_availability',
        digits=(16, 4),
        help='Current available stock for this product across all internal locations.',
    )
    shortage_qty = fields.Float(
        string='Shortage Qty',
        compute='_compute_availability',
        digits=(16, 4),
        help='Quantity still needed beyond current available stock. Never negative.',
    )

    # ── Status ────────────────────────────────────────────────────────────────

    status = fields.Selection(
        selection=[
            ('draft',      'Draft'),
            ('available',  'Available'),
            ('shortage',   'Shortage'),
            ('requested',  'Requested'),
            ('procured',   'Procured'),
        ],
        string='Status',
        compute='_compute_status',
        store=True,
        default='draft',
        index=True,
    )

    # ── Request linkage ───────────────────────────────────────────────────────

    request_line_ids = fields.One2many(
        comodel_name='construction.material.request.line',
        inverse_name='material_plan_id',
        string='Request Lines',
    )
    request_line_count = fields.Integer(
        string='Requests',
        compute='_compute_request_line_count',
    )

    # ── Notes ─────────────────────────────────────────────────────────────────

    notes = fields.Char(string='Notes')

    # ── Computes ──────────────────────────────────────────────────────────────

    @api.depends('product_id', 'planned_qty')
    def _compute_availability(self):
        for rec in self:
            if not rec.product_id:
                rec.available_qty = 0.0
                rec.shortage_qty = 0.0
                continue
            avail = rec.product_id.qty_available
            rec.available_qty = avail
            rec.shortage_qty = max(0.0, rec.planned_qty - avail)

    @api.depends(
        'planned_qty',
        'product_id',
        'request_line_ids',
        'request_line_ids.request_id.state',
    )
    def _compute_status(self):
        for rec in self:
            if not rec.product_id or not rec.planned_qty:
                rec.status = 'draft'
                continue

            # Check if any request line has been converted to procurement
            if rec.request_line_ids.filtered(
                lambda l: l.request_id.state == 'converted_to_procurement'
            ):
                rec.status = 'procured'
                continue

            # Check if any active (non-rejected) request exists
            if rec.request_line_ids.filtered(
                lambda l: l.request_id.state not in ('rejected', 'draft')
            ):
                rec.status = 'requested'
                continue

            # Evaluate stock availability
            avail = rec.product_id.qty_available
            if avail >= rec.planned_qty:
                rec.status = 'available'
            else:
                rec.status = 'shortage'

    @api.depends('request_line_ids')
    def _compute_request_line_count(self):
        for rec in self:
            rec.request_line_count = len(rec.request_line_ids)

    # ── Onchange helpers ──────────────────────────────────────────────────────

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.description = self.product_id.display_name
            if self.product_id.uom_id:
                self.unit = self.product_id.uom_id.name

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_create_request(self):
        """
        Generate a single Material Request from the selected plan lines.
        Grouped by project — one request per project.
        """
        if not self:
            raise UserError(_('Select at least one material plan line.'))

        # Group by project
        by_project = {}
        for plan in self:
            pid = plan.project_id.id
            by_project.setdefault(pid, [])
            by_project[pid].append(plan)

        created = self.env['construction.material.request']
        for project_id, plans in by_project.items():
            project = plans[0].project_id
            request = self.env['construction.material.request'].create({
                'project_id': project.id,
                'requested_by': self.env.uid,
                'request_date': fields.Date.context_today(self),
                'notes': _('Auto-generated from Material Plan'),
            })
            for plan in plans:
                self.env['construction.material.request.line'].create({
                    'request_id': request.id,
                    'boq_line_id': plan.boq_line_id.id,
                    'material_plan_id': plan.id,
                    'product_id': plan.product_id.id,
                    'description': plan.description or plan.product_id.display_name,
                    'unit': plan.unit,
                    'requested_qty': plan.shortage_qty or plan.planned_qty,
                    'remarks': plan.notes or '',
                })
            created |= request

        # Open the created request(s)
        if len(created) == 1:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Material Request'),
                'res_model': 'construction.material.request',
                'view_mode': 'form',
                'res_id': created.id,
            }
        return {
            'type': 'ir.actions.act_window',
            'name': _('Material Requests'),
            'res_model': 'construction.material.request',
            'view_mode': 'list,form',
            'domain': [('id', 'in', created.ids)],
        }

    def action_open_requests(self):
        """Open request lines linked to this plan."""
        self.ensure_one()
        request_ids = self.request_line_ids.mapped('request_id').ids
        return {
            'type': 'ir.actions.act_window',
            'name': _('Material Requests'),
            'res_model': 'construction.material.request',
            'view_mode': 'list,form',
            'domain': [('id', 'in', request_ids)],
        }
