#!/usr/bin/env python3
"""Render track_sheet/application_tracker.csv as a colour-coded xlsx view at
track_sheet/application_tracker_colored.xlsx (CLAUDE.md step 5).

Colours, per CLAUDE.md:
    Match Score       green strong / yellow reasonable / red stretch or reject
    Coding Intensity  light blue Low / yellow Medium / red High
    Location          orange when in BC, else white
    Work Type         dark blue Remote / light blue Hybrid / white In-person
                      (an extra column derived from Location)
    Status            response statuses tinted so outcomes stand out

The CSV stays the source of truth; this file is regenerated, never hand-edited.
Rebuilt 2026-09-28 (the original was lost); standard library only, as
openpyxl isn't installed.
"""
import os
import zipfile
from xml.sax.saxutils import escape

import tracker

XLSX_PATH = os.path.join(tracker.BASE, "track_sheet", "application_tracker_colored.xlsx")
COLUMNS = tracker.FIELDNAMES[:4] + ["Work Type"] + tracker.FIELDNAMES[4:]
WIDTHS = {"Date Found": 12, "Company": 28, "Job Title": 42, "Location": 26, "Work Type": 11, "Salary": 22,
          "Requires Class 5 Licence": 14, "Match Score": 24, "Coding Intensity": 11, "Status": 22,
          "Resume Path": 44, "Cover Letter Path": 44, "Job URL": 44}

# Fill colours (ARGB). Position in this list = fill id in styles.xml (0 and 1 are required defaults).
FILLS = ["none", "gray125", "FF1F3864", "FFC6EFCE", "FFFFEB9C", "FFFFC7CE", "FFDDEBF7", "FFFFD8A8",
         "FF9DC3E6", "FFE2EFDA", "FFD9D2E9"]
DARK_BLUE, GREEN, YELLOW, RED, LIGHT_BLUE, ORANGE, HYBRID_BLUE, SOFT_GREEN, PURPLE = range(2, 11)

STATUS_FILL = {"Applied": SOFT_GREEN, "Interview Scheduled": GREEN, "Offer Received": GREEN,
               "Next Steps - Assessment": PURPLE, "Rejected by Employer": RED, "Apply Failed": ORANGE}


def fill_for(col, row):
    v = row.get(col, "")
    if col == "Match Score":
        return {"strong": GREEN, "reasonable": YELLOW, "stretch": RED, "reject": RED}.get(tracker.match_tier(v), 0)
    if col == "Coding Intensity":
        return {"low": LIGHT_BLUE, "medium": YELLOW, "high": RED}.get(v.strip().lower(), 0)
    if col == "Location":
        return ORANGE if tracker.is_bc(v) else 0
    if col == "Work Type":
        return {"Remote": DARK_BLUE, "Hybrid": HYBRID_BLUE}.get(v, 0)
    if col == "Status":
        return STATUS_FILL.get(v, 0)
    return 0


def style_id(fill, header=False):
    """cellXfs index: 0 plain, 1 header, then one per fill (the dark blue one gets white text)."""
    return 1 if header else 2 + fill


def styles_xml():
    fills = []
    for f in FILLS:
        if f in ("none", "gray125"):
            fills.append(f'<fill><patternFill patternType="{f}"/></fill>')
        else:
            fills.append(f'<fill><patternFill patternType="solid"><fgColor rgb="{f}"/><bgColor indexed="64"/></patternFill></fill>')
    xfs = ['<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>',
           '<xf numFmtId="0" fontId="1" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1"/>']
    for i in range(len(FILLS)):
        font = 2 if i == DARK_BLUE else 0
        xfs.append(f'<xf numFmtId="0" fontId="{font}" fillId="{i}" borderId="0" xfId="0" applyFill="1" applyFont="1"/>')
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="3"><font><sz val="11"/><name val="Calibri"/></font>'
            '<font><b/><sz val="11"/><name val="Calibri"/></font>'
            '<font><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font></fonts>'
            f'<fills count="{len(fills)}">{"".join(fills)}</fills>'
            '<borders count="2"><border/><border><bottom style="medium"><color rgb="FF000000"/></bottom></border></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            f'<cellXfs count="{len(xfs)}">{"".join(xfs)}</cellXfs>'
            '</styleSheet>')


def col_letter(i):
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def cell(ref, value, style):
    return f'<c r="{ref}" t="inlineStr" s="{style}"><is><t xml:space="preserve">{escape(str(value))}</t></is></c>'


def sheet_xml(rows):
    cols = "".join(f'<col min="{i + 1}" max="{i + 1}" width="{WIDTHS.get(c, 16)}" customWidth="1"/>'
                   for i, c in enumerate(COLUMNS))
    out = ['<row r="1">' + "".join(cell(f"{col_letter(i)}1", c, style_id(0, header=True))
                                   for i, c in enumerate(COLUMNS)) + "</row>"]
    for n, row in enumerate(rows, start=2):
        row = dict(row, **{"Work Type": tracker.work_type(row["Location"])})
        cells = [cell(f"{col_letter(i)}{n}", row.get(c, ""), style_id(fill_for(c, row))) for i, c in enumerate(COLUMNS)]
        out.append(f'<row r="{n}">{"".join(cells)}</row>')
    last = f"{col_letter(len(COLUMNS) - 1)}{max(1, len(rows) + 1)}"
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
            f'<cols>{cols}</cols><sheetData>{"".join(out)}</sheetData>'
            f'<autoFilter ref="A1:{last}"/></worksheet>')


def main():
    rows = tracker.read_rows()
    os.makedirs(os.path.dirname(XLSX_PATH), exist_ok=True)
    tmp = XLSX_PATH + ".tmp"
    last = f"${col_letter(len(COLUMNS) - 1)}${max(1, len(rows) + 1)}"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                   '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                   '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
                   '</Types>')
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                   '</Relationships>')
        z.writestr("xl/workbook.xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                   '<sheets><sheet name="Applications" sheetId="1" r:id="rId1"/></sheets>'
                   '<definedNames><definedName name="_xlnm._FilterDatabase" localSheetId="0" hidden="1">'
                   f'Applications!$A$1:{last}</definedName></definedNames></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
                   '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                   '</Relationships>')
        z.writestr("xl/styles.xml", styles_xml())
        z.writestr("xl/worksheets/sheet1.xml", sheet_xml(rows))
    os.replace(tmp, XLSX_PATH)
    print(f"Wrote {os.path.relpath(XLSX_PATH, tracker.BASE)} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
