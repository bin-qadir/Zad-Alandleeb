"""
Migration 18.0.1.1.0 — farm.field: rename area (ha) → area_m2 (m²)

Renames the DB column, converts existing values, and updates the Odoo
field registry so the module update succeeds without errors.

    area_m2 = area * 10000
"""


def migrate(cr, version):
    # 1. Rename the column (idempotent — skip if already done)
    cr.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'farm_field' AND column_name = 'area';
    """)
    if cr.fetchone():
        cr.execute("ALTER TABLE farm_field RENAME COLUMN area TO area_m2;")

        # 2. Convert existing values from hectares to square meters
        cr.execute("""
            UPDATE farm_field
            SET area_m2 = area_m2 * 10000
            WHERE area_m2 != 0;
        """)

    # 3. Rename the ir.model.fields record so the registry loads cleanly
    cr.execute("""
        UPDATE ir_model_fields
        SET name            = 'area_m2',
            field_description = '{"en_US": "Area (m\u00b2)"}',
            complete_name     = '{"en_US": "Area (m\u00b2)"}'
        WHERE model = 'farm.field' AND name = 'area';
    """)
