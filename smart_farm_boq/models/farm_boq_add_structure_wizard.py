from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class FarmBoqAddStructureWizard(models.TransientModel):
    """Wizard: bulk-import work structure branches into a BOQ.

    Supports three import scenarios:

    A) Division only (subdivision_ids and sub_subdivision_ids both empty)
       → Imports ALL subdivisions + sub-subdivisions under the selected
         division(s).

    B) Division + specific Subdivisions (sub_subdivision_ids empty)
       → Imports only those subdivision branches and ALL their
         sub-subdivisions.

    C) Division + Subdivisions + specific Sub-Subdivisions
       → Imports exactly those sub-subdivision leaves (and their required
         parent rows).

    Duplicate-safe: existing structural rows are identified by their
    classification key (division_id / subdivision_id / sub_subdivision_id)
    and are skipped silently.

    A sequence rebuild is triggered automatically after every import so that
    BOQ codes (01 / 1.01 / 1.01.01) are always correct.
    """

    _name = 'farm.boq.add_structure.wizard'
    _description = 'Add BOQ Structure Wizard'

    # ── Context (pre-filled from the BOQ form button) ─────────────────────────
    boq_id = fields.Many2one(
        'farm.boq',
        string='BOQ Document',
        required=True,
        ondelete='cascade',
        readonly=True,
    )

    # ── Step 1: Divisions ─────────────────────────────────────────────────────
    division_ids = fields.Many2many(
        'farm.division.work',
        'boq_add_struct_wiz_div_rel',
        'wizard_id', 'division_id',
        string='Divisions',
        required=True,
        help='Select one or more Division(s) to import into the BOQ.',
    )

    # ── Step 2: Subdivisions (optional — filtered by selected divisions) ──────
    subdivision_ids = fields.Many2many(
        'farm.subdivision.work',
        'boq_add_struct_wiz_sub_rel',
        'wizard_id', 'subdivision_id',
        string='Subdivisions',
        domain="[('division_id', 'in', division_ids)]",
        help=(
            'Optional. If left empty, ALL subdivisions under the selected '
            'division(s) are imported.'
        ),
    )

    # ── Step 3: Sub-Subdivisions (optional — filtered by selected subdivisions)
    sub_subdivision_ids = fields.Many2many(
        'farm.sub_subdivision.work',
        'boq_add_struct_wiz_subsub_rel',
        'wizard_id', 'sub_subdivision_id',
        string='Sub-Subdivisions',
        domain="[('subdivision_id', 'in', subdivision_ids)]",
        help=(
            'Optional. If left empty, ALL sub-subdivisions under the '
            'selected (or resolved) subdivision(s) are imported.'
        ),
    )

    # ────────────────────────────────────────────────────────────────────────
    # Onchange — clear dependent selections when parent changes
    # ────────────────────────────────────────────────────────────────────────

    @api.onchange('division_ids')
    def _onchange_division_ids(self):
        """Clear subdivision/sub-subdivision when divisions change."""
        invalid_subs = self.subdivision_ids.filtered(
            lambda s: s.division_id not in self.division_ids
        )
        if invalid_subs:
            self.subdivision_ids -= invalid_subs
        # Clearing subdivisions also clears sub-subdivisions via next onchange

    @api.onchange('subdivision_ids')
    def _onchange_subdivision_ids(self):
        """Clear sub-subdivisions that no longer belong to selected subdivisions."""
        if not self.subdivision_ids:
            self.sub_subdivision_ids = False
            return
        invalid_subsubs = self.sub_subdivision_ids.filtered(
            lambda ss: ss.subdivision_id not in self.subdivision_ids
        )
        if invalid_subsubs:
            self.sub_subdivision_ids -= invalid_subsubs

    # ────────────────────────────────────────────────────────────────────────
    # Validation
    # ────────────────────────────────────────────────────────────────────────

    @api.constrains('division_ids', 'subdivision_ids', 'sub_subdivision_ids')
    def _check_selection_consistency(self):
        """Ensure subdivision/sub-subdivision selections are within parent scope."""
        for rec in self:
            if rec.subdivision_ids:
                invalid = rec.subdivision_ids.filtered(
                    lambda s: s.division_id not in rec.division_ids
                )
                if invalid:
                    raise ValidationError(_(
                        'The following subdivisions do not belong to the '
                        'selected division(s): %s',
                        ', '.join(invalid.mapped('name')),
                    ))

            if rec.sub_subdivision_ids:
                # Resolve which subdivisions are in scope
                if rec.subdivision_ids:
                    in_scope_subs = rec.subdivision_ids
                else:
                    in_scope_subs = rec.env['farm.subdivision.work'].search(
                        [('division_id', 'in', rec.division_ids.ids)]
                    )
                invalid = rec.sub_subdivision_ids.filtered(
                    lambda ss: ss.subdivision_id not in in_scope_subs
                )
                if invalid:
                    raise ValidationError(_(
                        'The following sub-subdivisions do not belong to the '
                        'selected (or resolved) subdivision(s): %s',
                        ', '.join(invalid.mapped('name')),
                    ))

    # ────────────────────────────────────────────────────────────────────────
    # Main action
    # ────────────────────────────────────────────────────────────────────────

    def action_import(self):
        """Execute the import and return a success notification."""
        self.ensure_one()

        if not self.division_ids:
            raise UserError(_('Please select at least one Division.'))

        boq = self.boq_id
        created, skipped = self._import_structure()
        boq._rebuild_sequence()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Structure Imported'),
                'message': _(
                    '%d structural row(s) added to "%s".  '
                    '%d row(s) already existed and were skipped.',
                    created, boq.name, skipped,
                ),
                'type': 'success',
                'sticky': False,
            },
        }

    # ────────────────────────────────────────────────────────────────────────
    # Import logic
    # ────────────────────────────────────────────────────────────────────────

    def _import_structure(self):
        """Build the selected structure tree in the BOQ.

        Returns (created_count, skipped_count).

        Duplicate detection key:
          line_section        → (boq_id, display_type='line_section', division_id)
          line_subsection     → (boq_id, display_type='line_subsection', subdivision_id)
          line_sub_subsection → (boq_id, display_type='line_sub_subsection', sub_subdivision_id)

        No subitems are created — this wizard inserts structural scaffolding only.
        """
        boq = self.boq_id
        BoqLine = self.env['farm.boq.line']
        created = 0
        skipped = 0

        # Pre-load existing structural lines for fast duplicate lookup
        existing_sections = {
            l.division_id.id: l
            for l in boq.line_ids
            if l.display_type == 'line_section' and l.division_id
        }
        existing_subsections = {
            l.subdivision_id.id: l
            for l in boq.line_ids
            if l.display_type == 'line_subsection' and l.subdivision_id
        }
        existing_sub_subsections = {
            l.sub_subdivision_id.id: l
            for l in boq.line_ids
            if l.display_type == 'line_sub_subsection' and l.sub_subdivision_id
        }

        # ── Sort divisions by master sequence ─────────────────────────────────
        divisions = self.division_ids.sorted(lambda d: (d.sequence, d.id))

        for div_rank, division in enumerate(divisions, start=1):
            div_label = division.display_name_bilingual or division.name

            # ── Level 1: Division row ─────────────────────────────────────────
            if division.id in existing_sections:
                section = existing_sections[division.id]
                skipped += 1
            else:
                section = BoqLine.create({
                    'boq_id':        boq.id,
                    'display_type':  'line_section',
                    'name':          div_label,
                    'division_id':   division.id,
                    'sequence_main': div_rank,
                    'div_rank':      div_rank,
                })
                existing_sections[division.id] = section
                created += 1

            # ── Resolve which subdivisions to import ──────────────────────────
            if self.subdivision_ids:
                subdivisions = self.subdivision_ids.filtered(
                    lambda s: s.division_id.id == division.id
                ).sorted(lambda s: (s.sequence, s.id))
            else:
                subdivisions = self.env['farm.subdivision.work'].search(
                    [('division_id', '=', division.id)],
                    order='sequence asc, id asc',
                )

            for sub_rank, subdivision in enumerate(subdivisions, start=1):
                sub_label = subdivision.display_name_bilingual or subdivision.name

                # ── Level 2: Subdivision row ──────────────────────────────────
                if subdivision.id in existing_subsections:
                    subsection = existing_subsections[subdivision.id]
                    skipped += 1
                else:
                    subsection = BoqLine.create({
                        'boq_id':           boq.id,
                        'display_type':     'line_subsection',
                        'name':             sub_label,
                        'division_id':      division.id,
                        'subdivision_id':   subdivision.id,
                        'section_line_id':  section.id,
                        'div_rank':         div_rank,
                        'sub_rank':         sub_rank,
                        'sequence_sub':     sub_rank,
                    })
                    existing_subsections[subdivision.id] = subsection
                    created += 1

                # ── Resolve which sub-subdivisions to import ──────────────────
                if self.sub_subdivision_ids:
                    sub_subdivisions = self.sub_subdivision_ids.filtered(
                        lambda ss: ss.subdivision_id.id == subdivision.id
                    ).sorted(lambda ss: (ss.sequence, ss.id))
                else:
                    sub_subdivisions = self.env['farm.sub_subdivision.work'].search(
                        [('subdivision_id', '=', subdivision.id)],
                        order='sequence asc, id asc',
                    )

                for sub_sub_rank, sub_subdivision in enumerate(sub_subdivisions, start=1):
                    sub_sub_label = (
                        sub_subdivision.display_name_bilingual or sub_subdivision.name
                    )

                    # ── Level 3: Sub-Subdivision row ──────────────────────────
                    if sub_subdivision.id in existing_sub_subsections:
                        skipped += 1
                    else:
                        BoqLine.create({
                            'boq_id':              boq.id,
                            'display_type':        'line_sub_subsection',
                            'name':                sub_sub_label,
                            'division_id':         division.id,
                            'subdivision_id':      subdivision.id,
                            'sub_subdivision_id':  sub_subdivision.id,
                            'subsection_line_id':  subsection.id,
                            'div_rank':            div_rank,
                            'sub_rank':            sub_rank,
                            'sub_sub_rank':        sub_sub_rank,
                            'sequence_sub':        sub_sub_rank,
                        })
                        existing_sub_subsections[sub_subdivision.id] = True
                        created += 1

        return created, skipped
