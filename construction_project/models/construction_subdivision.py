from odoo import api, fields, models


class ConstructionSubdivision(models.Model):
    _name = 'construction.subdivision'
    _description = 'Construction Subdivision'
    _order = 'sequence, name'

    name = fields.Char(string='Subdivision Name', required=True)
    code = fields.Char(string='Code', required=True, size=20)
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(string='Active', default=True)

    division_id = fields.Many2one(
        comodel_name='construction.division',
        string='Division',
        required=True,
        ondelete='cascade',
        index=True,
    )
    # Stored for easy filtering/dashboards without joining through division
    project_id = fields.Many2one(
        comodel_name='construction.project',
        string='Project',
        related='division_id.project_id',
        store=True,
        readonly=True,
        index=True,
    )

    @api.onchange('division_id')
    def _onchange_division_id(self):
        """Auto-propagate project from division."""
        pass  # project_id is a related field; nothing extra needed
