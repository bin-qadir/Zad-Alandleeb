"""
farm.project — Construction extension
======================================

Adds construction-specific fields to farm.project:
  - construction_phase  — Pre-Tender / Tender / Post-Tender / Execution / Closure
  - construction_status — First Ideas / New / In Progress / On Hold / Completed / Cancelled
  - material_request_ids / material_request_count
  - procurement_count, purchase_order_count
  - AI Insight linkage (latest insight, risk score, AI status)
  - Action methods for all project form tabs + AI recompute
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

    # ── Construction Status (operational) ────────────────────────────────────

    construction_status = fields.Selection(
        selection=[
            ('first_ideas',  'First Ideas'),
            ('new',          'New Project'),
            ('in_progress',  'In Progress'),
            ('on_hold',      'On Hold'),
            ('completed',    'Completed'),
            ('cancelled',    'Cancelled'),
        ],
        string='Project Status',
        default='first_ideas',
        index=True,
        tracking=True,
        help=(
            'Operational status of this construction project.\n'
            '• First Ideas  — early concept, not yet committed\n'
            '• New Project  — contract awarded, mobilisation pending\n'
            '• In Progress  — active on-site execution\n'
            '• On Hold      — temporarily suspended\n'
            '• Completed    — all works done, closure in progress\n'
            '• Cancelled    — project cancelled'
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

    # ── Building / Zone relationships ─────────────────────────────────────────

    building_ids = fields.One2many(
        comodel_name='construction.project.building',
        inverse_name='project_id',
        string='Buildings',
    )
    zone_ids = fields.One2many(
        comodel_name='construction.project.zone',
        inverse_name='project_id',
        string='Zones',
    )

    # ── Area totals ───────────────────────────────────────────────────────────

    total_building_area = fields.Float(
        string='Buildings Total Area (m²)',
        digits=(16, 2),
        compute='_compute_construction_area_totals',
        help='Sum of all floor areas across all buildings.',
    )
    total_zone_area = fields.Float(
        string='Zones Total Area (m²)',
        digits=(16, 2),
        compute='_compute_construction_area_totals',
        help='Sum of all zone areas.',
    )
    construction_total_area = fields.Float(
        string='Grand Total Area (m²)',
        digits=(16, 2),
        compute='_compute_construction_area_totals',
        help='Buildings + Zones combined area.',
    )

    # ── AI Insight linkage ────────────────────────────────────────────────────

    ai_insight_ids = fields.One2many(
        'construction.ai.insight',
        'project_id',
        string='AI Insights',
    )
    latest_ai_insight_id = fields.Many2one(
        'construction.ai.insight',
        compute='_compute_latest_ai_insight',
        string='Latest AI Insight',
        store=False,
    )
    ai_risk_score = fields.Float(
        compute='_compute_latest_ai_insight',
        string='AI Risk Score',
        digits=(16, 1),
        store=False,
    )
    ai_status = fields.Selection(
        selection=[
            ('healthy',  'Healthy'),
            ('warning',  'Warning'),
            ('critical', 'Critical'),
        ],
        compute='_compute_latest_ai_insight',
        string='AI Status',
        store=False,
    )
    ai_recommendation = fields.Text(
        compute='_compute_latest_ai_insight',
        string='AI Recommendation',
        store=False,
    )

    # ────────────────────────────────────────────────────────────────────────
    # Compute
    # ────────────────────────────────────────────────────────────────────────

    @api.depends(
        'building_ids',
        'building_ids.floor_ids',
        'building_ids.floor_ids.area',
        'zone_ids',
        'zone_ids.area',
    )
    def _compute_construction_area_totals(self):
        for rec in self:
            building_area = sum(
                floor.area
                for bldg in rec.building_ids
                for floor in bldg.floor_ids
            )
            zone_area = sum(z.area for z in rec.zone_ids)
            rec.total_building_area   = building_area
            rec.total_zone_area       = zone_area
            rec.construction_total_area = building_area + zone_area

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

    @api.depends('ai_insight_ids', 'ai_insight_ids.date_generated')
    def _compute_latest_ai_insight(self):
        Insight = self.env['construction.ai.insight']
        for rec in self:
            latest = Insight.search(
                [('project_id', '=', rec.id)],
                order='date_generated desc',
                limit=1,
            )
            rec.latest_ai_insight_id = latest.id if latest else False
            rec.ai_risk_score        = latest.risk_score        if latest else 0.0
            rec.ai_status            = latest.status            if latest else False
            rec.ai_recommendation    = latest.recommended_action if latest else False

    # ────────────────────────────────────────────────────────────────────────
    # AI Insight action
    # ────────────────────────────────────────────────────────────────────────

    def action_recompute_ai_insight(self):
        """Button: recompute AI insight for this project."""
        self.ensure_one()
        Insight = self.env['construction.ai.insight']
        insight = Insight.generate_for_project(self)
        return {
            'type': 'ir.actions.client',
            'tag':  'display_notification',
            'params': {
                'title':   _('AI Insight Updated'),
                'message': _(
                    '%(status)s — Risk score: %(score)s%%',
                    status=dict(insight._fields['status'].selection).get(insight.status, ''),
                    score=int(insight.risk_score),
                ),
                'type':    'success' if insight.status == 'healthy' else 'warning',
                'sticky':  False,
            },
        }

    def action_open_ai_insights(self):
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'name':      _('AI Insights — %s') % self.name,
            'res_model': 'construction.ai.insight',
            'view_mode': 'list,form',
            'domain':    [('project_id', '=', self.id)],
            'context':   {'default_project_id': self.id},
        }

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
                'default_project_id':        self.id,
                'default_business_activity': 'construction',
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
