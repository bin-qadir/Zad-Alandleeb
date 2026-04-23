from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ConstructionBOQLineMaterialExt(models.Model):
    """Extend construction.boq.line with material planning linkage."""
    _inherit = 'construction.boq.line'

    material_plan_ids = fields.One2many(
        comodel_name='construction.material.plan',
        inverse_name='boq_line_id',
        string='Material Plan List',
    )
    material_plan_count = fields.Integer(
        string='Material Plans',
        compute='_compute_material_counts',
    )
    material_request_count = fields.Integer(
        string='Material Requests',
        compute='_compute_material_counts',
    )

    @api.depends('material_plan_ids', 'material_plan_ids.request_line_ids')
    def _compute_material_counts(self):
        for rec in self:
            rec.material_plan_count = len(rec.material_plan_ids)
            request_ids = rec.material_plan_ids.mapped(
                'request_line_ids.request_id'
            )
            rec.material_request_count = len(request_ids)

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_open_material_plans(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Material Plans — %s') % self.description,
            'res_model': 'construction.material.plan',
            'view_mode': 'list,form',
            'domain': [('boq_line_id', '=', self.id)],
            'context': {
                'default_boq_line_id': self.id,
                'default_project_id': self.project_id.id,
            },
        }

    def action_open_material_requests(self):
        self.ensure_one()
        request_ids = self.material_plan_ids.mapped(
            'request_line_ids.request_id'
        ).ids
        return {
            'type': 'ir.actions.act_window',
            'name': _('Material Requests — %s') % self.description,
            'res_model': 'construction.material.request',
            'view_mode': 'list,form',
            'domain': [('id', 'in', request_ids)],
            'context': {'default_project_id': self.project_id.id},
        }

    def action_create_material_request(self):
        """
        Generate a Material Request directly from this BOQ line's
        material plan lines that have a shortage.
        Raises if no material plans exist.
        """
        self.ensure_one()
        plans = self.material_plan_ids.filtered(
            lambda p: p.status not in ('procured',)
        )
        if not plans:
            raise UserError(
                _('No active material plan lines found for BOQ line "%s".\n'
                  'Add material plan lines first.')
                % self.description
            )
        return plans.action_create_request()
