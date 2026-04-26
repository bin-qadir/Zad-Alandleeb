from odoo import api, fields, models, _
from odoo.exceptions import UserError


class FarmProjectContractPhase(models.Model):
    """Extend farm.project with:
    - project_phase Selection: Pre-Tender → Tender → Contract → Execution
    - contract_ids / contract_count (stat button)
    - Phase transition actions with contract-approval gate on Execution
    """

    _inherit = 'farm.project'

    # ── TECHNICAL NOTE: Two parallel phase fields exist on farm.project ─────────
    #
    #   project_phase  (Selection)                             — defined HERE
    #     Origin  : smart_farm_contract
    #     Purpose : Drives the project LIFECYCLE gate (Pre-Tender → Tender →
    #               Contract → Execution → Closing). Controls button visibility,
    #               permitted actions, phase banners, and the Job Order approval
    #               gate (requires has_approved_contract in Execution phase).
    #     Values  : pre_tender | tender | contract | execution | closing
    #
    #   project_phase_id  (Many2one → project.phase.master)   — defined in
    #                                                            smart_farm_boq
    #     Origin  : smart_farm_boq
    #     Purpose : Tracks the BOQ/procurement phase master record used to tag
    #               BOQs and BOQ lines with a named phase. Displayed as a
    #               statusbar in the project form header.
    #
    #   These two fields are INDEPENDENT. No automatic sync exists between them.
    #   Do not attempt to unify them without a full migration plan.
    # ─────────────────────────────────────────────────────────────────────────────

    # ── Project lifecycle phase ────────────────────────────────────────────────
    project_phase = fields.Selection(
        selection=[
            ('pre_tender', 'Pre-Tender'),
            ('tender',     'Tender'),
            ('contract',   'Contract'),
            ('execution',  'Execution'),
            ('closing',    'Closing'),
        ],
        string='Lifecycle Phase',
        default='pre_tender',
        required=True,
        tracking=True,
        help=(
            'Pre-Tender: BOQ preparation and analysis.\n'
            'Tender: RFQ, pricing negotiation.\n'
            'Contract: Contract creation and approval.\n'
            'Execution: Job Orders, Materials, Labour, Progress.\n'
            'Closing: Final handover, punch list, financial close-out.'
        ),
    )

    # ── Contract links ────────────────────────────────────────────────────────
    contract_ids = fields.One2many(
        'farm.contract',
        'project_id',
        string='Contracts',
    )
    contract_count = fields.Integer(
        string='Contract Count',
        compute='_compute_contract_count',
    )

    # ────────────────────────────────────────────────────────────────────────
    # Computed
    # ────────────────────────────────────────────────────────────────────────

    @api.depends('contract_ids')
    def _compute_contract_count(self):
        for rec in self:
            rec.contract_count = len(rec.contract_ids)

    # ────────────────────────────────────────────────────────────────────────
    # Phase transition actions
    # ────────────────────────────────────────────────────────────────────────

    def action_phase_to_tender(self):
        """Pre-Tender → Tender."""
        self.filtered(
            lambda r: r.project_phase == 'pre_tender'
        ).write({'project_phase': 'tender'})

    def action_phase_to_contract(self):
        """Tender → Contract."""
        self.filtered(
            lambda r: r.project_phase == 'tender'
        ).write({'project_phase': 'contract'})

    def action_phase_to_execution(self):
        """Contract → Execution.

        GATE: At least one approved or active contract must exist.
        """
        for rec in self.filtered(lambda r: r.project_phase == 'contract'):
            approved = rec.contract_ids.filtered(
                lambda c: c.state in ('approved', 'active')
            )
            if not approved:
                raise UserError(_(
                    'Cannot move project "%s" to Execution phase.\n\n'
                    'An approved or active contract is required before execution can begin.\n\n'
                    'Go to Contracts on this project and approve a contract first.',
                    rec.name,
                ))
            rec.project_phase = 'execution'

    def action_phase_to_closing(self):
        """Execution → Closing."""
        self.filtered(
            lambda r: r.project_phase == 'execution'
        ).write({'project_phase': 'closing'})

    def action_phase_reset(self):
        """Execution → Contract (correction by manager)."""
        self.filtered(
            lambda r: r.project_phase in ('execution', 'closing')
        ).write({'project_phase': 'contract'})

    # ────────────────────────────────────────────────────────────────────────
    # Navigation
    # ────────────────────────────────────────────────────────────────────────

    def action_open_contracts(self):
        """Open Contracts filtered to this project."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Contracts — %s') % self.name,
            'res_model': 'farm.contract',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
        }
