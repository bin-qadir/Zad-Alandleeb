from odoo import api, fields, models, _


class FarmJobOrderMR(models.Model):
    """Extend farm.job.order with Material Request reverse link."""

    _inherit = 'farm.job.order'

    material_request_ids = fields.One2many(
        'farm.material.request',
        'job_order_id',
        string='Material Requests',
    )
    material_request_count = fields.Integer(
        string='Mat. Requests',
        compute='_compute_material_request_count',
    )

    def _compute_material_request_count(self):
        for rec in self:
            rec.material_request_count = len(rec.material_request_ids)

    def action_open_material_requests(self):
        """Open Material Requests for this Job Order."""
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'name':      _('Material Requests — %s') % self.name,
            'res_model': 'farm.material.request',
            'view_mode': 'list,form',
            'domain':    [('job_order_id', '=', self.id)],
            'context':   {
                'default_job_order_id': self.id,
                'default_project_id':   self.project_id.id,
            },
        }
