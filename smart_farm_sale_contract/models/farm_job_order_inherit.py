from odoo import fields, models, _


class FarmJobOrderSaleContract(models.Model):
    """Extend farm.job.order with Sales Order traceability and Odoo Task link.

    Adds:
    - sale_order_id / sale_order_line_id  — commercial contract traceability
    - task_count + action_view_tasks()    — link to Odoo project.task records
    """

    _inherit = 'farm.job.order'

    # ── Sales Order traceability ──────────────────────────────────────────────

    sale_order_id = fields.Many2one(
        'sale.order',
        string='Sales Order',
        ondelete='restrict',
        index=True,
        tracking=True,
        help='The approved Sales Order (commercial contract) that generated this Job Order.',
    )

    sale_order_line_id = fields.Many2one(
        'sale.order.line',
        string='Contract Line',
        ondelete='set null',
        index=True,
        help='The specific Sales Order line that this Job Order was created from.',
    )

    # ── Odoo Task link ────────────────────────────────────────────────────────

    task_count = fields.Integer(
        string='Tasks',
        compute='_compute_task_count',
    )

    # ────────────────────────────────────────────────────────────────────────
    # Computed
    # ────────────────────────────────────────────────────────────────────────

    def _compute_task_count(self):
        Task = self.env['project.task']
        for rec in self:
            rec.task_count = Task.search_count([('job_order_id', '=', rec.id)])

    # ────────────────────────────────────────────────────────────────────────
    # Navigation
    # ────────────────────────────────────────────────────────────────────────

    def action_view_tasks(self):
        """Open all Odoo Tasks linked to this Job Order."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Tasks — %s') % self.name,
            'res_model': 'project.task',
            'view_mode': 'list,form',
            'domain': [('job_order_id', '=', self.id)],
            'context': {
                'default_job_order_id': self.id,
            },
        }

    def action_open_sale_order(self):
        """Open the linked Sales Order (contract)."""
        self.ensure_one()
        if not self.sale_order_id:
            return
        return {
            'type': 'ir.actions.act_window',
            'name': _('Contract — %s') % self.sale_order_id.name,
            'res_model': 'sale.order',
            'view_mode': 'form',
            'res_id': self.sale_order_id.id,
        }
