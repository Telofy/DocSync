from __future__ import annotations

from docfs.google_docs import tab_to_ir
from docfs.markdown_codec import ir_to_markdown


def test_pull_preserves_bold_markdown_from_docs_text_style() -> None:
    tab = {
        "documentTab": {
            "body": {
                "content": [
                    {
                        "paragraph": {
                            "elements": [
                                {
                                    "textRun": {
                                        "content": "Short Glossary of Essential Terms\n",
                                        "textStyle": {"bold": True},
                                    }
                                }
                            ],
                            "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                        }
                    }
                ]
            }
        }
    }

    md = ir_to_markdown(tab_to_ir(tab))
    assert "**Short Glossary of Essential Terms**" in md


def test_pull_preserves_horizontal_rule() -> None:
    tab = {
        "documentTab": {
            "body": {
                "content": [
                    {
                        "paragraph": {
                            "elements": [{"horizontalRule": {}}],
                            "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                        }
                    },
                ]
            }
        }
    }

    md = ir_to_markdown(tab_to_ir(tab))
    assert md.strip() == "---"


def test_pull_preserves_spacing_around_heading_and_rule() -> None:
    tab = {
        "documentTab": {
            "body": {
                "content": [
                    {
                        "paragraph": {
                            "elements": [{"textRun": {"content": "Front Matter\n", "textStyle": {}}}],
                            "paragraphStyle": {"namedStyleType": "HEADING_3"},
                        }
                    },
                    {
                        "paragraph": {
                            "elements": [
                                {
                                    "textRun": {
                                        "content": "Short Glossary of Essential Terms\n",
                                        "textStyle": {"bold": True},
                                    }
                                }
                            ],
                            "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                        }
                    },
                    {
                        "paragraph": {
                            "elements": [{"textRun": {"content": "Full glossary at back of book\n", "textStyle": {}}}],
                            "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                        }
                    },
                    {
                        "paragraph": {
                            "elements": [{"horizontalRule": {}}],
                            "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                        }
                    },
                ]
            }
        }
    }

    md = ir_to_markdown(tab_to_ir(tab))
    assert "### Front Matter\n\n**Short Glossary of Essential Terms**\n\nFull glossary at back of book\n\n---\n" == md
