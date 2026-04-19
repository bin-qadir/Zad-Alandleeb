"""
SMART FARM CONTROL — HARD PHASE LOCK ENGINE
============================================

Enforces strict backend phase gating across all execution models.

Phase rules:
  pre_tender  → BOQ/Analysis only. Everything else blocked.
  tender      → Quotations/RFQs allowed. No execution.
  contract    → Contract approval workflow. No execution entry.
  execution   → Full execution access (JO/Material/Labour/Progress).

Double-gate for Job Orders:
  BOTH conditions must be true:
  1. project.project_phase == 'execution'
  2. at least one approved contract (farm.contract OR sale.order with
     is_contract_approved = True)

All checks are backend-enforced via create()/write() overrides.
A clear UserError is raised for every blocked operation.
"""
import logging

from odoo import api, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Phases that count as "execution-ready"
_EXECUTION_PHASE = 'execution'

# Phases where contract approval is allowed
_CONTRACT_ALLOWED_PHASES = ('contract', 'execution')

# Phase display labels
_PHASE_LABELS = {
    'pre_tender': 'Pre-Tender',
    'tender':     'Tender',
    'contract':   'Contract',
    'execution':  'Execution',
    'closing':    'Closing',
}


def _phase_label(phase):
    return _PHASE_LABELS.get(phase, phase or 'Unknown')


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────

def _resolve_project(env, project_id):
    """Safe browse that returns a project or None."""
    if not project_id:
        return None
    try:
        project = env['farm.project'].sudo().browse(project_id)
        if project.exists():
            return project
    except Exception:
        pass
    return None


def _has_approved_contract(project):
    """True if the project has at least one approved/active farm.contract
    OR an approved sale.order (is_contract_approved = True)."""
    if not project:
        return False
    approved_fc = project.contract_ids.filtered(
        lambda c: c.state in ('approved', 'active')
    )
    if approved_fc:
        return True
    approved_so = project.env['sale.order'].search([
        ('farm_project_id', '=', project.id),
        ('is_contract_approved', '=', True),
    ], limit=1)
    return bool(approved_so)


# ────────────────────────────────────────────────────────────────────────────
# GATE 1 — Job Order
# ────────────────────────────────────────────────────────────────────────────

class FarmJobOrderPhaseGate(models.Model):
    """Backend phase gate on farm.job.order.

    Rules:
    - CREATE: project must be in 'execution' phase AND have an approved contract
    - WRITE (state → in_progress): same check as CREATE
    """

    _inherit = 'farm.job.order'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            project = _resolve_project(self.env, vals.get('project_id'))
            if not project:
                continue
            phase = project.project_phase
            if phase != _EXECUTION_PHASE:
                raise UserError(_(
                    'Execution is locked for project "%(proj)s".\n\n'
                    'Job Orders can only be created when the project is in '
                    'Execution phase.\n\n'
                    'Current phase: %(phase)s\n\n'
                    'Steps to unlock:\n'
                    '  1. Ensure a contract exists and is approved\n'
                    '  2. Click "Start Execution" on the project form to enter '
                    'Execution phase.',
                    proj=project.name,
                    phase=_phase_label(phase),
                ))
            if not _has_approved_contract(project):
                raise UserError(_(
                    'Execution is locked for project "%(proj)s".\n\n'
                    'An approved contract is required before Job Orders can be created.\n\n'
                    'Approve a Farm Contract or a Sales Order (Contract Stage → Approved) '
                    'linked to this project first.',
                    proj=project.name,
                ))
        return super().create(vals_list)

    def write(self, vals):
        # Enforce gate when manually advancing to in_progress
        if vals.get('state') in ('in_progress', 'completed'):
            for rec in self:
                project = rec.project_id
                if not project:
                    continue
                if project.project_phase != _EXECUTION_PHASE:
                    raise UserError(_(
                        'Execution is locked for project "%(proj)s".\n\n'
                        'Job Order "%(jo)s" cannot be advanced to %(state)s '
                        'while the project is in %(phase)s phase.\n\n'
                        'Move the project to Execution phase first.',
                        proj=project.name,
                        jo=rec.name,
                        state=vals['state'].replace('_', ' ').title(),
                        phase=_phase_label(project.project_phase),
                    ))
                if not _has_approved_contract(project):
                    raise UserError(_(
                        'Execution is locked for project "%(proj)s".\n\n'
                        'An approved contract is required before advancing '
                        'Job Order "%(jo)s".',
                        proj=project.name,
                        jo=rec.name,
                    ))
        return super().write(vals)


# ────────────────────────────────────────────────────────────────────────────
# GATE 2 — Material Consumption
# ────────────────────────────────────────────────────────────────────────────

class FarmMaterialConsumptionPhaseGate(models.Model):
    """Backend phase gate on farm.material.consumption.

    Material entries may only be created when the parent Job Order's
    project is in Execution phase.
    """

    _inherit = 'farm.material.consumption'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            jo_id = vals.get('job_order_id')
            if not jo_id:
                continue
            try:
                jo = self.env['farm.job.order'].sudo().browse(jo_id)
                if not jo.exists():
                    continue
                project = jo.project_id
            except Exception:
                continue
            if not project:
                continue
            if project.project_phase != _EXECUTION_PHASE:
                raise UserError(_(
                    'Execution is locked for project "%(proj)s".\n\n'
                    'Material entries can only be created when the project is in '
                    'Execution phase.\n\n'
                    'Current phase: %(phase)s',
                    proj=project.name,
                    phase=_phase_label(project.project_phase),
                ))
        return super().create(vals_list)


# ────────────────────────────────────────────────────────────────────────────
# GATE 3 — Labour Entry
# ────────────────────────────────────────────────────────────────────────────

class FarmLabourEntryPhaseGate(models.Model):
    """Backend phase gate on farm.labour.entry."""

    _inherit = 'farm.labour.entry'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            jo_id = vals.get('job_order_id')
            if not jo_id:
                continue
            try:
                jo = self.env['farm.job.order'].sudo().browse(jo_id)
                if not jo.exists():
                    continue
                project = jo.project_id
            except Exception:
                continue
            if not project:
                continue
            if project.project_phase != _EXECUTION_PHASE:
                raise UserError(_(
                    'Execution is locked for project "%(proj)s".\n\n'
                    'Labour entries can only be created when the project is in '
                    'Execution phase.\n\n'
                    'Current phase: %(phase)s',
                    proj=project.name,
                    phase=_phase_label(project.project_phase),
                ))
        return super().create(vals_list)


# ────────────────────────────────────────────────────────────────────────────
# GATE 4 — Progress Log
# ────────────────────────────────────────────────────────────────────────────

class FarmJobProgressLogPhaseGate(models.Model):
    """Backend phase gate on farm.job.progress.log."""

    _inherit = 'farm.job.progress.log'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            jo_id = vals.get('job_order_id')
            if not jo_id:
                continue
            try:
                jo = self.env['farm.job.order'].sudo().browse(jo_id)
                if not jo.exists():
                    continue
                project = jo.project_id
            except Exception:
                continue
            if not project:
                continue
            if project.project_phase != _EXECUTION_PHASE:
                raise UserError(_(
                    'Execution is locked for project "%(proj)s".\n\n'
                    'Progress logs can only be created when the project is in '
                    'Execution phase.\n\n'
                    'Current phase: %(phase)s',
                    proj=project.name,
                    phase=_phase_label(project.project_phase),
                ))
        return super().create(vals_list)


# ────────────────────────────────────────────────────────────────────────────
# GATE 5 — Sales Order Contract Approval
# ────────────────────────────────────────────────────────────────────────────

class SaleOrderContractPhaseGate(models.Model):
    """Enforce that SO contract approval only happens in Contract/Execution phase.

    A Sales Order linked to a Farm Project cannot be contract-approved
    while the project is still in Pre-Tender or Tender phase.
    """

    _inherit = 'sale.order'

    def action_contract_approve(self):
        """Override to add project phase gate before approving."""
        for rec in self.filtered(lambda r: r.farm_project_id):
            project = rec.farm_project_id
            if project.project_phase not in _CONTRACT_ALLOWED_PHASES:
                raise UserError(_(
                    'Contract cannot be approved while project "%(proj)s" is in '
                    '%(phase)s phase.\n\n'
                    'Contract approval is only allowed from Contract phase onwards.\n\n'
                    'Steps:\n'
                    '  1. Move the project to Contract phase first\n'
                    '     (Project form → "Move to Contract" button)\n'
                    '  2. Then approve this Sales Order contract.',
                    proj=project.name,
                    phase=_phase_label(project.project_phase),
                ))
        return super().action_contract_approve()
