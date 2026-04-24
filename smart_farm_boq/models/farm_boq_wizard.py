from odoo import api, fields, models, _
from odoo.exceptions import UserError


class FarmBoqLineTemplateUseWizard(models.TransientModel):
    """Wizard: pick a target BOQ and create a full BOQ Line from a template.

    The template is a read-only source — it is never modified.
    Inserted item is a working copy with all cost component lines.
    main_quantity drives child quantities: child.qty = main_qty × base_ratio_qty.
    """

    _name = 'farm.boq.line.template.use.wizard'
    _description = 'Create BOQ Line from Template'

    template_id = fields.Many2one(
        'farm.boq.line.template', string='Template', required=True,
    )
    boq_id = fields.Many2one(
        'farm.boq', string='Target BOQ', required=True,
    )
    main_quantity = fields.Float(
        string='Main Quantity | الكمية الرئيسية',
        default=1.0,
        digits=(16, 2),
        help=(
            'The project quantity for this BOQ item.\n'
            'All child cost component quantities are derived as:\n'
            '  child.qty = main_quantity × base_ratio_qty'
        ),
    )

    @api.onchange('template_id')
    def _onchange_template_id(self):
        """Pre-fill main_quantity from template's reference quantity."""
        if self.template_id:
            self.main_quantity = self.template_id.quantity or 1.0

    def action_create(self):
        """Instantiate the template: create a farm.boq.line + ALL cost lines.

        Template is source-only — never written.
        Child cost lines get base_ratio_qty so parent qty change drives them.
        Navigates to the newly created BOQ line on completion.
        """
        self.ensure_one()
        tmpl = self.template_id
        boq = self.boq_id
        main_qty = self.main_quantity or 1.0
        tmpl_qty = max(tmpl.quantity or 1.0, 1e-9)

        # ── Parent BOQ line ──────────────────────────────────────────────────
        BoqLine = self.env['farm.boq.line']
        line = BoqLine.create({
            'boq_id':       boq.id,
            'name':         tmpl.name,
            'description':  tmpl.description,
            'division_id':  tmpl.division_id.id or False,
            'subdivision_id': tmpl.subdivision_id.id or False,
            'quantity':     1.0,
            'boq_qty':      main_qty,
            'unit_id':      tmpl.unit_id.id or False,
            **({'margin_percent': tmpl.margin_percent}
               if 'margin_percent' in BoqLine._fields
               else {}),
        })

        # ── Child cost lines — ALL template types ────────────────────────────
        CostLine = self.env.get('farm.boq.line.cost')
        if CostLine is not None:
            for vals in self._template_to_cost_vals(tmpl, line.id, main_qty, tmpl_qty):
                CostLine.create(vals)

        return {
            'type': 'ir.actions.act_window',
            'name': _('BOQ Line'),
            'res_model': 'farm.boq.line',
            'res_id': line.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ────────────────────────────────────────────────────────────────────────
    # Private helper — mirrors the same helper in farm_boq_add_item_wizard
    # ────────────────────────────────────────────────────────────────────────

    def _template_to_cost_vals(self, template, boq_line_id, main_qty, tmpl_qty):
        """Return list of farm.boq.line.cost creation dicts for ALL template types."""
        lines = []

        for m in template.material_ids:
            ratio = (m.quantity or 0.0) / tmpl_qty
            lines.append({
                'boq_line_id':    boq_line_id,
                'job_type':       'material',
                'product_id':     m.product_id.id if m.product_id else False,
                'description':    m.description or (m.product_id.name if m.product_id else 'Material'),
                'uom_id':         m.uom_id.id if m.uom_id else False,
                'base_ratio_qty': ratio,
                'quantity':       main_qty * ratio,
                'unit_cost':      m.unit_price,
            })

        for l in template.labor_ids:
            ratio = (l.hours or 0.0) / tmpl_qty
            lines.append({
                'boq_line_id':    boq_line_id,
                'job_type':       'labour',
                'product_id':     l.product_id.id if l.product_id else False,
                'description':    l.description or (l.product_id.name if l.product_id else 'Labour'),
                'uom_id':         l.uom_id.id if l.uom_id else False,
                'base_ratio_qty': ratio,
                'quantity':       main_qty * ratio,
                'unit_cost':      l.cost_per_hour,
            })

        for s in template.subcontractor_ids:
            ratio = (s.quantity or 0.0) / tmpl_qty
            lines.append({
                'boq_line_id':    boq_line_id,
                'job_type':       'subcontractor',
                'product_id':     s.product_id.id if s.product_id else False,
                'description':    s.description or (s.product_id.name if s.product_id else 'Subcontractor'),
                'uom_id':         s.uom_id.id if s.uom_id else False,
                'base_ratio_qty': ratio,
                'quantity':       main_qty * ratio,
                'unit_cost':      s.unit_price,
            })

        for eq in template.equipment_ids:
            ratio = (eq.quantity or 0.0) / tmpl_qty
            lines.append({
                'boq_line_id':    boq_line_id,
                'job_type':       'equipment',
                'product_id':     eq.product_id.id if eq.product_id else False,
                'description':    eq.description or (eq.product_id.name if eq.product_id else 'Equipment'),
                'uom_id':         eq.uom_id.id if eq.uom_id else False,
                'base_ratio_qty': ratio,
                'quantity':       main_qty * ratio,
                'unit_cost':      eq.unit_price,
            })

        for t in template.tools_ids:
            ratio = (t.quantity or 0.0) / tmpl_qty
            lines.append({
                'boq_line_id':    boq_line_id,
                'job_type':       'tools',
                'product_id':     t.product_id.id if t.product_id else False,
                'description':    t.description or (t.product_id.name if t.product_id else 'Tools'),
                'uom_id':         t.uom_id.id if t.uom_id else False,
                'base_ratio_qty': ratio,
                'quantity':       main_qty * ratio,
                'unit_cost':      t.unit_price,
            })

        for o in template.overhead_ids:
            ratio = (o.quantity or 0.0) / tmpl_qty
            lines.append({
                'boq_line_id':    boq_line_id,
                'job_type':       'other',
                'product_id':     o.product_id.id if o.product_id else False,
                'description':    o.name or (o.product_id.name if o.product_id else 'Other'),
                'uom_id':         o.uom_id.id if o.uom_id else False,
                'base_ratio_qty': ratio,
                'quantity':       main_qty * ratio,
                'unit_cost':      o.unit_price,
            })

        return lines
