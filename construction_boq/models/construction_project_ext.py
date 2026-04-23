from odoo import api, fields, models, _


class ConstructionProjectBOQExt(models.Model):
    """Extend construction.project with BOQ linkage."""
    _inherit = 'construction.project'

    boq_ids = fields.One2many(
        comodel_name='construction.boq',
        inverse_name='project_id',
        string='BOQ Documents',
    )
    boq_count = fields.Integer(
        string='BOQs',
        compute='_compute_boq_count',
    )

    @api.depends('boq_ids')
    def _compute_boq_count(self):
        for rec in self:
            rec.boq_count = len(rec.boq_ids)

    def action_open_boqs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('BOQs — %s') % self.name,
            'res_model': 'construction.boq',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
        }
