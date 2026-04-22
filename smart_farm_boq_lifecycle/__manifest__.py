{
    'name': 'Smart Farm — BOQ Lifecycle Tracking',
    'version': '18.0.1.0.0',
    'summary': 'Full quantity lifecycle tracking across procurement, inspection, and claims',
    'category': 'Construction',
    'author': 'Smart Farm',
    'license': 'LGPL-3',
    'depends': [
        'smart_farm_boq_analysis',
        'smart_farm_execution',
        'smart_farm_procurement',
        'smart_farm_material_request',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/farm_boq_lifecycle_views.xml',
        'views/farm_boq_analysis_form_inherit.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
