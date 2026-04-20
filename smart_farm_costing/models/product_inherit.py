from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    """Extend product.template with job_type for BOQ cost classification.

    Rules
    -----
    Goods (type != 'service')  → job_type is always 'material' (auto-set, readonly)
    Service (type == 'service') → job_type ∈ {labour, tools, equipment,
                                   subcontractor, other}  (user-selectable)

    Enforcement layers
    ------------------
    1. default_get()  — new product form opens pre-filled with 'material' for goods
    2. _onchange_type_set_job_type()  — fires immediately when the user changes
                                        the product type in the form
    3. create() / write() — programmatic / import / API path: auto-corrects or
                            raises if the caller passes an invalid combination
    4. _check_job_type_consistency() — final constraint guard on every save
    """

    _inherit = 'product.template'

    job_type = fields.Selection(
        selection=[
            ('material',      'Material'),
            ('labour',        'Labour'),
            ('tools',         'Tools'),
            ('equipment',     'Equipment'),
            ('subcontractor', 'Subcontractor'),
            ('other',         'Other'),
        ],
        string='Job Type | نوع العمل',
        index=True,
        help=(
            'Used to classify this product in BOQ cost breakdowns.\n'
            '• Goods / Consumable / Storable: always Material (auto-set).\n'
            '• Service: choose Labour / Tools / Equipment / Subcontractor / Other.'
        ),
    )

    # ────────────────────────────────────────────────────────────────────────
    # Layer 1 — default_get: pre-fill job_type when a new form opens
    # ────────────────────────────────────────────────────────────────────────

    @api.model
    def default_get(self, fields_list):
        """Pre-fill job_type='material' for new goods products.

        When a new product form opens, the default type is already 'consu'
        (Consumable / Goods).  The onchange only fires on user-triggered
        changes, so without this override the job_type field would be empty
        on form load for goods products.
        """
        res = super().default_get(fields_list)
        if 'job_type' in fields_list:
            # default type coming from context or field default
            default_type = res.get('type') or self._fields['type'].default(self) or 'consu'
            if default_type != 'service':
                res.setdefault('job_type', 'material')
        return res

    # ────────────────────────────────────────────────────────────────────────
    # Layer 2 — onchange: immediate UI reaction when product type changes
    # ────────────────────────────────────────────────────────────────────────

    @api.onchange('type', 'detailed_type')
    def _onchange_type_set_job_type(self):
        for rec in self:
            if rec.type != 'service':
                # Goods / Consumable / Storable → must be material
                rec.job_type = 'material'
            elif rec.job_type == 'material':
                # Type changed to Service → clear the invalid 'material' value
                rec.job_type = False

    # ────────────────────────────────────────────────────────────────────────
    # Layer 3 — create / write: auto-correct on programmatic / API paths
    # ────────────────────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        """Auto-set job_type='material' for goods products on create.

        Guard: only process records where job_type is explicitly present in
        vals.  Standard Odoo modules (hr_expense, sale, purchase, …) never
        pass job_type, so those products are left completely untouched.
        Smart Farm UI always includes job_type via default_get + onchange.
        """
        for vals in vals_list:
            if 'job_type' not in vals:
                # Not a Smart Farm product creation — skip all job_type logic.
                continue
            prod_type = vals.get('type', 'consu')
            if prod_type != 'service':
                # Goods / Consumable / Storable → force material
                vals['job_type'] = 'material'
            elif vals.get('job_type') == 'material':
                # Service product explicitly given 'material' — clear it
                # (onchange should have done this already, but be safe)
                vals['job_type'] = False
        return super().create(vals_list)

    def write(self, vals):
        """Auto-correct job_type when product type changes programmatically.

        Guard: only enforce job_type rules when the caller is explicitly
        changing job_type OR type on a record that already has a job_type.
        Standard Odoo writes that don't touch job_type at all are passed
        through unchanged so they never trigger constraint errors.
        """
        new_type = vals.get('type')
        new_jt = vals.get('job_type')

        # Nothing job_type-related in this write → nothing to enforce
        if new_type is None and new_jt is None:
            return super().write(vals)

        # At least one of type / job_type is changing.
        # Only act on records that have job_type set (Smart Farm products).
        # For records with no job_type, pass through without modification.
        smart_farm_recs = self.filtered(lambda r: r.job_type)
        plain_recs = self - smart_farm_recs

        if plain_recs:
            # Standard products — only write if no job_type manipulation needed
            # (new_jt may be False/None so it's fine to let super handle it)
            super(ProductTemplate, plain_recs).write(vals)

        if smart_farm_recs:
            corrected = dict(vals)
            if new_type is not None:
                if new_type != 'service':
                    # Switching to Goods → force material
                    corrected['job_type'] = 'material'
                else:
                    # Switching to Service → clear material if not overridden
                    for rec in smart_farm_recs:
                        current_jt = new_jt or rec.job_type
                        if current_jt == 'material' and new_jt is None:
                            corrected = dict(corrected, job_type=False)
                            break
            super(ProductTemplate, smart_farm_recs).write(corrected)

        return True

    # ────────────────────────────────────────────────────────────────────────
    # Layer 4 — constraint: final guard on every save
    # ────────────────────────────────────────────────────────────────────────

    @api.constrains('type', 'job_type')
    def _check_job_type_consistency(self):
        """Validate job_type consistency — only for Smart Farm products.

        A record is considered a Smart Farm product if it has job_type set.
        Standard Odoo products have job_type = False and are skipped entirely.
        """
        for rec in self:
            if not rec.job_type:
                # No job_type set → not a Smart Farm product, skip validation
                continue
            if rec.type != 'service' and rec.job_type != 'material':
                raise ValidationError(_(
                    'Product "%s" is a Goods / Consumable / Storable product '
                    'and must have Job Type = Material.'
                ) % rec.name)
            if rec.type == 'service' and rec.job_type == 'material':
                raise ValidationError(_(
                    'Service product "%s" cannot have Job Type = Material. '
                    'Choose Labour / Tools / Equipment / Subcontractor / Other.'
                ) % rec.name)
