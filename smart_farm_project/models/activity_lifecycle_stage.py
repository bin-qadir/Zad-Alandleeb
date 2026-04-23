from odoo import fields, models


BUSINESS_ACTIVITY_SELECTION = [
    ('construction',  'Construction'),
    ('agriculture',   'Agriculture'),
    ('manufacturing', 'Manufacturing / Packing'),
    ('livestock',     'Livestock'),
]


class ActivityLifecycleStage(models.Model):
    _name = 'activity.lifecycle.stage'
    _description = 'Activity Lifecycle Stage'
    _order = 'business_activity, sequence, name'
    _rec_name = 'name'

    name = fields.Char(
        string='Stage Name',
        required=True,
        translate=True,
    )
    code = fields.Char(
        string='Code',
        required=True,
        help='Internal technical key for this stage (e.g. planning, harvest).',
    )
    business_activity = fields.Selection(
        selection=BUSINESS_ACTIVITY_SELECTION,
        string='Business Activity',
        required=True,
        index=True,
        help='The business activity this lifecycle stage belongs to.',
    )
    sequence = fields.Integer(
        string='Sequence',
        default=10,
        help='Display order within the same activity.',
    )
    active = fields.Boolean(
        string='Active',
        default=True,
        help='Uncheck to archive without deleting.',
    )

    _sql_constraints = [
        (
            'unique_code_activity',
            'UNIQUE(code, business_activity)',
            'A lifecycle stage with this code already exists for that business activity.',
        ),
    ]
