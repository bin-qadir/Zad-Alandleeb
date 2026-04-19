from odoo import _, api, fields, models
from odoo.exceptions import UserError


class FarmBoq(models.Model):
    """Extend farm.boq with:

    1. Analysis-aware approval guard — prevents approval unless every real
       subitem has at least one approved/final per-line analysis record.

    2. BOQ Analysis document link — ``doc_analysis_ids`` / ``doc_analysis_count``
       for the document-level Analysis (farm.boq.analysis) smart button, plus
       ``action_open_doc_analysis`` to open or create it.
    """

    _inherit = 'farm.boq'

    # ── Document-level Analysis (farm.boq.analysis) ───────────────────────────
    doc_analysis_ids = fields.One2many(
        'farm.boq.analysis',
        'boq_id',
        string='BOQ Analysis Documents',
    )
    doc_analysis_count = fields.Integer(
        string='Analysis Documents',
        compute='_compute_doc_analysis_count',
    )

    # ── Analysis line status counters (for Overview dashboard) ───────────────
    analysis_line_count = fields.Integer(
        string='Total Analysis Lines',
        compute='_compute_analysis_line_counts',
        store=True,
    )
    analysis_line_approved_count = fields.Integer(
        string='Approved Lines',
        compute='_compute_analysis_line_counts',
        store=True,
    )
    analysis_line_review_count = fields.Integer(
        string='Lines in Review',
        compute='_compute_analysis_line_counts',
        store=True,
    )
    analysis_line_draft_count = fields.Integer(
        string='Draft Lines',
        compute='_compute_analysis_line_counts',
        store=True,
    )

    # ── Financial totals — read-only, driven by the linked Analysis doc ─────────
    # Owned by this module; pulled from farm.boq.analysis so that the BOQ
    # dashboard shows the full cost/sale/profit picture without duplicating data.
    total_cost = fields.Float(
        string='Total Cost',
        compute='_compute_financial_from_analysis',
        store=True,
        digits=(16, 2),
        help='Total cost pulled from the linked BOQ Analysis document.',
    )
    total_sale = fields.Float(
        string='Total Sale',
        compute='_compute_financial_from_analysis',
        store=True,
        digits=(16, 2),
        help='Total sale pulled from the linked BOQ Analysis document.',
    )
    total_profit = fields.Float(
        string='Total Profit',
        compute='_compute_financial_from_analysis',
        store=True,
        digits=(16, 2),
        help='Profit (sale − cost) from the linked BOQ Analysis document.',
    )
    margin = fields.Float(
        string='Margin (%)',
        compute='_compute_financial_from_analysis',
        store=True,
        digits=(16, 2),
        help='Profit as % of cost from the linked BOQ Analysis document.',
    )

    # ── Subitem analysis coverage (for Alerts section) ────────────────────────
    subitem_no_analysis_count = fields.Integer(
        string='Items Without Analysis',
        compute='_compute_subitem_no_analysis_count',
        store=True,
        help='Subitems that have no analysis record at all.',
    )

    @api.depends(
        'doc_analysis_ids.total_cost',
        'doc_analysis_ids.total_sale',
        'doc_analysis_ids.total_profit',
        'doc_analysis_ids.total_margin',
    )
    def _compute_financial_from_analysis(self):
        """Pull financial totals from the linked BOQ Analysis document (1:1)."""
        for rec in self:
            analysis = rec.doc_analysis_ids[:1]
            if analysis:
                rec.total_cost   = analysis.total_cost
                rec.total_sale   = analysis.total_sale
                rec.total_profit = analysis.total_profit
                rec.margin       = analysis.total_margin
            else:
                rec.total_cost = rec.total_sale = rec.total_profit = rec.margin = 0.0

    @api.depends('doc_analysis_ids')
    def _compute_doc_analysis_count(self):
        for rec in self:
            rec.doc_analysis_count = len(rec.doc_analysis_ids)

    @api.depends('line_ids.analysis_state', 'line_ids.display_type', 'line_ids.parent_id')
    def _compute_subitem_no_analysis_count(self):
        for rec in self:
            subitems = rec.line_ids.filtered(
                lambda l: not l.display_type and l.parent_id
            )
            rec.subitem_no_analysis_count = len(
                subitems.filtered(lambda l: l.analysis_state == 'no_analysis')
            )

    def action_open_no_analysis_items(self):
        """Open structure filtered to subitems with analysis in draft state.

        Once a user creates an analysis for a 'no_analysis' subitem the line
        moves to 'draft'.  This action therefore shows all subitems that have
        been started but not yet progressed beyond draft — the next action
        point after the alert fires.
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Items with Draft Analysis — %s') % self.name,
            'res_model': 'farm.boq.line',
            'view_mode': 'list,form',
            'domain': [
                ('boq_id', '=', self.id),
                ('display_type', '=', False),
                ('parent_id', '!=', False),
                ('analysis_state', '=', 'draft'),
            ],
            'context': {'default_boq_id': self.id},
        }

    def action_open_draft_items(self):
        """Open structure filtered to subitems still in draft pricing."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Draft Items — %s') % self.name,
            'res_model': 'farm.boq.line',
            'view_mode': 'list,form',
            'domain': [
                ('boq_id', '=', self.id),
                ('display_type', '=', False),
                ('parent_id', '!=', False),
                ('boq_state', '=', 'draft'),
            ],
            'context': {'default_boq_id': self.id},
        }

    @api.depends(
        'doc_analysis_ids.line_ids.analysis_state',
    )
    def _compute_analysis_line_counts(self):
        for rec in self:
            lines = rec.doc_analysis_ids.mapped('line_ids')
            rec.analysis_line_count         = len(lines)
            rec.analysis_line_approved_count = len(lines.filtered(
                lambda l: l.analysis_state == 'approved'
            ))
            rec.analysis_line_review_count   = len(lines.filtered(
                lambda l: l.analysis_state == 'review'
            ))
            rec.analysis_line_draft_count    = len(lines.filtered(
                lambda l: l.analysis_state == 'draft'
            ))

    # ────────────────────────────────────────────────────────────────────────
    # Action: Open / Create BOQ Analysis document
    # ────────────────────────────────────────────────────────────────────────

    def action_open_doc_analysis(self):
        """Open the single BOQ Analysis for this BOQ.

        The DB-level UNIQUE(boq_id) constraint guarantees at most one Analysis
        per BOQ.  This method therefore has exactly two cases:

        • Analysis exists → open its form view.
        • No analysis yet → create one (auto-loads BOQ subitems via
          ``_load_boq_lines``), then open the new form.
        """
        self.ensure_one()

        analysis = self.env['farm.boq.analysis'].search(
            [('boq_id', '=', self.id)], limit=1,
        )

        if not analysis:
            # _load_boq_lines() is called automatically in create()
            analysis = self.env['farm.boq.analysis'].create({
                'boq_id': self.id,
            })

        return {
            'type': 'ir.actions.act_window',
            'name': _('B.O.Q Analysis — %s') % self.name,
            'res_model': 'farm.boq.analysis',
            'res_id': analysis.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ────────────────────────────────────────────────────────────────────────
    # Helpers
    # ────────────────────────────────────────────────────────────────────────

    def _assert_all_subitems_analysed(self):
        """Raise UserError if any subitem lacks an approved/final analysis."""
        for rec in self:
            subitems = rec.line_ids.filtered(
                lambda l: not l.display_type and l.parent_id
            )
            if not subitems:
                continue  # no subitems at all — allow

            not_approved = subitems.filtered(
                lambda l: l.analysis_state != 'approved'
            )
            if not not_approved:
                continue

            codes = ', '.join(
                filter(None, not_approved[:5].mapped('display_code'))
            ) or '(unknown)'
            extra = f' + {len(not_approved) - 5} more' if len(not_approved) > 5 else ''
            raise UserError(_(
                'Cannot approve BOQ "%(boq)s".\n\n'
                '%(n)d subitem(s) do not yet have an approved analysis:\n'
                '%(codes)s%(extra)s\n\n'
                'Open each subitem, go to the Analysis screen, complete and '
                'approve the analysis before approving the BOQ.',
                boq=rec.name,
                n=len(not_approved),
                codes=codes,
                extra=extra,
            ))

    # ────────────────────────────────────────────────────────────────────────
    # Workflow override
    # ────────────────────────────────────────────────────────────────────────

    def action_approve(self):
        """Submitted → Approved — only if all subitems are analysed."""
        self._assert_all_subitems_analysed()
        return super().action_approve()

    def write(self, vals):
        """Also guard the state=approved path via clickable statusbar."""
        if vals.get('state') == 'approved':
            self._assert_all_subitems_analysed()
        return super().write(vals)
