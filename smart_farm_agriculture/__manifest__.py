{
    'name': 'Smart Farm — Agriculture',
    'version': '18.0.1.0.0',
    'summary': 'Agriculture Company — seasons, crop plans, field operations, harvest, packing',
    'description': (
        'Operational module for the Agriculture Company.\n\n'
        'Provides:\n'
        '• Agriculture Seasons (growing cycles)\n'
        '• Crop Plans (per field/season)\n'
        '• Field Operations (irrigation, fertilization, planting, treatment)\n'
        '• Harvest Records\n'
        '• Packing & Dispatch\n\n'
        'All records are company-scoped and tied to the agriculture lifecycle.\n'
        'AI decision layer: risk_score, delay_score, budget_risk, next_recommended_action.\n'
    ),
    'category': 'Smart Farm/Agriculture',
    'author': 'bin-qadir',
    'license': 'LGPL-3',
    'depends': [
        'smart_farm_base',
        'smart_farm_project',
        'smart_farm_master',
        'analytic',
        'mail',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/agriculture_data.xml',
        'views/agriculture_season_views.xml',
        'views/agriculture_crop_plan_views.xml',
        'views/agriculture_field_operation_views.xml',
        'views/agriculture_harvest_views.xml',
        'views/agriculture_packing_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
