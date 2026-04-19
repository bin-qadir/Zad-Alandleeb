from odoo import fields, models


class FarmBoqLineTemplateUseWizard(models.TransientModel):
    """Wizard: pick a target BOQ and create a full BOQ Line from a template."""

    _name = 'farm.boq.line.template.use.wizard'
    _description = 'Create BOQ Line from Template'

    template_id = fields.Many2one(
        'farm.boq.line.template', string='Template', required=True,
    )
    boq_id = fields.Many2one(
        'farm.boq', string='Target BOQ', required=True,
    )

    def action_create(self):
        """Instantiate the template: creates a farm.boq.line and copies costing detail lines."""
        self.ensure_one()
        tmpl = self.template_id
        boq = self.boq_id

        # Create the main BOQ line.
        # unit_price is a computed field (when smart_farm_costing is installed)
        # so we only pass the inputs that drive it: quantity + margin_percent.
        # The ORM will compute unit_price automatically after cost lines exist.
        line = self.env['farm.boq.line'].create({
            'boq_id': boq.id,
            'name': tmpl.name,
            'description': tmpl.description,
            'division_id': tmpl.division_id.id or False,
            'subdivision_id': tmpl.subdivision_id.id or False,
            'quantity': 1.0,
            'boq_qty':  tmpl.quantity,
            'unit_id': tmpl.unit_id.id or False,
            # Pass margin so _compute_selling can derive the correct unit_price
            # once the child lines are created below.
            **({'margin_percent': tmpl.margin_percent}
               if 'margin_percent' in self.env['farm.boq.line']._fields
               else {'unit_price': tmpl.unit_price}),
        })

        # Copy costing detail lines (only if smart_farm_costing is installed)
        if 'farm.boq.line.material' in self.env:
            mat_fields = self.env['farm.boq.line.material']._fields
            for mat in tmpl.material_ids:
                self.env['farm.boq.line.material'].create({
                    'boq_line_id': line.id,
                    'product_id': mat.product_id.id or False,
                    'description': mat.description,
                    'quantity': mat.quantity,
                    'unit_price': mat.unit_price,
                    **({'uom_id': mat.uom_id.id or False}
                       if 'uom_id' in mat_fields else {}),
                })
            # Labor and overhead are now percent-based on the BOQ line;
            # no detail lines are created from templates.

        # Navigate to the newly created BOQ line
        return {
            'type': 'ir.actions.act_window',
            'name': 'BOQ Line',
            'res_model': 'farm.boq.line',
            'res_id': line.id,
            'view_mode': 'form',
            'target': 'current',
        }
