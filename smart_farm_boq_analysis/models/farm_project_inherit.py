from odoo import api, fields, models, _


class FarmProjectAnalysisInherit(models.Model):
    """Extend farm.project with BOQ Analysis navigation.

    Adds a stat button "Open BOQ Analysis" on the Farm Project form so users
    can navigate directly to all Analysis documents for this project.

    Analysis documents are accessed via:
        Cost Structure → B.O.Q Analysis     (global list)
        Farm Project form → Open BOQ Analysis button  (filtered to project)
    """

    _inherit = 'farm.project'

    # ── Analysis count (stat button) ──────────────────────────────────────────
    analysis_count = fields.Integer(
        string='BOQ Analysis',
        compute='_compute_analysis_count',
    )

    @api.depends('name')
    def _compute_analysis_count(self):
        Analysis = self.env['farm.boq.analysis']
        for rec in self:
            rec.analysis_count = Analysis.search_count([('project_id', '=', rec.id)])

    def action_open_project_analysis(self):
        """Open BOQ Analysis documents filtered to this project."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('BOQ Analysis — %s') % self.name,
            'res_model': 'farm.boq.analysis',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
        }
