from odoo import fields, models


class FarmProjectType(models.Model):
    _name = 'farm.project.type'
    _description = 'Farm Project Type'
    _order = 'activity, sequence, name'

    name = fields.Char(string='Type Name', required=True, translate=True)
    activity = fields.Selection(
        selection=[
            ('construction',  'Construction'),
            ('agriculture',   'Agriculture'),
            ('manufacturing', 'Manufacturing / Packing'),
            ('livestock',     'Livestock'),
        ],
        string='Business Activity',
        required=True,
        index=True,
        help='The business activity this project type belongs to.',
    )
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(
        string='Active',
        default=True,
        help='Uncheck to archive this project type without deleting it.',
    )

    _sql_constraints = [
        (
            'unique_name_activity',
            'UNIQUE(name, activity)',
            'A project type with this name already exists for that business activity.',
        ),
    ]
