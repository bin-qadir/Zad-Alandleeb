{
    'name': 'Lavandula — Planned vs Actual Engine',
    'version': '18.0.1.0.0',
    'summary': 'Qty, cost, revenue, and profit variance engine for construction projects',
    'description': (
        'Adds Planned vs Actual analysis at three levels:\n'
        '  • BOQ Analysis Line — actual qty from linked Job Orders\n'
        '  • Job Order          — qty variance, planned revenue, profitability\n'
        '  • Project            — aggregated revenue variance, margin, flags\n\n'
        'Complements smart_farm_control (which covers cost/forecast) by adding\n'
        'the revenue / profitability side and quantity overrun tracking.\n\n'
        'Intentionally avoids duplicating fields already defined in:\n'
        '  smart_farm_control  (estimated_cost, actual_total_cost, revenue,\n'
        '                        projected_profit, realized_profit, is_over_budget)\n'
        '  smart_farm_dashboard (project_health, is_negative_profit)'
    ),
    'category': 'Agriculture',
    'author': 'Smart Farm',
    'license': 'LGPL-3',
    'depends': [
        'smart_farm_project',       # farm.project base + form view
        'smart_farm_execution',     # farm.job.order
        'smart_farm_boq_analysis',  # farm.boq.analysis.line
        'smart_farm_sale_contract', # farm.project estimated_cost, job_order_ids
        'smart_farm_control',       # actual_total_cost (full 4-bucket), revenue
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/project_pva_views.xml',
        'views/job_order_pva_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
