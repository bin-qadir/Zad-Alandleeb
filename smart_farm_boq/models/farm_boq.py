import base64
import io

import xlsxwriter

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError


class FarmBoq(models.Model):
    _name = 'farm.boq'
    _description = 'Project Cost Structure | هيكل تكلفة المشروع'
    _order = 'name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # ── Identity ─────────────────────────────────────────────────────────────
    name = fields.Char(
        string='Reference',
        required=True,
        readonly=True,
        copy=False,
        default='/',
    )
    project_id = fields.Many2one(
        comodel_name='farm.project',
        string='Farm Project',
        required=True,
        ondelete='restrict',
        index=True,
    )
    business_activity = fields.Selection(
        related='project_id.business_activity',
        store=True,
        index=True,
        string='Business Activity',
        help='Derived from the linked Farm Project. Used for activity-filtered views.',
    )
    date = fields.Date(string='Date', default=fields.Date.today)
    description = fields.Char(
        string='Description / الوصف',
        help='Short description for this BOQ document.',
    )
    sequence = fields.Integer(
        string='Sequence / التسلسل',
        default=10,
        help='Controls display order within the project BOQ list.',
    )
    note = fields.Text(string='Notes')

    # ── Currency ─────────────────────────────────────────────────────────────
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        related='company_id.currency_id',
        store=True,
        readonly=True,
    )

    # ── Workflow state ────────────────────────────────────────────────────────
    state = fields.Selection(
        selection=[
            ('draft',       'Draft'),
            ('start',       'Start'),
            ('in_progress', 'In Progress'),
            ('submitted',   'Submitted'),
            ('approved',    'Approved'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
    )

    # ── Per-user flag: controls which statusbar version is rendered ──────────
    can_edit_state = fields.Boolean(
        string='Can Edit State',
        compute='_compute_can_edit_state',
        help='True when the current user belongs to the Smart Farm Manager group.',
    )

    # ── Revision tracking ────────────────────────────────────────────────────
    revision_no = fields.Integer(string='Revision No.', default=0)
    is_revision = fields.Boolean(string='Is Revision', default=False)
    base_boq_id = fields.Many2one(
        comodel_name='farm.boq',
        string='Base BOQ',
        ondelete='set null',
        copy=False,
    )

    # ── Project Phase ────────────────────────────────────────────────────────
    project_phase_id = fields.Many2one(
        comodel_name='project.phase.master',
        string='Project Phase',
        ondelete='set null',
        index=True,
        tracking=True,
        help=(
            'Project phase this BOQ belongs to.  All BOQ lines automatically '
            'inherit this phase via a related stored field.'
        ),
    )

    # ── Lines ────────────────────────────────────────────────────────────────
    line_ids = fields.One2many(
        comodel_name='farm.boq.line',
        inverse_name='boq_id',
        string='BOQ Lines',
    )

    # ── Totals & Progress ────────────────────────────────────────────────────
    total = fields.Float(
        string='Total',
        compute='_compute_total',
        store=True,
    )
    progress_percent = fields.Float(
        string='Completion (%)',
        compute='_compute_progress',
        store=True,
        digits=(5, 1),
        help='Percentage of BOQ subitems that have quantity and unit price filled in.',
    )

    # ── Division Summary (read-only HTML widget for the Summary tab) ─────────
    division_summary_html = fields.Html(
        string='Division Summary',
        compute='_compute_division_summary_html',
        sanitize=False,
    )

    # ── Subitem / BOQ-line status counters (for Overview dashboard) ──────────
    subitem_count = fields.Integer(
        string='Total Subitems',
        compute='_compute_subitem_counts',
        store=True,
    )
    subitem_approved_count = fields.Integer(
        string='Approved',
        compute='_compute_subitem_counts',
        store=True,
        help='Subitems with BOQ pricing locked (boq_state = approved).',
    )
    subitem_review_count = fields.Integer(
        string='In Review',
        compute='_compute_subitem_counts',
        store=True,
        help='Subitems whose pricing is under review.',
    )
    subitem_draft_count = fields.Integer(
        string='Draft',
        compute='_compute_subitem_counts',
        store=True,
        help='Subitems not yet priced or reviewed.',
    )

    # ────────────────────────────────────────────────────────────────────────
    # Helpers — item filter
    # ────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _is_countable_item(line):
        """Return True for lines counted toward the BOQ total.

        4-level design: subitems have parent_id = line_sub_subsection row.
        Legacy 3-level: subitems had parent_id = line_subsection row.
        Legacy standalone: display_type=False, parent_id=False.
        """
        if line.display_type:
            return False
        if not line.parent_id:
            return True   # legacy standalone item
        return line.parent_id.display_type in ('line_sub_subsection', 'line_subsection')

    # ────────────────────────────────────────────────────────────────────────
    # Computed
    # ────────────────────────────────────────────────────────────────────────

    @api.depends_context('uid')
    def _compute_can_edit_state(self):
        is_mgr = self.env.user.has_group('smart_farm_base.group_smart_farm_manager')
        for rec in self:
            rec.can_edit_state = is_mgr

    @api.depends(
        'line_ids.display_type',
        'line_ids.parent_id',
        'line_ids.boq_state',
    )
    def _compute_subitem_counts(self):
        for rec in self:
            subitems = rec.line_ids.filtered(self._is_countable_item)
            rec.subitem_count    = len(subitems)
            rec.subitem_approved_count = len(subitems.filtered(
                lambda l: l.boq_state == 'approved'
            ))
            rec.subitem_review_count = len(subitems.filtered(
                lambda l: l.boq_state == 'review'
            ))
            rec.subitem_draft_count = len(subitems.filtered(
                lambda l: l.boq_state == 'draft'
            ))

    # ────────────────────────────────────────────────────────────────────────
    # Actions
    # ────────────────────────────────────────────────────────────────────────

    def action_open_structure(self):
        """Open the full BOQ structure (line hierarchy) in a dedicated view."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Project B.O.Q Structure — %s') % self.name,
            'res_model': 'farm.boq.line',
            'view_mode': 'list,form',
            'domain': [('boq_id', '=', self.id)],
            'context': {
                'default_boq_id': self.id,
                'lock_classification': True,
                'search_default_main_items': 0,
            },
        }

    def action_open_excel_import(self):
        """Open the Excel Import wizard for this BOQ."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Import BOQ from Excel — %s') % self.name,
            'res_model': 'farm.boq.excel.import.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_boq_id': self.id},
        }

    # ── KPI-card click actions (filtered to real subitems by boq_state) ──────

    def _action_subitems(self, label, extra_domain=None):
        """Return act_window for real subitems of this BOQ.

        ``extra_domain`` is appended to the base subitem filter so each
        KPI card can restrict by boq_state without repeating the boilerplate.
        """
        self.ensure_one()
        domain = [
            ('boq_id',       '=',    self.id),
            ('display_type', '=',    False),
            ('parent_id',    '!=',   False),
        ]
        if extra_domain:
            domain += extra_domain
        return {
            'type': 'ir.actions.act_window',
            'name': '%s — %s' % (label, self.name),
            'res_model': 'farm.boq.line',
            'view_mode': 'list,form',
            'domain': domain,
            'context': {'default_boq_id': self.id},
        }

    def action_view_all_subitems(self):
        """KPI card: Total Subitems — all real subitem lines for this BOQ."""
        return self._action_subitems(_('All Subitems'))

    def action_view_approved_lines(self):
        """KPI card: Approved — subitems with boq_state = approved."""
        return self._action_subitems(
            _('Approved Items'), [('boq_state', '=', 'approved')]
        )

    def action_view_review_lines(self):
        """KPI card: In Review — subitems with boq_state = review."""
        return self._action_subitems(
            _('Items In Review'), [('boq_state', '=', 'review')]
        )

    def action_view_draft_lines(self):
        """KPI card: Draft — subitems with boq_state = draft."""
        return self._action_subitems(
            _('Draft Items'), [('boq_state', '=', 'draft')]
        )

    # ── Structure cleanup: remove duplicates + rebuild ordering ─────────────

    def action_cleanup_structure(self):
        """Remove duplicate lines and rebuild clean sequential ordering.

        Safe to run multiple times (idempotent):
        1. Detect duplicate line_sub_subsection rows per
           (boq_id, subsection_line_id, sub_subdivision_id or name).
        2. Reassign any children of duplicate rows to the kept row.
        3. Delete the duplicate rows.
        4. Rebuild div_rank / sub_rank / sub_sub_rank / sequence_sub
           sequentially at every hierarchy level.
        5. Stored computed field display_code is invalidated automatically.
        """
        self.ensure_one()
        removed = self._dedup_structure()
        self._rebuild_sequence()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Structure Cleaned'),
                'message': _(
                    'Removed %(n)d duplicate rows and rebuilt sequential ordering.',
                    n=removed,
                ),
                'type': 'success',
                'sticky': False,
            },
        }

    def _dedup_structure(self):
        """Remove duplicate structural rows at every hierarchy level.

        Returns the number of rows deleted.
        """
        Line = self.env['farm.boq.line']
        removed = 0

        for display_type, key_fn in [
            ('line_section',         lambda l: (l.division_id.id or 0,)),
            ('line_subsection',      lambda l: (l.section_line_id.id or 0,
                                                l.subdivision_id.id or 0)),
            ('line_sub_subsection',  lambda l: (l.subsection_line_id.id or 0,
                                                l.sub_subdivision_id.id or 0,
                                                l.name)),
        ]:
            rows = Line.search([
                ('boq_id',       '=', self.id),
                ('display_type', '=', display_type),
            ], order='id asc')

            seen = {}
            for row in rows:
                key = key_fn(row)
                if key in seen:
                    # Re-parent children (any level) before deletion
                    keeper = seen[key]
                    children = Line.search([('parent_id', '=', row.id)])
                    if children:
                        children.with_context(
                            allow_classification_change=True
                        ).write({'parent_id': keeper.id})
                    # Also fix cross-ref pointers on lines pointing to this row
                    ptr_field = {
                        'line_section':        'section_line_id',
                        'line_subsection':     'subsection_line_id',
                        'line_sub_subsection': 'sub_subsection_line_id',
                    }[display_type]
                    ref_lines = Line.search([
                        ('boq_id', '=', self.id),
                        (ptr_field, '=', row.id),
                    ])
                    if ref_lines:
                        ref_lines.write({ptr_field: keeper.id})
                    row.unlink()
                    removed += 1
                else:
                    seen[key] = row

        return removed

    def _rebuild_sequence(self):
        """Rebuild clean 1-based sequential ranks for all hierarchy levels.

        Updates div_rank / sub_rank / sub_sub_rank / sequence_sub without
        touching parent/child relationships.  Stored fields display_code and
        row_level are recomputed automatically by the ORM after rank writes.

        Uses ``skip_sequence_check=True`` in context so the uniqueness
        constraint on sequence_sub does not fire during intermediate states.
        """
        Line = self.env['farm.boq.line']
        # Skip uniqueness constraint during batch renumber to avoid spurious
        # conflicts when two subitems briefly share a sequence value mid-rebuild.
        ctx = {'skip_sequence_check': True}

        # ── Level 1: Sections ─────────────────────────────────────────────
        sections = Line.search([
            ('boq_id',       '=', self.id),
            ('display_type', '=', 'line_section'),
        ], order='div_rank asc, sequence_main asc, id asc')

        for rank, sec in enumerate(sections, start=1):
            if sec.div_rank != rank or sec.sequence_main != rank:
                sec.write({'div_rank': rank, 'sequence_main': rank})

            # ── Level 2: Subsections ──────────────────────────────────────
            subsections = Line.search([
                ('boq_id',          '=', self.id),
                ('display_type',    '=', 'line_subsection'),
                ('section_line_id', '=', sec.id),
            ], order='sub_rank asc, sequence_sub asc, id asc')

            for srank, sub in enumerate(subsections, start=1):
                vals = {}
                if sub.div_rank != rank:
                    vals['div_rank'] = rank
                if sub.sub_rank != srank:
                    vals['sub_rank'] = srank
                if sub.sequence_sub != srank:
                    vals['sequence_sub'] = srank
                if vals:
                    sub.write(vals)

                # ── Level 3: Sub-Subsections ──────────────────────────────
                sub_subs = Line.search([
                    ('boq_id',             '=', self.id),
                    ('display_type',       '=', 'line_sub_subsection'),
                    ('subsection_line_id', '=', sub.id),
                ], order='sub_sub_rank asc, sequence_sub asc, id asc')

                for ssrank, ssub in enumerate(sub_subs, start=1):
                    vals = {}
                    if ssub.div_rank != rank:
                        vals['div_rank'] = rank
                    if ssub.sub_rank != srank:
                        vals['sub_rank'] = srank
                    if ssub.sub_sub_rank != ssrank:
                        vals['sub_sub_rank'] = ssrank
                    if ssub.sequence_sub != ssrank:
                        vals['sequence_sub'] = ssrank
                    if vals:
                        ssub.write(vals)

                    # ── Level 4: Subitems ─────────────────────────────────
                    subitems = Line.search([
                        ('boq_id',       '=', self.id),
                        ('display_type', '=', False),
                        ('parent_id',    '=', ssub.id),
                    ], order='sequence_sub asc, id asc')

                    for irank, item in enumerate(subitems, start=1):
                        vals = {}
                        if item.div_rank != rank:
                            vals['div_rank'] = rank
                        if item.sub_rank != srank:
                            vals['sub_rank'] = srank
                        if item.sub_sub_rank != ssrank:
                            vals['sub_sub_rank'] = ssrank
                        if item.sequence_sub != irank:
                            vals['sequence_sub'] = irank
                        if vals:
                            item.with_context(**ctx).write(vals)

    def rebuild_boq_sequence(self):
        """Public API: rebuild sequence, ranks and display codes for this BOQ.

        Identical to the cleanup path but without the deduplication step —
        safe to call at any time without risk of removing intentional rows.

        Walks the full 4-level hierarchy:
            Division → Subdivision → Sub-Subdivision → Subitems

        After each write, stored computed fields (display_code, row_level) are
        automatically invalidated and recomputed by the ORM.

        Returns a client notification so it can be called from a button.
        """
        self.ensure_one()
        self._rebuild_sequence()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('BOQ Sequence Rebuilt'),
                'message': _(
                    'All BOQ line ranks, codes and ordering have been rebuilt.'
                ),
                'type': 'success',
                'sticky': False,
            },
        }

    @api.depends(
        'line_ids.total',
        'line_ids.display_type',
        'line_ids.parent_id',
        'line_ids.parent_id.display_type',
    )
    def _compute_total(self):
        for rec in self:
            items = rec.line_ids.filtered(rec._is_countable_item)
            rec.total = sum(items.mapped('total'))

    @api.depends(
        'line_ids',
        'line_ids.display_type',
        'line_ids.parent_id',
        'line_ids.parent_id.display_type',
        'line_ids.unit_price',
        'line_ids.boq_qty',
    )
    def _compute_progress(self):
        for rec in self:
            items = rec.line_ids.filtered(rec._is_countable_item)
            total = len(items)
            if not total:
                rec.progress_percent = 0.0
                continue
            filled = len(items.filtered(lambda l: l.unit_price > 0 and l.boq_qty > 0))
            rec.progress_percent = filled / total * 100.0

    @api.depends(
        'line_ids.total',
        'line_ids.display_type',
        'line_ids.division_id',
        'line_ids.parent_id',
        'line_ids.parent_id.display_type',
        'currency_id',
    )
    def _compute_division_summary_html(self):
        """Build an HTML summary table with one row per Division.

        Totals are aggregated from real subitems only (display_type=False),
        identical to the report grouping logic in _get_boq_report_data().
        """
        for rec in self:
            rd = rec._get_boq_report_data()
            divisions = rd['divisions']
            grand_total = rd['grand_total']
            currency_symbol = rd['currency_symbol']
            currency_name = rec.currency_id.name or ''

            # ── table styles (inline — safe inside HTML field) ────────────────
            s_table  = 'width:100%;border-collapse:collapse;font-size:13px;'
            s_th     = ('padding:8px 12px;text-align:left;background:#2c3e50;'
                        'color:#fff;font-weight:600;border:1px solid #1a252f;')
            s_th_r   = s_th.replace('text-align:left', 'text-align:right')
            s_td_div = ('padding:7px 12px;background:#efe2b8;font-weight:700;'
                        'border:1px solid #d4b86a;')
            s_td_num = ('padding:7px 12px;background:#efe2b8;font-weight:700;'
                        'border:1px solid #d4b86a;text-align:right;')
            s_td_pct = ('padding:7px 12px;background:#efe2b8;font-weight:700;'
                        'border:1px solid #d4b86a;text-align:right;color:#555;')
            s_td_code= ('padding:7px 12px;background:#efe2b8;font-weight:700;'
                        'border:1px solid #d4b86a;font-family:monospace;color:#555;')
            s_foot   = ('padding:9px 12px;background:#2c3e50;color:#fff;'
                        'font-weight:700;border:1px solid #1a252f;text-align:right;'
                        'font-size:14px;')
            s_foot_l = s_foot.replace('text-align:right', 'text-align:left')

            rows_html = []
            for d in divisions:
                sec = d['section']
                if not sec:
                    continue
                subtotal = d['subtotal']
                pct = (subtotal / grand_total * 100.0) if grand_total else 0.0
                rows_html.append(
                    f'<tr>'
                    f'<td style="{s_td_code}">{sec.display_code or ""}</td>'
                    f'<td style="{s_td_div}">{sec.name or ""}</td>'
                    f'<td style="{s_td_num}">{subtotal:,.2f}</td>'
                    f'<td style="{s_td_pct}">{pct:.1f}%</td>'
                    f'</tr>'
                )

            rows_str = ''.join(rows_html)

            html = (
                f'<table style="{s_table}">'
                f'<thead><tr>'
                f'<th style="{s_th}" width="80">Code</th>'
                f'<th style="{s_th}">Division | القسم</th>'
                f'<th style="{s_th_r}" width="160">Amount ({currency_name})</th>'
                f'<th style="{s_th_r}" width="90">%</th>'
                f'</tr></thead>'
                f'<tbody>{rows_str}</tbody>'
                f'<tfoot>'
                f'<tr>'
                f'<td colspan="2" style="{s_foot_l}">Grand Total | الإجمالي الكلي</td>'
                f'<td style="{s_foot}">{grand_total:,.2f} {currency_symbol}</td>'
                f'<td style="{s_foot}">100.0%</td>'
                f'</tr>'
                f'</tfoot>'
                f'</table>'
            )
            rec.division_summary_html = html

    # ────────────────────────────────────────────────────────────────────────
    # ORM
    # ────────────────────────────────────────────────────────────────────────

    def write(self, vals):
        """Guard state changes and approved-lock for non-managers.

        Two independent checks:
        1. Only managers may write the `state` field — raises AccessError
           so it blocks both UI and direct RPC/API calls.
        2. Approved BOQs are fully locked for non-managers.

        The superuser flag (env.su) is honoured so internal system
        operations (sequences, mail threads, cron) are never blocked.
        """
        if not self.env.su:
            is_mgr = self.env.user.has_group(
                'smart_farm_base.group_smart_farm_manager'
            )
            # Rule 1 — only managers may change state (blocks RPC too)
            if 'state' in vals and not is_mgr:
                raise AccessError(_(
                    'You do not have permission to change the BOQ status. '
                    'Only users in the Manager group can modify the workflow state.'
                ))
            # Rule 2 — approved BOQs are fully locked for non-managers
            if not is_mgr:
                locked = self.filtered(lambda r: r.state == 'approved')
                if locked:
                    raise AccessError(_(
                        'BOQ "%s" is approved and locked. '
                        'Only a Manager can modify it.'
                    ) % locked[0].name)
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = (
                    self.env['ir.sequence'].next_by_code('farm.boq') or '/'
                )
        records = super().create(vals_list)
        # Structure is added manually via "Add BOQ Structure" wizard — not auto-created.
        # (Use action_rebuild_structure() / _auto_create_structure() explicitly if needed.)
        return records

    def _auto_create_structure(self):
        """Create all 3 structural levels: division / subdivision / sub-subdivision.

        Uses each master record's bilingual label so BOQ rows automatically
        reflect both English and Arabic names.

        Safe to call multiple times (idempotent):
          - Missing rows are created.
          - Existing rows have name, ranks, and parent links refreshed.
          - Child subitems of updated rows receive updated rank values.

        Called automatically on BOQ create and via 'Rebuild Structure'.
        """
        BoqLine = self.env['farm.boq.line']
        divisions = self.env['farm.division.work'].search(
            [], order='sequence asc, id asc'
        )
        for div_rank, division in enumerate(divisions, start=1):
            div_label = division.display_name_bilingual or division.name

            # ── Level 1: Division section row ──────────────────────────────────
            section = self.line_ids.filtered(
                lambda l, d=division: (
                    l.display_type == 'line_section' and l.division_id.id == d.id
                )
            )
            if not section:
                section = BoqLine.create({
                    'boq_id': self.id,
                    'display_type': 'line_section',
                    'name': div_label,
                    'division_id': division.id,
                    'sequence_main': div_rank,
                    'div_rank': div_rank,
                })
            else:
                section = section[0]
                sec_upd = {}
                if section.name != div_label:
                    sec_upd['name'] = div_label
                if section.sequence_main != div_rank:
                    sec_upd['sequence_main'] = div_rank
                if section.div_rank != div_rank:
                    sec_upd['div_rank'] = div_rank
                if sec_upd:
                    section.write(sec_upd)

            # ── Level 2: Subdivision subsection rows ───────────────────────────
            subdivisions = self.env['farm.subdivision.work'].search(
                [('division_id', '=', division.id)],
                order='sequence asc, id asc',
            )
            for sub_rank, subdivision in enumerate(subdivisions, start=1):
                sub_label = subdivision.display_name_bilingual or subdivision.name

                subsection = self.line_ids.filtered(
                    lambda l, s=subdivision: (
                        l.display_type == 'line_subsection'
                        and l.subdivision_id.id == s.id
                    )
                )
                if not subsection:
                    subsection = BoqLine.create({
                        'boq_id': self.id,
                        'display_type': 'line_subsection',
                        'name': sub_label,
                        'division_id': division.id,
                        'subdivision_id': subdivision.id,
                        'section_line_id': section.id,
                        'div_rank': div_rank,
                        'sub_rank': sub_rank,
                        'sequence_sub': sub_rank,
                    })
                else:
                    subsection = subsection[0]
                    sub_upd = {}
                    if subsection.name != sub_label:
                        sub_upd['name'] = sub_label
                    if subsection.division_id.id != division.id:
                        sub_upd['division_id'] = division.id
                    if subsection.section_line_id.id != section.id:
                        sub_upd['section_line_id'] = section.id
                    if subsection.div_rank != div_rank:
                        sub_upd['div_rank'] = div_rank
                    if subsection.sub_rank != sub_rank:
                        sub_upd['sub_rank'] = sub_rank
                    if subsection.sequence_sub != sub_rank:
                        sub_upd['sequence_sub'] = sub_rank
                    if sub_upd:
                        subsection.write(sub_upd)

                # ── Level 3: Sub-subdivision rows ──────────────────────────────
                sub_subdivisions = self.env['farm.sub_subdivision.work'].search(
                    [('subdivision_id', '=', subdivision.id)],
                    order='sequence asc, id asc',
                )
                for sub_sub_rank, sub_subdivision in enumerate(sub_subdivisions, start=1):
                    sub_sub_label = sub_subdivision.display_name_bilingual or sub_subdivision.name

                    existing_ss = self.line_ids.filtered(
                        lambda l, ss=sub_subdivision: (
                            l.display_type == 'line_sub_subsection'
                            and l.sub_subdivision_id.id == ss.id
                        )
                    )
                    if not existing_ss:
                        BoqLine.create({
                            'boq_id': self.id,
                            'display_type': 'line_sub_subsection',
                            'name': sub_sub_label,
                            'division_id': division.id,
                            'subdivision_id': subdivision.id,
                            'sub_subdivision_id': sub_subdivision.id,
                            'section_line_id': section.id,
                            'subsection_line_id': subsection.id,
                            'div_rank': div_rank,
                            'sub_rank': sub_rank,
                            'sub_sub_rank': sub_sub_rank,
                            'sequence_sub': sub_sub_rank,
                        })
                    else:
                        existing_ss = existing_ss[0]
                        ss_upd = {}
                        if existing_ss.name != sub_sub_label:
                            ss_upd['name'] = sub_sub_label
                        if existing_ss.division_id.id != division.id:
                            ss_upd['division_id'] = division.id
                        if existing_ss.subdivision_id.id != subdivision.id:
                            ss_upd['subdivision_id'] = subdivision.id
                        if existing_ss.section_line_id.id != section.id:
                            ss_upd['section_line_id'] = section.id
                        if existing_ss.subsection_line_id.id != subsection.id:
                            ss_upd['subsection_line_id'] = subsection.id
                        if existing_ss.div_rank != div_rank:
                            ss_upd['div_rank'] = div_rank
                        if existing_ss.sub_rank != sub_rank:
                            ss_upd['sub_rank'] = sub_rank
                        if existing_ss.sub_sub_rank != sub_sub_rank:
                            ss_upd['sub_sub_rank'] = sub_sub_rank
                        if existing_ss.sequence_sub != sub_sub_rank:
                            ss_upd['sequence_sub'] = sub_sub_rank
                        if ss_upd:
                            existing_ss.write(ss_upd)
                            # Propagate rank changes to child subitems
                            if existing_ss.child_ids:
                                child_upd = {
                                    k: ss_upd[k]
                                    for k in ('div_rank', 'sub_rank', 'sub_sub_rank', 'division_id')
                                    if k in ss_upd
                                }
                                if child_upd:
                                    existing_ss.child_ids.write(child_upd)

    # ────────────────────────────────────────────────────────────────────────
    # Workflow actions
    # ────────────────────────────────────────────────────────────────────────

    def action_start(self):
        """Draft → Start.  Requires at least one BOQ subitem."""
        for rec in self:
            if rec.state != 'draft':
                continue
            items = rec.line_ids.filtered(rec._is_countable_item)
            if not items:
                raise UserError(
                    'Cannot start BOQ "%s": please add at least one subitem first.'
                    % rec.name
                )
            rec.write({'state': 'start'})

    def action_in_progress(self):
        """Start → In Progress."""
        invalid = self.filtered(lambda r: r.state != 'start')
        if invalid:
            raise UserError(
                'Only BOQs in "Start" state can be moved to In Progress.'
            )
        self.write({'state': 'in_progress'})

    def action_submit(self):
        """In Progress → Submitted.  Requires all subitems to have a unit price."""
        for rec in self:
            if rec.state != 'in_progress':
                continue
            items = rec.line_ids.filtered(rec._is_countable_item)
            incomplete = items.filtered(lambda l: not l.unit_price)
            if incomplete:
                raise UserError(
                    'Cannot submit BOQ "%s": %d item(s) still have no unit price set.'
                    % (rec.name, len(incomplete))
                )
            rec.write({'state': 'submitted'})

    def action_approve(self):
        """Submitted → Approved."""
        invalid = self.filtered(lambda r: r.state != 'submitted')
        if invalid:
            raise UserError('Only submitted BOQs can be approved.')
        self.write({'state': 'approved'})

    def action_rebuild_structure(self):
        """Clean wipe of all structural rows + full rebuild from master data.

        Structural rows (line_section / line_subsection / line_sub_subsection)
        are deleted and regenerated from Configuration.  Real subitems
        (display_type=False, parent_id set) are also removed since they rely
        on the structural parent chain; users re-add them after rebuild.
        """
        self.ensure_one()
        self.line_ids.unlink()   # cascade-deletes subitems too
        self._auto_create_structure()

    def action_add_structure(self):
        """Open the Add BOQ Structure wizard for selective structure import.

        Lets the user choose which Division(s) — and optionally specific
        Subdivisions and Sub-Subdivisions — to insert into this BOQ without
        wiping existing content.
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Add BOQ Structure'),
            'res_model': 'farm.boq.add_structure.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_boq_id': self.id},
        }

    # ────────────────────────────────────────────────────────────────────────
    # Report data helper
    # ────────────────────────────────────────────────────────────────────────

    def _get_division_summary(self):
        """Return per-division, per-subdivision aggregated totals for PDF reports.

        Used by the Division Summary page (Page 1) of the BOQ report.

        Returns a list of dicts::

            [
                {
                    'name':           str,   # division display label (bilingual)
                    'code':           str,   # division display_code
                    'subdivisions': [
                        {'name': str, 'code': str, 'total': float},
                        ...
                    ],
                    'division_total': float,
                },
                ...
            ]

        Only real subitems (display_type=False) contribute to totals.
        Structural headers (line_sub_subsection) are traversed but not summed.
        """
        self.ensure_one()
        lines = self.line_ids.sorted(
            lambda l: (l.div_rank, l.sub_rank, l.sub_sub_rank,
                       l.sequence_main, l.sequence_sub)
        )

        result = []
        current_div = None
        current_sub = None

        for line in lines:
            if line.display_type == 'line_section':
                # Flush previous subdivision and division
                if current_sub is not None and current_div is not None:
                    current_div['subdivisions'].append(current_sub)
                    current_sub = None
                if current_div is not None:
                    result.append(current_div)
                current_div = {
                    'name': line.name,
                    'code': line.display_code or '',
                    'subdivisions': [],
                    'division_total': 0.0,
                }
            elif line.display_type == 'line_subsection':
                if current_sub is not None and current_div is not None:
                    current_div['subdivisions'].append(current_sub)
                current_sub = {
                    'name': line.name,
                    'code': line.display_code or '',
                    'total': 0.0,
                }
            elif not line.display_type:          # real subitem
                total_val = line.total or 0.0
                if current_sub is not None:
                    current_sub['total'] = round(current_sub['total'] + total_val, 2)
                if current_div is not None:
                    current_div['division_total'] = round(
                        current_div['division_total'] + total_val, 2
                    )
            # line_sub_subsection: structural header — no totals to accumulate

        # Flush last bucket
        if current_sub is not None and current_div is not None:
            current_div['subdivisions'].append(current_sub)
        if current_div is not None:
            result.append(current_div)

        return result

    def _get_boq_report_data(self):
        """Return structured data used by the BOQ QWeb report.

        Returns a dict::

            {
                'divisions': [
                    {
                        'section':  farm.boq.line (line_section row),
                        'rows':     [farm.boq.line, ...],   # ALL lines for this div
                                                            # excluding the section itself
                        'subtotal': float,                  # sum of subitems only
                    },
                    ...
                ],
                'grand_total':    float,
                'currency_symbol': str,
            }

        Subtotals are computed **only from real subitems** (display_type=False),
        never from structural header rows.
        """
        self.ensure_one()
        lines = self.line_ids.sorted(
            lambda l: (l.div_rank, l.sub_rank, l.sub_sub_rank,
                       l.sequence_main, l.sequence_sub)
        )

        divisions = []
        current = None

        for line in lines:
            if line.display_type == 'line_section':
                if current is not None:
                    divisions.append(current)
                current = {
                    'section': line,
                    'rows': [],       # non-section rows for this division
                    'subtotal': 0.0,
                }
            else:
                if current is None:
                    # orphan rows before first section — create a placeholder bucket
                    current = {'section': None, 'rows': [], 'subtotal': 0.0}
                current['rows'].append(line)
                if not line.display_type:       # real subitem
                    current['subtotal'] = round(
                        current['subtotal'] + (line.total or 0.0), 2
                    )

        if current is not None:
            divisions.append(current)

        grand_total = round(sum(d['subtotal'] for d in divisions), 2)

        return {
            'divisions': divisions,
            'grand_total': grand_total,
            'currency_symbol': self.currency_id.symbol or '',
        }

    # ────────────────────────────────────────────────────────────────────────
    # Print / Export actions
    # ────────────────────────────────────────────────────────────────────────

    def action_print_boq(self):
        """Open the print wizard so the user can choose Full / Details / Summary."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'farm.boq.print.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_boq_id': self.id},
        }

    def action_export_pdf(self):
        """Download the BOQ as a PDF file (Full report mode)."""
        self.ensure_one()
        report = self.env.ref('smart_farm_boq.action_report_boq_full')
        pdf_content, _mime = report._render_qweb_pdf(
            report.report_name, [self.id]
        )
        filename = f'BOQ-{self.name}.pdf'
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': base64.b64encode(pdf_content),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/pdf',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

    def action_export_excel(self):
        """Generate and download a professional XLSX export of the BOQ."""
        self.ensure_one()

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('BOQ')

        # ── Formats ──────────────────────────────────────────────────────────
        fmt_title = workbook.add_format({
            'bold': True, 'font_size': 14, 'align': 'center', 'valign': 'vcenter',
            'font_color': '#FFFFFF', 'bg_color': '#2C3E50',
        })
        fmt_meta_label = workbook.add_format({
            'bold': True, 'font_size': 10, 'font_color': '#555555',
        })
        fmt_meta_value = workbook.add_format({
            'font_size': 10,
        })
        fmt_header = workbook.add_format({
            'bold': True, 'font_size': 10,
            'bg_color': '#2C3E50', 'font_color': '#FFFFFF',
            'align': 'center', 'valign': 'vcenter',
            'border': 1, 'border_color': '#1A252F',
        })
        fmt_header_right = workbook.add_format({
            'bold': True, 'font_size': 10,
            'bg_color': '#2C3E50', 'font_color': '#FFFFFF',
            'align': 'right', 'valign': 'vcenter',
            'border': 1, 'border_color': '#1A252F',
        })
        fmt_div = workbook.add_format({
            'bold': True, 'font_size': 11,
            'bg_color': '#EFE2B8', 'font_color': '#000000',
            'border': 1, 'border_color': '#C8A84B',
            'valign': 'vcenter',
        })
        fmt_div_num = workbook.add_format({
            'bold': True, 'font_size': 11,
            'bg_color': '#EFE2B8', 'font_color': '#000000',
            'border': 1, 'border_color': '#C8A84B',
            'num_format': '#,##0.00', 'align': 'right', 'valign': 'vcenter',
        })
        fmt_sub = workbook.add_format({
            'bold': True, 'italic': False, 'font_size': 10,
            'bg_color': '#FDF9EE', 'font_color': '#000000',
            'border': 1, 'border_color': '#E0D5B0',
            'indent': 1, 'valign': 'vcenter',
        })
        fmt_sub_num = workbook.add_format({
            'font_size': 10, 'bg_color': '#FDF9EE', 'font_color': '#000000',
            'border': 1, 'border_color': '#E0D5B0',
            'num_format': '#,##0.00', 'align': 'right', 'valign': 'vcenter',
        })
        fmt_subsub = workbook.add_format({
            'font_size': 10, 'italic': True,
            'bg_color': '#FFFDF5', 'font_color': '#444444',
            'border': 1, 'border_color': '#F0ECD8',
            'indent': 2, 'valign': 'vcenter',
        })
        fmt_subsub_num = workbook.add_format({
            'font_size': 10, 'bg_color': '#FFFDF5', 'font_color': '#444444',
            'border': 1, 'border_color': '#F0ECD8',
            'num_format': '#,##0.00', 'align': 'right', 'valign': 'vcenter',
        })
        fmt_item = workbook.add_format({
            'font_size': 10, 'bg_color': '#FFFFFF', 'font_color': '#000000',
            'border': 1, 'border_color': '#EEEEEE',
            'indent': 3, 'valign': 'vcenter',
        })
        fmt_item_num = workbook.add_format({
            'font_size': 10, 'bg_color': '#FFFFFF', 'font_color': '#000000',
            'border': 1, 'border_color': '#EEEEEE',
            'num_format': '#,##0.00', 'align': 'right', 'valign': 'vcenter',
        })
        fmt_item_qty = workbook.add_format({
            'font_size': 10, 'bg_color': '#FFFFFF', 'font_color': '#000000',
            'border': 1, 'border_color': '#EEEEEE',
            'num_format': '#,##0.00', 'align': 'right', 'valign': 'vcenter',
        })
        fmt_item_center = workbook.add_format({
            'font_size': 10, 'bg_color': '#FFFFFF', 'font_color': '#000000',
            'border': 1, 'border_color': '#EEEEEE',
            'align': 'center', 'valign': 'vcenter',
        })
        fmt_total_label = workbook.add_format({
            'bold': True, 'font_size': 11,
            'bg_color': '#2C3E50', 'font_color': '#FFFFFF',
            'align': 'right', 'valign': 'vcenter',
            'border': 1, 'border_color': '#1A252F',
        })
        fmt_total_num = workbook.add_format({
            'bold': True, 'font_size': 11,
            'bg_color': '#2C3E50', 'font_color': '#FFFFFF',
            'num_format': '#,##0.00', 'align': 'right', 'valign': 'vcenter',
            'border': 1, 'border_color': '#1A252F',
        })
        fmt_mono = workbook.add_format({
            'font_name': 'Courier New', 'font_size': 9,
        })

        # ── Column widths ─────────────────────────────────────────────────────
        # A: Code, B: Description, C: Unit, D: Qty, E: Unit Price, F: Total
        sheet.set_column('A:A', 14)   # Code
        sheet.set_column('B:B', 52)   # Description
        sheet.set_column('C:C', 10)   # Unit
        sheet.set_column('D:D', 12)   # Quantity
        sheet.set_column('E:E', 14)   # Unit Price
        sheet.set_column('F:F', 16)   # Total

        # ── Title row ─────────────────────────────────────────────────────────
        row = 0
        sheet.merge_range(row, 0, row, 5, 'Bill of Quantities  —  جدول الكميات', fmt_title)
        sheet.set_row(row, 26)
        row += 1

        # ── Meta block ────────────────────────────────────────────────────────
        sheet.write(row, 0, 'BOQ Reference', fmt_meta_label)
        sheet.write(row, 1, self.name, fmt_meta_value)
        row += 1
        sheet.write(row, 0, 'Project', fmt_meta_label)
        sheet.write(row, 1, self.project_id.name or '', fmt_meta_value)
        row += 1
        sheet.write(row, 0, 'Date', fmt_meta_label)
        sheet.write(row, 1, str(self.date) if self.date else '', fmt_meta_value)
        row += 1
        sheet.write(row, 0, 'Currency', fmt_meta_label)
        sheet.write(row, 1, self.currency_id.name or '', fmt_meta_value)
        row += 1
        row += 1  # blank spacer

        # ── Column header row ─────────────────────────────────────────────────
        sheet.set_row(row, 18)
        sheet.write(row, 0, 'Code',       fmt_header)
        sheet.write(row, 1, 'Description', fmt_header)
        sheet.write(row, 2, 'Unit',        fmt_header)
        sheet.write(row, 3, 'Quantity',    fmt_header_right)
        sheet.write(row, 4, 'Unit Price',  fmt_header_right)
        sheet.write(row, 5, 'Total',       fmt_header_right)
        row += 1

        # ── Data rows ─────────────────────────────────────────────────────────
        lines = self.line_ids.sorted(
            lambda l: (l.div_rank, l.sub_rank, l.sub_sub_rank, l.sequence_main, l.sequence_sub)
        )
        currency_symbol = self.currency_id.symbol or ''

        for line in lines:
            dt = line.display_type
            code = line.display_code or ''
            name = line.name or ''

            if dt == 'line_section':
                sheet.set_row(row, 16)
                sheet.write(row, 0, code,  fmt_div)
                sheet.merge_range(row, 1, row, 5, name, fmt_div)

            elif dt == 'line_subsection':
                sheet.set_row(row, 15)
                sheet.write(row, 0, code,  fmt_sub)
                sheet.merge_range(row, 1, row, 5, name, fmt_sub)

            elif dt == 'line_sub_subsection':
                sheet.set_row(row, 14)
                sheet.write(row, 0, code,   fmt_subsub)
                sheet.merge_range(row, 1, row, 5, name, fmt_subsub)

            else:
                # Subitem — write costing columns
                qty       = line.boq_qty    or 0.0
                up        = line.unit_price or 0.0
                total     = line.total      or 0.0
                unit_name = line.unit_id.name if line.unit_id else ''
                sheet.write(row, 0, code,      fmt_item)
                sheet.write(row, 1, name,      fmt_item)
                sheet.write(row, 2, unit_name, fmt_item_center)
                sheet.write(row, 3, qty,       fmt_item_qty)
                sheet.write(row, 4, up,        fmt_item_num)
                sheet.write(row, 5, total,     fmt_item_num)

            row += 1

        # ── Grand total ───────────────────────────────────────────────────────
        row += 1
        sheet.merge_range(row, 0, row, 4, f'GRAND TOTAL  ({currency_symbol})', fmt_total_label)
        sheet.write(row, 5, self.total or 0.0, fmt_total_num)

        workbook.close()
        xlsx_data = output.getvalue()

        filename = f'BOQ-{self.name}.xlsx'
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': base64.b64encode(xlsx_data),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

    # ────────────────────────────────────────────────────────────────────────
    # Revision copy
    # ────────────────────────────────────────────────────────────────────────

    def action_create_revision(self):
        """Duplicate this BOQ as a new revision, copying all lines."""
        self.ensure_one()

        base_boq = self.base_boq_id or self
        revision_no = (self.revision_no or 0) + 1

        # skip_auto_structure: structure rows are copied below, not re-generated
        new_boq = self.env['farm.boq'].with_context(skip_auto_structure=True).create({
            'name': f'BOQ-REVISED-NO-{revision_no}',
            'project_id': self.project_id.id,
            'date': fields.Date.today(),
            'state': 'draft',
            'revision_no': revision_no,
            'is_revision': True,
            'base_boq_id': base_boq.id,
            'note': self.note,
        })

        BoqLine = self.env['farm.boq.line']
        line_map = {}  # old_id → new_id

        # ── Step 1: copy all root lines (sections + subsections + old main items)
        root_lines = self.line_ids.filtered(
            lambda l: not l.parent_id
        ).sorted('sequence')

        for line in root_lines:
            vals = {
                'boq_id': new_boq.id,
                'display_type': line.display_type or False,
                'name': line.name,
                'description': line.description,
                'sequence': line.sequence,
                'sequence_main': line.sequence_main,
                'sequence_sub': line.sequence_sub,
                'division_id': line.division_id.id or False,
                'subdivision_id': line.subdivision_id.id or False,
                'div_rank': line.div_rank,
                'sub_rank': line.sub_rank,
                'quantity': 1.0,
                'boq_qty': line.boq_qty,
                'unit_id': line.unit_id.id or False,
            }
            if line.section_line_id and line.section_line_id.id in line_map:
                vals['section_line_id'] = line_map[line.section_line_id.id]
            if line.subsection_line_id and line.subsection_line_id.id in line_map:
                vals['subsection_line_id'] = line_map[line.subsection_line_id.id]

            new_line = BoqLine.create(vals)
            line_map[line.id] = new_line.id

        # ── Step 2: copy sub-items (subitems whose parent was a root line)
        for line in self.line_ids.filtered(
            lambda l: l.parent_id
        ).sorted('sequence_sub'):
            new_parent_id = line_map.get(line.parent_id.id)
            if not new_parent_id:
                continue
            BoqLine.create({
                'boq_id': new_boq.id,
                'parent_id': new_parent_id,
                'name': line.name,
                'description': line.description,
                'division_id': line.division_id.id or False,
                'subdivision_id': line.subdivision_id.id or False,
                'div_rank': line.div_rank,
                'sub_rank': line.sub_rank,
                'sequence': line.sequence,
                'sequence_sub': line.sequence_sub,
                'quantity': 1.0,
                'boq_qty': line.boq_qty,
                'unit_id': line.unit_id.id or False,
            })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'farm.boq',
            'res_id': new_boq.id,
            'view_mode': 'form',
            'target': 'current',
        }
