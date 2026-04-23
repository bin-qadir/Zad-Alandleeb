"""
farm.job.order — Division Pipeline extension
============================================
Adds a computed `pipeline_phase` field that maps the existing `jo_stage` to
one of the 10 division pipeline phases:

  draft               → planning
  approved            → ready_for_execution  (or material_request if no planned dates)
  in_progress         → in_progress
  handover_requested  → in_progress
  under_inspection    → inspection
  partially_accepted  → approval
  accepted            → approval
  ready_for_claim     → claim
  claimed             → claim
  closed              → completed
"""

from odoo import api, fields, models


_PHASE_MAP = {
    'draft':               'planning',
    'in_progress':         'in_progress',
    'handover_requested':  'in_progress',
    'under_inspection':    'inspection',
    'partially_accepted':  'approval',
    'accepted':            'approval',
    'ready_for_claim':     'claim',
    'claimed':             'claim',
    'closed':              'completed',
}


class FarmJobOrderPipelineInherit(models.Model):
    _inherit = 'farm.job.order'

    pipeline_phase = fields.Selection(
        selection=[
            # Pre-Execution
            ('planning',            'Planning'),
            ('material_request',    'Material Request'),
            ('procurement',         'Procurement'),
            ('resources',           'Resources'),
            ('ready_for_execution', 'Ready for Execution'),
            # Execution
            ('in_progress',         'In Progress'),
            ('completed',           'Completed'),
            # Control
            ('inspection',          'Inspection'),
            ('approval',            'Approval'),
            # Financial
            ('claim',               'Claim'),
        ],
        string='Pipeline Phase',
        compute='_compute_pipeline_phase',
        store=True,
        index=True,
        help='Auto-derived from JO Stage — shows where this Job Order sits in the division pipeline.',
    )

    @api.depends('jo_stage', 'planned_start_date', 'planned_end_date')
    def _compute_pipeline_phase(self):
        for rec in self:
            stage = rec.jo_stage or 'draft'

            if stage == 'approved':
                # Distinguish material_request vs ready_for_execution based on planning dates
                if rec.planned_start_date and rec.planned_end_date:
                    rec.pipeline_phase = 'ready_for_execution'
                else:
                    rec.pipeline_phase = 'material_request'
            else:
                rec.pipeline_phase = _PHASE_MAP.get(stage, 'planning')
