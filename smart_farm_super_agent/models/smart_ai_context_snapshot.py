"""
smart.ai.context.snapshot — Layer 1: Context Capture
=====================================================
Captures a structured snapshot of a project's current state for AI processing.
"""
import json
import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class SmartAiContextSnapshot(models.Model):
    _name        = 'smart.ai.context.snapshot'
    _description = 'AI Context Snapshot — Layer 1'
    _order       = 'captured_at desc'
    _rec_name    = 'name'

    name = fields.Char(string='Name', required=True, readonly=True)
    project_id = fields.Many2one(
        'farm.project',
        string='Project',
        required=True,
        ondelete='cascade',
        index=True,
    )
    business_activity = fields.Selection(
        related='project_id.business_activity',
        store=True,
        string='Business Activity',
    )
    source_model     = fields.Char(string='Source Model')
    source_record_id = fields.Integer(string='Source Record ID')
    context_type = fields.Selection(
        selection=[
            ('project',    'Project'),
            ('boq',        'BOQ'),
            ('job_order',  'Job Order'),
            ('material',   'Material Request'),
            ('execution',  'Execution'),
            ('inspection', 'Inspection'),
            ('claim',      'Claims'),
            ('financial',  'Financial'),
        ],
        string='Context Type',
        required=True,
        default='project',
    )
    summary     = fields.Text(string='Summary', readonly=True)
    key_metrics = fields.Text(string='Key Metrics (JSON)', readonly=True)
    captured_at = fields.Datetime(
        string='Captured At',
        default=fields.Datetime.now,
        readonly=True,
    )

    # ── Class method: capture snapshot for a project ──────────────────────────

    @api.model
    def capture_for_project(self, project):
        """Create or update the project-level context snapshot."""
        now = fields.Datetime.now()

        construction_phase = getattr(project, 'construction_phase', False) or 'N/A'
        end_date           = getattr(project, 'end_date', False)
        business_activity  = getattr(project, 'business_activity', 'construction')

        summary = (
            f"Project: {project.name} | "
            f"Phase: {construction_phase} | "
            f"End Date: {end_date or 'Not Set'} | "
            f"Activity: {business_activity}"
        )

        jo_count = self.env['farm.job.order'].search_count([('project_id', '=', project.id)])

        metrics = {
            'material_request_count':  getattr(project, 'material_request_count',  0) or 0,
            'procurement_count':       getattr(project, 'procurement_count',        0) or 0,
            'job_order_count':         jo_count,
            'total_approved_amount':   getattr(project, 'total_approved_amount',    0) or 0,
            'total_claimable_amount':  getattr(project, 'total_claimable_amount',   0) or 0,
        }
        key_metrics_json = json.dumps(metrics)

        name = f"Context: {project.name} @ {now.strftime('%Y-%m-%d %H:%M')}"

        existing = self.search([
            ('project_id',   '=', project.id),
            ('context_type', '=', 'project'),
        ], limit=1)

        vals = {
            'name':         name,
            'project_id':   project.id,
            'context_type': 'project',
            'summary':      summary,
            'key_metrics':  key_metrics_json,
            'captured_at':  now,
            'source_model': 'farm.project',
            'source_record_id': project.id,
        }

        if existing:
            existing.write(vals)
            return existing
        return self.create(vals)
