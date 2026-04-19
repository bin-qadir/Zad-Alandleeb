{
    'name': 'Smart Farm Sale Contract',
    'version': '18.0.1.0.0',
    'summary': 'Sales Order as the approved contract backbone for Job Order execution',
    'description': (
        'Transforms the Smart Farm execution pipeline into an enterprise EPC/\n'
        'construction ERP flow:\n\n'
        '1. BOQ Analysis = planning + pricing ONLY (Generate JO button hidden)\n'
        '2. Sales Order = commercial contract backbone with dedicated approval\n'
        '   workflow (contract_stage: new → in_progress → submitted → approved)\n'
        '3. Job Orders generated ONLY from an Approved Sales Order line\n'
        '4. Full traceability: SO Line → BOQ Analysis Line → BOQ Subitem → JO\n'
        '5. Project cost control: Estimated / Contract Value / Actual / Variance\n'
        '6. Project.task linked to Job Order for Odoo task management\n\n'
        'Phase gate update:\n'
        '  Pre-Tender → Tender → Contract → Execution\n'
        '  Execution gate: approved farm.contract OR approved sale.order\n'
    ),
    'category': 'Agriculture',
    'author': 'Smart Farm',
    'license': 'LGPL-3',
    'depends': [
        'smart_farm_contract',   # farm.contract + project_phase gate
        'sale_management',       # sale.order + sale.order.line
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/sale_order_views_inherit.xml',
        'views/farm_boq_analysis_views_inherit.xml',
        'views/farm_job_order_views_inherit.xml',
        'views/farm_project_views_inherit.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
