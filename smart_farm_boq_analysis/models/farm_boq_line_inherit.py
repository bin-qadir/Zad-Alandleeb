from odoo import api, fields, models


class FarmBoqLine(models.Model):
    """Extend farm.boq.line with analysis records and actuals tracking.

    ## Pricing responsibility

    This module owns the BOQ-level pricing fields on farm.boq.line:

        unit_price  = sale_unit_price from the final/approved analysis
        cost_total  = cost_unit_price * boq_qty  (from approved/final analysis)
        total       = boq_qty * unit_price        (base model _compute_total)

    These override any prior definitions from smart_farm_costing because
    this module is loaded after it (analysis depends on costing).

    ## Actuals tracking

    actual_* fields pull from the single 'final' analysis record so
    management can compare budgeted vs executed quantities/costs.
    """

    _inherit = 'farm.boq.line'

    # ── Analysis records ─────────────────────────────────────────────────────
    analysis_ids = fields.One2many(
        comodel_name='farm.boq.line.analysis',
        inverse_name='boq_line_id',
        string='Analysis',
    )
    analysis_count = fields.Integer(
        string='Analysis Count',
        compute='_compute_analysis_count',
    )
    analysis_state = fields.Selection(
        selection=[
            ('no_analysis', 'No Analysis'),
            ('draft',       'Draft'),
            ('analysis',    'In Analysis'),
            ('reviewed',    'Reviewed'),
            ('approved',    'Approved'),
        ],
        string='Analysis Status',
        compute='_compute_analysis_state',
        store=True,
    )

    # ── BOQ pricing — owned by this module, driven by analysis ────────────────
    # unit_price overrides the plain Float defined in the base model.
    # readonly=False allows action_approve() (on analysis lines) to write
    # directly.  The compute still fires on per-line analysis state changes
    # BUT skips records whose boq_state is 'approved' (price locked).
    unit_price = fields.Float(
        string='Unit Price',
        compute='_compute_unit_price_from_analysis',
        store=True,
        readonly=False,
        digits=(16, 6),
        help='Sale unit price — set by approved analysis or entered manually.',
    )

    # cost_total reflects the planned cost (cost_unit_price * boq_qty) from the
    # approved/final analysis.  Used for the difference_amount calculation.
    cost_total = fields.Float(
        string='Cost Total',
        compute='_compute_cost_total_from_analysis',
        store=True,
        digits=(16, 2),
        help='Cost total from the final or approved analysis (cost_unit_price × boq_qty).',
    )

    # ── Actuals — derived from the "Final" analysis record for this line ──────
    actual_requested_qty = fields.Float(
        string='Actual Requested Qty',
        compute='_compute_actuals',
        store=True,
        digits=(16, 3),
    )
    actual_po_qty = fields.Float(
        string='Actual PO Qty',
        compute='_compute_actuals',
        store=True,
        digits=(16, 3),
    )
    actual_vendor_bill = fields.Float(
        string='Actual Vendor Bill',
        compute='_compute_actuals',
        store=True,
        digits=(16, 2),
        help='Cost total from the Final analysis record.',
    )
    actual_invoiced_qty = fields.Float(
        string='Actual Customer Invoiced Qty',
        compute='_compute_actuals',
        store=True,
        digits=(16, 3),
    )

    # ── Cost unit price — pulled from analysis, displayed read-only in BOQ ──────
    # Mirrors cost_unit_price from the final/approved per-line analysis so the
    # BOQ Structure view can show it alongside unit_price (sale) without allowing
    # edits from the BOQ side.  Editing only happens inside BOQ Analysis.
    cost_unit_price = fields.Float(
        string='Cost Unit Price',
        compute='_compute_cost_unit_price_from_analysis',
        store=True,
        digits=(16, 4),
        help='Cost per unit from the final/approved per-line analysis. Read-only in BOQ.',
    )

    # ── Profit / Margin ──────────────────────────────────────────────────────
    profit = fields.Float(
        string='Profit',
        compute='_compute_profit_margin',
        store=True,
        digits=(16, 2),
        help='Sale total minus cost total.',
    )
    margin = fields.Float(
        string='Margin (%)',
        compute='_compute_profit_margin',
        store=True,
        digits=(16, 2),
        help='Profit as a percentage of cost total.',
    )

    # ── Differences (budget vs actual) ───────────────────────────────────────
    difference_amount = fields.Float(
        string='Difference Amount',
        compute='_compute_difference',
        store=True,
        digits=(16, 2),
        help='BOQ cost total minus actual vendor bill.',
    )
    difference_per_qty = fields.Float(
        string='Diff. / Item Qty',
        compute='_compute_difference',
        store=True,
        digits=(16, 4),
        help='Difference amount divided by item quantity.',
    )

    # ────────────────────────────────────────────────────────────────────────
    # Computed
    # ────────────────────────────────────────────────────────────────────────

    @api.depends('analysis_ids')
    def _compute_analysis_count(self):
        for rec in self:
            rec.analysis_count = len(rec.analysis_ids)

    @api.depends('analysis_ids.state', 'display_type', 'parent_id')
    def _compute_analysis_state(self):
        """Summarise all analysis records into one status value per subitem.

        Priority (highest wins):
            final / approved → 'approved'
            reviewed         → 'reviewed'
            analysis         → 'analysis'
            draft            → 'draft'
            (no records)     → 'no_analysis'

        Non-subitems (sections / subdivisions) receive False.
        """
        for rec in self:
            if rec.display_type or not rec.parent_id:
                rec.analysis_state = False
                continue
            if not rec.analysis_ids:
                rec.analysis_state = 'no_analysis'
                continue
            states = set(rec.analysis_ids.mapped('state'))
            if states & {'final', 'approved'}:
                rec.analysis_state = 'approved'
            elif 'reviewed' in states:
                rec.analysis_state = 'reviewed'
            elif 'analysis' in states:
                rec.analysis_state = 'analysis'
            else:
                rec.analysis_state = 'draft'

    @api.depends('analysis_ids.state', 'analysis_ids.sale_unit_price',
                 'display_type', 'parent_id', 'boq_state')
    def _compute_unit_price_from_analysis(self):
        """unit_price = sale_unit_price from final/approved per-line analysis.

        Skips records whose boq_state is 'approved' so that a price written
        by an analysis approval action is not overwritten by this compute.
        """
        for rec in self:
            if rec.display_type or not rec.parent_id:
                rec.unit_price = 0.0
                continue
            # Price locked by an approval action — preserve the stored value
            if rec.boq_state == 'approved':
                continue
            final = rec.analysis_ids.filtered(lambda a: a.state == 'final')[:1]
            if not final:
                final = rec.analysis_ids.filtered(lambda a: a.state == 'approved')[:1]
            rec.unit_price = final.sale_unit_price if final else 0.0

    @api.depends('analysis_ids.state', 'analysis_ids.cost_total', 'display_type', 'parent_id')
    def _compute_cost_total_from_analysis(self):
        """cost_total = cost_unit_price × boq_qty from final/approved analysis."""
        for rec in self:
            if rec.display_type or not rec.parent_id:
                rec.cost_total = 0.0
                continue
            final = rec.analysis_ids.filtered(lambda a: a.state == 'final')[:1]
            if not final:
                final = rec.analysis_ids.filtered(lambda a: a.state == 'approved')[:1]
            rec.cost_total = final.cost_total if final else 0.0

    @api.depends('analysis_ids.state', 'analysis_ids.cost_unit_price',
                 'display_type', 'parent_id')
    def _compute_cost_unit_price_from_analysis(self):
        """cost_unit_price from final/approved per-line analysis."""
        for rec in self:
            if rec.display_type or not rec.parent_id:
                rec.cost_unit_price = 0.0
                continue
            final = rec.analysis_ids.filtered(lambda a: a.state == 'final')[:1]
            if not final:
                final = rec.analysis_ids.filtered(lambda a: a.state == 'approved')[:1]
            rec.cost_unit_price = final.cost_unit_price if final else 0.0

    @api.depends('total', 'cost_total', 'display_type', 'parent_id')
    def _compute_profit_margin(self):
        for rec in self:
            if rec.display_type or not rec.parent_id:
                rec.profit = rec.margin = 0.0
                continue
            rec.profit = (rec.total or 0.0) - (rec.cost_total or 0.0)
            rec.margin = (rec.profit / rec.cost_total * 100.0) if rec.cost_total else 0.0

    @api.depends(
        'analysis_ids.state',
        'analysis_ids.requested_qty',
        'analysis_ids.approved_qty',
        'analysis_ids.cost_total',
        'analysis_ids.invoiced_qty',
    )
    def _compute_actuals(self):
        """Pull actuals from the single 'final' analysis record (if any)."""
        for rec in self:
            final = rec.analysis_ids.filtered(lambda a: a.state == 'final')[:1]
            rec.actual_requested_qty = final.requested_qty if final else 0.0
            rec.actual_po_qty = final.approved_qty if final else 0.0
            rec.actual_vendor_bill = final.cost_total if final else 0.0
            rec.actual_invoiced_qty = final.invoiced_qty if final else 0.0

    @api.depends('cost_total', 'actual_vendor_bill', 'quantity')
    def _compute_difference(self):
        for rec in self:
            if rec.display_type:
                rec.difference_amount = 0.0
                rec.difference_per_qty = 0.0
                continue
            rec.difference_amount = (rec.cost_total or 0.0) - (rec.actual_vendor_bill or 0.0)
            qty = rec.quantity or 0.0
            rec.difference_per_qty = rec.difference_amount / qty if qty else 0.0

    # ────────────────────────────────────────────────────────────────────────
    # Actions
    # ────────────────────────────────────────────────────────────────────────

    def action_open_boq_analysis(self):
        """Navigate to the BOQ Analysis document for the parent BOQ.

        Used by the 'Edit Pricing' button in the BOQ Structure list so users
        can jump straight to the document-level pricing screen without hunting
        through menus.  Delegates to the BOQ's own action_open_doc_analysis
        which creates the analysis on-the-fly if it doesn't exist yet.
        """
        self.ensure_one()
        return self.boq_id.action_open_doc_analysis()

    def action_open_analysis(self):
        """Open the Analysis screen for this subitem.

        Behaviour:
        • 0 analyses  → create a new draft analysis and open its form
        • 1 analysis  → open that form directly
        • 2+ analyses → open the list filtered to this subitem
        """
        self.ensure_one()
        Analysis = self.env['farm.boq.line.analysis']

        if not self.analysis_ids:
            analysis = Analysis.create({
                'name': f'{self.display_code or self.name} — Analysis',
                'boq_line_id': self.id,
            })
            return {
                'type': 'ir.actions.act_window',
                'name': 'BOQ Analysis',
                'res_model': 'farm.boq.line.analysis',
                'res_id': analysis.id,
                'view_mode': 'form',
                'target': 'new',
                'context': {'default_boq_line_id': self.id},
            }

        if len(self.analysis_ids) == 1:
            return {
                'type': 'ir.actions.act_window',
                'name': 'BOQ Analysis',
                'res_model': 'farm.boq.line.analysis',
                'res_id': self.analysis_ids[0].id,
                'view_mode': 'form',
                'target': 'new',
                'context': {'default_boq_line_id': self.id},
            }

        return {
            'type': 'ir.actions.act_window',
            'name': 'BOQ Analysis',
            'res_model': 'farm.boq.line.analysis',
            'view_mode': 'list,form',
            'domain': [('boq_line_id', '=', self.id)],
            'target': 'new',
            'context': {'default_boq_line_id': self.id},
        }
