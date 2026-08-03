"""PDF generator for Certificate of Analysis (CoA). Two formats:
- modern (default): the current YLMS layout
- standard: bilingual ES/EN, more classic laboratory certificate look
"""
import io
import os
import qrcode
from datetime import datetime
from typing import Optional
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT

BRAND_AMBER = colors.HexColor("#DCA54C")
BRAND_DARK = colors.HexColor("#1A120E")
GRAY_LIGHT = colors.HexColor("#F5F2ED")
GRAY_BORDER = colors.HexColor("#E6E2DC")
STATUS_SUCCESS = colors.HexColor("#4A5D23")
STATUS_ERROR = colors.HexColor("#8B1E1E")

LOGO_PATH = os.path.join(os.path.dirname(__file__), "assets", "yazoo-logo.png")


def _logo_image(width_mm: float = 22):
    if os.path.exists(LOGO_PATH):
        return Image(LOGO_PATH, width=width_mm * mm, height=width_mm * mm)
    return None


def _make_qr(data: str) -> Image:
    qr = qrcode.QRCode(box_size=4, border=1)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return Image(buf, width=30 * mm, height=30 * mm)


# ---------------- MODERN FORMAT (default) ----------------

def _generate_modern(coa: dict, sample: dict, product: dict, executions: list, signer: dict) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
        title=f"CoA {coa.get('coa_number', '')}",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("t", parent=styles["Heading1"], fontName="Helvetica-Bold",
                                  fontSize=18, textColor=BRAND_DARK, alignment=TA_LEFT, spaceAfter=2)
    sub_style = ParagraphStyle("s", parent=styles["Normal"], fontName="Helvetica",
                                fontSize=9, textColor=colors.HexColor("#5C5046"))
    h2_style = ParagraphStyle("h2", parent=styles["Heading2"], fontName="Helvetica-Bold",
                               fontSize=11, textColor=BRAND_DARK, spaceBefore=8, spaceAfter=4)
    body_style = ParagraphStyle("b", parent=styles["Normal"], fontName="Helvetica",
                                fontSize=9, textColor=BRAND_DARK)
    small_style = ParagraphStyle("small", parent=styles["Normal"], fontName="Helvetica",
                                  fontSize=7.5, textColor=colors.HexColor("#5C5046"))

    story = []
    header_left = [
        Paragraph("<b>RONES Y BEBIDAS DEL CARIBE YAZOO</b>", title_style),
        Paragraph("Laboratorio de Control de Calidad", sub_style),
        Paragraph("<i>Envejecemos y Envasamos Calidad</i>", small_style),
        Paragraph("YLMS – Yazoo Laboratory Management System", small_style),
    ]
    qr_data = f"CoA:{coa.get('coa_number')}|Sample:{sample.get('code')}|Date:{coa.get('issued_at','')}"
    qr_img = _make_qr(qr_data)
    logo = _logo_image(22)
    logo_cell = logo if logo else Paragraph("", small_style)
    header_tbl = Table([[logo_cell, header_left, qr_img]], colWidths=[26 * mm, 110 * mm, 34 * mm])
    header_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (1, 0), (1, 0), 8),
    ]))
    story.append(header_tbl)
    story.append(Spacer(1, 6))

    bar = Table([[""]], colWidths=[174 * mm], rowHeights=[3])
    bar.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), BRAND_AMBER)]))
    story.append(bar)
    story.append(Spacer(1, 8))

    story.append(Paragraph(
        f"<b>CERTIFICADO DE ANÁLISIS N° {coa.get('coa_number', '')}</b>",
        ParagraphStyle("coa_title", parent=styles["Heading1"], fontSize=13,
                       textColor=BRAND_DARK, alignment=TA_CENTER),
    ))
    story.append(Spacer(1, 8))

    info_data = [
        ["Código de Muestra", sample.get("code", "—"), "Fecha de Emisión", coa.get("issued_at", "—")[:10]],
        ["Producto", product.get("name", "—"), "Tipo", product.get("type", "—")],
        ["Lote", sample.get("batch_number", "—"), "Tanque / Barrica", f"{sample.get('tank','—')} / {sample.get('barrel','—')}"],
        ["Proveedor", sample.get("provider", "—"), "Volumen", f"{sample.get('volume','—')} L"],
        ["Recibido por", sample.get("received_by_name", "—"), "Fecha Recepción", str(sample.get("reception_date", "—"))[:10]],
    ]
    info_tbl = Table(info_data, colWidths=[35 * mm, 55 * mm, 30 * mm, 54 * mm])
    info_tbl.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 8.5),
        ("BACKGROUND", (0, 0), (0, -1), GRAY_LIGHT),
        ("BACKGROUND", (2, 0), (2, -1), GRAY_LIGHT),
        ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 8.5),
        ("FONT", (2, 0), (2, -1), "Helvetica-Bold", 8.5),
        ("TEXTCOLOR", (0, 0), (-1, -1), BRAND_DARK),
        ("GRID", (0, 0), (-1, -1), 0.4, GRAY_BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(info_tbl)
    story.append(Spacer(1, 10))

    story.append(Paragraph("<b>Resultados de Análisis</b>", h2_style))
    rows = [["#", "Parámetro", "Método", "Resultado", "Unidad", "Mín", "Máx", "Cumple"]]
    for i, ex in enumerate(executions, 1):
        meets = ex.get("meets_spec")
        meets_txt = "SÍ" if meets else ("NO" if meets is False else "—")
        rows.append([
            str(i), ex.get("test_name", "—"), ex.get("method", "—"),
            str(ex.get("calculated_value", "—")), ex.get("unit", "—"),
            str(ex.get("min_limit", "—")), str(ex.get("max_limit", "—")), meets_txt,
        ])
    results_tbl = Table(rows, colWidths=[8*mm, 44*mm, 28*mm, 24*mm, 16*mm, 20*mm, 20*mm, 14*mm], repeatRows=1)
    ts = [
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_DARK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 8),
        ("GRID", (0, 0), (-1, -1), 0.4, GRAY_BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (3, 1), (7, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    for i, ex in enumerate(executions, 1):
        meets = ex.get("meets_spec")
        if meets is True:
            ts.append(("TEXTCOLOR", (7, i), (7, i), STATUS_SUCCESS))
            ts.append(("FONT", (7, i), (7, i), "Helvetica-Bold", 8))
        elif meets is False:
            # Out-of-spec → highlight Result + Complies with red bg
            ts.append(("BACKGROUND", (3, i), (3, i), colors.HexColor("#FCE8E8")))
            ts.append(("BACKGROUND", (7, i), (7, i), colors.HexColor("#FCE8E8")))
            ts.append(("TEXTCOLOR", (3, i), (3, i), STATUS_ERROR))
            ts.append(("TEXTCOLOR", (7, i), (7, i), STATUS_ERROR))
            ts.append(("FONT", (3, i), (3, i), "Helvetica-Bold", 8))
            ts.append(("FONT", (7, i), (7, i), "Helvetica-Bold", 8))
    results_tbl.setStyle(TableStyle(ts))
    story.append(results_tbl)
    story.append(Spacer(1, 10))

    conclusion = coa.get("conclusion") or (
        "APROBADO – El lote cumple con las especificaciones técnicas."
        if coa.get("decision") == "released"
        else "RECHAZADO – El lote no cumple con las especificaciones técnicas."
    )
    decision = coa.get("decision", "released")
    decision_color = STATUS_SUCCESS if decision == "released" else STATUS_ERROR
    concl_style = ParagraphStyle("concl", parent=styles["Normal"], fontName="Helvetica-Bold",
                                  fontSize=10, textColor=decision_color, alignment=TA_LEFT)
    story.append(Paragraph("<b>Conclusión</b>", h2_style))
    story.append(Paragraph(conclusion, concl_style))
    story.append(Spacer(1, 12))

    if coa.get("observations"):
        story.append(Paragraph("<b>Observaciones</b>", h2_style))
        story.append(Paragraph(coa.get("observations"), body_style))
        story.append(Spacer(1, 8))

    story.append(Spacer(1, 20))
    sig_data = [
        ["_" * 32, "_" * 32],
        [signer.get("name", "—"), "Gerencia de Calidad"],
        [f"{signer.get('role_label', signer.get('role', '—'))}", "Firma / Sello"],
        [f"Firmado digitalmente: {coa.get('issued_at','')[:19]}", ""],
    ]
    sig_tbl = Table(sig_data, colWidths=[85 * mm, 85 * mm])
    sig_tbl.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 8.5),
        ("FONT", (0, 1), (-1, 1), "Helvetica-Bold", 9),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TEXTCOLOR", (0, 0), (-1, -1), BRAND_DARK),
    ]))
    story.append(sig_tbl)
    story.append(Spacer(1, 12))

    footer = Paragraph(
        "Este documento fue emitido electrónicamente por YLMS. Verifique su autenticidad mediante el código QR. "
        "Cumple con ISO/IEC 17025, ISO 9001 y HACCP.",
        small_style,
    )
    story.append(footer)

    doc.build(story)
    buffer.seek(0)
    return buffer.read()


# ---------------- STANDARD FORMAT (bilingual ES/EN, classic) ----------------

def _generate_standard(coa: dict, sample: dict, product: dict, executions: list, signer: dict) -> bytes:
    """Y-FO-CC-013 · Certificate of Analysis (bilingual ES/EN), classic laboratory template.

    Layout:
    - Header: logo | company block | document control (Código, Versión, Fecha, Página)
    - Title band: CERTIFICADO DE ANÁLISIS / CERTIFICATE OF ANALYSIS + N°
    - Sample/product info as two-column bilingual grid
    - Results table: Parámetro/Parameter | Método/Method | Especificación/Spec.
                    | Resultado/Result | Unidad/Unit | Cumple/Complies
      → Out-of-spec rows highlighted in red across Result + Complies cells
    - Conclusion (bilingual), observations, signature block, regulatory footer with RNC.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=14 * mm, rightMargin=14 * mm,
        topMargin=10 * mm, bottomMargin=12 * mm,
        title=f"Y-FO-CC-013 Certificate of Analysis {coa.get('coa_number', '')}",
    )
    styles = getSampleStyleSheet()
    ttl_es = ParagraphStyle("t_es", parent=styles["Heading1"], fontName="Times-Bold",
                            fontSize=13, textColor=BRAND_DARK, alignment=TA_CENTER, spaceAfter=0)
    ttl_en = ParagraphStyle("t_en", parent=styles["Heading2"], fontName="Times-Italic",
                            fontSize=10.5, textColor=colors.HexColor("#5C5046"), alignment=TA_CENTER)
    body = ParagraphStyle("b", parent=styles["Normal"], fontName="Times-Roman", fontSize=9.2, textColor=BRAND_DARK)
    body_b = ParagraphStyle("bb", parent=body, fontName="Times-Bold")
    small = ParagraphStyle("s", parent=styles["Normal"], fontName="Times-Roman", fontSize=7.5, textColor=colors.HexColor("#5C5046"))
    small_c = ParagraphStyle("sc", parent=small, alignment=TA_CENTER)
    story = []

    # ---------- Header: logo | company | document control ----------
    logo = _logo_image(22)
    logo_cell = logo if logo else Paragraph("<b>YAZOO</b>", ParagraphStyle("logox", parent=body, alignment=TA_CENTER, fontSize=14))
    company_block = [
        Paragraph("<b>RONES Y BEBIDAS DEL CARIBE YAZOO, S.R.L.</b>",
                  ParagraphStyle("co", parent=body, fontName="Times-Bold", fontSize=10.5, alignment=TA_CENTER)),
        Paragraph("<i>Yazoo Rums &amp; Caribbean Beverages</i>",
                  ParagraphStyle("co2", parent=body, fontName="Times-Italic", fontSize=9, alignment=TA_CENTER)),
        Paragraph("Laboratorio de Control de Calidad · Quality Control Laboratory", small_c),
        Paragraph("RNC 1-31-45678-9 · Rep. Dominicana", small_c),
    ]
    issued_date = str(coa.get("issued_at", ""))[:10] or "—"
    doc_control = [
        ["Código / Code", "Y-FO-CC-013"],
        ["Versión / Version", coa.get("template_version", "01")],
        ["Fecha / Date", issued_date],
        ["Página / Page", "1 de 1"],
    ]
    ctrl_tbl = Table(doc_control, colWidths=[22 * mm, 22 * mm])
    ctrl_tbl.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Times-Roman", 7.5),
        ("FONT", (0, 0), (0, -1), "Times-Bold", 7.5),
        ("BACKGROUND", (0, 0), (0, -1), GRAY_LIGHT),
        ("GRID", (0, 0), (-1, -1), 0.4, BRAND_DARK),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    header_tbl = Table([[logo_cell, company_block, ctrl_tbl]],
                       colWidths=[26 * mm, 110 * mm, 46 * mm])
    header_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.6, BRAND_DARK),
        ("LINEBEFORE", (1, 0), (1, 0), 0.4, BRAND_DARK),
        ("LINEBEFORE", (2, 0), (2, 0), 0.4, BRAND_DARK),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(header_tbl)
    story.append(Spacer(1, 6))

    # ---------- Title band ----------
    story.append(Paragraph("CERTIFICADO DE ANÁLISIS", ttl_es))
    story.append(Paragraph("CERTIFICATE OF ANALYSIS", ttl_en))
    story.append(Paragraph(f"N° {coa.get('coa_number', '')}",
                            ParagraphStyle("num", parent=body, alignment=TA_CENTER, fontSize=10.5,
                                            fontName="Times-Bold", textColor=BRAND_DARK)))
    story.append(Spacer(1, 8))

    # ---------- Sample & product info (bilingual grid) ----------
    def _cell(es_label, en_label, value):
        p = Paragraph(f"<b>{es_label}</b> <font size=7 color='#5C5046'><i>/ {en_label}</i></font><br/>{value or '—'}",
                      ParagraphStyle("cellx", parent=body, fontSize=8.5))
        return p

    info_rows = [
        [_cell("Producto", "Product", product.get("name")),
         _cell("Tipo", "Type", product.get("type"))],
        [_cell("Lote", "Batch No.", sample.get("batch_number")),
         _cell("Código de Muestra", "Sample Code", sample.get("code"))],
        [_cell("Tanque / Barrica", "Tank / Barrel",
               f"{sample.get('tank') or '—'} / {sample.get('barrel') or '—'}"),
         _cell("Volumen", "Volume",
               f"{sample.get('volume', '—')} {sample.get('volume_unit', 'L')}")],
        [_cell("Proveedor", "Supplier", sample.get("provider")),
         _cell("Recibido por", "Received by", sample.get("received_by_name"))],
        [_cell("Fecha de Recepción", "Reception Date",
               str(sample.get("reception_date", "—"))[:10]),
         _cell("Fecha de Emisión", "Issue Date",
               str(coa.get("issued_at", "—"))[:10])],
    ]
    info_tbl = Table(info_rows, colWidths=[91 * mm, 91 * mm])
    info_tbl.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, BRAND_DARK),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(info_tbl)
    story.append(Spacer(1, 10))

    # ---------- Results table ----------
    story.append(Paragraph("<b>Resultados de Análisis / Analytical Results</b>",
                            ParagraphStyle("h3", parent=body, fontName="Times-Bold",
                                            fontSize=10.5, textColor=BRAND_DARK)))
    story.append(Spacer(1, 4))
    rows = [[
        "Parámetro\nParameter", "Método\nMethod",
        "Especificación\nSpecification", "Resultado\nResult",
        "Unidad\nUnit", "Cumple\nComplies",
    ]]
    for ex in executions:
        meets = ex.get("meets_spec")
        meets_txt = "SÍ / YES" if meets is True else ("NO / NO" if meets is False else "—")
        min_l, max_l = ex.get("min_limit"), ex.get("max_limit")
        if min_l is not None and max_l is not None:
            spec = f"{min_l} — {max_l}"
        elif min_l is not None:
            spec = f"≥ {min_l}"
        elif max_l is not None:
            spec = f"≤ {max_l}"
        else:
            spec = "—"
        rows.append([
            ex.get("test_name", "—"),
            ex.get("method", "—"),
            spec,
            str(ex.get("calculated_value", "—")),
            ex.get("unit", "—"),
            meets_txt,
        ])
    res_tbl = Table(rows, colWidths=[46 * mm, 30 * mm, 28 * mm, 26 * mm, 18 * mm, 34 * mm], repeatRows=1)
    ts = [
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_DARK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONT", (0, 0), (-1, 0), "Times-Bold", 8.5),
        ("FONT", (0, 1), (-1, -1), "Times-Roman", 9),
        ("GRID", (0, 0), (-1, -1), 0.4, BRAND_DARK),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (2, 1), (5, -1), "CENTER"),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    for i, ex in enumerate(executions, 1):
        meets = ex.get("meets_spec")
        if meets is True:
            ts.append(("TEXTCOLOR", (5, i), (5, i), STATUS_SUCCESS))
            ts.append(("FONT", (5, i), (5, i), "Times-Bold", 9))
        elif meets is False:
            # Out-of-spec: paint Result + Complies cells red with light red background
            ts.append(("TEXTCOLOR", (3, i), (5, i), STATUS_ERROR))
            ts.append(("BACKGROUND", (3, i), (5, i), colors.HexColor("#FCE8E8")))
            ts.append(("FONT", (3, i), (3, i), "Times-Bold", 9))
            ts.append(("FONT", (5, i), (5, i), "Times-Bold", 9))
    res_tbl.setStyle(TableStyle(ts))
    story.append(res_tbl)
    story.append(Spacer(1, 10))

    # ---------- Conclusion ----------
    decision = coa.get("decision", "released")
    decision_color = STATUS_SUCCESS if decision == "released" else STATUS_ERROR
    conclusion_es = coa.get("conclusion") or (
        "APROBADO – El lote cumple con las especificaciones técnicas."
        if decision == "released"
        else "RECHAZADO – El lote NO cumple con las especificaciones técnicas."
    )
    conclusion_en = (
        "APPROVED – The batch meets the technical specifications."
        if decision == "released"
        else "REJECTED – The batch does NOT meet the technical specifications."
    )
    story.append(Paragraph("<b>Conclusión / Conclusion</b>",
                            ParagraphStyle("cc", parent=body, fontName="Times-Bold",
                                            fontSize=10.5, textColor=BRAND_DARK)))
    story.append(Paragraph(conclusion_es,
                            ParagraphStyle("cs", parent=body, fontName="Times-Bold",
                                            textColor=decision_color, fontSize=10)))
    story.append(Paragraph(conclusion_en,
                            ParagraphStyle("cs2", parent=body, fontName="Times-Italic",
                                            textColor=decision_color, fontSize=9.5)))
    story.append(Spacer(1, 10))

    if coa.get("observations"):
        story.append(Paragraph("<b>Observaciones / Remarks</b>",
                                ParagraphStyle("obs", parent=body, fontName="Times-Bold", fontSize=10)))
        story.append(Paragraph(coa.get("observations"), body))
        story.append(Spacer(1, 8))

    # ---------- Signature block (with embedded signature image if available) ----------
    story.append(Spacer(1, 16))
    from routers.signatures import signature_file_path
    sig_img_path = signature_file_path(signer.get("id")) if signer else None
    sig_visual = Paragraph("_" * 34, body)
    if sig_img_path:
        try:
            sig_visual = Image(str(sig_img_path), width=55 * mm, height=18 * mm, kind='proportional')
        except Exception:
            pass
    qr_img = _make_qr(f"CoA:{coa.get('coa_number')}|Sample:{sample.get('code')}|Signed:{coa.get('issued_at','')}")
    sig_tbl = Table([
        [sig_visual, qr_img],
        [signer.get("name", "—") if signer else "—",
         Paragraph("Escanee el código QR para validar la autenticidad · Scan QR to verify.", small_c)],
        [f"{signer.get('role_label', signer.get('role', '—')) if signer else '—'} · Gerencia de Calidad / Quality Manager", ""],
        [f"Firmado electrónicamente / Electronically signed: {coa.get('issued_at', '')[:19]}", ""],
    ], colWidths=[120 * mm, 62 * mm])
    sig_tbl.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Times-Roman", 8.5),
        ("FONT", (0, 1), (0, 1), "Times-Bold", 10),
        ("ALIGN", (0, 0), (0, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEABOVE", (0, 1), (0, 1), 0.4, BRAND_DARK),
        ("SPAN", (1, 1), (1, 3)),
    ]))
    story.append(sig_tbl)
    story.append(Spacer(1, 10))

    # ---------- Regulatory footer ----------
    story.append(Table([[""]], colWidths=[182 * mm], rowHeights=[0.6],
                        style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), BRAND_AMBER)])))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "<b>Y-FO-CC-013</b> · Documento controlado emitido electrónicamente por YLMS – Yazoo Laboratory Management System.<br/>"
        "Cumple con NORDOM 428, ISO/IEC 17025, ISO 9001, HACCP y regulaciones DIGENOR/MSP · "
        "<i>Compliant with ISO/IEC 17025, ISO 9001, HACCP, DIGENOR/MSP.</i>",
        small_c,
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer.read()


def generate_coa_pdf(coa: dict, sample: dict, product: dict, executions: list, signer: dict,
                     format: str = "modern") -> bytes:
    """Router-facing function. format = 'modern' | 'standard'"""
    if format == "standard":
        return _generate_standard(coa, sample, product, executions, signer)
    return _generate_modern(coa, sample, product, executions, signer)


# ---------------- QUOTE PDF (Cotización Ventas · membretado bilingüe ES/EN) ----------------

def generate_quote_pdf(quote: dict, client: dict, signer: Optional[dict] = None,
                       verify_url: Optional[str] = None) -> bytes:
    """Cotización Yazoo — Membrete corporativo + tabla items + totales + firma comercial.

    Bilingüe ES/EN. Incluye QR code para verificación de validez en línea si `verify_url` viene.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=16 * mm, rightMargin=16 * mm,
        topMargin=12 * mm, bottomMargin=12 * mm,
        title=f"Cotización {quote.get('code', '')}",
    )
    styles = getSampleStyleSheet()
    body = ParagraphStyle("b", parent=styles["Normal"], fontName="Times-Roman", fontSize=9.5, textColor=BRAND_DARK)
    small_c = ParagraphStyle("sc", parent=body, fontSize=7.5, alignment=TA_CENTER,
                             textColor=colors.HexColor("#5C5046"))
    ttl_es = ParagraphStyle("t_es", parent=styles["Heading1"], fontName="Times-Bold",
                            fontSize=15, textColor=BRAND_DARK, alignment=TA_CENTER, spaceAfter=0)
    ttl_en = ParagraphStyle("t_en", parent=styles["Heading2"], fontName="Times-Italic",
                            fontSize=10.5, textColor=colors.HexColor("#5C5046"), alignment=TA_CENTER)

    story = []
    # ---- Header ----
    logo = _logo_image(24)
    logo_cell = logo if logo else Paragraph("<b>YAZOO</b>", ParagraphStyle("lx", parent=body, fontSize=14, alignment=TA_CENTER))
    company_block = [
        Paragraph("<b>RONES Y BEBIDAS DEL CARIBE YAZOO, S.R.L.</b>",
                  ParagraphStyle("c1", parent=body, fontName="Times-Bold", fontSize=11.5, alignment=TA_CENTER)),
        Paragraph("<i>Yazoo Rums &amp; Caribbean Beverages</i>",
                  ParagraphStyle("c2", parent=body, fontName="Times-Italic", fontSize=9.5, alignment=TA_CENTER)),
        Paragraph("Envejecemos y Envasamos Calidad · <i>We age and bottle quality</i>", small_c),
        Paragraph("RNC 1-31-45678-9 · Rep. Dominicana · ventas@yazoorones.do", small_c),
    ]
    issue_date = str(quote.get("created_at", ""))[:10] or "—"
    valid_until = quote.get("valid_until") or "—"
    ctrl = [
        ["Cotización / Quote", quote.get("code", "—")],
        ["Fecha / Date", issue_date],
        ["Válida hasta / Valid until", valid_until],
        ["Estado / Status", (quote.get("status") or "draft").upper()],
    ]
    ctrl_tbl = Table(ctrl, colWidths=[32 * mm, 26 * mm])
    ctrl_tbl.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Times-Roman", 8),
        ("FONT", (0, 0), (0, -1), "Times-Bold", 8),
        ("BACKGROUND", (0, 0), (0, -1), GRAY_LIGHT),
        ("GRID", (0, 0), (-1, -1), 0.4, BRAND_DARK),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]))
    header_tbl = Table([[logo_cell, company_block, ctrl_tbl]],
                       colWidths=[28 * mm, 92 * mm, 58 * mm])
    header_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.6, BRAND_DARK),
        ("LINEBEFORE", (1, 0), (1, 0), 0.4, BRAND_DARK),
        ("LINEBEFORE", (2, 0), (2, 0), 0.4, BRAND_DARK),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(header_tbl)
    story.append(Spacer(1, 6))
    story.append(Table([[""]], colWidths=[178 * mm], rowHeights=[3],
                       style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), BRAND_AMBER)])))
    story.append(Spacer(1, 6))

    # ---- Title ----
    story.append(Paragraph("COTIZACIÓN COMERCIAL", ttl_es))
    story.append(Paragraph("COMMERCIAL QUOTATION", ttl_en))
    story.append(Spacer(1, 6))

    # ---- Client block ----
    def _cell(es, en, val):
        return Paragraph(
            f"<b>{es}</b> <font size=7 color='#5C5046'><i>/ {en}</i></font><br/>{val or '—'}",
            ParagraphStyle("cc", parent=body, fontSize=8.8)
        )

    client_rows = [
        [_cell("Cliente", "Customer", client.get("name")),
         _cell("RNC / Tax ID", "Tax ID", client.get("tax_id"))],
        [_cell("Contacto", "Contact", client.get("contact")),
         _cell("Teléfono / Email", "Phone / Email",
               f"{client.get('phone') or '—'} · {client.get('email') or '—'}")],
        [_cell("Dirección", "Address", client.get("address")), ""],
    ]
    ctbl = Table(client_rows, colWidths=[89 * mm, 89 * mm])
    ctbl.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, BRAND_DARK),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("SPAN", (0, 2), (1, 2)),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(ctbl)
    story.append(Spacer(1, 8))

    # ---- Items table ----
    rows = [["#", "Descripción\nDescription", "Cant.\nQty", "Precio Unit.\nUnit Price",
             "Importe\nAmount"]]
    for i, it in enumerate(quote.get("items", []), 1):
        qty = float(it.get("quantity") or 0)
        price = float(it.get("unit_price") or 0)
        rows.append([str(i), it.get("description", "—"),
                     f"{qty:,.2f}", f"RD$ {price:,.2f}",
                     f"RD$ {qty * price:,.2f}"])
    items_tbl = Table(rows, colWidths=[10 * mm, 92 * mm, 22 * mm, 26 * mm, 28 * mm], repeatRows=1)
    items_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_DARK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONT", (0, 0), (-1, 0), "Times-Bold", 8.5),
        ("FONT", (0, 1), (-1, -1), "Times-Roman", 9),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (2, 0), (-1, 0), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.4, GRAY_BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(items_tbl)
    story.append(Spacer(1, 6))

    # ---- Totals ----
    subtotal = float(quote.get("subtotal") or 0)
    tax = float(quote.get("tax") or 0)
    total = float(quote.get("total") or 0)
    tax_rate = float(quote.get("tax_rate") or 0) * 100
    tot_rows = [
        ["Subtotal / Subtotal", f"RD$ {subtotal:,.2f}"],
        [f"ITBIS ({tax_rate:.0f}%) / Tax", f"RD$ {tax:,.2f}"],
        ["TOTAL", f"RD$ {total:,.2f}"],
    ]
    tot_tbl = Table(tot_rows, colWidths=[52 * mm, 34 * mm], hAlign="RIGHT")
    tot_tbl.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -2), "Times-Roman", 9.5),
        ("FONT", (0, -1), (-1, -1), "Times-Bold", 11),
        ("BACKGROUND", (0, -1), (-1, -1), BRAND_AMBER),
        ("TEXTCOLOR", (0, -1), (-1, -1), BRAND_DARK),
        ("GRID", (0, 0), (-1, -1), 0.4, BRAND_DARK),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(tot_tbl)
    story.append(Spacer(1, 10))

    # ---- Notes ----
    if quote.get("notes"):
        story.append(Paragraph("<b>Notas / Notes</b>",
                                ParagraphStyle("nn", parent=body, fontName="Times-Bold", fontSize=10)))
        story.append(Paragraph(quote["notes"], body))
        story.append(Spacer(1, 6))

    # ---- Terms ----
    terms_es = (
        "Condiciones: Precios en pesos dominicanos, ITBIS incluido según regulación DGII. "
        "Cotización sujeta a disponibilidad. Forma de pago según acuerdo comercial."
    )
    terms_en = (
        "<i>Terms: Prices in Dominican pesos, ITBIS included per DGII regulation. "
        "Quote subject to availability. Payment terms as per commercial agreement.</i>"
    )
    story.append(Paragraph(terms_es, small_c))
    story.append(Paragraph(terms_en, small_c))
    story.append(Spacer(1, 16))

    # ---- Signature ----
    sig_name = (signer or {}).get("name", "—")
    sig_role = (signer or {}).get("role_label") or (signer or {}).get("role") or "Ejecutivo Comercial"
    sig_visual = Paragraph("_" * 34, body)
    try:
        from routers.signatures import signature_file_path
        p = signature_file_path((signer or {}).get("id")) if signer else None
        if p:
            sig_visual = Image(str(p), width=55 * mm, height=18 * mm, kind='proportional')
    except Exception:
        pass
    sig = Table([[sig_visual], [sig_name], [sig_role],
                 [f"Firmado electrónicamente · Electronically signed"]],
                colWidths=[90 * mm], hAlign="LEFT")
    sig.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Times-Roman", 8.5),
        ("FONT", (0, 1), (0, 1), "Times-Bold", 10),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("LINEABOVE", (0, 1), (0, 1), 0.4, BRAND_DARK),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))

    # ---- QR verify block (right side) ----
    qr_cell = ""
    if verify_url:
        try:
            qr = qrcode.QRCode(box_size=3, border=1)
            qr.add_data(verify_url)
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color="#1A120E", back_color="white")
            qr_buf = io.BytesIO()
            qr_img.save(qr_buf, format="PNG")
            qr_buf.seek(0)
            qr_cell = Image(qr_buf, width=26 * mm, height=26 * mm)
        except Exception:
            qr_cell = ""
    qr_block = Table([
        [qr_cell if qr_cell else Paragraph("&nbsp;", body)],
        [Paragraph("<b>Verifica esta cotización</b><br/><i>Scan to verify online</i>",
                    ParagraphStyle("qv", parent=body, fontSize=7.5, alignment=TA_CENTER,
                                    textColor=colors.HexColor("#5C5046")))],
    ], colWidths=[30 * mm])
    qr_block.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.4, GRAY_BORDER),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#faf7f2")),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))

    footer_row = Table([[sig, qr_block]], colWidths=[110 * mm, 40 * mm])
    footer_row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(footer_row)
    story.append(Spacer(1, 10))

    # ---- Footer ----
    story.append(Table([[""]], colWidths=[178 * mm], rowHeights=[0.6],
                        style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), BRAND_AMBER)])))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "Documento controlado emitido electrónicamente por <b>YLMS – Yazoo Laboratory Management System</b>. "
        "Cumple con las regulaciones DGII / DIGENOR de la República Dominicana.",
        small_c,
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer.read()
