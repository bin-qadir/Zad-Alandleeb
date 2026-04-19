from odoo import fields, models


class PurchaseOrderFarm(models.Model):
    """Adds Smart Farm traceability fields to Purchase Orders."""

    _inherit = 'purchase.order'

    farm_project_id = fields.Many2one(
        'farm.project',
        string='Farm Project',
        ondelete='set null',
        index=True,
    )
    farm_boq_id = fields.Many2one(
        'farm.boq',
        string='BOQ Document',
        ondelete='set null',
        index=True,
    )
    farm_analysis_id = fields.Many2one(
        'farm.boq.analysis',
        string='BOQ Analysis',
        ondelete='set null',
        index=True,
    )


class PurchaseOrderLineFarm(models.Model):
    """Links a Purchase Order Line back to the BOQ Analysis Line that generated it."""

    _inherit = 'purchase.order.line'

    farm_analysis_line_id = fields.Many2one(
        'farm.boq.analysis.line',
        string='Analysis Line',
        ondelete='set null',
        index=True,
        copy=False,
    )
