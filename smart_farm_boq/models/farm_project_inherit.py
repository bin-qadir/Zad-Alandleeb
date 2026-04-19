from odoo import api, fields, models, _


class FarmProjectBoqInherit(models.Model):
    """Extend farm.project with Project Phase and BOQ navigation.

    BOQ structure is accessed exclusively from:
        Cost Structure → Project Cost Structure

    or via the "Open BOQs" stat button on the Farm Project form.

    Farm Project = project management summary + navigation hub only.
    """

    _inherit = 'farm.project'

    project_phase_id = fields.Many2one(
        comodel_name='project.phase.master',
        string='Project Phase',
        ondelete='set null',
    )

    # ── BOQ count (stat button) ───────────────────────────────────────────────
    boq_count = fields.Integer(
        string='Cost Structures',
        compute='_compute_boq_count',
    )

    @api.depends('name')
    def _compute_boq_count(self):
        FarmBoq = self.env['farm.boq']
        for rec in self:
            rec.boq_count = FarmBoq.search_count([('project_id', '=', rec.id)])

    def action_open_boqs(self):
        """Open Cost Structures (BOQs) filtered to this project."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Cost Structures — %s') % self.name,
            'res_model': 'farm.boq',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
        }

    def action_new_boq(self):
        """Open a blank BOQ form pre-linked to this project."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('New Cost Structure — %s') % self.name,
            'res_model': 'farm.boq',
            'view_mode': 'form',
            'target': 'current',
            'context': {'default_project_id': self.id},
        }
