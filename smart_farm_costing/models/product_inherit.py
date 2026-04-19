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
        """Auto-set job_type='material' for goods products on create."""
        for vals in vals_list:
            prod_type = vals.get('type', 'consu')
            if prod_type != 'service':
                vals.setdefault('job_type', 'material')
                # If caller explicitly passed a non-material job_type for goods,
                # override it silently — the constraint will catch any real mistake.
                if vals.get('job_type') and vals['job_type'] != 'material':
                    vals['job_type'] = 'material'
        return super().create(vals_list)

    def write(self, vals):
        """Auto-correct job_type when product type changes programmatically."""
        new_type = vals.get('type')
        if new_type is not None:
            if new_type != 'service':
                # Switching to Goods → force job_type = material
                vals['job_type'] = 'material'
            else:
                # Switching to Service → if job_type was material, clear it
                for rec in self:
                    current_jt = vals.get('job_type') or rec.job_type
                    if current_jt == 'material' and 'job_type' not in vals:
                        # Only clear if the caller isn't also changing job_type
                        vals = dict(vals, job_type=False)
                        break
        return super().write(vals)

    # ────────────────────────────────────────────────────────────────────────
    # Layer 4 — constraint: final guard on every save
    # ────────────────────────────────────────────────────────────────────────

    @api.constrains('type', 'job_type')
    def _check_job_type_consistency(self):
        for rec in self:
            if not rec.job_type:
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
