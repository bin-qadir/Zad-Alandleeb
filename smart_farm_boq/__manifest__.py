{
    'name': 'Smart Farm BOQ',
    'version': '18.0.2.2.0',
    'summary': 'Bill of Quantities for the Smart Farm system',
    'description': (
        'Manage BOQ documents with template loading, manual entry, '
        'hierarchical auto-numbering, and revision tracking.'
    ),
    'category': 'Agriculture',
    'author': 'Smart Farm',
    'license': 'LGPL-3',
    'depends': [
        'smart_farm_base',
        'smart_farm_master',
        'smart_farm_project',
        'smart_farm_work_structure',
        'uom',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/sequences.xml',
        'data/project_phase_data.xml',
        'reports/farm_boq_report.xml',
        'views/farm_boq_division_cleanup.xml',
        'views/farm_boq_views.xml',
        'views/farm_boq_template_views.xml',
        'views/farm_boq_line_views.xml',
        'views/farm_boq_wizard_views.xml',
        'views/farm_boq_add_structure_wizard_views.xml',
        'views/farm_boq_print_wizard_views.xml',
        'views/farm_boq_excel_import_wizard_views.xml',
        'views/farm_project_views_inherit.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'smart_farm_boq/static/src/css/boq.css',
            'smart_farm_boq/static/src/css/boq_chatter.css',
            'smart_farm_boq/static/src/js/boq_chatter_toggle.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
