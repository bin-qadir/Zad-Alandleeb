Updated Odoo 18 bundle

Included modules:
1) solar_installation
   - Renamed from the developer export folder so its internal XML/file references work correctly.
2) project_by_phases
   - Extracted as a standalone module.
3) projects_task_checklists
   - Extracted as a standalone module.
4) task_boq_advanced
   - Added BOQ, RFQ, quotation, costing, and AI alerts module built for Odoo 18.

Recommended install order:
1. project_by_phases
2. projects_task_checklists
3. solar_installation
4. task_boq_advanced

Important notes:
- Put these module folders directly inside your custom addons path.
- Update Apps List before installation.
- If your database uses a different XML ID for the task/project base forms,
  you may need a small adjustment in task_boq_advanced view inheritance.
- task_boq_advanced record rules assume project.task has user_ids.
  If your database uses user_id instead, adjust security/security.xml in that module.
