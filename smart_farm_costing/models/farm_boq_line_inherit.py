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
        """Load ALL cost types from the selected template into cost_ids.

        Uses the current boq_qty as the main_quantity so child quantities
        are immediately correct: child.qty = main_qty × base_ratio_qty.
        The template itself is never modified.
        """
        if not self.template_id:
            return
        tmpl = self.template_id
        main_qty = self.boq_qty or 1.0
        tmpl_qty = max(tmpl.quantity or 1.0, 1e-9)

        lines = [(5, 0, 0)]
        for m in tmpl.material_ids:
            ratio = (m.quantity or 0.0) / tmpl_qty
            lines.append((0, 0, {
                'job_type':       'material',
                'product_id':     m.product_id.id or False,
                'description':    m.description or (m.product_id.name if m.product_id else 'Material'),
                'uom_id':         m.uom_id.id or False,
                'base_ratio_qty': ratio,
                'quantity':       main_qty * ratio,
                'unit_cost':      m.unit_price,
            }))
        for l in tmpl.labor_ids:
            ratio = (l.hours or 0.0) / tmpl_qty
            lines.append((0, 0, {
                'job_type':       'labour',
                'product_id':     l.product_id.id or False,
                'description':    l.description or (l.product_id.name if l.product_id else 'Labour'),
                'uom_id':         l.uom_id.id or False,
                'base_ratio_qty': ratio,
                'quantity':       main_qty * ratio,
                'unit_cost':      l.cost_per_hour,
            }))
        for s in tmpl.subcontractor_ids:
            ratio = (s.quantity or 0.0) / tmpl_qty
            lines.append((0, 0, {
                'job_type':       'subcontractor',
                'product_id':     s.product_id.id or False,
                'description':    s.description or (s.product_id.name if s.product_id else 'Subcontractor'),
                'uom_id':         s.uom_id.id or False,
                'base_ratio_qty': ratio,
                'quantity':       main_qty * ratio,
                'unit_cost':      s.unit_price,
            }))
        for eq in tmpl.equipment_ids:
            ratio = (eq.quantity or 0.0) / tmpl_qty
            lines.append((0, 0, {
                'job_type':       'equipment',
                'product_id':     eq.product_id.id or False,
                'description':    eq.description or (eq.product_id.name if eq.product_id else 'Equipment'),
                'uom_id':         eq.uom_id.id or False,
                'base_ratio_qty': ratio,
                'quantity':       main_qty * ratio,
                'unit_cost':      eq.unit_price,
            }))
        for t in tmpl.tools_ids:
            ratio = (t.quantity or 0.0) / tmpl_qty
            lines.append((0, 0, {
                'job_type':       'tools',
                'product_id':     t.product_id.id or False,
                'description':    t.description or (t.product_id.name if t.product_id else 'Tools'),
                'uom_id':         t.uom_id.id or False,
                'base_ratio_qty': ratio,
                'quantity':       main_qty * ratio,
                'unit_cost':      t.unit_price,
            }))
        for o in tmpl.overhead_ids:
            ratio = (o.quantity or 0.0) / tmpl_qty
            lines.append((0, 0, {
                'job_type':       'other',
                'product_id':     o.product_id.id or False,
                'description':    o.name or (o.product_id.name if o.product_id else 'Other'),
                'uom_id':         o.uom_id.id or False,
                'base_ratio_qty': ratio,
                'quantity':       main_qty * ratio,
                'unit_cost':      o.unit_price,
            }))
        self.cost_ids = lines

    # ────────────────────────────────────────────────────────────────────────
    # ORM override: cascade child quantity when parent boq_qty changes
    # ────────────────────────────────────────────────────────────────────────

    def write(self, vals):
        """Propagate boq_qty change to linked cost lines that have base_ratio_qty.

        Only cost lines created from a template (base_ratio_qty > 0) are
        updated. Manually added lines (base_ratio_qty = 0) are left alone.
        This gives: child.quantity = parent.boq_qty × child.base_ratio_qty
        """
        res = super().write(vals)
        if 'boq_qty' in vals:
            new_qty = vals['boq_qty'] or 0.0
            for rec in self:
                ratio_lines = rec.cost_ids.filtered(
                    lambda l: (l.base_ratio_qty or 0.0) > 0
                )
                for cline in ratio_lines:
                    cline.quantity = new_qty * cline.base_ratio_qty
        return res

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
