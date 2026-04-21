from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class FarmMaterialRequest(models.Model):
    """Material Request — procurement trigger linked to a Job Order and BOQ.

    Workflow:
        draft  → to_approve  (Submit to PM)
        to_approve → approved  (PM Approve)  → PO auto-created
        to_approve → rejected  (PM Reject)
        approved   → rfq       (PO in draft/sent)
        rfq        → ordered   (PO confirmed)
        ordered    → received  (all lines fully received)

    Cost link:
        Each line carries boq_line_id, contract_qty, remaining_qty.
        On receipt, received_qty and actual_cost are updated from the PO.
    """

    _name        = 'farm.material.request'
    _description = 'Material Request'
    _order       = 'request_date desc, name desc'
    _rec_name    = 'name'
    _inherit     = ['mail.thread', 'mail.activity.mixin']

    # ── Identity ──────────────────────────────────────────────────────────────
    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
        tracking=True,
    )

    # ── Project / JO link ─────────────────────────────────────────────────────
    project_id = fields.Many2one(
        'farm.project',
        string='Farm Project',
        required=True,
        ondelete='restrict',
        index=True,
        tracking=True,
    )
    job_order_id = fields.Many2one(
        'farm.job.order',
        string='Job Order',
        ondelete='set null',
        index=True,
        domain="[('project_id', '=', project_id)]",
        tracking=True,
        help='Optional: link this request to a specific Job Order for traceability.',
    )

    # ── State ─────────────────────────────────────────────────────────────────
    state = fields.Selection(
        selection=[
            ('draft',      'Draft'),
            ('to_approve', 'Pending Approval'),
            ('approved',   'Approved'),
            ('rejected',   'Rejected'),
            ('rfq',        'RFQ Sent'),
            ('ordered',    'Ordered'),
            ('received',   'Received'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
        copy=False,
    )

    # ── Who / When ────────────────────────────────────────────────────────────
    requested_by = fields.Many2one(
        'res.users',
        string='Requested By',
        default=lambda self: self.env.user,
        required=True,
        tracking=True,
        ondelete='restrict',
    )
    request_date = fields.Date(
        string='Request Date',
        default=fields.Date.today,
        required=True,
        tracking=True,
    )
    approved_by = fields.Many2one(
        'res.users',
        string='Approved / Rejected By',
        readonly=True,
        tracking=True,
        ondelete='set null',
        copy=False,
    )
    approval_date = fields.Datetime(
        string='Approval Date',
        readonly=True,
        copy=False,
    )
    rejection_reason = fields.Text(
        string='Rejection Reason',
        copy=False,
        tracking=True,
    )

    # ── Lines ─────────────────────────────────────────────────────────────────
    line_ids = fields.One2many(
        'farm.material.request.line',
        'request_id',
        string='Requested Materials',
        copy=True,
    )

    # ── Purchase Orders ───────────────────────────────────────────────────────
    purchase_order_ids = fields.One2many(
        'purchase.order',
        'material_request_id',
        string='Purchase Orders',
    )
    purchase_order_count = fields.Integer(
        string='PO Count',
        compute='_compute_purchase_order_count',
    )

    # ── Summary KPIs ─────────────────────────────────────────────────────────
    total_estimated_cost = fields.Float(
        string='Total Estimated Cost',
        compute='_compute_totals',
        digits=(16, 2),
        store=True,
    )
    total_received_qty = fields.Float(
        string='Lines Received',
        compute='_compute_totals',
        store=True,
    )
    total_actual_cost = fields.Float(
        string='Total Actual Cost',
        compute='_compute_totals',
        digits=(16, 2),
        store=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='project_id.currency_id',
        string='Currency',
        readonly=True,
    )

    # ── Notes ─────────────────────────────────────────────────────────────────
    notes = fields.Text(string='Internal Notes')

    # ────────────────────────────────────────────────────────────────────────
    # Computed
    # ────────────────────────────────────────────────────────────────────────

    def _compute_purchase_order_count(self):
        for rec in self:
            rec.purchase_order_count = len(rec.purchase_order_ids)

    @api.depends(
        'line_ids.estimated_cost',
        'line_ids.actual_cost',
        'line_ids.received_qty',
    )
    def _compute_totals(self):
        for rec in self:
            rec.total_estimated_cost = sum(rec.line_ids.mapped('estimated_cost'))
            rec.total_actual_cost    = sum(rec.line_ids.mapped('actual_cost'))
            rec.total_received_qty   = sum(rec.line_ids.mapped('received_qty'))

    # ────────────────────────────────────────────────────────────────────────
    # ORM
    # ────────────────────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'farm.material.request'
                ) or _('New')
        return super().create(vals_list)

    # ────────────────────────────────────────────────────────────────────────
    # Workflow actions
    # ────────────────────────────────────────────────────────────────────────

    def action_submit(self):
        """Draft → Pending Approval."""
        for rec in self.filtered(lambda r: r.state == 'draft'):
            if not rec.line_ids:
                raise UserError(_(
                    'Cannot submit "%s": no material lines defined.',
                    rec.name,
                ))
            rec.state = 'to_approve'
            rec.message_post(
                body=_('Material Request submitted for approval by %s.',
                       rec.requested_by.name),
            )

    def action_approve(self):
        """Pending Approval → Approved + auto-create Purchase Order(s)."""
        for rec in self.filtered(lambda r: r.state == 'to_approve'):
            rec.write({
                'state':         'approved',
                'approved_by':   self.env.user.id,
                'approval_date': fields.Datetime.now(),
            })
            po_count = rec._create_purchase_orders()
            rec.message_post(
                body=_(
                    'Approved by %(user)s. %(count)d Purchase Order(s) created.',
                    user=self.env.user.name,
                    count=po_count,
                ),
            )

    def action_reject(self):
        """Pending Approval → Rejected (opens wizard for reason)."""
        self.ensure_one()
        if self.state != 'to_approve':
            raise UserError(_('Only pending requests can be rejected.'))
        return {
            'type':     'ir.actions.act_window',
            'name':     _('Rejection Reason'),
            'res_model': 'farm.material.request.reject.wizard',
            'view_mode': 'form',
            'target':   'new',
            'context':  {'default_request_id': self.id},
        }

    def action_reset_to_draft(self):
        """Allow resetting rejected/draft requests back to Draft."""
        for rec in self.filtered(lambda r: r.state in ('rejected', 'draft')):
            rec.write({
                'state':           'draft',
                'approved_by':     False,
                'approval_date':   False,
                'rejection_reason': False,
            })

    def action_open_purchase_orders(self):
        """Open linked Purchase Orders."""
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Purchase Orders — %s') % self.name,
            'res_model': 'purchase.order',
            'view_mode': 'list,form',
            'domain':    [('material_request_id', '=', self.id)],
            'context':   {
                'default_material_request_id': self.id,
                'default_farm_project_id':     self.project_id.id,
            },
        }

    # ────────────────────────────────────────────────────────────────────────
    # PO creation
    # ────────────────────────────────────────────────────────────────────────

    def _create_purchase_orders(self):
        """Create Purchase Order(s) from approved MR lines.

        Lines are grouped by vendor (partner_id on the line).
        Lines without a vendor are grouped together into a single RFQ
        with no partner set (to be filled in later).

        Returns the number of POs created.
        """
        self.ensure_one()
        PO = self.env['purchase.order']

        # Group lines by vendor
        vendor_map = {}   # partner_id (or False) → [lines]
        for line in self.line_ids.filtered(
            lambda l: l.product_id and l.requested_qty > 0
        ):
            key = line.vendor_id.id if line.vendor_id else False
            vendor_map.setdefault(key, []).append(line)

        if not vendor_map:
            return 0

        po_count = 0
        for partner_id, lines in vendor_map.items():
            po_vals = {
                'partner_id':           partner_id or self.env['res.partner'].search(
                    [('supplier_rank', '>', 0)], limit=1,
                ).id or self.env.company.partner_id.id,
                'farm_project_id':      self.project_id.id,
                'material_request_id':  self.id,
                'order_line':           [],
                'notes':                _('Auto-generated from Material Request %s') % self.name,
            }

            for line in lines:
                uom = line.uom_id or line.product_id.uom_po_id or line.product_id.uom_id
                po_vals['order_line'].append((0, 0, {
                    'product_id':      line.product_id.id,
                    'product_qty':     line.requested_qty,
                    'product_uom':     uom.id,
                    'price_unit':      line.unit_cost or line.product_id.standard_price,
                    'name':            line.product_id.display_name,
                    'mr_line_id':      line.id,
                }))

            po = PO.create(po_vals)
            # Link PO lines back to MR lines
            for po_line in po.order_line:
                mr_line = po_line.mr_line_id
                if mr_line:
                    mr_line.purchase_order_line_id = po_line

            po_count += 1

        # Update state to rfq once POs exist
        if po_count:
            self.state = 'rfq'

        return po_count

    # ────────────────────────────────────────────────────────────────────────
    # State sync from PO
    # ────────────────────────────────────────────────────────────────────────

    def _sync_state_from_po(self):
        """Called when linked PO state changes (from PO inherit)."""
        for rec in self.filtered(lambda r: r.state in ('rfq', 'ordered')):
            po_states = set(rec.purchase_order_ids.mapped('state'))
            if not po_states:
                continue
            # If any PO is confirmed/done → ordered
            if po_states & {'purchase', 'done'}:
                rec.state = 'ordered'
            # If all POs are received → received
            # (check via stock picking state or receipt qty)
            all_received = all(
                ml.received_qty >= ml.requested_qty
                for ml in rec.line_ids
                if ml.requested_qty > 0
            )
            if all_received and rec.state == 'ordered':
                rec.state = 'received'


class FarmMaterialRequestRejectWizard(models.TransientModel):
    """Tiny wizard to capture rejection reason."""

    _name        = 'farm.material.request.reject.wizard'
    _description = 'Reject Material Request'

    request_id = fields.Many2one(
        'farm.material.request',
        string='Material Request',
        required=True,
        ondelete='cascade',
    )
    rejection_reason = fields.Text(
        string='Rejection Reason',
        required=True,
    )

    def action_confirm_reject(self):
        self.ensure_one()
        self.request_id.write({
            'state':            'rejected',
            'approved_by':      self.env.user.id,
            'approval_date':    fields.Datetime.now(),
            'rejection_reason': self.rejection_reason,
        })
        self.request_id.message_post(
            body=_(
                'Rejected by %(user)s. Reason: %(reason)s',
                user=self.env.user.name,
                reason=self.rejection_reason,
            ),
        )
        return {'type': 'ir.actions.act_window_close'}
