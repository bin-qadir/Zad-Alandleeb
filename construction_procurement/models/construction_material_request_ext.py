from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ConstructionMaterialRequestProcurementExt(models.Model):
    """Extend material request with procurement creation action."""
    _inherit = 'construction.material.request'

    procurement_ids = fields.One2many(
        comodel_name='construction.procurement',
        inverse_name=False,
        string='Procurement List',
        compute='_compute_procurement_ids',
    )
    procurement_count = fields.Integer(
        string='Procurements',
        compute='_compute_procurement_ids',
    )

    def _compute_procurement_ids(self):
        Proc = self.env['construction.procurement']
        for rec in self:
            procs = Proc.search([('material_request_ids', 'in', rec.id)])
            rec.procurement_ids = procs
            rec.procurement_count = len(procs)

    def action_create_procurement(self):
        """
        Generate a construction.procurement record from this approved request.
        Groups all request lines into a single procurement per project.
        """
        self.ensure_one()
        if self.state != 'approved':
            raise UserError(
                _('Only approved material requests can generate a procurement.\n'
                  'Current state: "%s".') % self.state
            )
        if not self.line_ids:
            raise UserError(
                _('Material request "%s" has no lines.') % self.name
            )

        procurement = self.env['construction.procurement'].create({
            'project_id': self.project_id.id,
            'division_id': self.division_id.id or False,
            'subdivision_id': self.subdivision_id.id or False,
            'procurement_date': fields.Date.context_today(self),
        })
        procurement.material_request_ids = [(4, self.id)]

        for rl in self.line_ids:
            self.env['construction.procurement.line'].create({
                'procurement_id': procurement.id,
                'material_request_line_id': rl.id,
                'boq_line_id': rl.boq_line_id.id or False,
                'material_plan_id': rl.material_plan_id.id or False,
                'product_id': rl.product_id.id,
                'description': rl.description or rl.product_id.display_name,
                'unit': rl.unit,
                'requested_qty': rl.requested_qty,
                'ordered_qty': rl.requested_qty,
                'unit_price': rl.product_id.standard_price or 0.0,
            })

        return {
            'type': 'ir.actions.act_window',
            'name': _('Procurement'),
            'res_model': 'construction.procurement',
            'view_mode': 'form',
            'res_id': procurement.id,
        }

    def action_open_procurements(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Procurements — %s') % self.name,
            'res_model': 'construction.procurement',
            'view_mode': 'list,form',
            'domain': [('material_request_ids', 'in', self.id)],
            'context': {'default_project_id': self.project_id.id},
        }
