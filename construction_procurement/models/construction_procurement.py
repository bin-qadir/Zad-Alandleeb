from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ConstructionProcurement(models.Model):
    _name = 'construction.procurement'
    _description = 'Construction Procurement'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'procurement_date desc, name desc'
    _rec_name = 'name'

    # ── Identity ──────────────────────────────────────────────────────────────

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
        tracking=True,
    )

    # ── Project / Structure ───────────────────────────────────────────────────

    project_id = fields.Many2one(
        comodel_name='construction.project',
        string='Project',
        required=True,
        ondelete='cascade',
        index=True,
        tracking=True,
    )
    division_id = fields.Many2one(
        comodel_name='construction.division',
        string='Division',
        ondelete='set null',
        domain="[('project_id', '=', project_id)]",
        tracking=True,
    )
    subdivision_id = fields.Many2one(
        comodel_name='construction.subdivision',
        string='Subdivision',
        ondelete='set null',
        domain="[('division_id', '=', division_id)]",
        tracking=True,
    )

    # ── Source request ────────────────────────────────────────────────────────

    material_request_ids = fields.Many2many(
        comodel_name='construction.material.request',
        relation='construction_procurement_request_rel',
        column1='procurement_id',
        column2='request_id',
        string='Material Requests',
        copy=False,
    )
    material_request_count = fields.Integer(
        string='Requests',
        compute='_compute_material_request_count',
    )

    # ── Vendor / Date ─────────────────────────────────────────────────────────

    vendor_id = fields.Many2one(
        comodel_name='res.partner',
        string='Vendor',
        ondelete='set null',
        tracking=True,
        domain=[('supplier_rank', '>', 0)],
    )
    procurement_date = fields.Date(
        string='Procurement Date',
        default=fields.Date.context_today,
        required=True,
        tracking=True,
    )

    # ── PO linkage ────────────────────────────────────────────────────────────

    purchase_order_id = fields.Many2one(
        comodel_name='purchase.order',
        string='Purchase Order',
        ondelete='set null',
        copy=False,
        tracking=True,
    )
    purchase_order_state = fields.Char(
        string='PO Status',
        compute='_compute_po_info',
    )
    picking_count = fields.Integer(
        string='Receipts',
        compute='_compute_po_info',
    )

    # ── State ─────────────────────────────────────────────────────────────────

    state = fields.Selection(
        selection=[
            ('draft',              'Draft'),
            ('rfq',                'RFQ'),
            ('ordered',            'Ordered'),
            ('partially_received', 'Partially Received'),
            ('fully_received',     'Fully Received'),
            ('cancelled',          'Cancelled'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
        copy=False,
    )

    # ── Lines ─────────────────────────────────────────────────────────────────

    line_ids = fields.One2many(
        comodel_name='construction.procurement.line',
        inverse_name='procurement_id',
        string='Procurement Lines',
    )
    line_count = fields.Integer(
        string='Lines',
        compute='_compute_line_count',
    )

    # ── Financial totals ──────────────────────────────────────────────────────

    total_ordered_qty = fields.Float(
        string='Total Ordered',
        compute='_compute_totals',
        store=True,
        digits=(16, 4),
    )
    total_received_qty = fields.Float(
        string='Total Received',
        compute='_compute_totals',
        store=True,
        digits=(16, 4),
    )
    total_price = fields.Float(
        string='Total Value',
        compute='_compute_totals',
        store=True,
        digits=(16, 4),
    )

    # ── Notes ─────────────────────────────────────────────────────────────────

    notes = fields.Html(string='Notes')

    # ── Computes ──────────────────────────────────────────────────────────────

    @api.depends('material_request_ids')
    def _compute_material_request_count(self):
        for rec in self:
            rec.material_request_count = len(rec.material_request_ids)

    @api.depends('line_ids')
    def _compute_line_count(self):
        for rec in self:
            rec.line_count = len(rec.line_ids)

    @api.depends(
        'line_ids.ordered_qty',
        'line_ids.received_qty',
        'line_ids.total_price',
    )
    def _compute_totals(self):
        for rec in self:
            lines = rec.line_ids
            rec.total_ordered_qty = sum(lines.mapped('ordered_qty'))
            rec.total_received_qty = sum(lines.mapped('received_qty'))
            rec.total_price = sum(lines.mapped('total_price'))

    @api.depends('purchase_order_id', 'purchase_order_id.state',
                 'purchase_order_id.picking_ids')
    def _compute_po_info(self):
        for rec in self:
            if rec.purchase_order_id:
                po = rec.purchase_order_id
                state_map = {
                    'draft': 'RFQ',
                    'sent': 'RFQ Sent',
                    'to approve': 'To Approve',
                    'purchase': 'Purchase Order',
                    'done': 'Locked',
                    'cancel': 'Cancelled',
                }
                rec.purchase_order_state = state_map.get(po.state, po.state)
                rec.picking_count = len(po.picking_ids)
            else:
                rec.purchase_order_state = ''
                rec.picking_count = 0

    # ── ORM ───────────────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'construction.procurement'
                ) or _('New')
        return super().create(vals_list)

    # ── State transitions ─────────────────────────────────────────────────────

    def action_cancel(self):
        for rec in self:
            if rec.purchase_order_id and rec.purchase_order_id.state == 'purchase':
                raise UserError(
                    _('Cannot cancel procurement "%s": the linked Purchase Order is '
                      'already confirmed. Cancel the PO first.') % rec.name
                )
        self.write({'state': 'cancelled'})

    def action_reset_draft(self):
        self.write({'state': 'draft'})

    def action_sync_from_po(self):
        """
        Refresh procurement state by reading the current PO / receipt state.
        Call this after confirming a PO or validating a receipt.
        """
        for rec in self:
            if not rec.purchase_order_id:
                continue
            po = rec.purchase_order_id
            # Refresh received_qty on all lines from PO lines
            for line in rec.line_ids:
                if line.purchase_order_line_id:
                    line.received_qty = line.purchase_order_line_id.qty_received
            # Sync individual line states from receipt_status
            for line in rec.line_ids.filtered(lambda l: l.state != 'cancelled'):
                rs = line.receipt_status
                if rs == 'fully_received':
                    line.state = 'fully_received'
                elif rs == 'partially_received':
                    line.state = 'partially_received'
                elif po.state in ('purchase', 'done'):
                    line.state = 'ordered'

            # Derive header state from PO
            if po.state in ('draft', 'sent'):
                rec.state = 'rfq'
            elif po.state in ('purchase', 'done'):
                lines = rec.line_ids.filtered(lambda l: l.state != 'cancelled')
                if all(l.receipt_status == 'fully_received' for l in lines):
                    rec.state = 'fully_received'
                elif any(l.receipt_status != 'not_received' for l in lines):
                    rec.state = 'partially_received'
                else:
                    rec.state = 'ordered'
            elif po.state == 'cancel':
                rec.state = 'cancelled'
        return True

    # ── RFQ / PO creation ────────────────────────────────────────────────────

    def action_create_rfq(self):
        """
        Create a native purchase.order (RFQ) from this procurement record.
        Requires vendor to be set and at least one line.
        """
        self.ensure_one()
        if not self.vendor_id:
            raise UserError(
                _('Please set a Vendor before creating the RFQ.')
            )
        if not self.line_ids:
            raise UserError(
                _('Cannot create RFQ: procurement "%s" has no lines.') % self.name
            )
        if self.purchase_order_id:
            raise UserError(
                _('A Purchase Order already exists for this procurement: %s')
                % self.purchase_order_id.name
            )

        # Build analytic distribution if project has analytic account
        analytic_distribution = {}
        proj = self.project_id
        if proj.analytic_account_id:
            analytic_distribution = {str(proj.analytic_account_id.id): 100}

        # Create PO header
        po_vals = {
            'partner_id': self.vendor_id.id,
            'date_order': fields.Datetime.now(),
            'company_id': proj.company_id.id,
            'notes': 'Generated from Construction Procurement %s — %s' % (
                self.name, proj.name,
            ),
        }
        po = self.env['purchase.order'].sudo().create(po_vals)

        # Create PO lines
        for line in self.line_ids.filtered(lambda l: l.state != 'cancelled'):
            product = line.product_id
            uom = (product.uom_po_id or product.uom_id)
            pol_vals = {
                'order_id': po.id,
                'product_id': product.id,
                'name': line.description or product.display_name,
                'product_qty': line.ordered_qty,
                'product_uom': uom.id if uom else False,
                'price_unit': line.unit_price,
                'date_planned': self.procurement_date,
            }
            if analytic_distribution:
                pol_vals['analytic_distribution'] = analytic_distribution
            pol = self.env['purchase.order.line'].sudo().create(pol_vals)
            line.write({
                'purchase_order_line_id': pol.id,
                'state': 'rfq',
            })

        # Link PO back to procurement
        self.write({
            'purchase_order_id': po.id,
            'state': 'rfq',
        })
        # Update linked material requests
        self.material_request_ids.write({'state': 'converted_to_procurement'})

        return {
            'type': 'ir.actions.act_window',
            'name': _('Purchase Order'),
            'res_model': 'purchase.order',
            'view_mode': 'form',
            'res_id': po.id,
        }

    # ── Smart button actions ──────────────────────────────────────────────────

    def action_open_purchase_order(self):
        self.ensure_one()
        if not self.purchase_order_id:
            return {}
        return {
            'type': 'ir.actions.act_window',
            'name': _('Purchase Order'),
            'res_model': 'purchase.order',
            'view_mode': 'form',
            'res_id': self.purchase_order_id.id,
        }

    def action_open_receipts(self):
        self.ensure_one()
        if not self.purchase_order_id:
            return {}
        pickings = self.purchase_order_id.picking_ids
        return {
            'type': 'ir.actions.act_window',
            'name': _('Receipts — %s') % self.name,
            'res_model': 'stock.picking',
            'view_mode': 'list,form',
            'domain': [('id', 'in', pickings.ids)],
        }

    def action_open_material_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Material Requests — %s') % self.name,
            'res_model': 'construction.material.request',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.material_request_ids.ids)],
        }
