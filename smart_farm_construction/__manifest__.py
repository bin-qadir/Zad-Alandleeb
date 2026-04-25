{
    'name': 'Smart Farm — Construction',
    'version': '18.0.2.2.0',
    'summary': 'Construction activity — project-driven enterprise workflow',
    'description': (
        'Smart Farm Construction — Project-driven Enterprise Module\n\n'
        'ARCHITECTURE\n'
        '  Filtered mirror of the Smart Farm engine with construction-specific\n'
        '  extensions. No duplicate models. All data is farm.project / farm.boq /\n'
        '  farm.job.order filtered by business_activity = "construction".\n\n'
        'MENU (clean, 3 items)\n'
        '  Dashboard  — Construction Executive Dashboard\n'
        '  Projects   — Gateway to all sub-workflows\n'
        '  Configuration — Divisions & Subdivisions reference data\n\n'
        'CONSTRUCTION DASHBOARD\n'
        '  Portfolio KPIs · Execution Progress · Project Phases ·\n'
        '  Stage Distribution · Department Breakdown\n\n'
        'PROJECT FORM TABS\n'
        '  Scope (BOQ) · Tasks · Materials · Procurement · Resources ·\n'
        '  Execution · Inspection · Claims · Financial · AI Insights\n\n'
        'AI DECISION ENGINE\n'
        '  construction.ai.insight — weighted risk scoring (delay, execution,\n'
        '  procurement, cost, claim) · smart KPI cards · daily cron automation\n'
    ),
    'category': 'Smart Farm',
    'author': 'bin-qadir',
    'license': 'LGPL-3',
    'depends': [
        'smart_farm_material_request',   # full Smart Farm engine chain (incl. execution, dashboard)
        'smart_farm_work_structure',     # Divisions / Subdivisions reference data
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/construction_dashboard_data.xml',
        'data/construction_cron.xml',
        'views/actions.xml',
        'views/construction_dashboard_views.xml',
        'views/construction_ai_insight_views.xml',
        'views/farm_boq_construction_views.xml',
        'views/farm_project_construction_views.xml',
        'views/farm_job_order_construction_inherit.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'smart_farm_construction/static/src/css/construction_dashboard.css',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
