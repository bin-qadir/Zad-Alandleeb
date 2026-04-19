from odoo import api, fields, models, _
from odoo.exceptions import UserError


class FarmBoqLine(models.Model):
    """Extend farm.boq.line with unit-cost breakdown.

    ## Responsibility

    This module is responsible for ONE thing only: computing the **cost per
    unit** of a subitem.

    ## Tab isolation strategy

    Each tab uses a DEDICATED One2many field filtered to one job_type.
    A line stored with job_type='labour' appears ONLY in the Labours tab.

    ## Calculation model (unit cost only — no BOQ-level totals)

        material_total      = Σ material_cost_ids.total_cost
        labor_total         = Σ labor_cost_ids.total_cost
        … (per type)
        total_direct_cost   = Σ all type totals
        risk_amount         = total_direct_cost × risk_percent / 100
        final_unit_cost     = total_direct_cost + risk_amount

    `final_unit_cost` is the cost to deliver ONE unit of this subitem.
    BOQ-level totals (cost_total, unit_price, selling_total) are the
    responsibility of the smart_farm_boq_analysis module.
    """

    _inherit = 'farm.boq.line'

    # ── Unified cost lines (all types, for compute & template loading) ────────
    cost_ids = fields.One2many(
        comodel_name='farm.boq.line.cost',
        inverse_name='boq_line_id',
        string='All Cost Lines',
    )

    # ── Per-type One2many fields (dedicated, domain-filtered) ─────────────────
    material_cost_ids = fields.One2many(
        comodel_name='farm.boq.line.cost',
        inverse_name='boq_line_id',
        domain=[('job_type', '=', 'material')],
        string='Materials',
    )
    labor_cost_ids = fields.One2many(
        comodel_name='farm.boq.line.cost',
        inverse_name='boq_line_id',
        domain=[('job_type', '=', 'labour')],
        string='Labours',
    )
    subcontractor_cost_ids = fields.One2many(
        comodel_name='farm.boq.line.cost',
        inverse_name='boq_line_id',
        domain=[('job_type', '=', 'subcontractor')],
        string='Subcontractor',
    )
    tools_cost_ids = fields.One2many(
        comodel_name='farm.boq.line.cost',
        inverse_name='boq_line_id',
        domain=[('job_type', '=', 'tools')],
        string='Tools',
    )
    equipment_cost_ids = fields.One2many(
        comodel_name='farm.boq.line.cost',
        inverse_name='boq_line_id',
        domain=[('job_type', '=', 'equipment')],
        string='Equipment',
    )
    other_cost_ids = fields.One2many(
        comodel_name='farm.boq.line.cost',
        inverse_name='boq_line_id',
        domain=[('job_type', '=', 'other')],
        string='Others',
    )

    # Legacy relations — kept for DB compatibility, not used in compute
    material_ids = fields.One2many('farm.boq.line.material',  'boq_line_id', string='Materials (legacy)')
    labor_ids    = fields.One2many('farm.boq.line.labor',     'boq_line_id', string='Labor (legacy)')
    overhead_ids = fields.One2many('farm.boq.line.overhead',  'boq_line_id', string='Overhead (legacy)')

    # ── Per-type totals (unit cost components) ────────────────────────────────
    material_total = fields.Float(
        string='Total Material Cost',
        compute='_compute_type_totals', store=True,
    )
    labor_total = fields.Float(
        string='Total Labour Cost',
        compute='_compute_type_totals', store=True,
    )
    subcontractor_total = fields.Float(
        string='Total Subcontractor Cost',
        compute='_compute_type_totals', store=True,
    )
    tools_total = fields.Float(
        string='Total Tools Cost',
        compute='_compute_type_totals', store=True,
    )
    equipment_total = fields.Float(
        string='Total Equipment Cost',
        compute='_compute_type_totals', store=True,
    )
    other_total = fields.Float(
        string='Total Other Cost',
        compute='_compute_type_totals', store=True,
    )
    total_direct_cost = fields.Float(
        string='Total Direct Cost',
        compute='_compute_type_totals', store=True,
    )

    # ── Risk ──────────────────────────────────────────────────────────────────
    risk_percent = fields.Float(
        string='Risk (%)',
        default=0.0,
        digits=(16, 2),
    )
    risk_amount = fields.Float(
        string='Risk Amount',
        compute='_compute_risk', store=True,
    )
    final_unit_cost = fields.Float(
        string='Final Unit Cost',
        compute='_compute_risk', store=True,
        help='Cost to deliver ONE unit of this subitem (all types + risk).',
    )

    # ── Notes ─────────────────────────────────────────────────────────────────
    notes = fields.Text(string='Notes')

    # ────────────────────────────────────────────────────────────────────────
    # Template loader onchange
    # ────────────────────────────────────────────────────────────────────────

    @api.onchange('template_id')
    def _onchange_template_id_costing(self):
        """Load margin + material lines from the selected template into cost_ids."""
        if not self.template_id:
            return
        tmpl = self.template_id
        self.cost_ids = [(5, 0, 0)] + [
            (0, 0, {
                'job_type':    'material',
                'product_id':  m.product_id.id or False,
                'description': m.description or (m.product_id.name if m.product_id else 'Material'),
                'uom_id':      m.uom_id.id or False,
                'quantity':    m.quantity,
                'unit_cost':   m.unit_price,
            })
            for m in tmpl.material_ids
        ]

    # ────────────────────────────────────────────────────────────────────────
    # Computed: per-type totals and direct cost
    # ────────────────────────────────────────────────────────────────────────

    @api.depends('cost_ids.total_cost', 'cost_ids.job_type', 'display_type')
    def _compute_type_totals(self):
        for rec in self:
            if rec.display_type:
                rec.material_total      = 0.0
                rec.labor_total         = 0.0
                rec.subcontractor_total = 0.0
                rec.tools_total         = 0.0
                rec.equipment_total     = 0.0
                rec.other_total         = 0.0
                rec.total_direct_cost   = 0.0
                continue
            bucket = {}
            for line in rec.cost_ids:
                bucket[line.job_type] = bucket.get(line.job_type, 0.0) + (line.total_cost or 0.0)
            rec.material_total      = bucket.get('material',      0.0)
            rec.labor_total         = bucket.get('labour',        0.0)
            rec.subcontractor_total = bucket.get('subcontractor', 0.0)
            rec.tools_total         = bucket.get('tools',         0.0)
            rec.equipment_total     = bucket.get('equipment',     0.0)
            rec.other_total         = bucket.get('other',         0.0)
            rec.total_direct_cost   = sum(bucket.values())

    # ────────────────────────────────────────────────────────────────────────
    # Computed: risk and final unit cost
    # ────────────────────────────────────────────────────────────────────────

    @api.depends('total_direct_cost', 'risk_percent', 'display_type')
    def _compute_risk(self):
        for rec in self:
            if rec.display_type:
                rec.risk_amount     = 0.0
                rec.final_unit_cost = 0.0
                continue
            direct = rec.total_direct_cost or 0.0
            risk   = direct * (rec.risk_percent or 0.0) / 100.0
            rec.risk_amount     = risk
            rec.final_unit_cost = direct + risk

    # ────────────────────────────────────────────────────────────────────────
    # Save as Template
    # ────────────────────────────────────────────────────────────────────────

    def action_save_as_template(self):
        """Create a reusable template from this subitem (material lines only)."""
        self.ensure_one()
        if not self.parent_id:
            raise UserError(_('Only subitems can be saved as templates.'))
        tmpl = self.env['farm.boq.line.template'].create({
            'name':           self.name,
            'description':    self.description or False,
            'division_id':    self.division_id.id or False,
            'subdivision_id': self.subdivision_id.id or False,
            'quantity':       1.0,
            'unit_id':        self.unit_id.id or False,
        })
        MatLine = self.env['farm.boq.line.template.material']
        for line in self.material_cost_ids:
            MatLine.create({
                'template_id': tmpl.id,
                'product_id':  line.product_id.id or False,
                'description': line.description,
                'uom_id':      line.uom_id.id or False,
                'quantity':    line.quantity,
                'unit_price':  line.unit_cost,
            })
        return {
            'type': 'ir.actions.act_window',
            'name': _('BOQ Template'),
            'res_model': 'farm.boq.line.template',
            'res_id': tmpl.id,
            'view_mode': 'form',
            'target': 'new',
        }
