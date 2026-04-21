"""
Migration 18.0.1.2.0 — farm.project: replace project_type (Selection) with
                         project_type (Many2one → farm.project.type)

The old field stored VARCHAR selection keys ('construction', 'irrigation', …).
The new field is a Many2one (int4 FK).  PostgreSQL cannot cast the old text
values to integer, so we must drop the column before Odoo tries to ALTER it.

We archive the old value in a new column `project_type_legacy` so no data is
silently discarded — an administrator can map legacy values to the new lookup
records if needed.
"""


def migrate(cr, version):
    # 1. Check whether the old text column still exists
    cr.execute("""
        SELECT data_type
        FROM   information_schema.columns
        WHERE  table_name  = 'farm_project'
        AND    column_name = 'project_type';
    """)
    row = cr.fetchone()
    if not row:
        # Already migrated (int4) or column absent — nothing to do
        return

    if row[0] in ('integer', 'int4', 'bigint'):
        # Column already converted to integer — skip
        return

    # 2. Archive the legacy text value into a new column
    cr.execute("""
        SELECT column_name
        FROM   information_schema.columns
        WHERE  table_name  = 'farm_project'
        AND    column_name = 'project_type_legacy';
    """)
    if not cr.fetchone():
        cr.execute("""
            ALTER TABLE farm_project
            ADD COLUMN project_type_legacy VARCHAR;
        """)

    cr.execute("""
        UPDATE farm_project
        SET    project_type_legacy = project_type
        WHERE  project_type IS NOT NULL;
    """)

    # 3. Drop the old text column so Odoo can recreate it as int4
    cr.execute("ALTER TABLE farm_project DROP COLUMN project_type;")

    # 4. Remove the stale ir.model.fields entry for the old Selection field
    #    (Odoo will re-create it as Many2one after migration)
    cr.execute("""
        DELETE FROM ir_model_fields
        WHERE  model = 'farm.project'
        AND    name  = 'project_type'
        AND    ttype = 'selection';
    """)
