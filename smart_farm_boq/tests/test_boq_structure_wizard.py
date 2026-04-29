"""
Tests for farm.boq.add_structure.wizard — Strict Scope Import.

Master structure used across all test cases:
    Division A
      Subdivision A1
        SubSub A1.1
        SubSub A1.2
      Subdivision A2
        SubSub A2.1
    Division B
      Subdivision B1
        SubSub B1.1

Test matrix:
    1. Full Structure      → imports Division A + Division B
    2. By Division A       → imports ONLY A (not B)
    3. By Subdivision A1   → imports ONLY A1 (not A2, not B)
    4. By Sub-Sub A1.1     → imports ONLY A1.1 (not A1.2, not A2.1)
    5. By Template (A)     → imports ONLY Template A item (not B)
    6. Empty selection     → UserError raised for all scoped modes
    7. Re-run same import  → no duplicate rows
    8. structure_icon      → correct emoji per row type
"""

import unittest

from odoo.fields import Command
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestBOQStructureWizard(TransactionCase):
    """Controlled unit tests for Add BOQ Structure wizard strict scope filtering."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))

        # ── Master work structure ──────────────────────────────────────────────
        WD  = cls.env['farm.division.work']
        WS  = cls.env['farm.subdivision.work']
        WSS = cls.env['farm.sub_subdivision.work']

        cls.div_a = WD.create({'name': 'TEST-WIZ Division A', 'sequence': 9901})
        cls.div_b = WD.create({'name': 'TEST-WIZ Division B', 'sequence': 9902})

        cls.sub_a1 = WS.create({'name': 'TEST-WIZ Sub A1', 'division_id': cls.div_a.id, 'sequence': 1})
        cls.sub_a2 = WS.create({'name': 'TEST-WIZ Sub A2', 'division_id': cls.div_a.id, 'sequence': 2})
        cls.sub_b1 = WS.create({'name': 'TEST-WIZ Sub B1', 'division_id': cls.div_b.id, 'sequence': 1})

        # sub_subdivision: division_id may be stored or related; pass explicitly if accepted
        def _mk_ss(name, subdivision, division):
            vals = {'name': name, 'subdivision_id': subdivision.id}
            # Try to pass division_id; model accepts or ignores it
            try:
                rec = WSS.with_context(tracking_disable=True).create(
                    dict(vals, division_id=division.id)
                )
            except Exception:
                rec = WSS.with_context(tracking_disable=True).create(vals)
            return rec

        cls.ss_a11 = _mk_ss('TEST-WIZ SubSub A1.1', cls.sub_a1, cls.div_a)
        cls.ss_a12 = _mk_ss('TEST-WIZ SubSub A1.2', cls.sub_a1, cls.div_a)
        cls.ss_a21 = _mk_ss('TEST-WIZ SubSub A2.1', cls.sub_a2, cls.div_a)
        cls.ss_b11 = _mk_ss('TEST-WIZ SubSub B1.1', cls.sub_b1, cls.div_b)

        # ── BOQ project + document ─────────────────────────────────────────────
        # Use an existing farm.project from demo data to avoid triggering
        # project.project creation (which has a billing_type NOT NULL constraint
        # that requires sale_timesheet-aware defaults we can't easily set here).
        cls.project = cls.env['farm.project'].search([], limit=1)
        if not cls.project:
            raise unittest.SkipTest('No farm.project found in database — cannot run BOQ wizard tests')
        cls.boq = cls.env['farm.boq'].create({
            'project_id': cls.project.id,
            'name': 'TEST-WIZ-BOQ-001',
        })

        # ── Templates for template-mode tests ────────────────────────────────
        cls.tmpl_a = cls.env['farm.boq.line.template'].create({
            'name':           'TEST-WIZ Template A',
            'division_id':    cls.div_a.id,
            'subdivision_id': cls.sub_a1.id,
        })
        cls.tmpl_b = cls.env['farm.boq.line.template'].create({
            'name':           'TEST-WIZ Template B',
            'division_id':    cls.div_b.id,
            'subdivision_id': cls.sub_b1.id,
        })

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _new_wizard(self, mode, **kw):
        return self.env['farm.boq.add_structure.wizard'].create({
            'boq_id':      self.boq.id,
            'insert_mode': mode,
            **kw,
        })

    def _boq_lines(self, display_type=None, division_id=None,
                   subdivision_id=None, sub_subdivision_id=None):
        domain = [('boq_id', '=', self.boq.id)]
        if display_type is not None:
            domain.append(('display_type', '=', display_type))
        if division_id is not None:
            domain.append(('division_id', '=', division_id.id))
        if subdivision_id is not None:
            domain.append(('subdivision_id', '=', subdivision_id.id))
        if sub_subdivision_id is not None:
            domain.append(('sub_subdivision_id', '=', sub_subdivision_id.id))
        return self.env['farm.boq.line'].search(domain)

    # ── Test 1: Full Structure ────────────────────────────────────────────────

    def test_01_full_structure_imports_all_divisions(self):
        """Full Structure must import both Division A and Division B."""
        wiz = self._new_wizard('full')
        wiz.action_import()

        self.assertTrue(
            self._boq_lines(display_type='line_section', division_id=self.div_a),
            'Full import must create Division A section row',
        )
        self.assertTrue(
            self._boq_lines(display_type='line_section', division_id=self.div_b),
            'Full import must create Division B section row',
        )
        # Sub-structure of both divisions
        for sub in (self.sub_a1, self.sub_a2, self.sub_b1):
            self.assertTrue(self._boq_lines(subdivision_id=sub),
                            f'{sub.name} must be imported in full mode')
        for ss in (self.ss_a11, self.ss_a12, self.ss_a21, self.ss_b11):
            self.assertTrue(self._boq_lines(sub_subdivision_id=ss),
                            f'{ss.name} must be imported in full mode')

    # ── Test 2: By Division ───────────────────────────────────────────────────

    def test_02_by_division_imports_only_selected_division(self):
        """By Division A must import ONLY Division A — Division B must be absent."""
        wiz = self._new_wizard('division',
                               division_ids=[Command.set([self.div_a.id])])
        wiz.action_import()

        # Division A present
        self.assertTrue(
            self._boq_lines(display_type='line_section', division_id=self.div_a),
            'Division A section row must be created',
        )
        # Division B MUST NOT be present
        self.assertFalse(
            self._boq_lines(display_type='line_section', division_id=self.div_b),
            'Division B section row must NOT be imported when only Division A is selected',
        )
        self.assertFalse(
            self._boq_lines(division_id=self.div_b),
            'No Division B lines must exist after By Division A import',
        )
        # A1 and A2 and their sub-subs must be present
        for sub in (self.sub_a1, self.sub_a2):
            self.assertTrue(self._boq_lines(subdivision_id=sub))
        for ss in (self.ss_a11, self.ss_a12, self.ss_a21):
            self.assertTrue(self._boq_lines(sub_subdivision_id=ss))

    # ── Test 3: By Subdivision ────────────────────────────────────────────────

    def test_03_by_subdivision_imports_only_selected_subdivision(self):
        """By Subdivision A1 must import ONLY A1 — A2 and B must be absent."""
        wiz = self._new_wizard('subdivision',
                               subdivision_ids=[Command.set([self.sub_a1.id])])
        wiz.action_import()

        # Subdivision A1 present
        self.assertTrue(
            self._boq_lines(subdivision_id=self.sub_a1),
            'Subdivision A1 must be created',
        )
        # Sibling A2 absent
        self.assertFalse(
            self._boq_lines(subdivision_id=self.sub_a2),
            'Sibling Subdivision A2 must NOT be imported',
        )
        # Division B entirely absent
        self.assertFalse(
            self._boq_lines(division_id=self.div_b),
            'Division B must NOT appear at all',
        )
        # A1.1 and A1.2 present; A2.1 absent
        self.assertTrue(self._boq_lines(sub_subdivision_id=self.ss_a11))
        self.assertTrue(self._boq_lines(sub_subdivision_id=self.ss_a12))
        self.assertFalse(
            self._boq_lines(sub_subdivision_id=self.ss_a21),
            'SubSub A2.1 must NOT be imported (belongs to sibling A2)',
        )
        # Parent Division A header auto-created
        self.assertTrue(
            self._boq_lines(display_type='line_section', division_id=self.div_a),
            'Parent Division A section row must be auto-created',
        )

    # ── Test 4: By Sub-Subdivision ────────────────────────────────────────────

    def test_04_by_sub_subdivision_imports_only_selected(self):
        """By Sub-Subdivision A1.1 must import ONLY A1.1 — A1.2 and A2.1 absent."""
        wiz = self._new_wizard('sub_subdivision',
                               sub_subdivision_ids=[Command.set([self.ss_a11.id])])
        wiz.action_import()

        # A1.1 present
        self.assertTrue(
            self._boq_lines(sub_subdivision_id=self.ss_a11),
            'SubSub A1.1 must be created',
        )
        # Sibling A1.2 absent
        self.assertFalse(
            self._boq_lines(sub_subdivision_id=self.ss_a12),
            'Sibling SubSub A1.2 must NOT be imported',
        )
        # A2.1 absent
        self.assertFalse(
            self._boq_lines(sub_subdivision_id=self.ss_a21),
            'SubSub A2.1 must NOT be imported',
        )
        # Division B absent
        self.assertFalse(
            self._boq_lines(division_id=self.div_b),
            'Division B must NOT appear at all',
        )
        # Parent headers auto-created
        self.assertTrue(
            self._boq_lines(display_type='line_section', division_id=self.div_a),
            'Parent Division A must be auto-created',
        )
        self.assertTrue(
            self._boq_lines(subdivision_id=self.sub_a1),
            'Parent Subdivision A1 must be auto-created',
        )
        # Sibling subdivision A2 must NOT be created
        self.assertFalse(
            self._boq_lines(subdivision_id=self.sub_a2),
            'Sibling Subdivision A2 must NOT be auto-created',
        )

    # ── Test 5: By Template ───────────────────────────────────────────────────

    def test_05_by_template_imports_only_selected_templates(self):
        """By Template A must import only Template A — Template B absent."""
        wiz = self._new_wizard('template',
                               template_ids=[Command.set([self.tmpl_a.id])])
        wiz.action_import()

        tmpl_a_items = self.env['farm.boq.line'].search([
            ('boq_id', '=', self.boq.id),
            ('template_id', '=', self.tmpl_a.id),
        ])
        self.assertTrue(tmpl_a_items, 'Template A item must be imported')

        tmpl_b_items = self.env['farm.boq.line'].search([
            ('boq_id', '=', self.boq.id),
            ('template_id', '=', self.tmpl_b.id),
        ])
        self.assertFalse(tmpl_b_items, 'Template B item must NOT be imported')

    # ── Test 6: Empty selection → UserError ───────────────────────────────────

    def test_06_empty_selection_raises_user_error(self):
        """Scoped modes with empty selection must raise UserError."""
        for mode in ('division', 'subdivision', 'sub_subdivision', 'template'):
            wiz = self._new_wizard(mode)
            with self.assertRaises(UserError,
                                   msg=f'Mode {mode!r} with empty selection must raise UserError'):
                wiz.action_import()

    # ── Test 7: Re-run → no duplicates ───────────────────────────────────────

    def test_07_no_duplicates_on_reimport(self):
        """Running the same scoped import twice must not create duplicate rows."""
        kwargs = {'subdivision_ids': [Command.set([self.sub_a1.id])]}

        wiz1 = self._new_wizard('subdivision', **kwargs)
        wiz1.action_import()

        count_after_first = self.env['farm.boq.line'].search_count(
            [('boq_id', '=', self.boq.id)]
        )

        wiz2 = self._new_wizard('subdivision', **kwargs)
        wiz2.action_import()

        count_after_second = self.env['farm.boq.line'].search_count(
            [('boq_id', '=', self.boq.id)]
        )
        self.assertEqual(
            count_after_first, count_after_second,
            'Re-running the same import must not add duplicate BOQ lines',
        )

    # ── Test 8: structure_icon ────────────────────────────────────────────────

    def test_08_structure_icon_field(self):
        """structure_icon computed field must return the correct emoji per display_type."""
        wiz = self._new_wizard('division',
                               division_ids=[Command.set([self.div_a.id])])
        wiz.action_import()

        sections = self._boq_lines(display_type='line_section')
        self.assertTrue(sections, 'Expected at least one line_section row')
        self.assertTrue(
            all(l.structure_icon == '🟦' for l in sections),
            'Division rows (line_section) must have structure_icon = 🟦',
        )

        subsections = self._boq_lines(display_type='line_subsection')
        self.assertTrue(subsections, 'Expected at least one line_subsection row')
        self.assertTrue(
            all(l.structure_icon == '🟩' for l in subsections),
            'Subdivision rows (line_subsection) must have structure_icon = 🟩',
        )

        sub_subs = self._boq_lines(display_type='line_sub_subsection')
        self.assertTrue(sub_subs, 'Expected at least one line_sub_subsection row')
        self.assertTrue(
            all(l.structure_icon == '🟨' for l in sub_subs),
            'Sub-Subdivision rows must have structure_icon = 🟨',
        )
