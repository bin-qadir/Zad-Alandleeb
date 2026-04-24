{
    'name': 'Smart Farm Holding — Enterprise Platform',
    'version': '18.0.1.0.0',
    'summary': (
        'SAP/Oracle-style master holding platform — '
        'company setup, unified dashboard, enterprise security, record rules'
    ),
    'description': (
        'Smart Farm Holding — Enterprise Master Platform\n\n'
        'The master holding module that governs the entire Smart Farm enterprise.\n\n'
        '1. HOLDING COMPANY SETUP\n'
        '   Company Activity Configuration — maps companies to activities.\n'
        '   Parent/child company hierarchy (Holding → Construction / Agriculture /\n'
        '   Manufacturing / Livestock).\n\n'
        '2. ENTERPRISE SECURITY ARCHITECTURE\n'
        '   • Holding Manager — sees ALL companies and ALL data\n'
        '   • Activity Company Manager — sees their company only\n'
        '   • Activity User — sees their assigned records\n'
        '   • Finance User — cross-company financial read access\n'
        '   • Procurement User — procurement across companies\n'
        '   • Project Control User — project control view\n\n'
        '3. RECORD RULES — DATA ISOLATION\n'
        '   Company-scoped rules on all operational models.\n'
        '   Holding Manager bypasses all rules.\n\n'
        '4. HOLDING EXECUTIVE DASHBOARD\n'
        '   Aggregated KPIs across all companies and activities.\n'
        '   Risk summary, lifecycle distribution, procurement overview.\n\n'
        '5. MENU VISIBILITY ENGINE\n'
        '   Smart Farm Configuration → Company Activity Setup.\n'
        '   Controls which menus each company sees.\n'
    ),
    'category': 'Smart Farm',
    'author': 'bin-qadir',
    'license': 'LGPL-3',
    'depends': [
        'smart_farm_base',
        'smart_farm_project',
        'construction_project',
        'smart_farm_agriculture',
        'smart_farm_manufacturing',
        'smart_farm_livestock',
    ],
    'data': [
        'security/security.xml',
        'security/record_rules.xml',
        'security/ir.model.access.csv',
        'data/holding_data.xml',
        'views/company_activity_views.xml',
        'views/holding_dashboard_views.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'smart_farm_holding/static/src/css/holding_dashboard.css',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
