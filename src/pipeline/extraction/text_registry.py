from src.pipeline.extraction.text_contracts import TextFieldSpec


def all_text_field_specs() -> list[TextFieldSpec]:
    return [
        TextFieldSpec(
            field_name="current_event_quant",
            route="issuer",
            form_families=("8-K", "6-K"),
            locators=("item_window", "section_window"),
            anchor_terms=("item", "press release", "current report"),
            regex_patterns=(
                r"(?i)\b(event|announcement|transaction|agreement)\b",
                r"(?i)\b(material\s+definitive\s+agreement|results\s+of\s+operations|financial\s+condition)\b",
            ),
            output_kind="text",
            qa_rules={
                "materiality_score_min": 0,
                "materiality_score_max": 5,
                "cash_impact_usd_nullable": True,
                "dilution_pct_nullable": True,
                "one_time_cost_usd_nullable": True,
            },
        ),
        TextFieldSpec(
            field_name="beneficial_ownership_intent_quant",
            route="owner",
            form_families=("13D", "13G"),
            locators=("section_window", "parse_text_window"),
            anchor_terms=("item 4", "purpose of transaction", "cover page"),
            regex_patterns=(
                r"(?i)\b(passive|engaged|activist|control)\b",
                r"(?i)\b(board\s+seat|proxy\s+fight|group\s+formed|strategic\s+alternatives|merger)\b",
            ),
            output_kind="text",
            qa_rules={
                "require_stance_enum": True,
                "require_group_flag": True,
                "allow_short": True,
                "allow_medium": True,
                "allow_long": True,
                "allow_unclear": True,
            },
        ),
        TextFieldSpec(
            field_name="amendment_scope_quant",
            route="holding",
            form_families=("13F-HR/A",),
            locators=("section_window", "parse_text_window"),
            anchor_terms=("amendment", "amendment note", "header"),
            regex_patterns=(
                r"(?i)\b(amendment|restatement|correction|addition|deletion)\b",
                r"(?i)\b(position\s+count\s+delta|value\s+delta|restatement\s+flag)\b",
            ),
            output_kind="text",
            qa_rules={
                "position_count_delta_nullable": True,
                "value_delta_usd_nullable": True,
                "restatement_flag_required": True,
            },
        ),
    ]
