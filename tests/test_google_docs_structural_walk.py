from __future__ import annotations

from docfs.google_docs import tab_to_ir


def test_tab_to_ir_reads_table_cell_paragraphs() -> None:
    tab = {
        "documentTab": {
            "body": {
                "content": [
                    {
                        "table": {
                            "tableRows": [
                                {
                                    "tableCells": [
                                        {
                                            "content": [
                                                {
                                                    "paragraph": {
                                                        "elements": [
                                                            {"textRun": {"content": "Part\n", "textStyle": {}}}
                                                        ],
                                                        "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                                                    }
                                                }
                                            ]
                                        },
                                        {
                                            "content": [
                                                {
                                                    "paragraph": {
                                                        "elements": [
                                                            {"textRun": {"content": "Chapters\n", "textStyle": {}}}
                                                        ],
                                                        "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                                                    }
                                                }
                                            ]
                                        },
                                    ]
                                }
                            ]
                        }
                    }
                ]
            }
        }
    }
    ir = tab_to_ir(tab)
    texts = [b.text for b in ir.blocks]
    assert texts == ["Part", "Chapters"]
