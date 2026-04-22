"""
SMART MAIL CONTROL CENTER — Operational Linking Engine
=======================================================

Extends mail.tracker.record with direct operational links into the
project, commercial, financial, and procurement workflows.

Per mail_type the engine locates the most relevant farm document
(scoped to the detected project where possible) and stores a direct
reference in typed fields — not just a generic linked_model/linked_res_id.

Linking map:
  claim     → farm.job.order        (scoped by farm.project)
  boq       → farm.boq              (scoped by farm.project)
  variation → farm.boq              (scoped by farm.project)
  contract  → farm.contract         (scoped by farm.project)
  invoice   → account.move          (matched by sender partner email)
  rfq       → farm.material.request (primary) | purchase.order (fallback)

Smart buttons appear in the form view button box when a link exists.
An "Operational Links" tab provides full detail for every linked record.

Entry-point: _route_operational_links()
Called from run_full_auto_processing() after _route_to_document().
Also callable manually via action_refresh_operational_links().
"""
import logging

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)

# ── State label maps for display ──────────────────────────────────────────────
_JO_STATE_LABELS = {
    'draft': 'Draft', 'approved': 'Approved', 'in_progress': 'In Progress',
    'handover_requested': 'Handover Requested', 'under_inspection': 'Under Inspection',
    'partially_accepted': 'Partially Accepted', 'accepted': 'Accepted',
    'ready_for_claim': 'Ready for Claim', 'claimed': 'Claimed', 'closed': 'Closed',
}
_BOQ_STATE_LABELS = {
    'draft': 'Draft', 'start': 'Started', 'in_progress': 'In Progress',
    'submitted': 'Submitted', 'approved': 'Approved',
}
_CONTRACT_STATE_LABELS = {
    'draft': 'Draft', 'review': 'Under Review', 'approved': 'Approved',
    'active': 'Active', 'closed': 'Closed',
}
_MR_STATE_LABELS = {
    'draft': 'Draft', 'to_approve': 'Pending Approval', 'approved': 'Approved',
    'rejected': 'Rejected', 'rfq': 'RFQ Sent', 'ordered': 'Ordered',
    'received': 'Received',
}


class MailTrackerOperational(models.Model):
    """Operational linking engine for mail.tracker.record."""

    _inherit = 'mail.tracker.record'

    # ── PART 1 — Claim / Job Order ─────────────────────────────────────────────

    op_claim_id = fields.Integer(
        string='Linked Job Order ID',
        readonly=True,
        index=True,
    )
    op_claim_name = fields.Char(
        string='Linked Claim / Job Order',
        readonly=True,
    )
    op_claim_state = fields.Char(
        string='Claim Status',
        readonly=True,
    )

    # ── PART 2 — BOQ ──────────────────────────────────────────────────────────

    op_boq_id = fields.Integer(
        string='Linked BOQ ID',
        readonly=True,
        index=True,
    )
    op_boq_name = fields.Char(
        string='Linked BOQ',
        readonly=True,
    )
    op_boq_state = fields.Char(
        string='BOQ Status',
        readonly=True,
    )

    # ── PART 3 — Contract ─────────────────────────────────────────────────────

    op_contract_id = fields.Integer(
        string='Linked Contract ID',
        readonly=True,
        index=True,
    )
    op_contract_name = fields.Char(
        string='Linked Contract',
        readonly=True,
    )
    op_contract_state = fields.Char(
        string='Contract Status',
        readonly=True,
    )

    # ── PART 4 — Invoice / Account Move ───────────────────────────────────────

    op_invoice_id = fields.Integer(
        string='Linked Invoice ID',
        readonly=True,
        index=True,
    )
    op_invoice_name = fields.Char(
        string='Linked Invoice',
        readonly=True,
    )
    op_invoice_state = fields.Char(
        string='Invoice Status',
        readonly=True,
    )

    # ── PART 5 — RFQ / Procurement ───────────────────────────────────────────

    op_rfq_id = fields.Integer(
        string='Linked RFQ ID',
        readonly=True,
        index=True,
    )
    op_rfq_name = fields.Char(
        string='Linked RFQ / Procurement',
        readonly=True,
    )
    op_rfq_state = fields.Char(
        string='RFQ Status',
        readonly=True,
    )
    op_rfq_model = fields.Char(
        string='RFQ Model',
        readonly=True,
        help='farm.material.request or purchase.order',
    )

    # ── Master routing entry-point ─────────────────────────────────────────────

    def _route_operational_links(self):
        """
        Detect and store operational document links for self.

        Routing is mail_type-aware and project-scoped where possible.
        Fields are only populated when empty (idempotent).
        """
        mt = self.mail_type or 'general'
        if mt == 'general':
            return

        # Resolve project scope
        farm_proj_id = (
            self.linked_res_id
            if self.linked_model == 'farm.project' and self.linked_res_id
            else None
        )
        odoo_project_id = self.project_id.id if self.project_id else None

        if mt == 'claim':
            if not self.op_claim_id:
                self._op_link_claim(farm_proj_id, odoo_project_id)
        elif mt in ('boq', 'variation'):
            if not self.op_boq_id:
                self._op_link_boq(farm_proj_id, odoo_project_id)
        elif mt == 'contract':
            if not self.op_contract_id:
                self._op_link_contract(farm_proj_id, odoo_project_id)
        elif mt == 'invoice':
            if not self.op_invoice_id:
                self._op_link_invoice(farm_proj_id, odoo_project_id)
        elif mt == 'rfq':
            if not self.op_rfq_id:
                self._op_link_rfq(farm_proj_id, odoo_project_id)

    # ── Part 1: Claim / Job Order linking ─────────────────────────────────────

    def _op_link_claim(self, farm_proj_id, odoo_project_id):
        JobOrder = self.env.get('farm.job.order')
        if JobOrder is None:
            return
        domain = self._op_project_domain(farm_proj_id, odoo_project_id, JobOrder)
        rec = JobOrder.sudo().search(domain, limit=1, order='id desc')
        if not rec:
            return
        state_raw = rec.jo_stage if hasattr(rec, 'jo_stage') and rec.jo_stage else (rec.state if hasattr(rec, 'state') else '')
        state_label = _JO_STATE_LABELS.get(state_raw, state_raw)
        self.write({
            'op_claim_id': rec.id,
            'op_claim_name': rec.display_name or rec.name or '',
            'op_claim_state': state_label,
        })
        _logger.debug('Mail Tracker Ops: linked record %d → farm.job.order[%d]', self.id, rec.id)

    # ── Part 2: BOQ linking ───────────────────────────────────────────────────

    def _op_link_boq(self, farm_proj_id, odoo_project_id):
        FarmBOQ = self.env.get('farm.boq')
        if FarmBOQ is None:
            return
        domain = self._op_project_domain(farm_proj_id, odoo_project_id, FarmBOQ)
        rec = FarmBOQ.sudo().search(domain, limit=1, order='id desc')
        if not rec:
            return
        state_raw = rec.state if hasattr(rec, 'state') else ''
        self.write({
            'op_boq_id': rec.id,
            'op_boq_name': rec.display_name or rec.name or '',
            'op_boq_state': _BOQ_STATE_LABELS.get(state_raw, state_raw),
        })
        _logger.debug('Mail Tracker Ops: linked record %d → farm.boq[%d]', self.id, rec.id)

    # ── Part 3: Contract linking ──────────────────────────────────────────────

    def _op_link_contract(self, farm_proj_id, odoo_project_id):
        FarmContract = self.env.get('farm.contract')
        if FarmContract is None:
            return
        domain = self._op_project_domain(farm_proj_id, odoo_project_id, FarmContract)
        rec = FarmContract.sudo().search(domain, limit=1, order='id desc')
        if not rec:
            return
        state_raw = rec.state if hasattr(rec, 'state') else ''
        self.write({
            'op_contract_id': rec.id,
            'op_contract_name': rec.display_name or rec.name or '',
            'op_contract_state': _CONTRACT_STATE_LABELS.get(state_raw, state_raw),
        })
        _logger.debug('Mail Tracker Ops: linked record %d → farm.contract[%d]', self.id, rec.id)

    # ── Part 4: Invoice linking ───────────────────────────────────────────────

    def _op_link_invoice(self, farm_proj_id, odoo_project_id):
        AccountMove = self.env.get('account.move')
        if AccountMove is None:
            return

        base_domain = [
            ('move_type', 'in', ['in_invoice', 'out_invoice', 'in_refund', 'out_refund']),
            ('state', '!=', 'cancel'),
        ]

        # Primary strategy: match by sender email → partner
        if self.sender_email:
            partner = self.env['res.partner'].sudo().search(
                [('email', '=ilike', self.sender_email)], limit=1
            )
            if partner:
                rec = AccountMove.sudo().search(
                    base_domain + [('partner_id', '=', partner.id)],
                    limit=1, order='invoice_date desc, id desc',
                )
                if rec:
                    self._op_write_invoice(rec)
                    return

        # Fallback: search by recipient email → partner
        if self.recipient_email:
            partner = self.env['res.partner'].sudo().search(
                [('email', '=ilike', self.recipient_email)], limit=1
            )
            if partner:
                rec = AccountMove.sudo().search(
                    base_domain + [('partner_id', '=', partner.id)],
                    limit=1, order='invoice_date desc, id desc',
                )
                if rec:
                    self._op_write_invoice(rec)
                    return

        # Last resort: most recent open invoice
        rec = AccountMove.sudo().search(
            base_domain + [('payment_state', 'not in', ['paid', 'in_payment'])],
            limit=1, order='invoice_date desc, id desc',
        )
        if rec:
            self._op_write_invoice(rec)

    def _op_write_invoice(self, rec):
        payment_state = ''
        if hasattr(rec, 'payment_state'):
            payment_state = rec.payment_state.replace('_', ' ').title() if rec.payment_state else ''
        elif hasattr(rec, 'state'):
            payment_state = rec.state
        self.write({
            'op_invoice_id': rec.id,
            'op_invoice_name': rec.display_name or rec.name or '',
            'op_invoice_state': payment_state,
        })
        _logger.debug('Mail Tracker Ops: linked record %d → account.move[%d]', self.id, rec.id)

    # ── Part 5: RFQ / Procurement linking ─────────────────────────────────────

    def _op_link_rfq(self, farm_proj_id, odoo_project_id):
        # Primary: farm.material.request (has project_id on farm.project)
        MatReq = self.env.get('farm.material.request')
        if MatReq is not None:
            domain = self._op_project_domain(farm_proj_id, odoo_project_id, MatReq)
            rec = MatReq.sudo().search(domain, limit=1, order='id desc')
            if rec:
                state_raw = rec.state if hasattr(rec, 'state') else ''
                self.write({
                    'op_rfq_id': rec.id,
                    'op_rfq_name': rec.display_name or rec.name or '',
                    'op_rfq_state': _MR_STATE_LABELS.get(state_raw, state_raw),
                    'op_rfq_model': 'farm.material.request',
                })
                _logger.debug('Mail Tracker Ops: linked record %d → farm.material.request[%d]', self.id, rec.id)
                return

        # Fallback: purchase.order
        PO = self.env.get('purchase.order')
        if PO is not None:
            po_domain = [('state', 'in', ['draft', 'sent', 'to approve'])]
            # purchase.order may have project_id via analytic
            po_fields = PO._fields
            if 'project_id' in po_fields and odoo_project_id:
                po_domain.append(('project_id', '=', odoo_project_id))
            rec = PO.sudo().search(po_domain, limit=1, order='id desc')
            if rec:
                self.write({
                    'op_rfq_id': rec.id,
                    'op_rfq_name': rec.display_name or rec.name or '',
                    'op_rfq_state': rec.state if hasattr(rec, 'state') else '',
                    'op_rfq_model': 'purchase.order',
                })
                _logger.debug('Mail Tracker Ops: linked record %d → purchase.order[%d]', self.id, rec.id)

    # ── Helper: build project-scoped domain ───────────────────────────────────

    @staticmethod
    def _op_project_domain(farm_proj_id, odoo_project_id, Model):
        """
        Build the most specific domain possible for the given model.
        Prefer farm.project scope; fall back to project.project; else empty.
        """
        if farm_proj_id and 'project_id' in Model._fields:
            return [('project_id', '=', farm_proj_id)]
        if odoo_project_id and 'project_id' in Model._fields:
            # odoo_project_id references project.project; farm models use farm.project
            # Only use if model's project_id comodel is project.project
            comodel = Model._fields.get('project_id')
            if comodel and getattr(comodel, 'comodel_name', '') == 'project.project':
                return [('project_id', '=', odoo_project_id)]
        return []

    # ── Manual refresh action ─────────────────────────────────────────────────

    def action_refresh_operational_links(self):
        """Force re-run operational linking (clears existing op_* links first)."""
        for rec in self:
            rec.write({
                'op_claim_id': 0, 'op_claim_name': '', 'op_claim_state': '',
                'op_boq_id': 0, 'op_boq_name': '', 'op_boq_state': '',
                'op_contract_id': 0, 'op_contract_name': '', 'op_contract_state': '',
                'op_invoice_id': 0, 'op_invoice_name': '', 'op_invoice_state': '',
                'op_rfq_id': 0, 'op_rfq_name': '', 'op_rfq_state': '', 'op_rfq_model': '',
            })
            rec._route_operational_links()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Operational Links Refreshed'),
                'message': _('Operational document links have been re-scanned.'),
                'type': 'success',
                'sticky': False,
            },
        }

    # ── PART 6: Smart button actions ──────────────────────────────────────────

    def action_open_linked_claim(self):
        """Open the linked farm.job.order in a form view."""
        if not self.op_claim_id:
            return
        return {
            'type': 'ir.actions.act_window',
            'name': self.op_claim_name or _('Claim / Job Order'),
            'res_model': 'farm.job.order',
            'view_mode': 'form',
            'res_id': self.op_claim_id,
            'target': 'current',
        }

    def action_open_linked_boq(self):
        """Open the linked farm.boq in a form view."""
        if not self.op_boq_id:
            return
        return {
            'type': 'ir.actions.act_window',
            'name': self.op_boq_name or _('BOQ'),
            'res_model': 'farm.boq',
            'view_mode': 'form',
            'res_id': self.op_boq_id,
            'target': 'current',
        }

    def action_open_linked_contract(self):
        """Open the linked farm.contract in a form view."""
        if not self.op_contract_id:
            return
        return {
            'type': 'ir.actions.act_window',
            'name': self.op_contract_name or _('Contract'),
            'res_model': 'farm.contract',
            'view_mode': 'form',
            'res_id': self.op_contract_id,
            'target': 'current',
        }

    def action_open_linked_invoice(self):
        """Open the linked account.move invoice in a form view."""
        if not self.op_invoice_id:
            return
        return {
            'type': 'ir.actions.act_window',
            'name': self.op_invoice_name or _('Invoice'),
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.op_invoice_id,
            'target': 'current',
        }

    def action_open_linked_rfq(self):
        """Open the linked procurement document in a form view."""
        if not self.op_rfq_id or not self.op_rfq_model:
            return
        return {
            'type': 'ir.actions.act_window',
            'name': self.op_rfq_name or _('RFQ / Procurement'),
            'res_model': self.op_rfq_model,
            'view_mode': 'form',
            'res_id': self.op_rfq_id,
            'target': 'current',
        }
