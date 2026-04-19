from odoo import api, fields, models


class FarmSubdivisionWork(models.Model):
    _name = 'farm.subdivision.work'
    _description = 'Farm Subdivision Work'
    # Order by division's own sequence (not its DB id), then by sub-sequence
    _order = 'division_sequence, sequence, name'

    name = fields.Char(string='Name (English)', required=True)
    name_ar = fields.Char(string='الاسم (عربي)')
    code = fields.Char(string='Code')
    sequence = fields.Integer(string='Sequence', default=10)
    division_id = fields.Many2one(
        comodel_name='farm.division.work',
        string='Division',
        required=True,
        ondelete='restrict',
        index=True,
    )
    # Stored so _order can sort by division sequence without a JOIN
    division_sequence = fields.Integer(
        string='Division Sequence',
        related='division_id.sequence',
        store=True,
        index=True,
    )
    active = fields.Boolean(string='Active', default=True)

    display_name_bilingual = fields.Char(
        string='Bilingual Label',
        compute='_compute_display_name_bilingual',
        store=True,
        help='Shows "English | Arabic" when both names are set, '
             'otherwise shows the English name only.',
    )

    @api.depends('name', 'name_ar')
    def _compute_display_name_bilingual(self):
        for rec in self:
            if rec.name_ar and rec.name_ar.strip():
                rec.display_name_bilingual = f'{rec.name}  |  {rec.name_ar.strip()}'
            else:
                rec.display_name_bilingual = rec.name or ''
