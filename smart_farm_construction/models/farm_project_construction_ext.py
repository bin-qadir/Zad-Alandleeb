"""
farm.project — Construction extension
======================================

Adds construction-specific fields to farm.project:
  - construction_phase  — Pre-Tender / Tender / Post-Tender / Execution / Closure
  - material_request_ids / material_request_count  — O2M to farm.material.request
  - Procurement count (farm.boq.analysis via search)
  - Action methods for all project form tabs
"""
from odoo import api, fields, models, _


class FarmProjectConstructionExt(models.Model):
    _inherit = 'farm.project'

    # ── Construction Phase ────────────────────────────────────────────────────

    construction_phase = fields.Selection(
        selection=[
            ('pre_tender',  'Pre-Tender'),
            ('tender',      'Tender'),
            ('post_tender', 'Post-Tender'),
            ('execution',   'Execution'),
            ('closure',     'Closure'),
        ],
        string='Construction Phase',
        default='pre_tender',
        index=True,
        tracking=True,
        help=(
            'Contractual phase of this construction project.\n'
            '• Pre-Tender  — planning, design, BOQ preparation\n'
            '• Tender      — tender issuance, bid evaluation, award\n'
            '• Post-Tender — contract signed, ready to mobilise\n'
            '• Execution   — active on-site work\n'
            '• Closure     — punch list, handover, final accounts'
        ),
    )

    # ── Material Requests ─────────────────────────────────────────────────────

    material_request_ids = fields.One2many(
        comodel_name='farm.material.request',
        inverse_name='project_id',
        string='Material Requests',
    )
    material_request_count = fields.Integer(
        string='Material Requests',
        compute='_compute_material_request_count',
    )

    # ── Procurement count (BOQ Analyses) ──────────────────────────────────────

    procurement_count = fields.Integer(
        string='Procurement Docs',
        compute='_compute_procurement_count',
    )

    # ── Purchase Order count ──────────────────────────────────────────────────

    purchase_order_count = fields.Integer(
        string='Purchase Orders',
        compute='_compute_purchase_order_count',
    )

    # ────────────────────────────────────────────────────────────────────────
    # Compute
    # ────────────────────────────────────────────────────────────────────────

    @api.depends('material_request_ids')
    def _compute_material_request_count(self):
        for rec in self:
            rec.material_request_count = len(rec.material_request_ids)

    def _compute_procurement_count(self):
        Analysis = self.env['farm.boq.analysis']
        for rec in self:
            rec.procurement_count = Analysis.search_count(
                [('project_id', '=', rec.id)]
            )

    def _compute_purchase_order_count(self):
        PO = self.env['purchase.order']
        for rec in self:
            rec.purchase_order_count = PO.search_count(
                [('farm_project_id', '=', rec.id)]
            )

    # ────────────────────────────────────────────────────────────────────────
    # Tab action buttons
    # ────────────────────────────────────────────────────────────────────────

    def action_open_material_requests(self):
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Material Requests — %s') % self.name,
            'res_model': 'farm.material.request',
            'view_mode': 'list,form',
            'domain':    [('project_id', '=', self.id)],
            'context':   {
                'default_project_id':          self.id,
                'default_business_activity':   'construction',
            },
        }

    def action_open_procurement(self):
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Procurement — %s') % self.name,
            'res_model': 'farm.boq.analysis',
            'view_mode': 'list,form',
            'domain':    [('project_id', '=', self.id)],
            'context':   {'default_project_id': self.id},
        }

    def action_open_purchase_orders(self):
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Purchase Orders — %s') % self.name,
            'res_model': 'purchase.order',
            'view_mode': 'list,form',
            'domain':    [('farm_project_id', '=', self.id)],
            'context':   {'default_farm_project_id': self.id},
        }

    def action_open_execution_jos(self):
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Execution — %s') % self.name,
            'res_model': 'farm.job.order',
            'view_mode': 'list,form',
            'domain':    [
                ('project_id', '=', self.id),
                ('jo_stage', 'in', ['approved', 'in_progress']),
            ],
            'context':   {'default_project_id': self.id},
        }

    def action_open_inspection_jos(self):
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Inspection — %s') % self.name,
            'res_model': 'farm.job.order',
            'view_mode': 'list,form',
            'domain':    [
                ('project_id', '=', self.id),
                ('jo_stage', 'in', ['handover_requested', 'under_inspection', 'partially_accepted', 'accepted']),
            ],
            'context':   {'default_project_id': self.id},
        }

    def action_open_claims_jos(self):
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Claims — %s') % self.name,
            'res_model': 'farm.job.order',
            'view_mode': 'list,form',
            'domain':    [
                ('project_id', '=', self.id),
                ('jo_stage', 'in', ['ready_for_claim', 'claimed']),
            ],
            'context':   {'default_project_id': self.id},
        }
