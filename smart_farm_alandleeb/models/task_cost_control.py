# -*- coding: utf-8 -*-
from collections import defaultdict
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


# ─────────────────────────────────────────────────────────────────────────────
# task.material  –  Material consumption line linked to a project task
# ─────────────────────────────────────────────────────────────────────────────
class TaskMaterial(models.Model):
    _name = 'task.material'
    _description = 'Task Material Line'
    _order = 'task_id, sequence, id'

    sequence = fields.Integer(default=10)

    task_id = fields.Many2one(
        'project.task',
        string='Task',
        required=True,
        ondelete='cascade',
        index=True,
    )
    project_id = fields.Many2one(
        related='task_id.project_id',
        store=True,
        string='Project',
    )

    product_id = fields.Many2one(
        'product.product',
        string='Material / Product',
        required=True,
        domain=[('purchase_ok', '=', True)],
    )
    description = fields.Char(
        string='Description',
        compute='_compute_description',
        store=True,
        readonly=False,
    )
    quantity = fields.Float(
        string='Ordered Qty',
        default=1.0,
        digits='Product Unit of Measure',
        required=True,
    )
    uom_id = fields.Many2one(
        'uom.uom',
        string='UoM',
        compute='_compute_uom',
        store=True,
        readonly=False,
    )
    unit_price = fields.Float(
        string='Unit Cost',
        digits='Product Price',
        compute='_compute_unit_price',
        store=True,
        readonly=False,
    )
    subtotal = fields.Monetary(
        string='Subtotal',
        compute='_compute_subtotal',
        store=True,
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        related='task_id.company_id.currency_id',
        store=True,
    )

    # ── Vendor ───────────────────────────────────────────────────────────────
    vendor_id = fields.Many2one(
        'res.partner',
        string='Vendor',
        compute='_compute_vendor',
        store=True,
        readonly=False,
        help='Preferred vendor from product supplier info. Override if needed.',
    )

    # ── RFQ / PO linkage ─────────────────────────────────────────────────────
    purchase_order_id = fields.Many2one(
        'purchase.order',
        string='RFQ / PO',
        readonly=True,
        copy=False,
    )
    purchase_line_id = fields.Many2one(
        'purchase.order.line',
        string='PO Line',
        readonly=True,
        copy=False,
    )

    # ── Receipt tracking ─────────────────────────────────────────────────────
    received_qty = fields.Float(
        string='Received Qty',
        digits='Product Unit of Measure',
        compute='_compute_received_qty',
        store=True,
        readonly=True,
        help='Quantity received via validated incoming shipments for the linked PO line.',
    )
    remaining_qty = fields.Float(
        string='Remaining Qty',
        digits='Product Unit of Measure',
        compute='_compute_received_qty',
        store=True,
        readonly=True,
    )
    receipt_progress = fields.Float(
        string='Receipt %',
        compute='_compute_received_qty',
        store=True,
        readonly=True,
        help='Percentage of ordered quantity that has been received.',
    )

    # ── State (5-value lifecycle) ─────────────────────────────────────────────
    state = fields.Selection([
        ('draft',      'Draft'),
        ('requested',  'RFQ Created'),
        ('partial',    'Partially Received'),
        ('received',   'Fully Received'),
        ('cancelled',  'Cancelled'),
    ], default='draft', string='Status', copy=False,
       compute='_compute_state', store=True, readonly=False)

    # ────────────────────────────────────────────────────────────────────────
    # Basic computes
    # ────────────────────────────────────────────────────────────────────────

    @api.depends('product_id')
    def _compute_description(self):
        for line in self:
            line.description = line.product_id.name or ''

    @api.depends('product_id')
    def _compute_uom(self):
        for line in self:
            line.uom_id = line.product_id.uom_po_id or line.product_id.uom_id

    @api.depends('product_id', 'quantity', 'uom_id')
    def _compute_unit_price(self):
        for line in self:
            if line.product_id:
                seller = line.product_id._select_seller(
                    quantity=line.quantity or 1.0,
                    uom_id=line.uom_id,
                )
                line.unit_price = seller.price if seller else line.product_id.standard_price
            else:
                line.unit_price = 0.0

    @api.depends('product_id', 'quantity', 'uom_id')
    def _compute_vendor(self):
        for line in self:
            seller = False
            if line.product_id:
                seller = line.product_id._select_seller(
                    quantity=line.quantity or 1.0,
                    uom_id=line.uom_id,
                )
            line.vendor_id = seller.partner_id if seller else False

    @api.depends('quantity', 'unit_price')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.unit_price

    # ────────────────────────────────────────────────────────────────────────
    # Received qty — computed from validated stock moves on the PO line
    # ────────────────────────────────────────────────────────────────────────

    @api.depends(
        'purchase_line_id',
        'purchase_line_id.qty_received',
        'purchase_line_id.move_ids.state',
        'purchase_line_id.move_ids.quantity',
        'quantity',
        'uom_id',
    )
    def _compute_received_qty(self):
        """
        Pull received quantity from the linked purchase.order.line.

        Strategy (Odoo 18):
          1. Use purchase_line_id.qty_received — Odoo keeps this up-to-date
             from validated stock.move records automatically.
          2. If the line's UoM differs from our material UoM, convert via
             uom._compute_quantity so the comparison is always in material UoM.
          3. Derive remaining_qty and receipt_progress from the result.
        """
        for line in self:
            if not line.purchase_line_id:
                line.received_qty    = 0.0
                line.remaining_qty   = line.quantity
                line.receipt_progress = 0.0
                continue

            po_line      = line.purchase_line_id
            qty_received = po_line.qty_received  # already in po_line.product_uom

            # Convert to material line UoM if needed
            if line.uom_id and po_line.product_uom and line.uom_id != po_line.product_uom:
                try:
                    qty_received = po_line.product_uom._compute_quantity(
                        qty_received, line.uom_id
                    )
                except Exception:
                    pass  # keep unconverted if UoM categories differ

            ordered = line.quantity or 0.0
            received = round(qty_received, 6)

            line.received_qty    = received
            line.remaining_qty   = max(ordered - received, 0.0)
            line.receipt_progress = (
                min((received / ordered) * 100.0, 100.0) if ordered else 0.0
            )

    # ────────────────────────────────────────────────────────────────────────
    # State auto-compute from receipt data
    # ────────────────────────────────────────────────────────────────────────

    @api.depends(
        'purchase_order_id',
        'purchase_line_id',
        'received_qty',
        'quantity',
    )
    def _compute_state(self):
        """
        Automatic state transitions based on receipt progress.

        Lifecycle:
          draft      → no PO linked yet (manual reset also lands here)
          requested  → PO exists, received_qty == 0
          partial    → PO exists, 0 < received_qty < ordered quantity
          received   → PO exists, received_qty >= ordered quantity
          cancelled  → set manually (e.g. line was cancelled on the PO)

        Note: 'cancelled' is never auto-set by this compute; it can only be
        set by action_cancel() so that it survives recomputation.
        """
        for line in self:
            # Don't override a manually cancelled line
            if line.state == 'cancelled':
                continue

            if not line.purchase_order_id:
                # No PO → draft (unless someone manually set another state without a PO,
                # which shouldn't happen in normal flow)
                line.state = 'draft'
                continue

            received = line.received_qty or 0.0
            ordered  = line.quantity    or 0.0

            if received <= 0.0:
                line.state = 'requested'
            elif received < ordered:
                line.state = 'partial'
            else:
                line.state = 'received'

    # ────────────────────────────────────────────────────────────────────────
    # Constraints
    # ────────────────────────────────────────────────────────────────────────

    @api.constrains('quantity')
    def _check_quantity(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError(_('Material quantity must be greater than zero.'))

    # ────────────────────────────────────────────────────────────────────────
    # Manual state actions
    # ────────────────────────────────────────────────────────────────────────

    def action_reset_to_draft(self):
        """
        Reset a requested/partial line back to draft so a new RFQ can be generated.
        Only allowed when no quantity has been received yet.
        """
        for line in self:
            if line.state == 'cancelled':
                continue
            if line.received_qty and line.received_qty > 0:
                raise UserError(_(
                    'Cannot reset "%s" to draft: %s units have already been received.'
                ) % (line.product_id.display_name, line.received_qty))
            line.write({
                'state':             'draft',
                'purchase_order_id': False,
                'purchase_line_id':  False,
            })

    def action_cancel(self):
        """Manually cancel a material line."""
        for line in self:
            if line.state == 'received':
                raise UserError(_(
                    'Cannot cancel "%s": the material has already been fully received.'
                ) % line.product_id.display_name)
            line.state = 'cancelled'

    def action_reopen(self):
        """Re-open a cancelled line back to draft."""
        for line in self:
            if line.state == 'cancelled':
                line.write({
                    'state':             'draft',
                    'purchase_order_id': False,
                    'purchase_line_id':  False,
                })


# ─────────────────────────────────────────────────────────────────────────────
# stock.picking  –  Hook: trigger task.material recompute on receipt validation
# ─────────────────────────────────────────────────────────────────────────────
class StockPickingReceiptHook(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        """
        After validating an incoming shipment, find any task.material lines
        linked to the purchase order and force-recompute their received_qty
        and state so the project task cost control panel is up-to-date.
        """
        result = super().button_validate()

        # Only care about incoming receipts (purchase receipts)
        incoming_pickings = self.filtered(
            lambda p: p.picking_type_code == 'incoming'
            and p.purchase_id
            and p.state == 'done'
        )
        if not incoming_pickings:
            return result

        purchase_ids = incoming_pickings.mapped('purchase_id').ids
        if not purchase_ids:
            return result

        mat_lines = self.env['task.material'].search([
            ('purchase_order_id', 'in', purchase_ids),
        ])
        if mat_lines:
            # Invalidate so the @api.depends recompute picks up fresh move data
            mat_lines.invalidate_recordset(['received_qty', 'remaining_qty', 'receipt_progress'])
            mat_lines._compute_received_qty()
            # _compute_state depends on received_qty so run it too
            mat_lines.invalidate_recordset(['state'])
            mat_lines._compute_state()

        return result


# ─────────────────────────────────────────────────────────────────────────────
# purchase.order.line  –  Hook: trigger recompute when qty_received changes
#                         (e.g. via backorders or manual done-qty edits)
# ─────────────────────────────────────────────────────────────────────────────
class PurchaseOrderLineReceiptHook(models.Model):
    _inherit = 'purchase.order.line'

    def write(self, vals):
        """
        When qty_received is updated on the PO line (Odoo updates it during
        stock.move validation), propagate the change to linked task.material lines.
        """
        result = super().write(vals)
        if 'qty_received' in vals or 'qty_received_manual' in vals:
            mat_lines = self.env['task.material'].search([
                ('purchase_line_id', 'in', self.ids),
            ])
            if mat_lines:
                mat_lines.invalidate_recordset(
                    ['received_qty', 'remaining_qty', 'receipt_progress', 'state']
                )
                mat_lines._compute_received_qty()
                mat_lines._compute_state()
        return result


# ─────────────────────────────────────────────────────────────────────────────
# task.labor  –  Labour cost line linked to a project task
# ─────────────────────────────────────────────────────────────────────────────
class TaskLabor(models.Model):
    _name = 'task.labor'
    _description = 'Task Labor Line'
    _order = 'task_id, sequence, id'

    sequence = fields.Integer(default=10)

    task_id = fields.Many2one(
        'project.task',
        string='Task',
        required=True,
        ondelete='cascade',
        index=True,
    )
    project_id = fields.Many2one(
        related='task_id.project_id',
        store=True,
        string='Project',
    )

    employee_id = fields.Many2one('hr.employee', string='Employee / Worker')
    job_title   = fields.Char(string='Role / Job Title')
    description = fields.Char(string='Work Description')
    work_date   = fields.Date(string='Date', default=fields.Date.today)
    hours       = fields.Float(string='Hours', digits=(6, 2), required=True, default=1.0)

    hourly_rate = fields.Monetary(
        string='Hourly Rate',
        currency_field='currency_id',
        required=True,
    )
    subtotal = fields.Monetary(
        string='Subtotal',
        compute='_compute_subtotal',
        store=True,
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        related='task_id.company_id.currency_id',
        store=True,
    )

    @api.depends('hours', 'hourly_rate')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.hours * line.hourly_rate

    @api.onchange('employee_id')
    def _onchange_employee(self):
        if self.employee_id:
            self.job_title = (
                self.employee_id.job_title
                or (self.employee_id.job_id and self.employee_id.job_id.name)
                or ''
            )
            if hasattr(self.employee_id, 'timesheet_cost'):
                self.hourly_rate = self.employee_id.timesheet_cost
            elif (
                hasattr(self.employee_id, 'contract_id')
                and self.employee_id.contract_id
                and self.employee_id.contract_id.wage
            ):
                self.hourly_rate = self.employee_id.contract_id.wage / 160.0

    @api.constrains('hours')
    def _check_hours(self):
        for line in self:
            if line.hours <= 0:
                raise ValidationError(_('Labor hours must be greater than zero.'))


# ─────────────────────────────────────────────────────────────────────────────
# project.task  –  Cost Control Center + RFQ Engine
# ─────────────────────────────────────────────────────────────────────────────
class ProjectTaskCostControl(models.Model):
    _inherit = 'project.task'

    # ── Lines ────────────────────────────────────────────────────────────────
    material_line_ids = fields.One2many('task.material', 'task_id', string='Material Lines')
    labor_line_ids    = fields.One2many('task.labor',    'task_id', string='Labor Lines')

    # ── Costs ────────────────────────────────────────────────────────────────
    material_cost = fields.Monetary(
        string='Material Cost', compute='_compute_costs', store=True,
        currency_field='cost_currency_id',
    )
    labor_cost = fields.Monetary(
        string='Labor Cost', compute='_compute_costs', store=True,
        currency_field='cost_currency_id',
    )
    overhead_cost = fields.Monetary(
        string='Overhead Cost', currency_field='cost_currency_id', tracking=True,
    )
    total_cost = fields.Monetary(
        string='Total Cost', compute='_compute_costs', store=True,
        currency_field='cost_currency_id',
    )
    cost_currency_id = fields.Many2one(
        'res.currency', compute='_compute_cost_currency', string='Cost Currency',
    )

    # ── Budget ───────────────────────────────────────────────────────────────
    budget_amount = fields.Monetary(
        string='Budget', currency_field='cost_currency_id', tracking=True,
    )
    budget_variance = fields.Monetary(
        string='Budget Variance', compute='_compute_budget_variance', store=True,
        currency_field='cost_currency_id',
    )
    budget_progress = fields.Float(
        string='Budget Used (%)', compute='_compute_budget_variance', store=True,
    )

    # ── Smart button counts ──────────────────────────────────────────────────
    material_count  = fields.Integer(compute='_compute_counts',          string='Materials')
    labor_count     = fields.Integer(compute='_compute_counts',          string='Labor Count')
    rfq_count       = fields.Integer(
        string='RFQs',
        compute='_compute_rfq_count',
        store=True,
        compute_sudo=True,
    )
    quotation_count = fields.Integer(compute='_compute_quotation_count', string='Quotations')

    # ── Receipt summary (task-level) ─────────────────────────────────────────
    materials_all_received = fields.Boolean(
        string='All Materials Received',
        compute='_compute_receipt_summary',
        store=True,
    )
    materials_partial = fields.Boolean(
        string='Some Materials Received',
        compute='_compute_receipt_summary',
        store=True,
    )

    # ── Has-draft helper (drives button visibility) ──────────────────────────
    has_draft_material_lines = fields.Boolean(
        compute='_compute_has_draft_material_lines',
        string='Has Draft Materials',
    )

    # ── Farm link (optional) ─────────────────────────────────────────────────
    farm_id       = fields.Many2one('farm.farm',  string='Farm', tracking=True)
    farm_field_id = fields.Many2one(
        'farm.field', string='Field',
        domain="[('farm_id','=',farm_id)]",
    )

    # ────────────────────────────────────────────────────────────────────────
    # Computes
    # ────────────────────────────────────────────────────────────────────────

    def _compute_cost_currency(self):
        for task in self:
            task.cost_currency_id = task.company_id.currency_id or self.env.company.currency_id

    @api.depends('material_line_ids.subtotal', 'labor_line_ids.subtotal', 'overhead_cost')
    def _compute_costs(self):
        for task in self:
            task.material_cost = sum(task.material_line_ids.mapped('subtotal'))
            task.labor_cost    = sum(task.labor_line_ids.mapped('subtotal'))
            task.total_cost    = task.material_cost + task.labor_cost + (task.overhead_cost or 0.0)

    @api.depends('total_cost', 'budget_amount')
    def _compute_budget_variance(self):
        for task in self:
            task.budget_variance = (task.budget_amount or 0.0) - task.total_cost
            task.budget_progress = (
                min((task.total_cost / task.budget_amount) * 100, 999.0)
                if task.budget_amount else 0.0
            )

    @api.depends('material_line_ids', 'labor_line_ids')
    def _compute_counts(self):
        for task in self:
            task.material_count = len(task.material_line_ids)
            task.labor_count    = len(task.labor_line_ids)

    @api.depends('material_line_ids.state', 'material_line_ids.quantity', 'material_line_ids.product_id')
    def _compute_has_draft_material_lines(self):
        for task in self:
            task.has_draft_material_lines = any(
                l.state == 'draft' and l.product_id and l.quantity > 0
                for l in task.material_line_ids
            )

    @api.depends('material_line_ids.state')
    def _compute_receipt_summary(self):
        for task in self:
            lines = task.material_line_ids.filtered(
                lambda l: l.state != 'cancelled'
            )
            if not lines:
                task.materials_all_received = False
                task.materials_partial      = False
                continue
            states = set(lines.mapped('state'))
            task.materials_all_received = states <= {'received'}
            task.materials_partial      = bool(
                states & {'partial', 'received'}
            ) and not task.materials_all_received

    @api.depends('material_line_ids.purchase_order_id', 'material_line_ids.state')
    def _compute_rfq_count(self):
        """Count distinct purchase orders linked via material lines + origin search."""
        for task in self:
            po_ids_from_lines  = task.material_line_ids.mapped('purchase_order_id').ids
            po_ids_from_origin = self.env['purchase.order'].search([
                ('origin', '=', task._rfq_origin()),
            ]).ids
            task.rfq_count = len(set(po_ids_from_lines + po_ids_from_origin))

    def _compute_quotation_count(self):
        SO = self.env['sale.order']
        for task in self:
            task.quotation_count = SO.search_count([
                ('origin', 'like', task.name),
                ('state', 'in', ('draft', 'sent')),
            ])

    # ────────────────────────────────────────────────────────────────────────
    # Internal helper
    # ────────────────────────────────────────────────────────────────────────

    def _rfq_origin(self):
        """
        Canonical origin string stamped on every purchase.order created from this task.
        Format:  [Project Name] Task Name
        """
        self.ensure_one()
        project_part = self.project_id.name if self.project_id else 'No Project'
        return '[%s] %s' % (project_part, self.name)

    # ────────────────────────────────────────────────────────────────────────
    # RFQ ENGINE
    # ────────────────────────────────────────────────────────────────────────

    def action_create_rfq(self):
        """
        Create one purchase.order per vendor from this task's draft material lines.

        Validation:
          1. At least one material line with product + qty > 0 must exist.
          2. Only DRAFT lines are processed (skip already-requested/received).
          3. Every qualifying draft line MUST have a vendor_id.
        After success:
          • purchase_order_id + purchase_line_id written on each material line.
          • Line state → 'requested' (via _compute_state).
        """
        self.ensure_one()

        eligible = self.material_line_ids.filtered(
            lambda l: l.product_id and l.quantity > 0 and l.state != 'cancelled'
        )
        if not eligible:
            raise UserError(_(
                'No eligible material lines found (need product + quantity > 0).\n'
                'Add materials in the Cost Control tab before creating an RFQ.'
            ))

        draft_lines = eligible.filtered(lambda l: l.state == 'draft')
        if not draft_lines:
            po_refs = ', '.join(eligible.mapped('purchase_order_id.name'))
            raise UserError(_(
                'All eligible material lines already have an RFQ: %s\n\n'
                'Reset the desired lines to Draft first (↺ button on each line).'
            ) % (po_refs or _('(see linked POs)')))

        no_vendor = draft_lines.filtered(lambda l: not l.vendor_id)
        if no_vendor:
            bullets = '\n• '.join(no_vendor.mapped('product_id.display_name'))
            raise ValidationError(_(
                'The following products have no vendor configured.\n'
                'Set a vendor on the product (Purchase tab) or on the material line:\n\n• %s'
            ) % bullets)

        # Group by vendor → one PO per vendor
        vendor_groups: dict = defaultdict(lambda: self.env['task.material'])
        for line in draft_lines:
            vendor_groups[line.vendor_id.id] |= line

        origin  = self._rfq_origin()
        company = self.company_id or self.env.company
        created_po_ids = []

        for vendor_id, lines in vendor_groups.items():
            vendor = self.env['res.partner'].browse(vendor_id)
            po_line_vals = [(0, 0, {
                'product_id':   l.product_id.id,
                'name':         l.description or l.product_id.display_name,
                'product_qty':  l.quantity,
                'product_uom':  l.uom_id.id,
                'price_unit':   l.unit_price,
                'date_planned': fields.Datetime.now(),
            }) for l in lines]

            po = self.env['purchase.order'].create({
                'partner_id': vendor.id,
                'company_id': company.id,
                'origin':     origin,
                'order_line': po_line_vals,
                'notes':      _('Auto-generated from Task: [%d] %s') % (self.id, self.name),
            })
            created_po_ids.append(po.id)

            # Write linkage back; _compute_state will auto-set → 'requested'
            for mat_line, po_line in zip(lines, po.order_line):
                mat_line.write({
                    'purchase_order_id': po.id,
                    'purchase_line_id':  po_line.id,
                })

        self.env.flush_all()
        self.invalidate_recordset(['rfq_count', 'has_draft_material_lines'])

        if len(created_po_ids) == 1:
            return {
                'type':      'ir.actions.act_window',
                'name':      _('RFQ Created'),
                'res_model': 'purchase.order',
                'res_id':    created_po_ids[0],
                'view_mode': 'form',
                'target':    'current',
            }
        return {
            'type':      'ir.actions.act_window',
            'name':      _('RFQs Created (%d vendors)') % len(created_po_ids),
            'res_model': 'purchase.order',
            'view_mode': 'list,form',
            'domain':    [('id', 'in', created_po_ids)],
            'target':    'current',
        }

    # ────────────────────────────────────────────────────────────────────────
    # Smart button actions
    # ────────────────────────────────────────────────────────────────────────

    def action_view_materials(self):
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Materials – %s') % self.name,
            'res_model': 'task.material',
            'view_mode': 'list,form',
            'domain':    [('task_id', '=', self.id)],
            'context':   {'default_task_id': self.id},
        }

    def action_view_labor(self):
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Labor – %s') % self.name,
            'res_model': 'task.labor',
            'view_mode': 'list,form',
            'domain':    [('task_id', '=', self.id)],
            'context':   {'default_task_id': self.id},
        }

    def action_view_rfqs(self):
        """
        Open RFQs linked to this task.
        1 RFQ → form. >1 RFQs → filtered tree.
        """
        self.ensure_one()
        po_ids = list(set(
            self.material_line_ids.mapped('purchase_order_id').ids
            + self.env['purchase.order'].search([
                ('origin', '=', self._rfq_origin())
            ]).ids
        ))
        if not po_ids:
            raise UserError(_('No RFQs found for this task.'))
        if len(po_ids) == 1:
            return {
                'type':      'ir.actions.act_window',
                'name':      _('RFQ'),
                'res_model': 'purchase.order',
                'res_id':    po_ids[0],
                'view_mode': 'form',
                'target':    'current',
            }
        return {
            'type':      'ir.actions.act_window',
            'name':      _('RFQs – %s') % self.name,
            'res_model': 'purchase.order',
            'view_mode': 'list,form',
            'domain':    [('id', 'in', po_ids)],
            'context':   {
                'default_origin':       self._rfq_origin(),
                'search_default_draft': 1,
            },
            'target':    'current',
        }

    def action_view_quotations(self):
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Quotations – %s') % self.name,
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain':    [('origin', 'like', self.name), ('state', 'in', ('draft', 'sent'))],
            'context':   {'default_origin': self.name},
        }


# ─────────────────────────────────────────────────────────────────────────────
# project.task  –  Quotation (Sale Order) Engine — extends the Cost Control class
# ─────────────────────────────────────────────────────────────────────────────
# NOTE: this is a second _inherit block; Odoo merges them automatically since
# they share the same _name.  We keep it separate for readability.
# ─────────────────────────────────────────────────────────────────────────────
class ProjectTaskQuotation(models.Model):
    _inherit = 'project.task'

    # ── Margin / Pricing ─────────────────────────────────────────────────────
    margin_type = fields.Selection([
        ('percent', 'Percentage (%)'),
        ('fixed',   'Fixed Amount'),
    ], string='Margin Type', default='percent', tracking=True,
       help='How the margin is applied on top of the total cost.')

    margin_percent = fields.Float(
        string='Margin %',
        default=0.0,
        digits=(6, 2),
        help='Percentage added on top of total cost when margin_type = percent.',
    )
    margin_amount = fields.Monetary(
        string='Margin Amount',
        currency_field='cost_currency_id',
        default=0.0,
        help='Fixed amount added on top of total cost when margin_type = fixed.',
    )
    selling_price = fields.Monetary(
        string='Selling Price',
        compute='_compute_selling_price',
        store=True,
        currency_field='cost_currency_id',
        help='Total Cost + Margin. Used as the price on the generated Sale Order.',
    )
    margin_value = fields.Monetary(
        string='Margin Value',
        compute='_compute_selling_price',
        store=True,
        currency_field='cost_currency_id',
        help='Absolute margin amount (computed from % or fixed).',
    )

    # ── Quotation linkage ────────────────────────────────────────────────────
    sale_order_ids = fields.Many2many(
        'sale.order',
        'project_task_sale_order_rel',
        'task_id',
        'sale_order_id',
        string='Quotations / Sale Orders',
        copy=False,
    )
    sale_order_count = fields.Integer(
        string='Sales Orders',
        compute='_compute_sale_order_count',
        store=True,
    )

    # ────────────────────────────────────────────────────────────────────────
    # Computes
    # ────────────────────────────────────────────────────────────────────────

    @api.depends('total_cost', 'margin_type', 'margin_percent', 'margin_amount')
    def _compute_selling_price(self):
        for task in self:
            cost = task.total_cost or 0.0
            if task.margin_type == 'percent':
                margin = cost * (task.margin_percent or 0.0) / 100.0
            else:  # fixed
                margin = task.margin_amount or 0.0
            task.margin_value  = margin
            task.selling_price = cost + margin

    @api.depends('sale_order_ids')
    def _compute_sale_order_count(self):
        for task in self:
            task.sale_order_count = len(task.sale_order_ids)

    # ────────────────────────────────────────────────────────────────────────
    # Origin helper
    # ────────────────────────────────────────────────────────────────────────

    def _quotation_origin(self):
        """
        Canonical origin stamped on every sale.order created from this task.
        Format:  [Project Name] Task Name (TASK-ID)
        """
        self.ensure_one()
        project_part = self.project_id.name if self.project_id else 'No Project'
        return '[%s] %s (TASK-%d)' % (project_part, self.name, self.id)

    # ────────────────────────────────────────────────────────────────────────
    # Quotation engine
    # ────────────────────────────────────────────────────────────────────────

    def action_create_quotation(self):
        """
        Create a structured sale.order from this task's cost data.

        Structure of SO lines:
          • One summary line per cost category that has a non-zero value:
              – Materials  → product = 'Task Materials' service product
              – Labor      → product = 'Task Labor'     service product
              – Overhead   → product = 'Task Overhead'  service product
          • The price_unit on each line is set to the actual cost value.
          • The grand total line uses the computed selling_price.

        Duplicate guard:
          • If an open (draft/sent) quotation already exists, an UserError is
            raised prompting the user to cancel it first or use the smart button
            to open the existing one.  Confirmed/done SOs are NOT considered a
            block; the user may always create a follow-up quotation.

        Origin format:  [Project Name] Task Name (TASK-ID)
        """
        self.ensure_one()

        if not self.total_cost:
            raise UserError(_(
                'Total cost is zero. Please add material, labor, or overhead costs '
                'in the Cost Control tab before creating a quotation.'
            ))

        # ── Duplicate guard: only block open (unconfirmed) quotations ─────────
        open_orders = self.sale_order_ids.filtered(
            lambda so: so.state in ('draft', 'sent')
        )
        if open_orders:
            names = ', '.join(open_orders.mapped('name'))
            raise UserError(_(
                'An open quotation already exists for this task: %s\n\n'
                'Open it from the Quotations smart button, or cancel it before '
                'creating a new one.'
            ) % names)

        company  = self.company_id or self.env.company
        origin   = self._quotation_origin()
        currency = self.cost_currency_id or company.currency_id

        # ── Resolve/create service products for each cost category ────────────
        def _get_or_create_service_product(name, description):
            """Get a generic service product by internal reference; create if missing."""
            ref = 'task_cost_%s' % name.lower().replace(' ', '_')
            prod = self.env['product.product'].search([
                ('default_code', '=', ref),
                ('type', '=', 'service'),
            ], limit=1)
            if not prod:
                prod = self.env['product.product'].create({
                    'name':          name,
                    'default_code':  ref,
                    'type':          'service',
                    'invoice_policy': 'order',
                    'description_sale': description,
                    'can_be_sold':   True,
                })
            return prod

        mat_product  = _get_or_create_service_product(
            'Task Materials', _('Materials procured for the project task'))
        lab_product  = _get_or_create_service_product(
            'Task Labor',     _('Labor hours applied to the project task'))
        ovh_product  = _get_or_create_service_product(
            'Task Overhead',  _('Overhead costs allocated to the project task'))
        sell_product = _get_or_create_service_product(
            'Task Delivery',  _('Full task delivery — all materials, labor, and overhead'))

        # ── Build sale order lines ─────────────────────────────────────────────
        order_lines = []
        line_seq    = 10

        def _add_line(product, description, qty, price, section_name=None):
            nonlocal line_seq
            if section_name:
                # Section separator line (display_type = 'line_section')
                order_lines.append((0, 0, {
                    'display_type': 'line_section',
                    'name':         section_name,
                    'sequence':     line_seq,
                }))
                line_seq += 1
            order_lines.append((0, 0, {
                'product_id':  product.id,
                'name':        description,
                'product_uom_qty': qty,
                'price_unit':  price,
                'sequence':    line_seq,
            }))
            line_seq += 1

        # Cost breakdown section
        if self.material_cost:
            _add_line(
                mat_product,
                _('Materials — %s') % self.name,
                1, self.material_cost,
                section_name=_('Cost Breakdown'),
            )
        if self.labor_cost:
            # First cost category might have already added the section; only add it once
            if not self.material_cost:
                _add_line(
                    lab_product,
                    _('Labor — %s') % self.name,
                    1, self.labor_cost,
                    section_name=_('Cost Breakdown'),
                )
            else:
                _add_line(lab_product, _('Labor — %s') % self.name, 1, self.labor_cost)

        if self.overhead_cost:
            _add_line(ovh_product, _('Overhead — %s') % self.name, 1, self.overhead_cost)

        # Separator before the final selling line
        order_lines.append((0, 0, {
            'display_type': 'line_section',
            'name':         _('Total'),
            'sequence':     line_seq,
        }))
        line_seq += 1

        # Summary / selling-price line
        margin_label = (
            _('(%.1f%% margin)') % self.margin_percent
            if self.margin_type == 'percent'
            else _('(fixed margin: %s)') % currency.symbol
        )
        _add_line(
            sell_product,
            _('Task: %s %s') % (self.name, margin_label),
            1,
            self.selling_price,
        )

        # ── Create the sale order ─────────────────────────────────────────────
        partner = (
            self.project_id.partner_id
            or company.partner_id
        )

        so = self.env['sale.order'].create({
            'partner_id':  partner.id,
            'company_id':  company.id,
            'origin':      origin,
            'order_line':  order_lines,
            'note':        _(
                'Quotation auto-generated from Task: %s\nProject: %s'
            ) % (self.name, self.project_id.name if self.project_id else '—'),
        })

        # ── Link SO back to the task ──────────────────────────────────────────
        self.sale_order_ids = [(4, so.id)]

        # Flush so the smart button counter updates
        self.env.flush_all()
        self.invalidate_recordset(['sale_order_count'])

        return {
            'type':      'ir.actions.act_window',
            'name':      _('Quotation Created'),
            'res_model': 'sale.order',
            'res_id':    so.id,
            'view_mode': 'form',
            'target':    'current',
        }

    # ────────────────────────────────────────────────────────────────────────
    # Smart button: view quotations
    # ────────────────────────────────────────────────────────────────────────

    def action_view_quotations(self):
        """
        Open quotations/SOs linked to this task.
        • 1 quotation  → opens SO form view directly.
        • >1 quotations → opens a filtered tree view.
        """
        self.ensure_one()
        so_ids = self.sale_order_ids.ids
        if not so_ids:
            raise UserError(_('No quotations found for this task.'))
        if len(so_ids) == 1:
            return {
                'type':      'ir.actions.act_window',
                'name':      _('Quotation'),
                'res_model': 'sale.order',
                'res_id':    so_ids[0],
                'view_mode': 'form',
                'target':    'current',
            }
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Quotations – %s') % self.name,
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain':    [('id', 'in', so_ids)],
            'context':   {
                'default_origin': self._quotation_origin(),
                'search_default_draft': 1,
            },
            'target':    'current',
        }
