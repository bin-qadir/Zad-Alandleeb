from odoo import api, fields, models


class ConstructionBOQLineProcurementExt(models.Model):
    """Extend BOQ line with procurement readiness metrics."""
    _inherit = 'construction.boq.line'

    procurement_line_ids = fields.One2many(
        comodel_name='construction.procurement.line',
        inverse_name='boq_line_id',
        string='Procurement Lines',
    )
    procurement_count = fields.Integer(
        string='Procurements',
        compute='_compute_procurement_readiness',
    )

    # ── Readiness aggregates ──────────────────────────────────────────────────

    material_requested_qty = fields.Float(
        string='Material Requested',
        compute='_compute_procurement_readiness',
        digits=(16, 4),
        help='Sum of requested_qty across all material request lines for this BOQ line.',
    )
    material_ordered_qty = fields.Float(
        string='Material Ordered',
        compute='_compute_procurement_readiness',
        digits=(16, 4),
        help='Sum of ordered_qty across all procurement lines for this BOQ line.',
    )
    material_received_qty = fields.Float(
        string='Material Received',
        compute='_compute_procurement_readiness',
        digits=(16, 4),
        help='Sum of received_qty across all procurement lines for this BOQ line.',
    )
    procurement_readiness_percent = fields.Float(
        string='Procurement Readiness %',
        compute='_compute_procurement_readiness',
        digits=(16, 2),
        help='received_qty / ordered_qty × 100. '
             'Indicates how much of the planned material has been received.',
    )

    @api.depends(
        'procurement_line_ids.ordered_qty',
        'procurement_line_ids.received_qty',
        'procurement_line_ids.state',
        'material_plan_ids.request_line_ids.requested_qty',
    )
    def _compute_procurement_readiness(self):
        for rec in self:
            active_plines = rec.procurement_line_ids.filtered(
                lambda l: l.state != 'cancelled'
            )
            rec.procurement_count = len(
                active_plines.mapped('procurement_id')
            )
            # Requested: from request lines traced through plans
            req_lines = rec.material_plan_ids.mapped('request_line_ids')
            rec.material_requested_qty = sum(req_lines.mapped('requested_qty'))
            # Ordered / received from procurement lines
            ordered = sum(active_plines.mapped('ordered_qty'))
            received = sum(active_plines.mapped('received_qty'))
            rec.material_ordered_qty = ordered
            rec.material_received_qty = received
            rec.procurement_readiness_percent = (
                (received / ordered * 100.0) if ordered else 0.0
            )

    def action_open_procurements(self):
        self.ensure_one()
        proc_ids = self.procurement_line_ids.mapped('procurement_id').ids
        return {
            'type': 'ir.actions.act_window',
            'name': 'Procurements — %s' % self.description,
            'res_model': 'construction.procurement',
            'view_mode': 'list,form',
            'domain': [('id', 'in', proc_ids)],
        }
