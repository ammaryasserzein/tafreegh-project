"""Behavioral tests for Pass 3 (_qa_punctuation) and Pass 4 (_qa_dialect_dialogue) QA seams."""

from __future__ import annotations

from tafreegh._qa_dialect_dialogue import check_dialect_and_dialogue
from tafreegh._qa_models import ParagraphRecord, ValidationReport
from tafreegh._qa_punctuation import check_punctuation_and_orthography
from tafreegh.workspace_catalog import RuleCatalog


def _make_records(*body: tuple[str, bool]) -> list[ParagraphRecord]:
    records = [
        ParagraphRecord(index=0, text="بسم الله الرحمن الرحيم", is_matn=False),
        ParagraphRecord(index=1, text="المادة: المنطق (السلم المنورق)", is_matn=False),
        ParagraphRecord(index=2, text="2026-10-17", is_matn=False),
    ]
    for offset, (text, is_matn) in enumerate(body):
        records.append(ParagraphRecord(index=3 + offset, text=text, is_matn=is_matn))
    return records


class TestDialectAndDialogueQA:
    def test_dialect_regex_strips_tashkeel_so_combining_marks_do_not_split_words(self):
        catalog = RuleCatalog.load()
        records = _make_records(
            ("وإليه أهَّلك هذا الحديث.", False),
            ("وإليه أَهْلك هذا الأمر.", False),
            ("إحنا أَه كِدَه.", False),
        )
        report = ValidationReport(docx_path="tashkeel_dialect.docx")

        check_dialect_and_dialogue(records, report, catalog)

        dialect_issues = [i for i in report.issues if i.code == "DIALECT_UNNORMALIZED"]
        flagged_paras = {i.paragraph_index for i in dialect_issues}
        assert 3 not in flagged_paras
        assert 4 not in flagged_paras
        assert 5 in flagged_paras
        assert len(dialect_issues) >= 3

    def test_student_colon_before_matn_passes_and_colon_before_prose_fails(self):
        catalog = RuleCatalog.load()
        valid_records = _make_records(
            ("طالب: الطبري قال كدا، قال:", False),
            ("", False),
            ("(يَقُولُ الْإِمَامُ الطَّبَرِيُّ كَذَا)", True),
            ("نعم هذا صحيح.", False),
        )
        valid_report = ValidationReport(docx_path="student_colon_matn.docx")
        check_dialect_and_dialogue(valid_records, valid_report, catalog)
        assert valid_report.issues == []

        invalid_records = _make_records(
            ("طالب: الطبري قال كدا، قال:", False),
            ("نعم هذا كلام الشيخ.", False),
        )
        invalid_report = ValidationReport(docx_path="student_colon_prose.docx")
        check_dialect_and_dialogue(invalid_records, invalid_report, catalog)
        assert [i.code for i in invalid_report.issues] == ["STUDENT_TERMINAL_PUNCTUATION_MISSING"]

    def test_standalone_inaudible_without_student_prefix_flags_while_mid_prose_passes(self):
        catalog = RuleCatalog.load()
        records = _make_records(
            ("صوت غير مسموع.", False),
            ("(صوت غير مسموع).", False),
            ("وكمل الشيخ كلامه (صوت غير مسموع) في الدرس.", False),
        )
        report = ValidationReport(docx_path="inaudible_prefix.docx")
        check_dialect_and_dialogue(records, report, catalog)

        inaudible_issues = [
            i for i in report.issues if i.code == "INAUDIBLE_STUDENT_PREFIX_MISSING"
        ]
        assert [i.paragraph_index for i in inaudible_issues] == [3, 4]

    def test_consecutive_student_turns_flags_non_laughter_and_exempts_room_laughter(self):
        catalog = RuleCatalog.load()
        bad_records = _make_records(
            ("طالب: سؤال أول؟", False),
            ("طالب: جواب ثان.", False),
        )
        bad_report = ValidationReport(docx_path="consecutive_students.docx")
        check_dialect_and_dialogue(bad_records, bad_report, catalog)
        assert [i.code for i in bad_report.issues] == ["CONSECUTIVE_STUDENT_TURNS"]
        assert bad_report.issues[0].paragraph_index == 4

        laughter_records = _make_records(
            ("طالب: قال شيئًا مضحكًا.", False),
            ("طالب: ههههه.", False),
        )
        laughter_report = ValidationReport(docx_path="student_laughter.docx")
        check_dialect_and_dialogue(laughter_records, laughter_report, catalog)
        assert laughter_report.issues == []


class TestPunctuationAndOrthographyQA:
    def test_quote_internal_space_allows_closing_question_and_period_while_catching_spaces(self):
        records = _make_records(
            ('قال: "أينقص الرطب إذا يبس؟" قالوا نعم، وقال: "حديث صحيح." ثم أكمل.', False),
            ('قال: "حديث أول سليم" ثم قال: " حديث شريف " في الدرس.', False),
            ('قال: "كلام أول غير مغلق ثم قال: "حديث نبوي سليم".', False),
            ('قال: "كلام أول غير مغلق ثم قال: " حديث شريف " في الدرس.', False),
        )
        report = ValidationReport(docx_path="quote_spacing.docx")
        check_punctuation_and_orthography(records, report)

        quote_issues = [i for i in report.issues if i.code == "QUOTE_INTERNAL_SPACE"]
        assert [i.paragraph_index for i in quote_issues] == [4, 6]
        assert all("حديث شريف" in i.snippet for i in quote_issues)

    def test_forbidden_punctuation_exempts_matn_source_brackets_and_flags_prose_guillemets_and_dashes(self):
        records = _make_records(
            ("(بَدِيعُ {السَّمَاوَاتِ} [البقرة: 117] وَقَالَ: «حَدِيثٌ»)", True),
            ("من صفحة 10 - 15 وتاريخ 2026-10-17 في الكتاب.", False),
            ("نقول [نعم] في {مسألة} هنا.", False),
            ("قال الشاعر «شر بلدة» في هذا البيت.", False),
            ("هذا - طبعًا - مهم جدا.", False),
            ("كلام — مهم، وكلام – آخر.", False),
        )
        report = ValidationReport(docx_path="forbidden_punc.docx")
        check_punctuation_and_orthography(records, report)

        punc_issues = [i for i in report.issues if i.code == "FORBIDDEN_PUNCTUATION"]
        assert [i.paragraph_index for i in punc_issues] == [5, 6, 7, 8]

    def test_standalone_parenthesized_poetry_passes_while_inline_prose_ellipsis_still_fails(self):
        records = _make_records(
            ("(فلما قرنته بالذي قد ذكرته ... وما زلت أرجو منه عودًا على بدء)", False),
            ("وهنا شرح فيه (وَأَنْ يَكُونَ نَافِعًا لِلْمُبْتَدِي ... بِهِ إِلَى الْمُطَوَّلَاتِ يَهْتَدِي) في وسط الكلام.", False),
            ("(والمرونق: المزين، قال الشاعر: فهذا عليه رونق الخط وحده ... وهذا عليه رونق الخط والملك)", True),
        )
        report = ValidationReport(docx_path="paren_poetry.docx")
        check_punctuation_and_orthography(records, report)

        el_issues = [i for i in report.issues if i.code == "ELLIPSIS_FORBIDDEN"]
        assert [i.paragraph_index for i in el_issues] == [4, 5]

    def test_izhan_nun_exempts_noun_permission_after_prepositions(self):
        records = _make_records(
            ("لا يخرج من غير إذن، ولا بدون إذن، ولا دون إذن، ولا عن إذن، ولا بعد إذن، وبإذن الله.", False),
            ("وبدون إذن ومِنْ غَيْرِ إذن لا يصح.", False),
            ("نقول إذن هذا الأمر واضح.", False),
            ("من غير إذن، نقول إذن هذا الأمر واضح.", False),
        )
        report = ValidationReport(docx_path="izhan_noun.docx")
        check_punctuation_and_orthography(records, report)

        izhan_issues = [i for i in report.issues if i.code == "ORTHOGRAPHY_IZHAN_NUN"]
        assert [i.paragraph_index for i in izhan_issues] == [5, 6]

    def test_prose_trailing_comma_flags_non_matn_comma_endings(self):
        records = _make_records(
            ("جمعوا ألف سيف لإبادة المسلمين،", False),
            ("طالب: سؤال فيه،", False),
            ("(وَهَذَا نَصُّ الْمَتْنِ،)", True),
            ("وهذا شرح مكتمل.", False),
        )
        report = ValidationReport(docx_path="trailing_comma.docx")
        check_punctuation_and_orthography(records, report)

        comma_issues = [i for i in report.issues if i.code == "PROSE_TRAILING_COMMA"]
        assert [i.paragraph_index for i in comma_issues] == [3, 4]


