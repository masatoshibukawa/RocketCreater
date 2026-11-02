"""Design report (Markdown/JSON) and bill-of-materials CSV export. Implemented in phase 3."""

from rocketwright.schema import Design, SimResult


def export_report_markdown(design: Design, result: SimResult) -> str:
    raise NotImplementedError("report.export_report_markdown: implemented in phase 3")


def export_bom_csv(design: Design) -> str:
    raise NotImplementedError("report.export_bom_csv: implemented in phase 3")
