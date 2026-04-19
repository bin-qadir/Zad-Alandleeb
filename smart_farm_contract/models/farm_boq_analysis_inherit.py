import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class FarmBoqAnalysisContractGate(models.Model):
    """Extend farm.boq.analysis to enforce the contract-approval gate.

    Overrides action_generate_job_orders():
    - Checks that the project has at least one contract in state
      'approved' or 'active'.
    - If the gate passes, delegates to super() (which runs the full
      generation logic from smart_farm_execution).
    - Automatically links each created Job Order to the best matching
      approved/active contract.
    """

    _inherit = 'farm.boq.analysis'

    # ────────────────────────────────────────────────────────────────────────
    # Override: generate_job_orders with contract gate
    # ────────────────────────────────────────────────────────────────────────

    def action_generate_job_orders(self):
        """Generate Job Orders — CONTRACT GATE enforced.

        Requires: at least one farm.contract with state 'approved' or 'active'
                  for this project.
        """
        self.ensure_one()

        # ── Contract gate ────────────────────────────────────────────────────
        approved_contract = self.env['farm.contract'].search([
            ('project_id', '=', self.project_id.id),
            ('state', 'in', ['approved', 'active']),
        ], limit=1)

        if not approved_contract:
            # Build a helpful message depending on what contracts exist
            any_contract = self.env['farm.contract'].search([
                ('project_id', '=', self.project_id.id),
            ], limit=1)
            if any_contract:
                raise UserError(_(
                    'Job Orders can only be generated after contract approval.\n\n'
                    'Project "%s" has a contract but it is not yet approved '
                    '(current status: %s).\n\n'
                    'Open the contract and click "Approve Contract" first.',
                    self.project_id.name,
                    dict(
                        self.env['farm.contract']._fields['state'].selection
                    ).get(any_contract.state, any_contract.state),
                ))
            raise UserError(_(
                'Job Orders can only be generated after contract approval.\n\n'
                'No contract exists for project "%s".\n\n'
                'Go to the Project form → Contracts, create and approve a '
                'contract before generating Job Orders.',
                self.project_id.name,
            ))

        _logger.info(
            'ContractGate [%s]: approved contract "%s" (id=%d) — gate passed',
            self.name, approved_contract.name, approved_contract.id,
        )

        # ── Delegate to the standard generation logic ─────────────────────────
        # super() calls smart_farm_execution's action_generate_job_orders which
        # creates the JOs, populates materials from templates, etc.
        result = super().action_generate_job_orders()

        # ── Back-fill contract_id on newly created JOs ────────────────────────
        # Find all JOs for this analysis that have no contract yet and link them
        # to the best contract (prefer 'active', then 'approved').
        best_contract = self.env['farm.contract'].search([
            ('project_id', '=', self.project_id.id),
            ('state', 'in', ['active', 'approved']),
        ], order='state asc', limit=1)
        # 'active' < 'approved' alphabetically → sort asc picks 'active' first

        if best_contract:
            unlinked_jos = self.env['farm.job.order'].search([
                ('analysis_id', '=', self.id),
                ('contract_id', '=', False),
            ])
            if unlinked_jos:
                unlinked_jos.write({'contract_id': best_contract.id})
                _logger.info(
                    'ContractGate [%s]: linked %d JO(s) to contract "%s"',
                    self.name, len(unlinked_jos), best_contract.name,
                )

        return result
