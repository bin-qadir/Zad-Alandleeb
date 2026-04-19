"""
SMART FARM CONTROL — PROJECT CLOSING PHASE
==========================================

Extends the project_phase selection with 'closing' as the terminal stage.

Full pipeline:
    pre_tender → tender → contract → execution → closing

Closing semantics:
    • Project is in read-only mode — no new execution records allowed.
    • The hard phase gate in farm_phase_gate.py already blocks new JOs,
      Materials, Labour, and Progress Logs (phase != 'execution').
    • Close Project button requires no gate — project owner decides when ready.

Manager override: action_phase_reopen() → closing → execution
"""

from odoo import fields, models


class FarmProjectClosing(models.Model):
    """Adds the 'closing' terminal stage to the farm.project phase pipeline."""

    _inherit = 'farm.project'

    # ── Extend project_phase with 'closing' ───────────────────────────────────
    # selection_add is the safe Odoo way to extend a selection field without
    # losing existing data. ondelete specifies what happens on module uninstall.

    project_phase = fields.Selection(
        selection_add=[('closing', 'Closing')],
        ondelete={'closing': 'set default'},
    )

    # ────────────────────────────────────────────────────────────────────────
    # Phase transition: Execution → Closing
    # ────────────────────────────────────────────────────────────────────────

    def action_phase_to_closing(self):
        """Execution → Closing.

        No gate — project owner decides when the project is ready to close.
        The hard phase lock in farm_phase_gate.py automatically blocks any
        new Job Orders, Materials, Labour, or Progress Logs once closing.
        """
        self.filtered(
            lambda r: r.project_phase == 'execution'
        ).write({'project_phase': 'closing'})

    # ────────────────────────────────────────────────────────────────────────
    # Phase transition: Closing → Execution (manager override)
    # ────────────────────────────────────────────────────────────────────────

    def action_phase_reopen(self):
        """Closing → Execution (correction by manager).

        Reopens a closed project back to Execution phase.
        Restricted to Smart Farm Manager group.
        """
        self.filtered(
            lambda r: r.project_phase == 'closing'
        ).write({'project_phase': 'execution'})
