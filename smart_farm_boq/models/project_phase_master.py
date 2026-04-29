"""
project.phase.master — Project Phase master records.

Phases classify BOQs by project lifecycle stage (e.g. Pre-Tender, Execution).
They are intentionally separate from the BOQ approval workflow status.
Each phase can optionally be linked to a specific farm.project.
"""

from odoo import api, fields, models, _


class ProjectPhaseMaster(models.Model):
    """Project Phase Master — planning classification (Pre-Tender / Tender / Post-Tender).

    This is intentionally separate from the BOQ workflow status (draft → approved).
    Phases represent when in the project lifecycle a piece of work belongs,
    not the document review/approval state.
    """

    _name = 'project.phase.master'
    _description = 'Project Phase'
    _order = 'sequence, id'
    _rec_name = 'name'

    # ── Identity ─────────────────────────────────────────────────────────────────
    name = fields.Char(
        string='Phase Name / اسم المرحلة',
        required=True,
        translate=True,
    )
    code = fields.Char(
        string='Phase Code / كود المرحلة',
        help='Short identifier for this phase (e.g. PH-01).',
    )
    sequence = fields.Integer(
        string='Sequence / التسلسل',
        default=10,
        help='Controls display order; lower numbers appear first.',
    )
    active = fields.Boolean(
        string='Active / نشط',
        default=True,
    )
    description = fields.Text(
        string='Description / الوصف',
        help='Detailed description of this phase.',
    )

    # ── Project relation ──────────────────────────────────────────────────────────
    project_id = fields.Many2one(
        comodel_name='farm.project',
        string='Project / المشروع',
        ondelete='set null',
        index=True,
        help='Optional: link this phase to a specific farm project.',
    )

    # ── Timeline ──────────────────────────────────────────────────────────────────
    start_date = fields.Date(string='Start Date / تاريخ البداية')
    end_date   = fields.Date(string='End Date / تاريخ النهاية')

    # ── Inverse relations — populated from farm.boq ───────────────────────────────
    boq_ids = fields.One2many(
        comodel_name='farm.boq',
        inverse_name='project_phase_id',
        string='BOQs / جداول الكميات',
    )

    # ── Computed counts ───────────────────────────────────────────────────────────
    boq_count = fields.Integer(
        string='BOQs / جداول الكميات',
        compute='_compute_boq_count',
        help='Number of Cost Structures linked to this phase.',
    )
    task_count = fields.Integer(
        string='Tasks / المهام',
        compute='_compute_task_count',
        help='Number of project tasks in projects that use this phase.',
    )
    job_order_count = fields.Integer(
        string='Job Orders / أوامر العمل',
        compute='_compute_job_order_count',
        help='Number of job orders under BOQs in this phase.',
    )

    # ── Compute ───────────────────────────────────────────────────────────────────

    @api.depends('boq_ids')
    def _compute_boq_count(self):
        for rec in self:
            rec.boq_count = len(rec.boq_ids)

    @api.depends('boq_ids.project_id')
    def _compute_task_count(self):
        Task = self.env['project.task']
        for rec in self:
            # Traverse: phase → BOQ → farm.project → odoo project → tasks
            farm_project_ids = rec.boq_ids.mapped('project_id').ids
            if not farm_project_ids:
                rec.task_count = 0
                continue
            odoo_project_ids = self.env['farm.project'].browse(
                farm_project_ids
            ).mapped('odoo_project_id').ids
            rec.task_count = (
                Task.search_count([('project_id', 'in', odoo_project_ids)])
                if odoo_project_ids else 0
            )

    @api.depends('boq_ids')
    def _compute_job_order_count(self):
        JO = self.env.get('farm.job.order')
        for rec in self:
            if JO is None:
                rec.job_order_count = 0
            else:
                rec.job_order_count = JO.search_count(
                    [('boq_id', 'in', rec.boq_ids.ids)]
                )

    # ── Actions ───────────────────────────────────────────────────────────────────

    def action_open_boqs(self):
        """Open Cost Structures (BOQs) filtered to this phase."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('BOQs — %s') % self.name,
            'res_model': 'farm.boq',
            'view_mode': 'list,form',
            'domain': [('project_phase_id', '=', self.id)],
            'context': {'default_project_phase_id': self.id},
        }

    def action_open_tasks(self):
        """Open project tasks linked (via project) to this phase."""
        self.ensure_one()
        farm_project_ids = self.boq_ids.mapped('project_id').ids
        odoo_project_ids = self.env['farm.project'].browse(
            farm_project_ids
        ).mapped('odoo_project_id').ids
        return {
            'type': 'ir.actions.act_window',
            'name': _('Tasks — %s') % self.name,
            'res_model': 'project.task',
            'view_mode': 'list,form',
            'domain': [('project_id', 'in', odoo_project_ids)],
        }

    def action_open_job_orders(self):
        """Open Job Orders whose BOQ belongs to this phase."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Job Orders — %s') % self.name,
            'res_model': 'farm.job.order',
            'view_mode': 'list,form',
            'domain': [('boq_id', 'in', self.boq_ids.ids)],
        }
