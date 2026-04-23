from odoo import api, fields, models, _


class ConstructionProjectMaterialExt(models.Model):
    """Extend construction.project with material request linkage."""
    _inherit = 'construction.project'

    material_request_ids = fields.One2many(
        comodel_name='construction.material.request',
        inverse_name='project_id',
        string='Material Request List',
    )
    material_request_count = fields.Integer(
        string='Material Requests',
        compute='_compute_material_request_count',
    )

    @api.depends('material_request_ids')
    def _compute_material_request_count(self):
        for rec in self:
            rec.material_request_count = len(rec.material_request_ids)

    def action_open_material_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Material Requests — %s') % self.name,
            'res_model': 'construction.material.request',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
        }
