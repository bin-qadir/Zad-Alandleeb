from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class FarmBoqAddStructureWizard(models.TransientModel):
    """Wizard: flexible insertion of work structure into a BOQ.

    ## Insert Modes

    full
        Import ALL divisions, subdivisions, and sub-subdivisions from the
        master catalogue.  Existing rows are skipped.

    division
        User selects one or more Divisions.  All their Subdivisions and
        Sub-Subdivisions are imported.

    subdivision
        User selects one or more Subdivisions (optionally filter by Division
        first).  All their Sub-Subdivisions are imported.

    sub_subdivision
        User selects specific Sub-Subdivisions (optionally filter by higher
        levels first).  Only those rows — plus required parent rows — are
        imported.

    template
        Redirects to the Add Item wizard pre-set to "Use Ready Template" mode.
        The user then picks the template and sub-subdivision interactively.

    manual
        Redirects to the Add Item wizard pre-set to "Create New Subitem" mode.
        The user fills in the item details manually.

    ## Duplicate safety

    All structural modes use the same duplicate-detection keys:
      line_section        → (boq_id, division_id)
      line_subsection     → (boq_id, subdivision_id)
      line_sub_subsection → (boq_id, sub_subdivision_id)

    Existing rows are silently skipped; the BOQ sequence is rebuilt after.
    """

    _name = 'farm.boq.add_structure.wizard'
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
            ('full',            'Full Structure'),
            ('division',        'By Division'),
            ('subdivision',     'By Subdivision'),
            ('sub_subdivision', 'By Sub-Subdivision'),
            ('template',        'By Template / Item'),
            ('manual',          'Manual (line by line)'),
        ],
        string='Insert Mode',
        required=True,
        default='division',
    )

    # ── Division selector ─────────────────────────────────────────────────────
    division_ids = fields.Many2many(
        'farm.division.work',
        'boq_add_struct_wiz_div_rel',
        'wizard_id', 'division_id',
        string='Divisions',
        help=(
            'Required for "By Division" mode.\n'
            'Optional filter for "By Subdivision" and "By Sub-Subdivision".'
        ),
    )

    # ── Subdivision selector ──────────────────────────────────────────────────
    subdivision_ids = fields.Many2many(
        'farm.subdivision.work',
        'boq_add_struct_wiz_sub_rel',
        'wizard_id', 'subdivision_id',
        string='Subdivisions',
        domain="[('division_id', 'in', division_ids)]",
        help=(
            'Required for "By Subdivision" mode.\n'
            'Optional filter for "By Sub-Subdivision".\n'
            'Leave empty in "By Division" → all subdivisions are imported.'
        ),
    )

    # ── Sub-Subdivision selector ──────────────────────────────────────────────
    sub_subdivision_ids = fields.Many2many(
        'farm.sub_subdivision.work',
        'boq_add_struct_wiz_subsub_rel',
        'wizard_id', 'sub_subdivision_id',
        string='Sub-Subdivisions',
        domain="[('subdivision_id', 'in', subdivision_ids)]",
        help=(
            'Required for "By Sub-Subdivision" mode.\n'
            'Leave empty in higher modes → all sub-subdivisions are imported.'
        ),
    )

    # ────────────────────────────────────────────────────────────────────────
    # Onchanges — cascade-clear dependent selections on mode or parent change
    # ────────────────────────────────────────────────────────────────────────

    @api.onchange('insert_mode')
    def _onchange_insert_mode(self):
        """Clear selections that are irrelevant to the newly chosen mode."""
        mode = self.insert_mode
        if mode in ('full', 'template', 'manual'):
            self.division_ids = False
            self.subdivision_ids = False
            self.sub_subdivision_ids = False
        elif mode == 'division':
            self.subdivision_ids = False
            self.sub_subdivision_ids = False
        elif mode == 'subdivision':
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
            return
        invalid = self.sub_subdivision_ids.filtered(
            lambda ss: ss.subdivision_id not in self.subdivision_ids
        )
        if invalid:
            self.sub_subdivision_ids -= invalid

    # ────────────────────────────────────────────────────────────────────────
    # Public action — entry point from the wizard footer
    # ────────────────────────────────────────────────────────────────────────

    def action_import(self):
        """Dispatch to the appropriate handler based on insert_mode."""
        self.ensure_one()
        mode = self.insert_mode

        # Redirect modes — open Add Item wizard instead
        if mode == 'template':
            return self._action_open_add_item_wizard(default_mode='use_template')
        if mode == 'manual':
            return self._action_open_add_item_wizard(default_mode='create_new')

        # Structure-insertion modes
        created, skipped = self._dispatch_import(mode)
        self.boq_id._rebuild_sequence()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Structure Imported'),
                'message': _(
                    '%d structural row(s) added to "%s".  '
                    '%d row(s) already existed and were skipped.',
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
        """Return (created, skipped) after running the correct import for mode."""
        if mode == 'full':
            divisions = self.env['farm.division.work'].search(
                [], order='sequence asc, id asc',
            )
            return self._do_import_structure(divisions=divisions)

        if mode == 'division':
            if not self.division_ids:
                raise UserError(_('Please select at least one Division.'))
            return self._do_import_structure(
                divisions=self.division_ids.sorted(lambda d: (d.sequence, d.id)),
            )

        if mode == 'subdivision':
            if not self.subdivision_ids:
                raise UserError(_('Please select at least one Subdivision.'))
            return self._do_import_by_subdivision()

        if mode == 'sub_subdivision':
            if not self.sub_subdivision_ids:
                raise UserError(_('Please select at least one Sub-Subdivision.'))
            return self._do_import_by_sub_subdivision()

        raise UserError(_('Unknown insert mode: %s') % mode)

    # ────────────────────────────────────────────────────────────────────────
    # Helper: pre-load existing structural rows for duplicate detection
    # ────────────────────────────────────────────────────────────────────────

    def _build_existing_maps(self):
        """Return (sections_dict, subsections_dict, sub_subs_set) for this BOQ."""
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
        """Get or create line_section row. Returns (row, was_new)."""
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

    def _ensure_subsection(self, subdivision, sub_rank, div_rank, section_row, subsections, boq):
        """Get or create line_subsection row. Returns (row, was_new)."""
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
        """Create line_sub_subsection row if not duplicate. Returns True if created."""
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
        all_divs = self.env['farm.division.work'].search([], order='sequence asc, id asc')
        ids = list(all_divs.ids)
        return (ids.index(division.id) + 1) if division.id in ids else 1

    def _get_sub_rank(self, subdivision):
        all_subs = self.env['farm.subdivision.work'].search(
            [('division_id', '=', subdivision.division_id.id)],
            order='sequence asc, id asc',
        )
        ids = list(all_subs.ids)
        return (ids.index(subdivision.id) + 1) if subdivision.id in ids else 1

    # ────────────────────────────────────────────────────────────────────────
    # Import mode: full / division
    # ────────────────────────────────────────────────────────────────────────

    def _do_import_structure(self, divisions):
        """Import divisions and their children.

        self.subdivision_ids (if set) narrows to specific subdivisions.
        self.sub_subdivision_ids (if set) narrows to specific sub-subdivisions.
        These filters apply only in 'division' mode when the user explicitly
        chose partial filtering; they are empty for 'full' mode.
        """
        boq = self.boq_id
        created = 0
        skipped = 0
        sections, subsections, sub_subs_set = self._build_existing_maps()

        for division in divisions:
            div_rank = self._get_div_rank(division)

            section_row, new = self._ensure_section(division, div_rank, sections, boq)
            created += int(new)
            skipped += int(not new)

            # Resolve subdivisions in scope
            if self.subdivision_ids:
                subs = self.subdivision_ids.filtered(
                    lambda s: s.division_id.id == division.id
                ).sorted(lambda s: (s.sequence, s.id))
            else:
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

                # Resolve sub-subdivisions in scope
                if self.sub_subdivision_ids:
                    ss_scope = self.sub_subdivision_ids.filtered(
                        lambda ss: ss.subdivision_id.id == subdivision.id
                    ).sorted(lambda ss: (ss.sequence, ss.id))
                else:
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
    # Import mode: subdivision
    # ────────────────────────────────────────────────────────────────────────

    def _do_import_by_subdivision(self):
        """Import starting from the selected subdivisions.

        Parent division rows are created automatically if missing.
        All sub-subdivisions under each selected subdivision are imported.
        """
        boq = self.boq_id
        created = 0
        skipped = 0
        sections, subsections, sub_subs_set = self._build_existing_maps()

        sorted_subs = self.subdivision_ids.sorted(
            lambda s: (s.division_id.sequence, s.division_id.id, s.sequence, s.id)
        )

        for subdivision in sorted_subs:
            division = subdivision.division_id
            div_rank = self._get_div_rank(division)
            sub_rank = self._get_sub_rank(subdivision)

            section_row, new = self._ensure_section(division, div_rank, sections, boq)
            created += int(new)
            skipped += int(not new)

            subsection_row, new = self._ensure_subsection(
                subdivision, sub_rank, div_rank, section_row, subsections, boq,
            )
            created += int(new)
            skipped += int(not new)

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
    # Import mode: sub_subdivision
    # ────────────────────────────────────────────────────────────────────────

    def _do_import_by_sub_subdivision(self):
        """Import only the selected sub-subdivisions.

        Parent division and subdivision rows are created automatically if missing.
        sub_sub_rank is assigned sequentially within each parent subdivision.
        """
        boq = self.boq_id
        created = 0
        skipped = 0
        sections, subsections, sub_subs_set = self._build_existing_maps()

        sorted_ss = self.sub_subdivision_ids.sorted(
            lambda ss: (
                ss.division_id.sequence, ss.division_id.id,
                ss.subdivision_id.sequence, ss.subdivision_id.id,
                ss.sequence, ss.id,
            )
        )

        # Track running sub_sub_rank per parent-subsection to assign sequential codes
        sub_sub_counters = {}  # subsection_row.id → next rank int

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
    # Redirect modes: template / manual
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
