{
    'name': 'Smart Farm — Livestock',
    'version': '18.0.1.0.0',
    'summary': 'Livestock Company — herds, animals, breeding, health, feeding, sales',
    'description': (
        'Operational module for the Livestock Company.\n\n'
        'Provides:\n'
        '• Herd Management\n'
        '• Animal Records\n'
        '• Breeding Records\n'
        '• Health Checks\n'
        '• Feeding Plans\n'
        '• Livestock Sales\n\n'
        'All records are company-scoped and tied to the livestock lifecycle.\n'
        'AI decision layer: risk_score, delay_score, budget_risk, next_recommended_action.\n'
    ),
    'category': 'Smart Farm/Livestock',
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
        'data/livestock_data.xml',
        'views/livestock_herd_views.xml',
        'views/livestock_animal_views.xml',
        'views/livestock_health_check_views.xml',
        'views/livestock_feeding_plan_views.xml',
        'views/livestock_sale_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
