"""Rename job_type key 'labor' → 'labour' in cost lines and products."""


def migrate(cr, version):
    if not version:
        return

    # farm.boq.line.cost — rename stored job_type value
    cr.execute("""
        UPDATE farm_boq_line_cost
           SET job_type = 'labour'
         WHERE job_type = 'labor'
    """)

    # product.template — rename stored job_type value
    cr.execute("""
        UPDATE product_template
           SET job_type = 'labour'
         WHERE job_type = 'labor'
    """)
