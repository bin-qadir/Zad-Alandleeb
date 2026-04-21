{
    'name': 'Smart Farm Executive Dashboard',
    'version': '18.0.1.0.0',
    'summary': 'PMO portfolio dashboard: phase distribution, KPIs, health, financials',
    'description': (
        'Executive / PMO visibility layer for Smart Farm:\n\n'
        '1. PROJECT HEALTH ENGINE\n'
        '   Computed health (healthy / warning / critical) on every project.\n'
        '   Based on projected profit, gross margin %, commitment level.\n\n'
        '2. EXECUTIVE DASHBOARD\n'
        '   Singleton dashboard with real-time aggregated KPIs.\n'
        '   Portfolio phase distribution, health counts, full financial summary.\n\n'
        '3. DRILL-DOWN ACTIONS\n'
        '   One-click filtered project lists for every phase and health state.\n'
        '   Critical / Warning / Over-Budget / Negative-Profit / Execution lists.\n\n'
        '4. MANAGEMENT ENHANCEMENTS\n'
        '   Health badge in project list view.\n'
        '   Over-budget and negative-profit flags on every project.\n'
    ),
    'category': 'Agriculture',
    'author': 'Smart Farm',
    'license': 'LGPL-3',
    'depends': [
        'smart_farm_control',     # cost fields, phase engine, has_approved_contract
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/farm_project_health_views.xml',
        'views/farm_dashboard_views.xml',
        'views/farm_activity_dashboard_views.xml',
        'views/farm_civil_dashboard_views.xml',
        'views/farm_construction_projects_dashboard_views.xml',
        'views/farm_construction_project_dashboard_views.xml',
        'views/analytics_actions.xml',   # client action must precede menu
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            # Executive PMO cockpit styles
            'smart_farm_dashboard/static/src/css/farm_dashboard.css',
            # Activity-specific dashboard styles
            'smart_farm_dashboard/static/src/css/activity_dashboard.css',
            # Analytics dashboard (Owl + Chart.js)
            'smart_farm_dashboard/static/src/css/analytics_dashboard.css',
            'smart_farm_dashboard/static/src/xml/analytics_dashboard.xml',
            'smart_farm_dashboard/static/src/js/analytics_dashboard.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
