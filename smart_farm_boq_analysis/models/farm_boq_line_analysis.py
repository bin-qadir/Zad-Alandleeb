from odoo import api, fields, models
from odoo.exceptions import ValidationError


class FarmBoqLineAnalysis(models.Model):
    _name = 'farm.boq.line.analysis'
    _description = 'BOQ Line Analysis'
    _order = 'date desc, id desc'

    # ── Identity ──────────────────────────────────────────────────────────────
    name = fields.Char(string='Analysis Name', required=True)
    boq_line_id = fields.Many2one(
        comodel_name='farm.boq.line',
        string='BOQ Line',
        required=True,
        ondelete='cascade',
        index=True,
    )
    # Context passthrough — no DB columns
    boq_id = fields.Many2one(
        comodel_name='farm.boq',
        string='BOQ Document',
        related='boq_line_id.boq_id',
        store=False,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='boq_line_id.currency_id',
        store=False,
    )
    date = fields.Date(string='Date', default=fields.Date.today)
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('analysis', 'Analysis'),
            ('reviewed', 'Reviewed'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
            ('final', 'Final'),
        ],
        string='Status',
        default='draft',
        required=True,
    )

    # ── Quantity Tracking ─────────────────────────────────────────────────────
    boq_qty = fields.Float(
        string='BOQ Qty',
        related='boq_line_id.boq_qty',
        store=False,
    )
    requested_qty = fields.Float(string='Requested Qty')
    executed_qty = fields.Float(string='Executed Qty')
    approved_qty = fields.Float(string='Approved Qty')
    invoiced_qty = fields.Float(string='Invoiced Qty')

    # ── Financial Analysis ────────────────────────────────────────────────────
    cost_unit_price = fields.Float(string='Cost Unit Price', digits=(16, 4))
    cost_total = fields.Float(
        string='Cost Total',
        compute='_compute_financials',
        store=True,
    )
    sale_unit_price = fields.Float(string='Sale Unit Price', digits=(16, 4))
    sale_total = fields.Float(
        string='Sale Total',
        compute='_compute_financials',
        store=True,
    )
    profit = fields.Float(
        string='Profit',
        compute='_compute_financials',
        store=True,
    )
    margin_percent = fields.Float(
        string='Margin (%)',
        compute='_compute_financials',
        store=True,
        digits=(16, 2),
    )

    # ── Approval ──────────────────────────────────────────────────────────────
    approved_by = fields.Many2one(
        comodel_name='res.users',
        string='Approved By',
        readonly=True,
        copy=False,
    )
    approved_date = fields.Datetime(
        string='Approved Date',
        readonly=True,
        copy=False,
    )
    notes = fields.Text(string='Notes')

    # ────────────────────────────────────────────────────────────────────────
    # Computed
    # ────────────────────────────────────────────────────────────────────────

    @api.depends('boq_qty', 'cost_unit_price', 'sale_unit_price')
    def _compute_financials(self):
        for rec in self:
            rec.cost_total = rec.boq_qty * rec.cost_unit_price
            rec.sale_total = rec.boq_qty * rec.sale_unit_price
            rec.profit = rec.sale_total - rec.cost_total
            rec.margin_percent = (
                (rec.profit / rec.sale_total * 100.0)
                if rec.sale_total
                else 0.0
            )

    # ────────────────────────────────────────────────────────────────────────
    # Constraints
    # ────────────────────────────────────────────────────────────────────────

    @api.constrains('state', 'boq_line_id')
    def _check_single_final(self):
        for rec in self:
            if rec.state == 'final':
                duplicate = self.search([
                    ('boq_line_id', '=', rec.boq_line_id.id),
                    ('state', '=', 'final'),
                    ('id', '!=', rec.id),
                ])
                if duplicate:
                    raise ValidationError(
                        'BOQ Line "%s" already has a Final analysis. '
                        'Only one Final analysis is allowed per BOQ line.'
                        % rec.boq_line_id.display_code
                    )

    # ────────────────────────────────────────────────────────────────────────
    # Workflow actions
    # ────────────────────────────────────────────────────────────────────────

    def action_set_analysis(self):
        self.filtered(lambda r: r.state == 'draft').write({'state': 'analysis'})

    def action_review(self):
        self.filtered(lambda r: r.state == 'analysis').write({'state': 'reviewed'})

    def action_approve(self):
        approved = self.filtered(lambda r: r.state == 'reviewed')
        approved.write({
            'state': 'approved',
            'approved_by': self.env.user.id,
            'approved_date': fields.Datetime.now(),
        })
        # Write sale_unit_price back to the linked BOQ line and lock it
        for rec in approved:
            if rec.boq_line_id and not rec.boq_line_id.display_type:
                rec.boq_line_id.sudo().write({
                    'unit_price': rec.sale_unit_price,
                    'boq_state': 'approved',
                })

    def action_reject(self):
        self.filtered(lambda r: r.state not in ('rejected', 'final')).write(
            {'state': 'rejected'}
        )

    def action_set_final(self):
        """Promote to Final.  Demotes any other Final on the same BOQ line
        back to Approved so the one-final constraint is always satisfied.
        """
        for rec in self.filtered(lambda r: r.state == 'approved'):
            existing = self.search([
                ('boq_line_id', '=', rec.boq_line_id.id),
                ('state', '=', 'final'),
                ('id', '!=', rec.id),
            ])
            if existing:
                existing.write({'state': 'approved'})
            rec.write({'state': 'final'})
