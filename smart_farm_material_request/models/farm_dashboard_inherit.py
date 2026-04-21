from odoo import api, fields, models, _


class FarmDashboardMR(models.Model):
    """Extend farm.dashboard with Material Request KPIs."""

    _inherit = 'farm.dashboard'

    # ── Material Request KPIs ─────────────────────────────────────────────────
    mr_count_pending  = fields.Integer(
        compute='_compute_mr_kpis',
        string='Pending MRs',
        help='Material Requests awaiting approval.',
    )
    mr_count_approved = fields.Integer(
        compute='_compute_mr_kpis',
        string='Approved MRs',
        help='Approved Material Requests (PO not yet fully received).',
    )
    mr_count_rejected = fields.Integer(
        compute='_compute_mr_kpis',
        string='Rejected MRs',
    )
    mr_count_received = fields.Integer(
        compute='_compute_mr_kpis',
        string='Received MRs',
        help='MRs where all materials have been received.',
    )
    mr_total_estimated_cost = fields.Monetary(
        compute='_compute_mr_kpis',
        string='Total MR Estimated Cost',
        currency_field='currency_id',
        help='Sum of estimated costs across all non-rejected Material Requests.',
    )
    mr_total_actual_cost = fields.Monetary(
        compute='_compute_mr_kpis',
        string='Total MR Actual Cost',
        currency_field='currency_id',
        help='Sum of actual costs (received materials) across all MRs.',
    )

    def _compute_mr_kpis(self):
        MR = self.env['farm.material.request']
        all_mrs = MR.search([])

        pending  = len(all_mrs.filtered(lambda r: r.state == 'to_approve'))
        approved = len(all_mrs.filtered(
            lambda r: r.state in ('approved', 'rfq', 'ordered')
        ))
        rejected = len(all_mrs.filtered(lambda r: r.state == 'rejected'))
        received = len(all_mrs.filtered(lambda r: r.state == 'received'))

        active_mrs = all_mrs.filtered(lambda r: r.state != 'rejected')
        total_est    = sum(active_mrs.mapped('total_estimated_cost'))
        total_actual = sum(active_mrs.mapped('total_actual_cost'))

        for rec in self:
            rec.mr_count_pending         = pending
            rec.mr_count_approved        = approved
            rec.mr_count_rejected        = rejected
            rec.mr_count_received        = received
            rec.mr_total_estimated_cost  = total_est
            rec.mr_total_actual_cost     = total_actual

    # ── Drill-down actions ────────────────────────────────────────────────────

    def _mr_list_action(self, name, domain):
        return {
            'type':      'ir.actions.act_window',
            'name':      _(name),
            'res_model': 'farm.material.request',
            'view_mode': 'list,form',
            'domain':    domain,
        }

    def action_view_mr_pending(self):
        return self._mr_list_action(
            'Pending Material Requests',
            [('state', '=', 'to_approve')],
        )

    def action_view_mr_approved(self):
        return self._mr_list_action(
            'Approved Material Requests',
            [('state', 'in', ('approved', 'rfq', 'ordered'))],
        )

    def action_view_mr_rejected(self):
        return self._mr_list_action(
            'Rejected Material Requests',
            [('state', '=', 'rejected')],
        )

    def action_view_mr_received(self):
        return self._mr_list_action(
            'Received Material Requests',
            [('state', '=', 'received')],
        )

    def action_view_all_mr(self):
        return self._mr_list_action('All Material Requests', [])
