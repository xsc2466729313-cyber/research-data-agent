from __future__ import annotations

from backend.app.parsers import ParseRequest, ParserRegistry


def test_csv_parser_profiles_types_and_missing_tokens() -> None:
    result = ParserRegistry().parse(
        ParseRequest(
            source_id="file:csv-1",
            filename="clinical.csv",
            text="patient_id,her2_status,age\nP1,Positive,52\nP2,NA,unknown\n",
        )
    )
    assert result.status == "PARSED"
    assert result.records
    assert any(item.raw_field == "her2_status" and item.raw_value == "Positive" for item in result.records)
    assert any(item.inferred_semantic_type == "missing" for item in result.records)


def test_html_table_keeps_source_location() -> None:
    result = ParserRegistry().parse(
        ParseRequest(
            source_id="web:table-1",
            filename="page.html",
            html="<table><caption>Demo</caption><tr><th>gene</th><th>status</th></tr><tr><td>PIK3CA</td><td>mut</td></tr></table>",
        )
    )
    assert result.status == "PARSED"
    assert result.records[0].raw_field == "gene"
    assert result.records[0].raw_value == "PIK3CA"
    assert "table:0" in result.records[0].source_location


def test_excel_inline_rows() -> None:
    result = ParserRegistry().parse(
        ParseRequest(
            source_id="file:xlsx-1",
            filename="supplement.xlsx",
            rows=[{"sample_id": "S1", "pCR": "yes"}],
        )
    )
    assert result.status == "PARSED"
    assert any(item.raw_field == "pCR" for item in result.records)


def test_pdf_text_does_not_invent_tables() -> None:
    result = ParserRegistry().parse(
        ParseRequest(
            source_id="file:pdf-1",
            filename="paper.pdf",
            text="Abstract\nPIK3CA mutation and pCR.\nMethods\nHER2 IHC was recorded.\n",
        )
    )
    assert result.status == "PARSED"
    assert any(item.raw_field == "content_hash" for item in result.records)


def test_empty_pdf_is_review_not_guessed() -> None:
    result = ParserRegistry().parse(ParseRequest(source_id="file:pdf-empty", filename="scan.pdf", text=""))
    assert result.status == "REVIEW"
    assert result.records == []


JATS_ARTICLE = """<article>
<table-wrap>
<table>
<tr><th>gene</th><th>pCR</th></tr>
<tr><td>BRCA1</td><td>yes</td></tr>
</table>
</table-wrap>
<fig><caption>Figure 1. Kaplan-Meier curve of pCR. Values must not be read from pixels.</caption></fig>
</article>
"""


def test_jats_parser_extracts_table_cells_and_reviews_figure_captions() -> None:
    result = ParserRegistry().parse(
        ParseRequest(source_id="pmc:PMC1", filename="PMC1.xml", text=JATS_ARTICLE)
    )
    assert result.status == "PARSED"
    assert any(item.raw_field == "gene" and item.raw_value == "BRCA1" for item in result.records)
    captions = [item for item in result.records if item.raw_field == "figure_caption"]
    assert captions
    assert captions[0].status == "REVIEW"
    assert any("像素" in warning for warning in result.warnings)


def test_empty_jats_does_not_invent_numbers() -> None:
    result = ParserRegistry().parse(ParseRequest(source_id="pmc:empty", filename="empty.xml", text=""))
    assert result.status == "REVIEW"
    assert result.records == []
    assert any("禁止" in warning or "像素" in warning for warning in result.warnings)
