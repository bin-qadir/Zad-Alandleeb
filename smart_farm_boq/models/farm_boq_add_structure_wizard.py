"""
farm.boq.add_structure.wizard — Flexible insertion of work structure into a BOQ.
=================================================================================

## Insert Modes

full            → Import ALL divisions, subdivisions, sub-subdivisions.
division        → Import ONLY the selected divisions and their children.
subdivision     → Import ONLY the selected subdivisions + parent div headers.
sub_subdivision → Import ONLY the selected sub-subdivisions + parent headers.
template        → Import ONLY the selected templates as BOQ items + headers.
manual          → Redirect to the Add Item wizard for manual line entry.

## Strict Filtering Rules

Every import query is filtered by the selected IDs.
No fallback to full structure when scoped IDs are provided.
UserError raised (Arabic message) if a scoped mode has empty selection.

## Duplicate Safety

Structural rows: keyed by (boq_id, division_id / subdivision_id / sub_subdivision_id).
Template items:  keyed by (boq_id, template_id).
Existing rows are silently skipped; sequence is rebuilt after import.

## Logging

All imports emit: _logger.info('BOQ import mode=%s selected_ids=%s created=%s skipped=%s')
"""

import json
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class FarmBoqAddStructureWizard(models.TransientModel):
    _name        = 'farm.boq.add_structure.wizard'
    _description = 'Add BOQ Structure Wizard'

    # ── Context ───────────────────────────────────────────────────────────────
    boq_id = fields.Many2one(
        'farm.boq',
        string='BOQ Document',
        required=True,
        ondelete='cascade',
        readonly=True,
    )

    # ── Mode ──────────────────────────────────────────────────────────────────
    insert_mode = fields.Selection(
        selection=[
            ('full',            'كامل الهيكل — Full Structure'),
            ('division',        'حسب القسم — By Division'),
            ('subdivision',     'حسب الفرع — By Subdivision'),
            ('sub_subdivision', 'حسب البند الفرعي — By Sub-Subdivision'),
            ('template',        'حسب البند/القالب — By Template / Item'),
            ('manual',          'إدخال يدوي — Manual'),
        ],
        string='Insert Mode / نمط الإدراج',
        required=True,
        default='division',
    )

    # ── Division selector ─────────────────────────────────────────────────────
    division_ids = fields.Many2many(
        'farm.division.work',
        'boq_add_struct_wiz_div_rel',
        'wizard_id', 'division_id',
        string='Divisions / الأقسام',
        help='Required for "By Division". Optional filter for sub-modes.',
    )

    # ── Subdivision selector ──────────────────────────────────────────────────
    subdivision_ids = fields.Many2many(
        'farm.subdivision.work',
        'boq_add_struct_wiz_sub_rel',
        'wizard_id', 'subdivision_id',
        string='Subdivisions / الفروع',
        domain="[('division_id', 'in', division_ids)] if division_ids else []",
    )

    # ── Sub-Subdivision selector ──────────────────────────────────────────────
    sub_subdivision_ids = fields.Many2many(
        'farm.sub_subdivision.work',
        'boq_add_struct_wiz_subsub_rel',
        'wizard_id', 'sub_subdivision_id',
        string='Sub-Subdivisions / البنود الفرعية',
        domain="[('subdivision_id', 'in', subdivision_ids)] if subdivision_ids else ([('division_id', 'in', division_ids)] if division_ids else [])",
    )

    # ── Template selector ─────────────────────────────────────────────────────
    template_ids = fields.Many2many(
        'farm.boq.line.template',
        'boq_add_struct_wiz_tmpl_rel',
        'wizard_id', 'template_id',
        string='Templates / القوالب',
        domain="[('division_id', 'in', division_ids)] if division_ids else ([('subdivision_id', 'in', subdivision_ids)] if subdivision_ids else [])",
        help='Required for "By Template". Select the specific items to import.',
    )

    # ────────────────────────────────────────────────────────────────────────
    # Onchanges — cascade-clear dependent selections on mode or parent change
    # ────────────────────────────────────────────────────────────────────────

    @api.onchange('insert_mode')
    def _onchange_insert_mode(self):
        mode = self.insert_mode
        if mode in ('full', 'manual'):
            self.division_ids        = False
            self.subdivision_ids     = False
            self.sub_subdivision_ids = False
            self.template_ids        = False
        elif mode == 'division':
            self.subdivision_ids     = False
            self.sub_subdivision_ids = False
            self.template_ids        = False
        elif mode == 'subdivision':
            self.sub_subdivision_ids = False
            self.template_ids        = False
        elif mode == 'sub_subdivision':
            self.template_ids        = False
        elif mode == 'template':
            self.sub_subdivision_ids = False

    @api.onchange('division_ids')
    def _onchange_division_ids(self):
        invalid = self.subdivision_ids.filtered(
            lambda s: s.division_id not in self.division_ids
        )
        if invalid:
            self.subdivision_ids -= invalid

    @api.onchange('subdivision_ids')
    def _onchange_subdivision_ids(self):
        if not self.subdivision_ids:
            self.sub_subdivision_ids = False
            self.template_ids        = False
            return
        invalid_ss = self.sub_subdivision_ids.filtered(
            lambda ss: ss.subdivision_id not in self.subdivision_ids
        )
        if invalid_ss:
            self.sub_subdivision_ids -= invalid_ss

    # ────────────────────────────────────────────────────────────────────────
    # Public action — entry point from the wizard footer
    # ────────────────────────────────────────────────────────────────────────

    def action_import(self):
        """Dispatch to the appropriate handler based on insert_mode.

        Returns a notification dict on success.
        Raises UserError if a scoped mode has an empty selection.
        """
        self.ensure_one()
        mode = self.insert_mode

        # Redirect modes — open Add Item wizard instead of importing
        if mode == 'manual':
            return self._action_open_add_item_wizard(default_mode='create_new')

        # Validate and execute
        created, skipped = self._dispatch_import(mode)
        self.boq_id._rebuild_sequence()

        _logger.info(
            'BOQ import: boq_id=%s mode=%s created=%s skipped=%s',
            self.boq_id.id, mode, created, skipped,
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('تم استيراد الهيكل'),
                'message': _(
                    'تمت إضافة %d صف بنجاح إلى "%s". '
                    'تم تخطي %d صف موجود مسبقاً.',
                    created, self.boq_id.name, skipped,
                ),
                'type': 'success',
                'sticky': False,
            },
        }

    # ────────────────────────────────────────────────────────────────────────
    # Internal dispatch
    # ────────────────────────────────────────────────────────────────────────

    def _dispatch_import(self, mode):
        """Validate selection and call the matching import method.

        Returns (created, skipped).
        Raises UserError (Arabic) if selection is empty for a scoped mode.
        """
        if mode == 'full':
            return self._import_full_structure()

        if mode == 'division':
            if not self.division_ids:
                raise UserError(_('يرجى تحديد العناصر المطلوبة قبل الاستيراد.'))
            return self._import_by_divisions(self.division_ids)

        if mode == 'subdivision':
            if not self.subdivision_ids:
                raise UserError(_('يرجى تحديد العناصر المطلوبة قبل الاستيراد.'))
            return self._import_by_subdivisions(self.subdivision_ids)

        if mode == 'sub_subdivision':
            if not self.sub_subdivision_ids:
                raise UserError(_('يرجى تحديد العناصر المطلوبة قبل الاستيراد.'))
            return self._import_by_sub_subdivisions(self.sub_subdivision_ids)

        if mode == 'template':
            if not self.template_ids:
                raise UserError(_('يرجى تحديد العناصر المطلوبة قبل الاستيراد.'))
            return self._import_by_templates(self.template_ids)

        raise UserError(_('نمط إدراج غير معروف: %s') % mode)

    # ────────────────────────────────────────────────────────────────────────
    # Helper: pre-load existing structural rows for duplicate detection
    # ────────────────────────────────────────────────────────────────────────

    def _build_existing_maps(self):
        """Return (sections, subsections, sub_subs_set) for this BOQ.

        sections    : {division_id.id: boq.line}
        subsections : {subdivision_id.id: boq.line}
        sub_subs    : {sub_subdivision_id.id}  (set of IDs)
        """
        boq = self.boq_id
        sections = {
            l.division_id.id: l
            for l in boq.line_ids
            if l.display_type == 'line_section' and l.division_id
        }
        subsections = {
            l.subdivision_id.id: l
            for l in boq.line_ids
            if l.display_type == 'line_subsection' and l.subdivision_id
        }
        sub_subs = {
            l.sub_subdivision_id.id
            for l in boq.line_ids
            if l.display_type == 'line_sub_subsection' and l.sub_subdivision_id
        }
        return sections, subsections, sub_subs

    # ────────────────────────────────────────────────────────────────────────
    # Helpers: get-or-create structural rows
    # ────────────────────────────────────────────────────────────────────────

    def _ensure_section(self, division, div_rank, sections, boq):
        """Get or create a line_section row. Returns (row, was_new)."""
        if division.id in sections:
            return sections[division.id], False
        row = self.env['farm.boq.line'].create({
            'boq_id':        boq.id,
            'display_type':  'line_section',
            'name':          division.display_name_bilingual or division.name,
            'division_id':   division.id,
            'sequence_main': div_rank,
            'div_rank':      div_rank,
        })
        sections[division.id] = row
        return row, True

    def _ensure_subsection(self, subdivision, sub_rank, div_rank,
                           section_row, subsections, boq):
        """Get or create a line_subsection row. Returns (row, was_new)."""
        if subdivision.id in subsections:
            return subsections[subdivision.id], False
        row = self.env['farm.boq.line'].create({
            'boq_id':          boq.id,
            'display_type':    'line_subsection',
            'name':            subdivision.display_name_bilingual or subdivision.name,
            'division_id':     subdivision.division_id.id,
            'subdivision_id':  subdivision.id,
            'section_line_id': section_row.id,
            'div_rank':        div_rank,
            'sub_rank':        sub_rank,
            'sequence_sub':    sub_rank,
        })
        subsections[subdivision.id] = row
        return row, True

    def _ensure_sub_subsection(self, ss, sub_sub_rank, div_rank, sub_rank,
                                subsection_row, sub_subs_set, boq):
        """Create a line_sub_subsection row if not a duplicate.

        Returns True if created, False if skipped.
        """
        if ss.id in sub_subs_set:
            return False
        self.env['farm.boq.line'].create({
            'boq_id':             boq.id,
            'display_type':       'line_sub_subsection',
            'name':               ss.display_name_bilingual or ss.name,
            'division_id':        ss.division_id.id,
            'subdivision_id':     ss.subdivision_id.id,
            'sub_subdivision_id': ss.id,
            'subsection_line_id': subsection_row.id,
            'div_rank':           div_rank,
            'sub_rank':           sub_rank,
            'sub_sub_rank':       sub_sub_rank,
            'sequence_sub':       sub_sub_rank,
        })
        sub_subs_set.add(ss.id)
        return True

    def _get_div_rank(self, division):
        """1-based position of a division in the global sorted list."""
        all_divs = self.env['farm.division.work'].search(
            [], order='sequence asc, id asc',
        )
        ids = list(all_divs.ids)
        return (ids.index(division.id) + 1) if division.id in ids else 1

    def _get_sub_rank(self, subdivision):
        """1-based position of a subdivision within its parent division."""
        all_subs = self.env['farm.subdivision.work'].search(
            [('division_id', '=', subdivision.division_id.id)],
            order='sequence asc, id asc',
        )
        ids = list(all_subs.ids)
        return (ids.index(subdivision.id) + 1) if subdivision.id in ids else 1

    # ────────────────────────────────────────────────────────────────────────
    # Import mode: full  (ALL divisions → subdivisions → sub-subdivisions)
    # ────────────────────────────────────────────────────────────────────────

    def _import_full_structure(self):
        """Import every division, subdivision, and sub-subdivision from the master.

        Existing rows are silently skipped. Returns (created, skipped).
        """
        all_divisions = self.env['farm.division.work'].search(
            [], order='sequence asc, id asc',
        )
        _logger.info(
            'BOQ import: mode=full boq_id=%s total_divisions=%s',
            self.boq_id.id, len(all_divisions),
        )
        created, skipped = self._import_by_divisions(all_divisions)
        _logger.info(
            'BOQ import: mode=full selected_ids=ALL created=%s skipped=%s',
            created, skipped,
        )
        return created, skipped

    # ────────────────────────────────────────────────────────────────────────
    # Import mode: division  (ONLY selected divisions and their children)
    # ────────────────────────────────────────────────────────────────────────

    def _import_by_divisions(self, division_ids):
        """Import ONLY the given divisions plus ALL their subdivisions and sub-subdivisions.

        domain applied: division_id in selected_division_ids
        No other divisions are touched.

        Returns (created, skipped).
        """
        boq     = self.boq_id
        created = 0
        skipped = 0
        sections, subsections, sub_subs_set = self._build_existing_maps()

        divisions = division_ids.sorted(lambda d: (d.sequence, d.id))

        _logger.info(
            'BOQ import: mode=division boq_id=%s selected_ids=%s',
            boq.id, list(division_ids.ids),
        )

        for division in divisions:
            div_rank = self._get_div_rank(division)

            section_row, new = self._ensure_section(division, div_rank, sections, boq)
            created += int(new)
            skipped += int(not new)

            # ALL subdivisions of this division — strict domain filter
            subs = self.env['farm.subdivision.work'].search(
                [('division_id', '=', division.id)],
                order='sequence asc, id asc',
            )

            for subdivision in subs:
                sub_rank = self._get_sub_rank(subdivision)
                subsection_row, new = self._ensure_subsection(
                    subdivision, sub_rank, div_rank, section_row, subsections, boq,
                )
                created += int(new)
                skipped += int(not new)

                # ALL sub-subdivisions of this subdivision — strict domain filter
                ss_scope = self.env['farm.sub_subdivision.work'].search(
                    [('subdivision_id', '=', subdivision.id)],
                    order='sequence asc, id asc',
                )
                for sub_sub_rank, ss in enumerate(ss_scope, start=1):
                    new = self._ensure_sub_subsection(
                        ss, sub_sub_rank, div_rank, sub_rank,
                        subsection_row, sub_subs_set, boq,
                    )
                    created += int(new)
                    skipped += int(not new)

        return created, skipped

    # ────────────────────────────────────────────────────────────────────────
    # Import mode: subdivision  (ONLY selected subdivisions + parent headers)
    # ────────────────────────────────────────────────────────────────────────

    def _import_by_subdivisions(self, subdivision_ids):
        """Import ONLY the given subdivisions, their sub-subdivisions, and parent headers.

        domain applied: subdivision_id in selected_subdivision_ids
        Sibling subdivisions are NOT imported.

        Returns (created, skipped).
        """
        boq     = self.boq_id
        created = 0
        skipped = 0
        sections, subsections, sub_subs_set = self._build_existing_maps()

        sorted_subs = subdivision_ids.sorted(
            lambda s: (s.division_id.sequence, s.division_id.id, s.sequence, s.id)
        )

        _logger.info(
            'BOQ import: mode=subdivision boq_id=%s selected_ids=%s',
            boq.id, list(subdivision_ids.ids),
        )

        for subdivision in sorted_subs:
            division = subdivision.division_id
            div_rank = self._get_div_rank(division)
            sub_rank = self._get_sub_rank(subdivision)

            # Parent division header (created only if missing)
            section_row, new = self._ensure_section(division, div_rank, sections, boq)
            created += int(new)
            skipped += int(not new)

            subsection_row, new = self._ensure_subsection(
                subdivision, sub_rank, div_rank, section_row, subsections, boq,
            )
            created += int(new)
            skipped += int(not new)

            # ALL sub-subdivisions under THIS subdivision only
            ss_scope = self.env['farm.sub_subdivision.work'].search(
                [('subdivision_id', '=', subdivision.id)],
                order='sequence asc, id asc',
            )
            for sub_sub_rank, ss in enumerate(ss_scope, start=1):
                new = self._ensure_sub_subsection(
                    ss, sub_sub_rank, div_rank, sub_rank,
                    subsection_row, sub_subs_set, boq,
                )
                created += int(new)
                skipped += int(not new)

        return created, skipped

    # ────────────────────────────────────────────────────────────────────────
    # Import mode: sub_subdivision  (ONLY selected sub-subdivisions + headers)
    # ────────────────────────────────────────────────────────────────────────

    def _import_by_sub_subdivisions(self, sub_subdivision_ids):
        """Import ONLY the given sub-subdivisions plus required parent headers.

        domain applied: sub_subdivision_id in selected_sub_subdivision_ids
        Sibling sub-subdivisions are NOT imported.

        Returns (created, skipped).
        """
        boq     = self.boq_id
        created = 0
        skipped = 0
        sections, subsections, sub_subs_set = self._build_existing_maps()

        sorted_ss = sub_subdivision_ids.sorted(
            lambda ss: (
                ss.division_id.sequence, ss.division_id.id,
                ss.subdivision_id.sequence, ss.subdivision_id.id,
                ss.sequence, ss.id,
            )
        )

        # Track sequential sub_sub_rank per parent subsection row
        sub_sub_counters = {}  # subsection_row.id → next rank

        _logger.info(
            'BOQ import: mode=sub_subdivision boq_id=%s selected_ids=%s',
            boq.id, list(sub_subdivision_ids.ids),
        )

        for ss in sorted_ss:
            division    = ss.division_id
            subdivision = ss.subdivision_id
            div_rank    = self._get_div_rank(division)
            sub_rank    = self._get_sub_rank(subdivision)

            section_row, new = self._ensure_section(division, div_rank, sections, boq)
            created += int(new)
            skipped += int(not new)

            subsection_row, new = self._ensure_subsection(
                subdivision, sub_rank, div_rank, section_row, subsections, boq,
            )
            created += int(new)
            skipped += int(not new)

            sub_sub_rank = sub_sub_counters.get(subsection_row.id, 1)
            new = self._ensure_sub_subsection(
                ss, sub_sub_rank, div_rank, sub_rank,
                subsection_row, sub_subs_set, boq,
            )
            if new:
                sub_sub_counters[subsection_row.id] = sub_sub_rank + 1
                created += 1
            else:
                skipped += 1

        return created, skipped

    # ────────────────────────────────────────────────────────────────────────
    # Import mode: template  (ONLY selected templates as BOQ items + headers)
    # ────────────────────────────────────────────────────────────────────────

    def _import_by_templates(self, template_ids):
        """Import ONLY the selected templates as standalone BOQ items.

        Templates carry division_id and subdivision_id but NOT sub_subdivision_id.
        To satisfy the hierarchy constraint (which only enforces sub_subdivision_id
        on items with parent_id set), templates are imported as standalone items:
          display_type = False, parent_id = False.

        For each template:
          - Creates division/subdivision header rows if missing.
          - Creates a standalone BOQ item (no parent_id) with division_id,
            subdivision_id, and template_id populated from the template.
          - Deduplication: skips if a BOQ line with template_id=tmpl.id already
            exists in this BOQ document.

        domain applied: template.id in selected_template_ids
        All other templates are ignored.

        Returns (created, skipped).
        """
        boq     = self.boq_id
        created = 0
        skipped = 0
        sections, subsections, _sub_subs = self._build_existing_maps()

        # Existing template items dedup set
        existing_template_items = {
            l.template_id.id
            for l in boq.line_ids
            if not l.display_type and l.template_id
        }

        sorted_templates = template_ids.sorted(
            lambda t: (
                t.division_id.sequence if t.division_id else 0,
                t.division_id.id       if t.division_id else 0,
                t.subdivision_id.sequence if t.subdivision_id else 0,
                t.subdivision_id.id    if t.subdivision_id else 0,
                t.code or '', t.id,
            )
        )

        _logger.info(
            'BOQ import: mode=template boq_id=%s selected_ids=%s',
            boq.id, list(template_ids.ids),
        )

        for tmpl in sorted_templates:
            # ── Division header ───────────────────────────────────────────
            if tmpl.division_id:
                div_rank = self._get_div_rank(tmpl.division_id)
                section_row, new = self._ensure_section(
                    tmpl.division_id, div_rank, sections, boq,
                )
                created += int(new)
                skipped += int(not new)
            else:
                section_row = None
                div_rank    = 0

            # ── Subdivision header ────────────────────────────────────────
            if tmpl.subdivision_id and section_row:
                sub_rank = self._get_sub_rank(tmpl.subdivision_id)
                subsection_row, new = self._ensure_subsection(
                    tmpl.subdivision_id, sub_rank, div_rank, section_row,
                    subsections, boq,
                )
                created += int(new)
                skipped += int(not new)
            else:
                subsection_row = None
                sub_rank       = 0

            # ── Template item dedup check ─────────────────────────────────
            if tmpl.id in existing_template_items:
                _logger.debug(
                    'BOQ import: template_id=%s already in boq_id=%s — skipped.',
                    tmpl.id, boq.id,
                )
                skipped += 1
                continue

            # ── Create standalone BOQ item from template ──────────────────
            # Standalone means no parent_id — hierarchy constraint only
            # requires sub_subdivision_id when parent_id is set.
            self.env['farm.boq.line'].create({
                'boq_id':             boq.id,
                'display_type':       False,
                'name':               tmpl.name,
                'description':        tmpl.description or False,
                'division_id':        tmpl.division_id.id    if tmpl.division_id    else False,
                'subdivision_id':     tmpl.subdivision_id.id if tmpl.subdivision_id else False,
                'template_id':        tmpl.id,
                'boq_qty':            tmpl.quantity or 1.0,
                'unit_id':            tmpl.unit_id.id if tmpl.unit_id else False,
                'subsection_line_id': subsection_row.id if subsection_row else False,
                'section_line_id':    section_row.id    if section_row    else False,
                'div_rank':           div_rank,
                'sub_rank':           sub_rank,
                'sub_sub_rank':       0,
                'sequence_sub':       0,
            })
            existing_template_items.add(tmpl.id)
            created += 1

        return created, skipped

    # ────────────────────────────────────────────────────────────────────────
    # Redirect modes: manual
    # ────────────────────────────────────────────────────────────────────────

    def _action_open_add_item_wizard(self, default_mode='use_template'):
        """Close this wizard and open the Add Item / Add Subitem wizard."""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Add Item'),
            'res_model': 'farm.boq.add.subitem.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_boq_id': self.boq_id.id,
                'default_mode':   default_mode,
                'lock_location':  False,
            },
        }
