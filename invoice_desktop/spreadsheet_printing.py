"""通过独立Excel实例把工作簿排版为A5 PDF，统一使用现有打印机队列。"""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path

import fitz


def render_excel_to_pdf(excel_path: Path, pdf_path: Path) -> Path:
    import pythoncom
    from win32com.client import DispatchEx

    if not excel_path.is_file():
        raise FileNotFoundError(f"未找到私车公用Excel：{excel_path}")
    application = workbook = sheet = setup = None
    pythoncom.CoInitialize()
    try:
        try:
            # DispatchEx不复用用户已打开的Excel，不切换用户的默认打印机。
            application = DispatchEx("Excel.Application")
        except Exception as exc:
            raise RuntimeError("私车Excel打印需要本机安装Microsoft Excel且可正常启动。未发送任何打印任务。") from exc
        application.Visible = False
        application.DisplayAlerts = False
        application.AskToUpdateLinks = False
        application.AutomationSecurity = 3  # msoAutomationSecurityForceDisable
        workbook = application.Workbooks.Open(Filename=str(excel_path.resolve()), UpdateLinks=0, ReadOnly=True)
        for sheet in workbook.Worksheets:
            setup = sheet.PageSetup
            setup.PrintArea = "$B$1:$K$26"
            setup.PaperSize = 11  # xlPaperA5
            setup.Orientation = 2  # xlLandscape
            setup.Zoom = False
            setup.FitToPagesWide = 1
            setup.FitToPagesTall = 1
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        workbook.ExportAsFixedFormat(Type=0, Filename=str(pdf_path.resolve()),
                                     Quality=0, IgnorePrintAreas=False, OpenAfterPublish=False)
        if not pdf_path.is_file():
            raise RuntimeError("Excel未能生成私车公用打印文件，未发送任何打印任务。")
        with fitz.open(pdf_path) as document:
            if len(document) == 0:
                raise RuntimeError("私车公用打印文件为空，未发送任何打印任务。")
        return pdf_path
    finally:
        # 即使排版失败，也只关闭本次独立实例，不影响用户其他Excel窗口。
        setup = sheet = None
        if workbook is not None:
            with suppress(Exception):
                workbook.Close(SaveChanges=False)
        workbook = None
        if application is not None:
            with suppress(Exception):
                application.Quit()
        application = None
        pythoncom.CoUninitialize()