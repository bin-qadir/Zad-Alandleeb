{
    'name': 'Smart Farm BOQ Analysis',
    'version': '18.0.1.1.0',
    'summary': 'Professional BOQ analysis: cost comparison, pricing strategy, approval workflow',
    'description': (
        'Owns all pricing fields on farm.boq.line (unit_price, cost_total, '
        'total, profit, margin) and drives them from approved analysis records. '
        'Adds per-line analysis workflow, document-level B.O.Q Analysis screen, '
        'and injects pricing columns into the BOQ structure list view.'
    ),
    'category': 'Agriculture',
    'author': 'Smart Farm',
    'license': 'LGPL-3',
    'depends': [
        'smart_farm_base',
        'smart_farm_master',
        'smart_farm_boq',
        'smart_farm_costing',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/farm_boq_line_analysis_views.xml',
        'views/farm_boq_line_views_inherit.xml',
        'views/farm_boq_form_inherit.xml',
        'views/farm_boq_doc_analysis_views.xml',
        'views/farm_boq_form_doc_analysis_inherit.xml',
        'views/farm_project_views_inherit.xml',
        'reports/farm_boq_analysis_report.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'smart_farm_boq_analysis/static/src/css/boq_analysis.css',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
