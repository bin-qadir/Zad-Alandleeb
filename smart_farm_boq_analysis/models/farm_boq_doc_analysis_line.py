from odoo import api, fields, models


class FarmBoqAnalysisLine(models.Model):
    """BOQ Analysis Line — one row per BOQ line (structural OR subitem).

    After the hierarchy enhancement, analysis lines mirror the full BOQ
    structure:
      row_level 0 — Division     (display_type='line_section')
      row_level 1 — Subdivision  (display_type='line_subsection')
      row_level 2 — Sub-Sub      (display_type='line_sub_subsection')
      row_level 3 — Subitem      (display_type=False, boq_parent_id set)

    Structural rows carry no pricing data (cost_total / sale_total = 0).
    Pricing is entered only on subitem rows.

    _parent_store = True enables the Odoo list-view tree
    (parent_field="boq_parent_id") to show collapsible hierarchy.
    """

    _name         = 'farm.boq.analysis.line'
    _description  = 'BOQ Analysis Line'
    _parent_name  = 'boq_parent_id'
    _parent_store = True
    _order        = 'analysis_id, div_rank, sub_rank, sub_sub_rank, row_level, sequence_sub'

    # ── Hierarchy ─────────────────────────────────────────────────────────────

    boq_parent_id = fields.Many2one(
        'farm.boq.analysis.line',
        string='Parent',
        index=True,
        ondelete='cascade',
    )
    parent_path = fields.Char(index=True)

    row_level = fields.Integer(
        string='Row Level',
        default=3,
        index=True,
        help='0=Division, 1=Subdivision, 2=Sub-Subdivision, 3=Subitem',
    )

    # ── Links ─────────────────────────────────────────────────────────────────

    analysis_id = fields.Many2one(
        'farm.boq.analysis',
        string='Analysis',
        required=True,
        ondelete='cascade',
        index=True,
    )
    # boq_line_id — general link (structural OR subitem)
    boq_line_id = fields.Many2one(
        'farm.boq.line',
        string='BOQ Line',
        ondelete='set null',
        index=True,
    )
    # subitem_id — set only for real subitem rows (row_level=3)
    subitem_id = fields.Many2one(
        'farm.boq.line',
        string='Subitem',
        ondelete='cascade',
        index=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='analysis_id.currency_id',
        store=False,
    )

    # ── Identity ──────────────────────────────────────────────────────────────

    display_code = fields.Char(string='Code')
    name         = fields.Char(string='Name', required=True)

    # ── Display type (mirrors farm.boq.line) ─────────────────────────────────

    display_type = fields.Selection(
        selection=[
            ('line_section',        'Division Section'),
            ('line_subsection',     'Subdivision Section'),
            ('line_sub_subsection', 'Sub-Subdivision Section'),
        ],
        string='Display Type',
        default=False,
    )

    # ── Ordering (mirrors farm.boq.line rank fields for stable sort) ──────────

    div_rank      = fields.Integer(default=0)
    sub_rank      = fields.Integer(default=0)
    sub_sub_rank  = fields.Integer(default=0)
    sequence_main = fields.Integer(default=0)
    sequence_sub  = fields.Integer(default=0)

    # ── BOQ data (read-only — synced from BOQ line) ───────────────────────────

    boq_qty = fields.Float(string='BOQ Qty', digits=(16, 2))
    unit_id = fields.Many2one('uom.uom', string='Unit')

    # ── Pricing (user-entered; subitems only) ─────────────────────────────────

    cost_unit_price = fields.Float(
        string='Cost Unit Price',
        digits=(16, 4),
    )
    sale_unit_price = fields.Float(
        string='Sale Unit Price',
        digits=(16, 4),
    )

    # ── Computed financials (zero for structural rows) ────────────────────────

    cost_total = fields.Float(
        string='Cost Total',
        compute='_compute_financials',
        store=True,
        digits=(16, 2),
    )
    sale_total = fields.Float(
        string='Sale Total',
        compute='_compute_financials',
        store=True,
        digits=(16, 2),
    )
    profit = fields.Float(
        string='Profit',
        compute='_compute_financials',
        store=True,
        digits=(16, 2),
    )
    margin = fields.Float(
        string='Margin (%)',
        compute='_compute_financials',
        store=True,
        digits=(16, 2),
    )

    # ── Analysis status (subitems only) ──────────────────────────────────────

    analysis_state = fields.Selection(
        selection=[
            ('draft',    'Draft'),
            ('review',   'Review'),
            ('approved', 'Approved'),
        ],
        string='Analysis Status',
        default='draft',
        index=True,
        copy=False,
    )

    # ── Linked BOQ line status ────────────────────────────────────────────────

    boq_state = fields.Selection(
        string='BOQ Status',
        related='boq_line_id.boq_state',
        store=False,
    )

    # Legacy parent link — kept for DB compatibility; superseded by boq_parent_id
    parent_id = fields.Many2one(
        'farm.boq.analysis.line',
        string='Legacy Parent',
        ondelete='set null',
        index=True,
    )

    # ────────────────────────────────────────────────────────────────────────
    # Computed
    # ────────────────────────────────────────────────────────────────────────

    @api.depends('boq_qty', 'cost_unit_price', 'sale_unit_price')
    def _compute_financials(self):
        """Structural rows always return 0 (no boq_qty set for them)."""
        for rec in self:
            qty  = rec.boq_qty or 0.0
            cost = qty * (rec.cost_unit_price or 0.0)
            sale = qty * (rec.sale_unit_price or 0.0)
            rec.cost_total = cost
            rec.sale_total = sale
            rec.profit     = sale - cost
            rec.margin     = (rec.profit / cost * 100.0) if cost else 0.0

    # ────────────────────────────────────────────────────────────────────────
    # Workflow actions (subitems only)
    # ────────────────────────────────────────────────────────────────────────

    def action_set_review(self):
        """Draft → Review (subitems only)."""
        self.filtered(
            lambda r: r.analysis_state == 'draft' and not r.display_type
        ).write({'analysis_state': 'review'})

    def action_approve(self):
        """Review → Approved + write back to BOQ line."""
        to_approve = self.filtered(
            lambda r: r.analysis_state == 'review' and not r.display_type
        )
        to_approve.write({'analysis_state': 'approved'})
        for rec in to_approve:
            target = rec.subitem_id or rec.boq_line_id
            if target and not target.display_type:
                target.sudo().write({
                    'unit_price': rec.sale_unit_price,
                    'boq_state':  'approved',
                })

    def action_reset_draft(self):
        """Approved / Review → Draft (subitems only)."""
        self.filtered(
            lambda r: r.analysis_state != 'draft' and not r.display_type
        ).write({'analysis_state': 'draft'})
