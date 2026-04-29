from odoo import api, fields, models, _


class FarmProjectBoqInherit(models.Model):
    """Extend farm.project with Project Phase and BOQ navigation.

    BOQ structure is accessed exclusively from:
        Cost Structure → Project Cost Structure

    or via the "Open BOQs" stat button on the Farm Project form.

    Farm Project = project management summary + navigation hub only.
    """

    _inherit = 'farm.project'

    # ── TECHNICAL NOTE: Two parallel phase fields exist on farm.project ─────────
    #
    #   project_phase_id  (Many2one → project.phase.master)   — defined HERE
    #     Origin  : smart_farm_boq
    #     Purpose : Tracks the BOQ/procurement phase master record. Used to tag
    #               BOQs and their lines with a named phase (e.g. "Phase 1 –
    #               Foundation"). Shown as a statusbar in the form header by
    #               smart_farm_boq's inject view.
    #     Relation: farm.boq.project_phase_id also points to project.phase.master.
    #
    #   project_phase  (Selection field)                       — defined in
    #                                                            smart_farm_contract
    #     Origin  : smart_farm_contract
    #     Purpose : Drives the project LIFECYCLE gate (Pre-Tender → Tender →
    #               Contract → Execution → Closing). Controls which header buttons
    #               are visible, which actions are permitted, and which phase
    #               banners are shown.
    #     Relation: No link to project.phase.master; fully self-contained.
    #
    #   These two fields are INDEPENDENT. No automatic sync exists between them.
    #   Do not attempt to unify them without a full migration plan:
    #     - project_phase_id is a Many2one with stored BOQ/line relations
    #     - project_phase is a Selection driving execution-gate business logic
    # ─────────────────────────────────────────────────────────────────────────────
    project_phase_id = fields.Many2one(
        comodel_name='project.phase.master',
        string='Project Phase',
        ondelete='set null',
    )

    # ── BOQ back-relation (used for reactivity + count) ──────────────────────
    boq_ids = fields.One2many(
        comodel_name='farm.boq',
        inverse_name='project_id',
        string='BOQ List',
    )

    # ── BOQ count (stat button) ───────────────────────────────────────────────
    boq_count = fields.Integer(
        string='Cost Structures',
        compute='_compute_boq_count',
        help='Number of Cost Structures (BOQs) linked to this project.',
    )

    # ── Phase count (distinct phases used across BOQs) ───────────────────────
    phase_count = fields.Integer(
        string='Phases',
        compute='_compute_phase_count',
        help='Number of distinct project phases used across BOQs on this project.',
    )

    @api.depends('boq_ids.project_phase_id')
    def _compute_phase_count(self):
        for rec in self:
            rec.phase_count = len(rec.boq_ids.mapped('project_phase_id'))

    def action_open_phases(self):
        """Open project phases used in BOQs for this project."""
        self.ensure_one()
        phase_ids = self.boq_ids.mapped('project_phase_id').ids
        return {
            'type': 'ir.actions.act_window',
            'name': _('Project Phases — %s') % self.name,
            'res_model': 'project.phase.master',
            'view_mode': 'list,form',
            'domain': [('id', 'in', phase_ids)],
        }

    @api.depends('boq_ids')
    def _compute_boq_count(self):
        for rec in self:
            rec.boq_count = len(rec.boq_ids)

    def action_open_boqs(self):
        """Open Cost Structures (BOQs) filtered to this project."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Cost Structures — %s') % self.name,
            'res_model': 'farm.boq',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
        }

    def action_new_boq(self):
        """Open a blank BOQ form pre-linked to this project.

        Defaults:
        - project_id         = current project
        - project_phase_id   = current project's active phase (if set)
        - sequence           = max existing BOQ sequence + 10
        - revision_no        = 0
        """
        self.ensure_one()
        last_boq = self.env['farm.boq'].search(
            [('project_id', '=', self.id)],
            order='sequence desc',
            limit=1,
        )
        next_seq = (last_boq.sequence + 10) if last_boq else 10
        return {
            'type': 'ir.actions.act_window',
            'name': _('New Cost Structure — %s') % self.name,
            'res_model': 'farm.boq',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_project_id':       self.id,
                'default_project_phase_id': self.project_phase_id.id or False,
                'default_sequence':         next_seq,
                'default_revision_no':      0,
            },
        }
