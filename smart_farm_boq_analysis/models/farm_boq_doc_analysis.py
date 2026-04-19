import base64
import io

import xlsxwriter

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class FarmBoqDocAnalysis(models.Model):
    """BOQ Analysis Document — prices the Subitems of one BOQ.

    Each BOQ has exactly one Analysis document (enforced by the
    ``boq_unique`` SQL constraint).

    After the hierarchy enhancement, analysis lines now include structural
    rows (division / subdivision / sub-subdivision) so the list view can
    render a collapsible engineering BOQ tree identical to the BOQ Structure.

    Pricing entry (cost_unit_price / sale_unit_price) is on subitem lines
    only — structural rows carry no pricing value.
    """

    _name = 'farm.boq.analysis'
    _description = 'BOQ Analysis Document'
    _order = 'date desc, id desc'
    _rec_name = 'name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    _sql_constraints = [
        (
            'boq_unique',
            'UNIQUE(boq_id)',
            'Only one Analysis document is allowed per BOQ.',
        ),
    ]

    # ── Identity ──────────────────────────────────────────────────────────────

    name = fields.Char(
        string='Analysis Reference',
        required=True,
        copy=False,
        default=lambda self: _('New'),
    )
    boq_id = fields.Many2one(
        'farm.boq',
        string='BOQ Document',
        required=True,
        ondelete='cascade',
        index=True,
    )
    project_id = fields.Many2one(
        'farm.project',
        string='Farm Project',
        related='boq_id.project_id',
        store=True,
        index=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='boq_id.currency_id',
        store=False,
    )
    date  = fields.Date(string='Date', default=fields.Date.today)
    notes = fields.Text(string='Notes')

    # ── Workflow ──────────────────────────────────────────────────────────────

    analysis_state = fields.Selection(
        selection=[
            ('draft',    'Draft'),
            ('review',   'Review'),
            ('approved', 'Approved'),
        ],
        string='Status',
        default='draft',
        required=True,
        index=True,
        tracking=True,
    )

    # ── Lines ─────────────────────────────────────────────────────────────────

    line_ids = fields.One2many(
        'farm.boq.analysis.line',
        'analysis_id',
        string='Analysis Lines',
    )

    # ── Summary totals ────────────────────────────────────────────────────────

    total_cost = fields.Float(
        string='Total Cost',
        compute='_compute_totals',
        store=True,
        digits=(16, 2),
    )
    total_sale = fields.Float(
        string='Total Sale',
        compute='_compute_totals',
        store=True,
        digits=(16, 2),
    )
    total_profit = fields.Float(
        string='Total Profit',
        compute='_compute_totals',
        store=True,
        digits=(16, 2),
    )
    total_margin = fields.Float(
        string='Margin (%)',
        compute='_compute_totals',
        store=True,
        digits=(16, 2),
    )
    item_count = fields.Integer(
        string='Priced Items',
        compute='_compute_totals',
        store=True,
    )

    # ────────────────────────────────────────────────────────────────────────
    # Computed
    # ────────────────────────────────────────────────────────────────────────

    @api.depends('line_ids.cost_total', 'line_ids.sale_total')
    def _compute_totals(self):
        """Only subitem lines (row_level=3) carry pricing."""
        for rec in self:
            sublines = rec.line_ids.filtered(lambda l: not l.display_type)
            rec.total_cost   = sum(sublines.mapped('cost_total'))
            rec.total_sale   = sum(sublines.mapped('sale_total'))
            rec.total_profit = rec.total_sale - rec.total_cost
            rec.total_margin = (
                rec.total_profit / rec.total_cost * 100.0
                if rec.total_cost else 0.0
            )
            rec.item_count = len(sublines.filtered(
                lambda l: l.cost_unit_price or l.sale_unit_price
            ))

    # ────────────────────────────────────────────────────────────────────────
    # ORM overrides
    # ────────────────────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        # Block direct creation — analysis must be initiated from an approved BOQ.
        if not self.env.context.get('from_boq_analysis_create'):
            raise UserError(_(
                'BOQ Analysis cannot be created manually.\n\n'
                'Open an approved B.O.Q document and click '
                '"Open BOQ Analysis" to create the analysis.'
            ))
        seq = self.env['ir.sequence']
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = seq.next_by_code('farm.boq.analysis') or _('New')
        records = super().create(vals_list)
        for rec in records:
            rec._load_boq_lines()
        return records

    # ────────────────────────────────────────────────────────────────────────
    # Core: load / sync BOQ lines (with full structural hierarchy)
    # ────────────────────────────────────────────────────────────────────────

    def _load_boq_lines(self):
        """(Re)sync the full BOQ structure into analysis lines.

        Includes BOTH structural rows (division / subdivision / sub-sub)
        AND real subitem rows so the analysis list view can render a
        collapsible engineering tree.

        Structural rows carry no pricing — they serve as visual headers only.

        Algorithm:
        1. Iterate BOQ lines in natural (rank) order.
        2. Create or update each line, tracking the current structural
           parents as we go (set boq_parent_id immediately on create).
        3. Delete analysis lines whose BOQ line no longer exists.

        Idempotent: safe to call multiple times; pricing on subitems is
        preserved across syncs.
        """
        self.ensure_one()

        # All BOQ lines in natural order (structural + subitems)
        all_boq_lines = self.boq_id.line_ids.sorted(
            lambda l: (l.div_rank, l.sub_rank, l.sub_sub_rank,
                       l.row_level, l.sequence_sub)
        )

        # Existing analysis lines indexed by boq_line_id for fast lookup
        existing_map = {}
        for al in self.line_ids:
            if al.boq_line_id and al.boq_line_id.id not in existing_map:
                existing_map[al.boq_line_id.id] = al

        AnalysisLine = self.env['farm.boq.analysis.line']

        _LEVEL = {
            'line_section':        0,
            'line_subsection':     1,
            'line_sub_subsection': 2,
        }

        wanted_boq_ids   = set()
        current_div_id   = False   # analysis line id of current division
        current_sub_id   = False   # analysis line id of current subdivision
        current_subsub_id= False   # analysis line id of current sub-subdivision

        for bl in all_boq_lines:
            dt          = bl.display_type
            is_section  = bool(dt)
            is_subitem  = not dt and bool(bl.parent_id)

            if not is_section and not is_subitem:
                continue   # legacy item without parent — skip

            wanted_boq_ids.add(bl.id)
            row_level = _LEVEL.get(dt, 3)

            # Parent link based on current trackers (set BEFORE create so
            # _parent_store populates parent_path correctly on the first write)
            if dt == 'line_section':
                parent_al_id = False
            elif dt == 'line_subsection':
                parent_al_id = current_div_id
            elif dt == 'line_sub_subsection':
                parent_al_id = current_sub_id
            else:
                parent_al_id = current_subsub_id

            vals = {
                'boq_line_id':  bl.id,
                'display_code': bl.display_code or '',
                'name':         bl.name or '',
                'display_type': dt or False,
                'row_level':    row_level,
                'div_rank':     bl.div_rank,
                'sub_rank':     bl.sub_rank,
                'sub_sub_rank': bl.sub_sub_rank,
                'sequence_main':bl.sequence_main,
                'sequence_sub': bl.sequence_sub if is_subitem else 0,
                'boq_parent_id':parent_al_id,
            }

            if is_subitem:
                vals['subitem_id'] = bl.id
                vals['boq_qty']    = bl.boq_qty
                vals['unit_id']    = bl.unit_id.id if bl.unit_id else False
            else:
                # Structural rows carry no pricing values
                vals['subitem_id'] = False
                vals['boq_qty']    = 0.0
                vals['unit_id']    = False

            if bl.id in existing_map:
                al = existing_map[bl.id]
                al.write(vals)
            else:
                al = AnalysisLine.create(dict(vals, analysis_id=self.id))

            # Update structural trackers AFTER the record exists
            if dt == 'line_section':
                current_div_id    = al.id
                current_sub_id    = False
                current_subsub_id = False
            elif dt == 'line_subsection':
                current_sub_id    = al.id
                current_subsub_id = False
            elif dt == 'line_sub_subsection':
                current_subsub_id = al.id

        # Remove analysis lines whose BOQ line no longer exists or is no
        # longer a valid structural/subitem row
        obsolete = self.line_ids.filtered(
            lambda l: l.boq_line_id.id not in wanted_boq_ids
        )
        if obsolete:
            obsolete.unlink()

    # ────────────────────────────────────────────────────────────────────────
    # Report data helpers
    # ────────────────────────────────────────────────────────────────────────

    def _get_analysis_report_data(self):
        """Return structured dict for the QWeb PDF report.

        Returns:
        {
          'divisions': [
              {
                'section':        analysis_line (division),
                'rows':           [analysis_line, ...],   # subdiv + subsub + items
                'subtotal_cost':  float,
                'subtotal_sale':  float,
                'subtotal_profit':float,
              },
              ...
          ],
          'total_cost':   float,
          'total_sale':   float,
          'total_profit': float,
          'total_margin': float,
          'currency_symbol': str,
        }
        """
        self.ensure_one()

        lines = self.line_ids.sorted(
            lambda l: (l.div_rank, l.sub_rank, l.sub_sub_rank,
                       l.row_level, l.sequence_sub)
        )

        divisions    = []
        current_div  = None

        for line in lines:
            if line.display_type == 'line_section':
                current_div = {
                    'section':         line,
                    'rows':            [],
                    'subtotal_cost':   0.0,
                    'subtotal_sale':   0.0,
                    'subtotal_profit': 0.0,
                }
                divisions.append(current_div)
            elif current_div is not None:
                current_div['rows'].append(line)
                if not line.display_type:          # subitem only
                    current_div['subtotal_cost']   += line.cost_total
                    current_div['subtotal_sale']   += line.sale_total
                    current_div['subtotal_profit'] += line.profit
            else:
                # Lines before any division (flat / legacy)
                divisions.append({
                    'section':         False,
                    'rows':            [line],
                    'subtotal_cost':   line.cost_total if not line.display_type else 0.0,
                    'subtotal_sale':   line.sale_total if not line.display_type else 0.0,
                    'subtotal_profit': line.profit     if not line.display_type else 0.0,
                })

        return {
            'divisions':       divisions,
            'total_cost':      self.total_cost,
            'total_sale':      self.total_sale,
            'total_profit':    self.total_profit,
            'total_margin':    self.total_margin,
            'currency_symbol': self.currency_id.symbol or '',
        }

    # ────────────────────────────────────────────────────────────────────────
    # Workflow actions
    # ────────────────────────────────────────────────────────────────────────

    def action_review(self):
        for rec in self.filtered(lambda r: r.analysis_state == 'draft'):
            rec.analysis_state = 'review'

    def action_approve(self):
        for rec in self.filtered(lambda r: r.analysis_state == 'review'):
            rec.analysis_state = 'approved'

    def action_reset_draft(self):
        for rec in self.filtered(lambda r: r.analysis_state != 'approved'):
            rec.analysis_state = 'draft'

    # ── Line-level cascade ────────────────────────────────────────────────────

    def action_set_lines_review(self):
        self.ensure_one()
        self.line_ids.action_set_review()

    def action_approve_lines(self):
        self.ensure_one()
        self.line_ids.action_approve()

    def action_reset_lines_draft(self):
        self.ensure_one()
        self.line_ids.action_reset_draft()

    def action_refresh_from_boq(self):
        """Re-sync full BOQ structure without touching pricing data."""
        if self.analysis_state == 'approved':
            raise UserError(_('Cannot refresh an approved Analysis. Reset to Draft first.'))
        self._load_boq_lines()
        return {
            'type': 'ir.actions.client',
            'tag':  'display_notification',
            'params': {
                'title':   _('BOQ Analysis refreshed'),
                'message': _('All BOQ lines have been re-synced (structure + subitems).'),
                'type':    'success',
                'sticky':  False,
            },
        }

    # ────────────────────────────────────────────────────────────────────────
    # PART 1 — PDF Report
    # ────────────────────────────────────────────────────────────────────────

    def action_print_pdf(self):
        """Print the BOQ Analysis as a PDF (QWeb report)."""
        self.ensure_one()
        return self.env.ref(
            'smart_farm_boq_analysis.action_report_boq_analysis_pdf'
        ).report_action(self)

    # ────────────────────────────────────────────────────────────────────────
    # PART 1 — Excel Export (2 sheets)
    # ────────────────────────────────────────────────────────────────────────

    def action_export_excel(self):
        """Generate and download a professional XLSX export of the BOQ Analysis.

        Sheet 1 — Full Analysis: hierarchical rows with all financial columns.
        Sheet 2 — Summary:       per-division cost / sale / profit / margin.
        """
        self.ensure_one()

        output   = io.BytesIO()
        wb       = xlsxwriter.Workbook(output, {'in_memory': True})
        currency = self.currency_id.name or ''

        # ── Common formats ────────────────────────────────────────────────────

        def _fmt(**kw):
            return wb.add_format(kw)

        BASE = dict(font_name='Arial', font_size=10, valign='vcenter')

        fmt_title = _fmt(**BASE, bold=True, font_size=13,
                         align='center', font_color='#FFFFFF',
                         bg_color='#1A3A5C', border=0)

        fmt_meta_lbl = _fmt(**BASE, bold=True, font_color='#555555')
        fmt_meta_val = _fmt(**BASE)

        fmt_col_hdr = _fmt(**BASE, bold=True, font_size=10,
                           bg_color='#1A3A5C', font_color='#FFFFFF',
                           align='center', border=1, border_color='#0D2035',
                           text_wrap=True)
        fmt_col_hdr_r = _fmt(**BASE, bold=True, font_size=10,
                             bg_color='#1A3A5C', font_color='#FFFFFF',
                             align='right', border=1, border_color='#0D2035',
                             text_wrap=True)

        # Division row (beige / bold)
        fmt_div     = _fmt(**BASE, bold=True, font_size=11,
                           bg_color='#EFE2B8', font_color='#000000',
                           border=1, border_color='#C8A84B')
        fmt_div_num = _fmt(**BASE, bold=True, font_size=11,
                           bg_color='#EFE2B8', font_color='#000000',
                           border=1, border_color='#C8A84B',
                           num_format='#,##0.00', align='right')

        # Subdivision row (cream / semi-bold)
        fmt_sub     = _fmt(**BASE, bold=True, font_size=10,
                           bg_color='#FDF9EE', font_color='#000000',
                           border=1, border_color='#E0D5B0', indent=1)
        fmt_sub_num = _fmt(**BASE, font_size=10,
                           bg_color='#FDF9EE', font_color='#000000',
                           border=1, border_color='#E0D5B0',
                           num_format='#,##0.00', align='right')

        # Sub-subdivision row (off-white / italic)
        fmt_subsub     = _fmt(**BASE, italic=True, font_size=10,
                              bg_color='#FFFDF5', font_color='#444444',
                              border=1, border_color='#F0ECD8', indent=2)
        fmt_subsub_num = _fmt(**BASE, font_size=10,
                              bg_color='#FFFDF5', font_color='#444444',
                              border=1, border_color='#F0ECD8',
                              num_format='#,##0.00', align='right')

        # Subitem rows
        fmt_item        = _fmt(**BASE, bg_color='#FFFFFF', font_color='#000000',
                               border=1, border_color='#EEEEEE', indent=3)
        fmt_item_center = _fmt(**BASE, bg_color='#FFFFFF', font_color='#000000',
                               border=1, border_color='#EEEEEE', align='center')
        fmt_item_num    = _fmt(**BASE, bg_color='#FFFFFF', font_color='#000000',
                               border=1, border_color='#EEEEEE',
                               num_format='#,##0.00', align='right')
        fmt_item_pct    = _fmt(**BASE, bg_color='#FFFFFF', font_color='#000000',
                               border=1, border_color='#EEEEEE',
                               num_format='0.00"%"', align='right')

        # Status badge-like colors
        def _status_fmt(text_col, bg_col):
            return _fmt(**BASE, font_color=text_col, bg_color=bg_col,
                        align='center', border=1, border_color='#EEEEEE')

        fmt_st_draft    = _status_fmt('#555555', '#F0F0F0')
        fmt_st_review   = _status_fmt('#7A4F00', '#FFF3CD')
        fmt_st_approved = _status_fmt('#155724', '#D4EDDA')

        def boq_state_fmt(state):
            return {'draft': fmt_st_draft,
                    'review': fmt_st_review,
                    'approved': fmt_st_approved}.get(state, fmt_st_draft)

        def ana_state_fmt(state):
            return {'draft': fmt_st_draft,
                    'review': fmt_st_review,
                    'approved': fmt_st_approved}.get(state, fmt_st_draft)

        # Subtotal / grand-total
        fmt_subtot_lbl = _fmt(**BASE, bold=True, font_size=10,
                              bg_color='#D5E8D4', font_color='#000000',
                              align='right', border=1, border_color='#82B366')
        fmt_subtot_num = _fmt(**BASE, bold=True, font_size=10,
                              bg_color='#D5E8D4', font_color='#000000',
                              num_format='#,##0.00', align='right',
                              border=1, border_color='#82B366')
        fmt_grand_lbl  = _fmt(**BASE, bold=True, font_size=11,
                              bg_color='#1A3A5C', font_color='#FFFFFF',
                              align='right', border=1, border_color='#0D2035')
        fmt_grand_num  = _fmt(**BASE, bold=True, font_size=11,
                              bg_color='#1A3A5C', font_color='#FFFFFF',
                              num_format='#,##0.00', align='right',
                              border=1, border_color='#0D2035')
        fmt_grand_pct  = _fmt(**BASE, bold=True, font_size=11,
                              bg_color='#1A3A5C', font_color='#FFFFFF',
                              num_format='0.00"%"', align='right',
                              border=1, border_color='#0D2035')

        # ══════════════════════════════════════════════════════════════════════
        # SHEET 1 — FULL BOQ ANALYSIS
        # ══════════════════════════════════════════════════════════════════════

        ws = wb.add_worksheet('BOQ Analysis')

        # Column widths
        # A=Code, B=Description, C=Qty, D=Unit,
        # E=Cost UP, F=Sale UP, G=Cost Tot, H=Sale Tot, I=Profit, J=Margin%,
        # K=BOQ Status, L=Analysis Status
        ws.set_column('A:A', 14)
        ws.set_column('B:B', 48)
        ws.set_column('C:C', 10)
        ws.set_column('D:D',  8)
        ws.set_column('E:E', 14)
        ws.set_column('F:F', 14)
        ws.set_column('G:G', 14)
        ws.set_column('H:H', 14)
        ws.set_column('I:I', 14)
        ws.set_column('J:J', 10)
        ws.set_column('K:K', 13)
        ws.set_column('L:L', 14)
        NCOLS = 12   # A..L (0..11)

        # Title
        row = 0
        ws.merge_range(row, 0, row, NCOLS - 1,
                       'BOQ Analysis Report  —  تقرير تحليل جدول الكميات',
                       fmt_title)
        ws.set_row(row, 26)
        row += 1

        # Meta block
        meta = [
            ('Analysis Ref',  self.name),
            ('BOQ Document',  self.boq_id.name or ''),
            ('Project',       self.project_id.name or ''),
            ('Date',          str(self.date) if self.date else ''),
            ('Currency',      currency),
            ('Status',        dict(self.fields_get(['analysis_state'])
                                   ['analysis_state']['selection'])
                              .get(self.analysis_state, '')),
        ]
        for lbl, val in meta:
            ws.write(row, 0, lbl, fmt_meta_lbl)
            ws.write(row, 1, val, fmt_meta_val)
            row += 1
        row += 1  # spacer

        # Column headers
        ws.set_row(row, 32)
        headers = [
            ('Code',            fmt_col_hdr),
            ('Description',     fmt_col_hdr),
            (f'BOQ Qty',        fmt_col_hdr_r),
            ('Unit',            fmt_col_hdr),
            (f'Cost UP\n({currency})',  fmt_col_hdr_r),
            (f'Sale UP\n({currency})',  fmt_col_hdr_r),
            (f'Cost Total\n({currency})',fmt_col_hdr_r),
            (f'Sale Total\n({currency})',fmt_col_hdr_r),
            (f'Profit\n({currency})',    fmt_col_hdr_r),
            ('Margin %',        fmt_col_hdr_r),
            ('BOQ Status',      fmt_col_hdr),
            ('Analysis Status', fmt_col_hdr),
        ]
        for col, (hdr, hfmt) in enumerate(headers):
            ws.write(row, col, hdr, hfmt)
        row += 1

        # Data rows
        data_lines = self.line_ids.sorted(
            lambda l: (l.div_rank, l.sub_rank, l.sub_sub_rank,
                       l.row_level, l.sequence_sub)
        )

        div_subtotals = {}   # div_rank → {'cost':0, 'sale':0, 'profit':0}

        for line in data_lines:
            dt   = line.display_type
            code = line.display_code or ''
            name = line.name or ''

            if dt == 'line_section':
                ws.set_row(row, 16)
                ws.write(row, 0, code, fmt_div)
                ws.merge_range(row, 1, row, NCOLS - 1, name, fmt_div)
                div_subtotals[line.div_rank] = {'cost': 0.0, 'sale': 0.0, 'profit': 0.0}

            elif dt == 'line_subsection':
                ws.set_row(row, 15)
                ws.write(row, 0, code, fmt_sub)
                ws.merge_range(row, 1, row, NCOLS - 1, name, fmt_sub)

            elif dt == 'line_sub_subsection':
                ws.set_row(row, 14)
                ws.write(row, 0, code,    fmt_subsub)
                ws.merge_range(row, 1, row, NCOLS - 1, name, fmt_subsub)

            else:
                # Subitem — full financial row
                qty  = line.boq_qty or 0.0
                cup  = line.cost_unit_price or 0.0
                sup  = line.sale_unit_price or 0.0
                ctot = line.cost_total or 0.0
                stot = line.sale_total or 0.0
                prf  = line.profit or 0.0
                mrg  = line.margin or 0.0
                unit = line.unit_id.name if line.unit_id else ''

                ws.write(row, 0,  code, fmt_item)
                ws.write(row, 1,  name, fmt_item)
                ws.write(row, 2,  qty,  fmt_item_num)
                ws.write(row, 3,  unit, fmt_item_center)
                ws.write(row, 4,  cup,  fmt_item_num)
                ws.write(row, 5,  sup,  fmt_item_num)
                ws.write(row, 6,  ctot, fmt_item_num)
                ws.write(row, 7,  stot, fmt_item_num)
                ws.write(row, 8,  prf,  fmt_item_num)
                ws.write(row, 9,  mrg,  fmt_item_pct)
                ws.write(row, 10, self._boq_state_label(line.boq_state),
                         boq_state_fmt(line.boq_state))
                ws.write(row, 11, self._ana_state_label(line.analysis_state),
                         ana_state_fmt(line.analysis_state))

                # Accumulate in current division bucket
                dr = line.div_rank
                if dr in div_subtotals:
                    div_subtotals[dr]['cost']   += ctot
                    div_subtotals[dr]['sale']   += stot
                    div_subtotals[dr]['profit'] += prf

            row += 1

        # Grand total row
        row += 1
        margin_pct = self.total_margin
        ws.merge_range(row, 0, row, 6,
                       f'GRAND TOTAL  /  الإجمالي الكلي  ({currency})',
                       fmt_grand_lbl)
        ws.write(row, 7,  self.total_sale,   fmt_grand_num)
        ws.write(row, 8,  self.total_profit, fmt_grand_num)
        ws.write(row, 9,  margin_pct,        fmt_grand_pct)
        ws.write(row, 10, '', fmt_grand_lbl)
        ws.write(row, 11, '', fmt_grand_lbl)

        # ══════════════════════════════════════════════════════════════════════
        # SHEET 2 — SUMMARY
        # ══════════════════════════════════════════════════════════════════════

        ws2 = wb.add_worksheet('Summary')

        ws2.set_column('A:A', 12)   # Code
        ws2.set_column('B:B', 40)   # Division
        ws2.set_column('C:C', 18)   # Cost
        ws2.set_column('D:D', 18)   # Sale
        ws2.set_column('E:E', 16)   # Profit
        ws2.set_column('F:F', 12)   # Margin %

        r2 = 0
        ws2.merge_range(r2, 0, r2, 5,
                        f'BOQ Analysis Summary  —  {self.name}', fmt_title)
        ws2.set_row(r2, 24)
        r2 += 1

        # Summary meta
        ws2.write(r2, 0, 'BOQ Document', fmt_meta_lbl)
        ws2.write(r2, 1, self.boq_id.name or '', fmt_meta_val)
        r2 += 1
        ws2.write(r2, 0, 'Project', fmt_meta_lbl)
        ws2.write(r2, 1, self.project_id.name or '', fmt_meta_val)
        r2 += 2

        # Summary header
        ws2.set_row(r2, 28)
        sum_hdrs = [
            ('Code', fmt_col_hdr),
            ('Division', fmt_col_hdr),
            (f'Total Cost ({currency})',   fmt_col_hdr_r),
            (f'Total Sale ({currency})',   fmt_col_hdr_r),
            (f'Profit ({currency})',       fmt_col_hdr_r),
            ('Margin %', fmt_col_hdr_r),
        ]
        for c, (h, f) in enumerate(sum_hdrs):
            ws2.write(r2, c, h, f)
        r2 += 1

        # Per-division rows
        rd = self._get_analysis_report_data()
        for div in rd['divisions']:
            if not div['section']:
                continue
            sc = div['section'].display_code or ''
            sn = div['section'].name or ''
            dc = div['subtotal_cost']
            ds = div['subtotal_sale']
            dp = div['subtotal_profit']
            dm = (dp / dc * 100.0) if dc else 0.0

            ws2.write(r2, 0, sc, fmt_div)
            ws2.write(r2, 1, sn, fmt_div)
            ws2.write(r2, 2, dc, fmt_div_num)
            ws2.write(r2, 3, ds, fmt_div_num)
            ws2.write(r2, 4, dp, fmt_div_num)
            ws2.write(r2, 5,
                      f'{dm:.1f}%' if dc else '—',
                      fmt_div)
            r2 += 1

        # Grand total
        r2 += 1
        ws2.merge_range(r2, 0, r2, 1, 'GRAND TOTAL  /  الإجمالي الكلي', fmt_grand_lbl)
        ws2.write(r2, 2, rd['total_cost'],   fmt_grand_num)
        ws2.write(r2, 3, rd['total_sale'],   fmt_grand_num)
        ws2.write(r2, 4, rd['total_profit'], fmt_grand_num)
        ws2.write(r2, 5,
                  f"{rd['total_margin']:.1f}%",
                  fmt_grand_pct)

        # ── Finalize ──────────────────────────────────────────────────────────

        wb.close()
        xlsx_data = output.getvalue()
        filename  = f'BOQ-Analysis-{self.name}.xlsx'

        attachment = self.env['ir.attachment'].create({
            'name':      filename,
            'type':      'binary',
            'datas':     base64.b64encode(xlsx_data),
            'res_model': self._name,
            'res_id':    self.id,
            'mimetype':  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        return {
            'type':   'ir.actions.act_url',
            'url':    f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _boq_state_label(state):
        return {'draft': 'Draft', 'review': 'Review', 'approved': 'Approved'}.get(state or '', '')

    @staticmethod
    def _ana_state_label(state):
        return {'draft': 'Draft', 'review': 'Review', 'approved': 'Approved'}.get(state or '', '')
