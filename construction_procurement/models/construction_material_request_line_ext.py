from odoo import api, fields, models


class ConstructionMaterialRequestLineProcurementExt(models.Model):
    """Extend request line with procurement status backflow."""
    _inherit = 'construction.material.request.line'

    procurement_line_ids = fields.One2many(
        comodel_name='construction.procurement.line',
        inverse_name='material_request_line_id',
        string='Procurement Lines',
    )

    ordered_qty = fields.Float(
        string='Ordered Qty',
        compute='_compute_procurement_status',
        store=True,
        digits=(16, 4),
    )
    received_qty_proc = fields.Float(
        string='Received Qty',
        compute='_compute_procurement_status',
        store=True,
        digits=(16, 4),
    )
    remaining_qty_proc = fields.Float(
        string='Remaining Qty',
        compute='_compute_procurement_status',
        store=True,
        digits=(16, 4),
    )
    procurement_status = fields.Selection(
        selection=[
            ('not_procured',       'Not Procured'),
            ('rfq',                'RFQ'),
            ('ordered',            'Ordered'),
            ('partially_received', 'Partially Received'),
            ('fully_received',     'Fully Received'),
        ],
        string='Procurement Status',
        compute='_compute_procurement_status',
        store=True,
    )

    @api.depends(
        'procurement_line_ids.ordered_qty',
        'procurement_line_ids.received_qty',
        'procurement_line_ids.state',
    )
    def _compute_procurement_status(self):
        for rec in self:
            plines = rec.procurement_line_ids.filtered(
                lambda l: l.state != 'cancelled'
            )
            if not plines:
                rec.ordered_qty = 0.0
                rec.received_qty_proc = 0.0
                rec.remaining_qty_proc = rec.requested_qty
                rec.procurement_status = 'not_procured'
                continue

            ordered = sum(plines.mapped('ordered_qty'))
            received = sum(plines.mapped('received_qty'))
            rec.ordered_qty = ordered
            rec.received_qty_proc = received
            rec.remaining_qty_proc = max(0.0, ordered - received)

            # Quantities take priority over line state flags
            if ordered > 0 and received >= ordered:
                rec.procurement_status = 'fully_received'
            elif received > 0:
                rec.procurement_status = 'partially_received'
            else:
                states = set(plines.mapped('state'))
                if 'ordered' in states:
                    rec.procurement_status = 'ordered'
                elif 'rfq' in states:
                    rec.procurement_status = 'rfq'
                else:
                    rec.procurement_status = 'not_procured'
