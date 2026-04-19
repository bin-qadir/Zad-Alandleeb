"""BOQ Excel Import Wizard — import an external Bill of Quantities from .xlsx.

Supports three import modes:
  • Append  — add new lines only; skip rows that already match.
  • Update  — update matching lines + append new ones.
  • Replace — delete all existing structure first, then re-import.

Matching priority (for Append / Update):
  1. By display_code (if a Code column is present in the Excel).
  2. By item name + parent sub-subdivision line.

Hierarchy resolution:
  Division / Subdivision / Sub-Subdivision values are matched against the
  farm.division.work / farm.subdivision.work / farm.sub_subdivision.work master
  data (case-insensitive).  If no match is found a new master record is created
  automatically so the import is never blocked by missing master data.
"""

import base64
import io
import json
import logging

import openpyxl

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Column-header alias table  (all lowercase)
# ─────────────────────────────────────────────────────────────────────────────
_COL_ALIASES = {
    'code':           ['code', 'item code', 'reference', 'ref', 'no.', 'no'],
    'division':       ['division', 'div', 'division name', 'chapter'],
    'subdivision':    ['subdivision', 'sub division', 'subdiv', 'sub div'],
    'sub_subdivision': [
        'sub-subdivision', 'sub subdivision', 'sub_subdivision',
        'sub sub division', 'subsub', 'sub-sub', 'section',
    ],
    'name':           [
        'name', 'description', 'item', 'item name', 'item description',
        'desc', 'work description', 'work item', 'activity',
    ],
    'qty':            ['qty', 'quantity', 'boq qty', 'boq quantity', 'amount', 'vol'],
    'unit':           ['unit', 'uom', 'unit of measure', 'u/m'],
    'unit_price':     [
        'unit price', 'unit cost', 'price', 'rate', 'unit rate',
        'cost', 'unit cost price',
    ],
    'notes':          ['notes', 'note', 'remarks', 'remark', 'comment', 'comments'],
}


def _detect_columns(header_row):
    """Map Excel column indices → field names using alias table."""
    col_map = {}
    for idx, cell in enumerate(header_row):
        val = str(cell.value or '').strip().lower()
        if not val:
            continue
        for field_name, aliases in _COL_ALIASES.items():
            if val in aliases and field_name not in col_map:
                col_map[field_name] = idx
    return col_map


# ─────────────────────────────────────────────────────────────────────────────
# Wizard
# ─────────────────────────────────────────────────────────────────────────────

class FarmBoqExcelImportWizard(models.TransientModel):
    """Two-step wizard:
       Step 1 (state=draft)     — upload file, choose mode, validate.
       Step 2 (state=validated) — review summary, confirm import.
       Step 3 (state=done)      — view result counters.
    """

    _name = 'farm.boq.excel.import.wizard'
    _description = 'BOQ Excel Import Wizard'

    # ── Identity ──────────────────────────────────────────────────────────────
    boq_id = fields.Many2one(
        'farm.boq', string='Cost Structure', required=True, readonly=True,
        ondelete='cascade',
    )

    # ── File upload ───────────────────────────────────────────────────────────
    excel_file = fields.Binary(string='Excel File (.xlsx)', attachment=False)
    file_name  = fields.Char(string='File Name')

    # ── Import options ────────────────────────────────────────────────────────
    import_mode = fields.Selection(
        selection=[
            ('append',  'Append — add new lines only (skip existing matches)'),
            ('update',  'Update — update matching lines + append new ones'),
            ('replace', 'Replace — delete all existing lines and re-import'),
        ],
        string='Import Mode',
        default='append',
        required=True,
        help=(
            'Append: new items are added; items that already match are left untouched.\n'
            'Update: matching items are updated (qty, price, notes); unmatched new items are added.\n'
            'Replace: ALL existing BOQ lines are deleted first, then the Excel is imported fresh.\n\n'
            'Matching is done by Code (if present) then by item Name + parent hierarchy.'
        ),
    )

    confirm_replace = fields.Boolean(
        string='I confirm: existing downstream analysis / job-order links may be broken',
        help='Required when Replace mode is chosen and downstream links exist.',
    )

    # ── Wizard state ──────────────────────────────────────────────────────────
    state = fields.Selection(
        selection=[
            ('draft',     'Configure'),
            ('validated', 'Review & Confirm'),
            ('done',      'Complete'),
        ],
        default='draft',
        readonly=True,
    )

    # ── Import metadata ───────────────────────────────────────────────────────
    import_date = fields.Datetime(
        string='Import Date', default=fields.Datetime.now, readonly=True,
    )
    imported_by = fields.Many2one(
        'res.users', string='Imported By',
        default=lambda self: self.env.user, readonly=True,
    )

    # ── Validation output ─────────────────────────────────────────────────────
    validation_html  = fields.Html(string='Validation Summary', readonly=True, sanitize=False)
    has_errors       = fields.Boolean(readonly=True)
    has_warnings     = fields.Boolean(readonly=True)
    has_downstream   = fields.Boolean(readonly=True)

    # ── Cached parsed rows (JSON) ─────────────────────────────────────────────
    parsed_json = fields.Text(readonly=True)

    # ── Result counters ───────────────────────────────────────────────────────
    result_created  = fields.Integer(string='Created',           readonly=True)
    result_updated  = fields.Integer(string='Updated',           readonly=True)
    result_skipped  = fields.Integer(string='Skipped',           readonly=True)
    result_deleted  = fields.Integer(string='Deleted/Replaced',  readonly=True)
    result_html     = fields.Html(string='Import Result',        readonly=True, sanitize=False)

    # ─────────────────────────────────────────────────────────────────────────
    # Step 1 — Validate
    # ─────────────────────────────────────────────────────────────────────────

    def action_validate_excel(self):
        """Parse the uploaded Excel, run validation, store results, advance state."""
        self.ensure_one()
        if not self.excel_file:
            raise UserError(_('Please upload an Excel (.xlsx) file first.'))

        try:
            rows, col_errors = self._parse_excel_rows()
        except Exception as exc:
            raise UserError(_('Failed to read the Excel file:\n%s') % str(exc)) from exc

        errors, warnings = self._validate_rows(rows, col_errors)

        # Replace-mode downstream safety check
        has_downstream = False
        if self.import_mode == 'replace':
            subitems = self.boq_id.line_ids.filtered(lambda l: not l.display_type)
            ds_warnings = subitems._check_downstream_links(subitems)
            if ds_warnings:
                has_downstream = True
                warnings.append(
                    _('Replace mode: existing BOQ has downstream links — %s')
                    % '; '.join(ds_warnings)
                )

        html = self._build_validation_html(rows, errors, warnings)
        self.write({
            'state':           'validated',
            'parsed_json':     json.dumps([dict(r) for r in rows]),
            'validation_html': html,
            'has_errors':      bool(errors),
            'has_warnings':    bool(warnings),
            'has_downstream':  has_downstream,
        })

        # Re-open the same wizard to show validation results
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Step 2 — Import
    # ─────────────────────────────────────────────────────────────────────────

    def action_confirm_import(self):
        """Execute the import using the cached validated rows."""
        self.ensure_one()

        if self.has_errors:
            raise UserError(_(
                'Cannot import: validation errors must be fixed first.\n'
                'Correct the Excel file and click "Re-validate".'
            ))
        if self.has_downstream and not self.confirm_replace:
            raise UserError(_(
                'Replace mode will break existing analysis and job-order links.\n\n'
                'Check the confirmation checkbox, then click Import again.'
            ))
        if not self.parsed_json:
            raise UserError(_('No validated data found. Please validate first.'))

        rows = json.loads(self.parsed_json)
        created, updated, skipped, deleted = self._execute_import(rows)

        self.write({
            'state':          'done',
            'result_created': created,
            'result_updated': updated,
            'result_skipped': skipped,
            'result_deleted': deleted,
            'result_html':    self._build_result_html(created, updated, skipped, deleted),
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Parsing
    # ─────────────────────────────────────────────────────────────────────────

    def _parse_excel_rows(self):
        """Read the uploaded .xlsx, detect columns, return (rows, col_errors)."""
        raw = base64.b64decode(self.excel_file)
        wb  = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        ws  = wb.active

        # Find the header row (first non-empty row)
        header_row = None
        data_iter  = ws.iter_rows()
        for row in data_iter:
            if any(c.value for c in row):
                header_row = row
                break

        if header_row is None:
            raise UserError(_('The Excel file appears to be empty.'))

        col_map    = _detect_columns(header_row)
        col_errors = []
        if 'name' not in col_map:
            col_errors.append(
                _('Missing required column: "Name" / "Description" / "Item".\n'
                  'The first matching column name (case-insensitive) is used.')
            )

        def _cell(row, field):
            idx = col_map.get(field)
            if idx is None or idx >= len(row):
                return ''
            val = row[idx].value
            return str(val).strip() if val is not None else ''

        def _float(row, field):
            idx = col_map.get(field)
            if idx is None or idx >= len(row):
                return 0.0
            val = row[idx].value
            if val is None or str(val).strip() == '':
                return 0.0
            try:
                return float(str(val).replace(',', '').strip())
            except (ValueError, TypeError):
                return None  # signals parse error

        parsed = []
        for row_num, row in enumerate(data_iter, start=2):
            if not any(c.value for c in row):
                continue
            parsed.append({
                '_row':          row_num,
                'code':          _cell(row, 'code'),
                'division':      _cell(row, 'division'),
                'subdivision':   _cell(row, 'subdivision'),
                'sub_subdivision': _cell(row, 'sub_subdivision'),
                'name':          _cell(row, 'name'),
                'qty':           _float(row, 'qty'),
                'unit':          _cell(row, 'unit'),
                'unit_price':    _float(row, 'unit_price'),
                'notes':         _cell(row, 'notes'),
            })

        wb.close()
        return parsed, col_errors

    # ─────────────────────────────────────────────────────────────────────────
    # Validation
    # ─────────────────────────────────────────────────────────────────────────

    def _validate_rows(self, rows, col_errors):
        errors   = list(col_errors)
        warnings = []

        if not rows:
            errors.append(_('The Excel file contains no data rows (below the header).'))
            return errors, warnings

        seen_codes  = {}
        has_div     = any(r['division']      for r in rows)
        has_sub     = any(r['subdivision']   for r in rows)
        has_sub_sub = any(r['sub_subdivision'] for r in rows)

        if has_sub and not has_div:
            warnings.append(_(
                'Subdivision column found but no Division column — '
                'subdivision hierarchy will be ignored.'
            ))
        if has_sub_sub and not has_sub:
            warnings.append(_(
                'Sub-Subdivision column found but no Subdivision column — '
                'sub-subdivision hierarchy will be ignored.'
            ))

        for r in rows:
            rn = r['_row']
            if not r['name']:
                errors.append(_('Row %d: missing item name/description.') % rn)
            if r['qty'] is None:
                errors.append(_('Row %d: invalid quantity value (not a number).') % rn)
            if r['unit_price'] is None:
                errors.append(_('Row %d: invalid unit price value (not a number).') % rn)
            if r['code']:
                if r['code'] in seen_codes:
                    warnings.append(_(
                        'Row %d: duplicate code "%s" (first seen on row %d) — '
                        'later row takes precedence in Update mode.'
                    ) % (rn, r['code'], seen_codes[r['code']]))
                else:
                    seen_codes[r['code']] = rn

        return errors, warnings

    # ─────────────────────────────────────────────────────────────────────────
    # Import execution
    # ─────────────────────────────────────────────────────────────────────────

    def _execute_import(self, rows):
        """Build or update the BOQ structure from parsed rows.

        Returns (created, updated, skipped, deleted).
        """
        boq  = self.boq_id
        Line = self.env['farm.boq.line']
        mode = self.import_mode

        # ── Replace: wipe existing structure ─────────────────────────────────
        deleted = 0
        if mode == 'replace':
            existing = Line.search([('boq_id', '=', boq.id)])
            deleted  = len(existing)
            existing.with_context(allow_classification_change=True).unlink()

        # ── Master-data caches (avoid redundant searches) ─────────────────────
        div_cache = {}   # name_lower → farm.division.work
        sub_cache = {}   # (div_id, name_lower) → farm.subdivision.work
        ss_cache  = {}   # (sub_id, name_lower) → farm.sub_subdivision.work

        # ── BOQ structural-line caches ────────────────────────────────────────
        div_line_cache = {}   # div_work.id → farm.boq.line (line_section)
        sub_line_cache = {}   # sub_work.id → farm.boq.line (line_subsection)
        ss_line_cache  = {}   # ss_work.id  → farm.boq.line (line_sub_subsection)

        if mode != 'replace':
            for line in Line.search([('boq_id', '=', boq.id), ('display_type', '!=', False)]):
                if line.display_type == 'line_section' and line.division_id:
                    div_line_cache[line.division_id.id] = line
                elif line.display_type == 'line_subsection' and line.subdivision_id:
                    sub_line_cache[line.subdivision_id.id] = line
                elif line.display_type == 'line_sub_subsection' and line.sub_subdivision_id:
                    ss_line_cache[line.sub_subdivision_id.id] = line

        # ── Existing-item caches (for append / update matching) ───────────────
        existing_by_code = {}   # display_code → farm.boq.line
        existing_by_name = {}   # (name_lower, parent_id) → farm.boq.line
        if mode in ('append', 'update'):
            for item in Line.search([
                ('boq_id',       '=', boq.id),
                ('display_type', '=', False),
                ('parent_id',    '!=', False),
            ]):
                if item.display_code:
                    existing_by_code[item.display_code] = item
                key = ((item.name or '').strip().lower(), item.parent_id.id)
                existing_by_name[key] = item

        created = updated = skipped = 0

        # ── Process each row ──────────────────────────────────────────────────
        for r in rows:
            name = r.get('name', '').strip()
            if not name:
                skipped += 1
                continue

            # Resolve master data
            div_work = self._get_or_create_division(r['division'], div_cache)
            sub_work = (
                self._get_or_create_subdivision(r['subdivision'], div_work, sub_cache)
                if div_work else None
            )
            ss_work = (
                self._get_or_create_sub_subdivision(r['sub_subdivision'], sub_work, ss_cache)
                if sub_work else None
            )

            # Ensure structural BOQ lines exist
            div_line = sub_line = ss_line = None

            if div_work:
                div_line = div_line_cache.get(div_work.id)
                if not div_line:
                    div_line = Line.create({
                        'boq_id':       boq.id,
                        'name':         div_work.name,
                        'display_type': 'line_section',
                        'division_id':  div_work.id,
                    })
                    div_line_cache[div_work.id] = div_line

            if sub_work and div_line:
                sub_line = sub_line_cache.get(sub_work.id)
                if not sub_line:
                    sub_line = Line.create({
                        'boq_id':          boq.id,
                        'name':            sub_work.name,
                        'display_type':    'line_subsection',
                        'division_id':     div_work.id,
                        'subdivision_id':  sub_work.id,
                        'section_line_id': div_line.id,
                    })
                    sub_line_cache[sub_work.id] = sub_line

            if ss_work and sub_line:
                ss_line = ss_line_cache.get(ss_work.id)
                if not ss_line:
                    ss_line = Line.create({
                        'boq_id':              boq.id,
                        'name':                ss_work.name,
                        'display_type':        'line_sub_subsection',
                        'division_id':         div_work.id,
                        'subdivision_id':      sub_work.id,
                        'sub_subdivision_id':  ss_work.id,
                        'section_line_id':     div_line.id,
                        'subsection_line_id':  sub_line.id,
                    })
                    ss_line_cache[ss_work.id] = ss_line

            if not ss_line:
                _logger.warning(
                    'BOQ Excel Import [%s]: row %s skipped — no valid sub-subdivision hierarchy',
                    boq.name, r['_row'],
                )
                skipped += 1
                continue

            # Resolve unit
            unit_id = self._find_unit(r['unit']) if r['unit'] else False

            item_vals = {
                'name':        name,
                'boq_qty':     r['qty']       or 0.0,
                'unit_id':     unit_id,
                'unit_price':  r['unit_price'] or 0.0,
                'description': r['notes']     or '',
            }

            # Match existing item
            existing = None
            if mode in ('append', 'update'):
                if r['code']:
                    existing = existing_by_code.get(r['code'])
                if not existing:
                    key = (name.lower(), ss_line.id)
                    existing = existing_by_name.get(key)

            if existing:
                if mode == 'update':
                    existing.write(item_vals)
                    updated += 1
                else:
                    skipped += 1   # append: already exists
            else:
                new_item = Line.create({
                    **item_vals,
                    'boq_id':    boq.id,
                    'parent_id': ss_line.id,
                })
                created += 1
                if r['code']:
                    existing_by_code[r['code']] = new_item
                existing_by_name[(name.lower(), ss_line.id)] = new_item

        # Rebuild sequence for clean codes
        boq._rebuild_sequence()
        _logger.info(
            'BOQ Excel Import [%s]: created=%d updated=%d skipped=%d deleted=%d',
            boq.name, created, updated, skipped, deleted,
        )
        return created, updated, skipped, deleted

    # ─────────────────────────────────────────────────────────────────────────
    # Master-data helpers (find or auto-create)
    # ─────────────────────────────────────────────────────────────────────────

    def _get_or_create_division(self, name, cache):
        if not name or not name.strip():
            return None
        key = name.strip().lower()
        if key in cache:
            return cache[key]
        Division = self.env['farm.division.work']
        rec = Division.search([('name', '=ilike', name.strip())], limit=1)
        if not rec:
            rec = Division.create({'name': name.strip()})
        cache[key] = rec
        return rec

    def _get_or_create_subdivision(self, name, division, cache):
        if not name or not name.strip() or not division:
            return None
        key = (division.id, name.strip().lower())
        if key in cache:
            return cache[key]
        Subdivision = self.env['farm.subdivision.work']
        rec = Subdivision.search([
            ('name', '=ilike', name.strip()),
            ('division_id', '=', division.id),
        ], limit=1)
        if not rec:
            rec = Subdivision.create({
                'name': name.strip(),
                'division_id': division.id,
            })
        cache[key] = rec
        return rec

    def _get_or_create_sub_subdivision(self, name, subdivision, cache):
        if not name or not name.strip() or not subdivision:
            return None
        key = (subdivision.id, name.strip().lower())
        if key in cache:
            return cache[key]
        SubSub = self.env['farm.sub_subdivision.work']
        rec = SubSub.search([
            ('name', '=ilike', name.strip()),
            ('subdivision_id', '=', subdivision.id),
        ], limit=1)
        if not rec:
            rec = SubSub.create({
                'name': name.strip(),
                'subdivision_id': subdivision.id,
                'division_id': subdivision.division_id.id,
            })
        cache[key] = rec
        return rec

    def _find_unit(self, unit_name):
        """Find a uom.uom record by name (any category, case-insensitive)."""
        if not unit_name or not unit_name.strip():
            return False
        rec = self.env['uom.uom'].search(
            [('name', '=ilike', unit_name.strip())], limit=1
        )
        return rec.id if rec else False

    # ─────────────────────────────────────────────────────────────────────────
    # HTML builders
    # ─────────────────────────────────────────────────────────────────────────

    def _build_validation_html(self, rows, errors, warnings):
        item_count  = sum(1 for r in rows if r.get('name'))
        div_count   = len({r['division']        for r in rows if r.get('division')})
        sub_count   = len({r['subdivision']     for r in rows if r.get('subdivision')})
        ss_count    = len({r['sub_subdivision'] for r in rows if r.get('sub_subdivision')})

        parts = []
        parts.append(
            '<div class="alert alert-info mb-3">'
            '<strong>Parsed:</strong> '
            f'{len(rows)} total rows — <strong>{item_count}</strong> items, '
            f'{div_count} divisions, {sub_count} subdivisions, {ss_count} sub-subdivisions'
            '</div>'
        )

        if errors:
            parts.append(
                '<div class="alert alert-danger"><strong>Errors (must fix before importing):</strong><ul>'
            )
            for e in errors[:20]:   # cap at 20 to avoid enormous HTML
                parts.append(f'<li>{e}</li>')
            if len(errors) > 20:
                parts.append(f'<li>… and {len(errors) - 20} more error(s).</li>')
            parts.append('</ul></div>')

        if warnings:
            parts.append(
                '<div class="alert alert-warning"><strong>Warnings:</strong><ul>'
            )
            for w in warnings[:20]:
                parts.append(f'<li>{w}</li>')
            if len(warnings) > 20:
                parts.append(f'<li>… and {len(warnings) - 20} more warning(s).</li>')
            parts.append('</ul></div>')

        if not errors and not warnings:
            parts.append(
                '<div class="alert alert-success">'
                '<strong>✓ Validation passed</strong> — ready to import.'
                '</div>'
            )
        elif not errors:
            parts.append(
                '<div class="alert alert-success">'
                '<strong>✓ No errors</strong> — you may import despite the warnings above.'
                '</div>'
            )

        return ''.join(parts)

    def _build_result_html(self, created, updated, skipped, deleted):
        parts = [
            '<div class="alert alert-success">'
            '<strong>Import complete!</strong>'
            '<ul style="margin-bottom:0">'
        ]
        parts.append(f'<li>Created: <strong>{created}</strong> new line(s)</li>')
        if updated:
            parts.append(f'<li>Updated: <strong>{updated}</strong> existing line(s)</li>')
        if skipped:
            parts.append(f'<li>Skipped: <strong>{skipped}</strong> line(s) (already matched / no hierarchy)</li>')
        if deleted:
            parts.append(f'<li>Deleted: <strong>{deleted}</strong> line(s) (Replace mode)</li>')
        parts.append('</ul></div>')
        return ''.join(parts)
