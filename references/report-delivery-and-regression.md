## PDF & Chart Report Workflow Lessons

### Telegram PDF Delivery (User-Corrected Convention)
- User has zero tolerance for any explanatory text, file paths, or "ready" messages when delivering PDFs.
- Final response MUST contain ONLY the native attachment: `MEDIA:/absolute/path/to/pdf`
- No surrounding prose, no "here is the report", no summary — instant attachment only in the current Telegram topic.
- This rule was reinforced multiple times after repeated delivery failures. Embed it in every PDF/report workflow.

### Regression Testing Discipline (User-Required)
- Every change to pdf_report.py, charts.py, weed_the_garden.py, or table layout must be followed by:
  `pytest tests/test_pdf_report_regression.py -q`
- Tests cover chart generation, PDF creation, and column name robustness.
- Purpose: Prevent breaking working charts/tables when making other improvements.

### Pitfall to Avoid
- Do not modify report generation logic without running the regression suite first.
- Brittle CSV parsers in charts.py are a common source of regressions — always use csv.DictReader + flexible column matching.