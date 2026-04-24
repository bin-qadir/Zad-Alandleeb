{
    'name': 'Smart Farm — Manufacturing',
    'version': '18.0.1.0.0',
    'summary': 'Manufacturing Company — production planning, work orders, QC, dispatch',
    'description': (
        'Operational module for the Manufacturing / Packing Company.\n\n'
        'Provides:\n'
        '• Production Plans\n'
        '• Work Orders (manufacturing runs)\n'
        '• Quality Control Checks\n'
        '• Finished Goods & Dispatch\n\n'
        'All records are company-scoped and tied to the manufacturing lifecycle.\n'
        'AI decision layer: risk_score, delay_score, budget_risk, next_recommended_action.\n'
    ),
    'category': 'Smart Farm/Manufacturing',
    'author': 'bin-qadir',
    'license': 'LGPL-3',
    'depends': [
        'smart_farm_base',
        'smart_farm_project',
        'smart_farm_master',
        'analytic',
        'mail',
        'uom',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/manufacturing_data.xml',
        'views/manufacturing_plan_views.xml',
        'views/manufacturing_work_order_views.xml',
        'views/manufacturing_qc_check_views.xml',
        'views/manufacturing_dispatch_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
