from odoo import fields, models


class ConstructionDivision(models.Model):
    _name = 'construction.division'
    _description = 'Construction Division'
    _order = 'sequence, name'

    name = fields.Char(string='Division Name', required=True)
    code = fields.Char(string='Code', required=True, size=10)
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(string='Active', default=True)

    project_id = fields.Many2one(
        comodel_name='construction.project',
        string='Project',
        required=True,
        ondelete='cascade',
        index=True,
    )

    subdivision_ids = fields.One2many(
        comodel_name='construction.subdivision',
        inverse_name='division_id',
        string='Subdivision List',
    )
    subdivision_count = fields.Integer(
        string='Subdivisions',
        compute='_compute_subdivision_count',
    )

    def _compute_subdivision_count(self):
        for rec in self:
            rec.subdivision_count = len(rec.subdivision_ids)

    def action_open_subdivisions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Subdivisions — %s' % self.name,
            'res_model': 'construction.subdivision',
            'view_mode': 'list,form',
            'domain': [('division_id', '=', self.id)],
            'context': {
                'default_division_id': self.id,
                'default_project_id': self.project_id.id,
            },
        }
