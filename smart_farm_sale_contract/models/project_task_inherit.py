from odoo import fields, models


class ProjectTask(models.Model):
    """Extend project.task with a link to farm.job.order.

    Enables Odoo task management (planning, assignments, time tracking)
    to be tied to a specific Farm Job Order.
    """

    _inherit = 'project.task'

    job_order_id = fields.Many2one(
        'farm.job.order',
        string='Job Order',
        ondelete='set null',
        index=True,
        tracking=True,
        help='Farm Job Order this task contributes to.',
    )
