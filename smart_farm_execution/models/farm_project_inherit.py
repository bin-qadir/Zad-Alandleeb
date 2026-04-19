from odoo import api, fields, models, _


class FarmProjectExecution(models.Model):
    """Adds Job Order navigation to Farm Project form."""

    _inherit = 'farm.project'

    # Single source of truth for the Job Orders relation on farm.project.
    # Used by @api.depends in smart_farm_sale_contract and smart_farm_control.
    # String intentionally distinct from job_order_count to avoid label collision.
    job_order_ids = fields.One2many(
        'farm.job.order',
        'project_id',
        string='Job Order List',
    )

    job_order_count = fields.Integer(
        string='Job Orders',
        compute='_compute_job_order_count',
    )

    def _compute_job_order_count(self):
        JobOrder = self.env['farm.job.order']
        for rec in self:
            rec.job_order_count = JobOrder.search_count(
                [('project_id', '=', rec.id)]
            )

    def action_open_job_orders(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Job Orders — %s') % self.name,
            'res_model': 'farm.job.order',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
        }
