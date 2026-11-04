import tempfile
import unittest
from pathlib import Path
import sys
import warnings
import docx
from docx.shared import Inches, Pt
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

# Ensure UTF-8 output on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

scripts_dir = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

from export_docx import create_docx
from verify_docx import (
    BASE_EXEMPT_NAMES,
    BASE_KINSHIP_NOUNS,
    BASE_KUNYA_PREFIXES,
    BASE_TITLE_PREFIXES,
    MatnAlignmentValidator,
    _verify_exported_matn_segment,
    verify_docx,
    Severity,
    load_dialect_replacements,
    load_attendee_anonymization_rules,
    AttendeeAnonymizationRules,
)


VALID_MINIMAL_MD = """بسم الله الرحمن الرحيم
المادة: المنطق (السلم المنورق)
2026-10-17

بسم الله والحمد لله، والصلاة والسلام على رسول الله.

**(فَهَاكَ مِنْ أُصُولِهِ قَوَاعِدَا ... تَجْمَعُ مِنْ فُنُونِهِ فَوَائِدَا)**

هذا شرح واضح ومفصل للبيت الأول، والحمد لله رب العالمين وصل اللهم على نبينا محمد وعلى آله وصحبه أجمعين، سبحانك اللهم وبحمدك نشهد أن لا إله إلا أنت نستغفرك ونتوب إليك.
"""


class TestVerifyDocxOOXML(unittest.TestCase):
    def test_valid_docx_passes_ooxml_checks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            docx_path = Path(tmpdir) / "valid.docx"
            create_docx(VALID_MINIMAL_MD, docx_path)
            report = verify_docx(docx_path)
            self.assertTrue(report.passed, f"Expected valid docx to pass, got issues: {report.issues}")
            self.assertEqual(report.error_count, 0)

    def test_detects_invalid_margins(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            docx_path = Path(tmpdir) / "bad_margins.docx"
            create_docx(VALID_MINIMAL_MD, docx_path)
            doc = docx.Document(str(docx_path))
            doc.sections[0].top_margin = Inches(1.0)
            doc.save(str(docx_path))

            report = verify_docx(docx_path)
            self.assertFalse(report.passed)
            codes = [i.code for i in report.issues if i.severity == Severity.ERROR]
            self.assertIn("MARGIN_INVALID", codes)

    def test_detects_wrong_font_size_and_color_and_manual_break(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            docx_path = Path(tmpdir) / "bad_style.docx"
            create_docx(VALID_MINIMAL_MD, docx_path)
            doc = docx.Document(str(docx_path))
            # Mutate body paragraph run
            body_p = doc.paragraphs[3]
            r = body_p.runs[0]
            r.font.size = Pt(14)
            rPr = r._r.get_or_add_rPr()
            color_el = OxmlElement('w:color')
            color_el.set(qn('w:val'), 'FF0000')
            rPr.append(color_el)
            r._r.append(OxmlElement('w:br'))
            doc.save(str(docx_path))

            report = verify_docx(docx_path)
            codes = [i.code for i in report.issues if i.severity == Severity.ERROR]
            self.assertIn("FONT_SIZE_INVALID", codes)
            self.assertIn("FONT_COLOR_FORBIDDEN", codes)
            self.assertIn("MANUAL_LINE_BREAK", codes)

    def test_detects_bold_on_student_or_explanation_or_header(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            docx_path = Path(tmpdir) / "bad_bold.docx"
            create_docx(VALID_MINIMAL_MD, docx_path)
            doc = docx.Document(str(docx_path))
            # Make header bold
            doc.paragraphs[0].runs[0].bold = True
            # Add a bold student line before conclusion
            p_stu = doc.add_paragraph("طالب: سؤال مهم؟")
            p_stu.runs[0].bold = True
            doc.save(str(docx_path))

            report = verify_docx(docx_path)
            codes = [i.code for i in report.issues if i.severity == Severity.ERROR]
            self.assertIn("HEADER_BOLD_FORBIDDEN", codes)
            self.assertIn("ILLEGAL_BOLD_RUN", codes)


class TestVerifyDocxHeaderAndConclusion(unittest.TestCase):
    def test_detects_invalid_headers_and_alignment(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            docx_path = Path(tmpdir) / "bad_header.docx"
            create_docx(VALID_MINIMAL_MD, docx_path)
            doc = docx.Document(str(docx_path))
            doc.paragraphs[0].text = "الحمد لله"
            doc.paragraphs[0].alignment = None
            doc.paragraphs[1].text = "المادة: مادة غير موجودة"
            doc.paragraphs[2].text = "تاريخ_غير_محدد"
            doc.save(str(docx_path))

            report = verify_docx(docx_path)
            codes = [i.code for i in report.issues if i.severity == Severity.ERROR]
            self.assertIn("HEADER_P0_INVALID", codes)
            self.assertIn("HEADER_ALIGN_INVALID", codes)
            self.assertIn("HEADER_P1_SUBJECT_INVALID", codes)
            self.assertIn("HEADER_P2_INVALID", codes)

    def test_detects_leaked_metadata_and_markdown_tokens(self):
        bad_md = """بسم الله الرحمن الرحيم
المادة: المنطق (السلم المنورق)
2026-10-17

الحمد لله button_magic Source guide 2026-10-17 منطق.mp3 هنا كلام.

شرح فيه نجمة (شطر أول * شطر ثاني) وكلام.

والحمد لله رب العالمين وصل اللهم على نبينا محمد وعلى آله وصحبه أجمعين، سبحانك اللهم وبحمدك نشهد أن لا إله إلا أنت نستغفرك ونتوب إليك.
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            docx_path = Path(tmpdir) / "leaked.docx"
            create_docx(bad_md, docx_path)
            report = verify_docx(docx_path)
            codes = [i.code for i in report.issues if i.severity == Severity.ERROR]
            self.assertIn("LEAKED_METADATA", codes)
            self.assertIn("FORBIDDEN_CHAR_ASTERISK", codes)

    def test_allows_spaced_asterisk_between_vowelized_quranic_ayahs_while_rejecting_invalid_asterisks(self):
        valid_quran_md = """بسم الله الرحمن الرحيم
المادة: رياض الصالحين
2026-10-22

قال تعالى: (عَمَّ يَتَسَاءَلُونَ * عَنِ النَّبَإِ الْعَظِيمِ * الَّذِي هُمْ فِيهِ مُخْتَلِفُونَ) في سورة النبأ.

**(قال المصنف رحمه الله في الآية: (وَلَا تَقُولَنَّ لِشَيْءٍ إِنِّي فَاعِلٌ ذَلِكَ غَدًا * إِلَّا أَنْ يَشَاءَ اللَّهُ))**

والحمد لله رب العالمين وصل اللهم على نبينا محمد وعلى آله وصحبه أجمعين، سبحانك اللهم وبحمدك نشهد أن لا إله إلا أنت نستغفرك ونتوب إليك.
"""
        invalid_asterisks_md = """بسم الله الرحمن الرحيم
المادة: رياض الصالحين
2026-10-22

آية بدون مسافة قبل النجمة: (عَمَّ يَتَسَاءَلُونَ* عَنِ النَّبَإِ الْعَظِيمِ) في الشرح.

شعر بدون تشكيل: (شطر أول * شطر ثاني) في الشرح.

**(الشَّطْرُ الْأَوَّلُ * الشَّطْرُ الثَّانِي)**

شرح فيه تسريب ماركداون، والحمد لله رب العالمين وصل اللهم على نبينا محمد وعلى آله وصحبه أجمعين، سبحانك اللهم وبحمدك نشهد أن لا إله إلا أنت نستغفرك ونتوب إليك.
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            ok_docx = Path(tmpdir) / "valid_quran_asterisk.docx"
            create_docx(valid_quran_md, ok_docx)
            rep_ok = verify_docx(ok_docx)
            self.assertTrue(rep_ok.passed, f"Expected spaced vowelized Quranic '*' to pass, got: {rep_ok.issues}")

            bad_docx = Path(tmpdir) / "invalid_asterisks.docx"
            create_docx(invalid_asterisks_md, bad_docx)
            doc_bad = docx.Document(str(bad_docx))
            doc_bad.paragraphs[6].runs[0].text = doc_bad.paragraphs[6].runs[0].text.replace(
                "ماركداون", "**متن**"
            )
            doc_bad.save(str(bad_docx))
            rep_bad = verify_docx(bad_docx)
            ast_paras = [i.paragraph_index for i in rep_bad.issues if i.code == "FORBIDDEN_CHAR_ASTERISK"]
            # Paragraph 5 **(الشَّطْرُ الْأَوَّلُ * الشَّطْرُ الثَّانِي)** is syntactically identical to a vowelized
            # ayah pair, so outer parens double as citation parens and it is not flagged here.
            self.assertEqual(ast_paras, [3, 4, 6])

    def test_standalone_bold_ayah_matn_allows_spaced_asterisk(self):
        md = """بسم الله الرحمن الرحيم
المادة: رياض الصالحين
2026-10-22

**(عَمَّ يَتَسَاءَلُونَ * عَنِ النَّبَإِ الْعَظِيمِ)**

والحمد لله رب العالمين وصل اللهم على نبينا محمد وعلى آله وصحبه أجمعين، سبحانك اللهم وبحمدك نشهد أن لا إله إلا أنت نستغفرك ونتوب إليك.
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            docx_path = Path(tmpdir) / "standalone_ayah.docx"
            create_docx(md, docx_path)
            report = verify_docx(docx_path)
            ast_issues = [i for i in report.issues if i.code == "FORBIDDEN_CHAR_ASTERISK"]
            self.assertEqual(len(ast_issues), 0, f"Expected standalone bold Ayah Matn to pass, got: {ast_issues}")

    def test_detects_wrong_concluding_dua(self):
        # Like line 89 of 2026-10-17_AI.md: وصلى الله instead of وصل اللهم, plus extra commas
        bad_dua_md = """بسم الله الرحمن الرحيم
المادة: المنطق (السلم المنورق)
2026-10-17

الحمد لله، والصلاة والسلام على رسول الله، وبعد، والحمد لله رب العالمين وصلى الله على نبينا محمد وعلى آله وصحبه أجمعين، سبحانك اللهم وبحمدك، نشهد أن لا إله إلا أنت، نستغفرك ونتوب إليك.
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            docx_path = Path(tmpdir) / "bad_dua.docx"
            create_docx(bad_dua_md, docx_path)
            report = verify_docx(docx_path)
            codes = [i.code for i in report.issues if i.severity == Severity.ERROR]
            self.assertIn("CONCLUSION_DUA_INVALID", codes)


class TestVerifyDocxPunctuationAndOrthography(unittest.TestCase):
    def test_detects_bracket_and_quote_internal_spacing(self):
        md = """بسم الله الرحمن الرحيم
المادة: المنطق (السلم المنورق)
2026-10-17

قال تعالى: ( أَوْ سُلَّمًا فِي السَّمَاءِ ) وقال: "حديث أول سليم" ثم قال: " حديث شريف "، والحمد لله رب العالمين وصل اللهم على نبينا محمد وعلى آله وصحبه أجمعين، سبحانك اللهم وبحمدك نشهد أن لا إله إلا أنت نستغفرك ونتوب إليك.
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            docx_path = Path(tmpdir) / "spacing.docx"
            create_docx(md, docx_path)
            report = verify_docx(docx_path)
            codes = [i.code for i in report.issues if i.severity == Severity.ERROR]
            self.assertIn("BRACKET_INTERNAL_SPACE", codes)
            self.assertIn("QUOTE_INTERNAL_SPACE", codes)
            quote_issues = [i for i in report.issues if i.code == "QUOTE_INTERNAL_SPACE"]
            self.assertEqual(len(quote_issues), 1)
            self.assertIn("حديث شريف", quote_issues[0].snippet)

    def test_quote_internal_spacing_ignores_unbalanced_quote_parity(self):
        unbalanced_clean_md = """بسم الله الرحمن الرحيم
المادة: المنطق (السلم المنورق)
2026-10-17

قال: "كلام أول غير مغلق ثم قال: "حديث نبوي سليم"، والحمد لله رب العالمين وصل اللهم على نبينا محمد وعلى آله وصحبه أجمعين، سبحانك اللهم وبحمدك نشهد أن لا إله إلا أنت نستغفرك ونتوب إليك.
"""
        unbalanced_spaced_md = """بسم الله الرحمن الرحيم
المادة: المنطق (السلم المنورق)
2026-10-17

قال: "كلام أول غير مغلق ثم قال: " حديث شريف "، والحمد لله رب العالمين وصل اللهم على نبينا محمد وعلى آله وصحبه أجمعين، سبحانك اللهم وبحمدك نشهد أن لا إله إلا أنت نستغفرك ونتوب إليك.
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            clean_docx = Path(tmpdir) / "unbalanced_clean.docx"
            create_docx(unbalanced_clean_md, clean_docx)
            clean_report = verify_docx(clean_docx)
            clean_quote_issues = [i for i in clean_report.issues if i.code == "QUOTE_INTERNAL_SPACE"]
            self.assertEqual(len(clean_quote_issues), 0)

            spaced_docx = Path(tmpdir) / "unbalanced_spaced.docx"
            create_docx(unbalanced_spaced_md, spaced_docx)
            spaced_report = verify_docx(spaced_docx)
            spaced_quote_issues = [i for i in spaced_report.issues if i.code == "QUOTE_INTERNAL_SPACE"]
            self.assertEqual(len(spaced_quote_issues), 1)
            self.assertIn("حديث شريف", spaced_quote_issues[0].snippet)

    def test_mid_paragraph_period_banned_in_explanation_but_exempt_in_matn(self):
        md = """بسم الله الرحمن الرحيم
المادة: المنطق (السلم المنورق)
2026-10-17

**(وَهُوَ حَقِيقَةٌ فِي الْحِسِّ، مَجَازٌ فِي الْمَعَانِي. وَوَجْهُ الْعَلَاقَةِ هُنَا أَنَّ هَذَا التَّأْلِيفَ)**

هذه جملة أولى فيها نقطة وسط الفقرة. وهذه جملة ثانية في نفس الفقرة، والحمد لله رب العالمين وصل اللهم على نبينا محمد وعلى آله وصحبه أجمعين، سبحانك اللهم وبحمدك نشهد أن لا إله إلا أنت نستغفرك ونتوب إليك.
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            docx_path = Path(tmpdir) / "mid_period.docx"
            create_docx(md, docx_path)
            report = verify_docx(docx_path)
            mid_issues = [i for i in report.issues if i.code == "MID_PARAGRAPH_PERIOD"]
            # Must NOT flag paragraph 3 (the bold Matn block), MUST flag paragraph 4 (the explanation)
            self.assertEqual(len(mid_issues), 1)
            self.assertEqual(mid_issues[0].paragraph_index, 4)

    def test_ellipsis_allowed_only_in_standalone_poetry_not_inline_prose(self):
        md = """بسم الله الرحمن الرحيم
المادة: المنطق (السلم المنورق)
2026-10-17

**(فَهَاكَ مِنْ أُصُولِهِ قَوَاعِدَا ... تَجْمَعُ مِنْ فُنُونِهِ فَوَائِدَا)**

فهذا عليه رونق الخط وحده ... وهذا عليه رونق الخط والملك

**(والمرونق: المزين، قال الشاعر: فهذا عليه رونق الخط وحده ... وهذا عليه رونق الخط والملك)**

وهنا شرح فيه إعادة قراءة inline (وَأَنْ يَكُونَ نَافِعًا لِلْمُبْتَدِي ... بِهِ إِلَى الْمُطَوَّلَاتِ يَهْتَدِي) أو توقف ... في وسط الكلام، والحمد لله رب العالمين وصل اللهم على نبينا محمد وعلى آله وصحبه أجمعين، سبحانك اللهم وبحمدك نشهد أن لا إله إلا أنت نستغفرك ونتوب إليك.
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            docx_path = Path(tmpdir) / "ellipsis.docx"
            create_docx(md, docx_path)
            report = verify_docx(docx_path)
            el_issues = [i for i in report.issues if i.code == "ELLIPSIS_FORBIDDEN"]
            # P3 (bold matn poetry) and P4 (standalone shahid poetry) are valid;
            # P5 (prose + poetry merged in one bold block) and P6 (inline prose) are invalid
            self.assertEqual([i.paragraph_index for i in el_issues], [5, 6])

    def test_detects_forbidden_punctuation_and_izhan_with_nun(self):
        md = """بسم الله الرحمن الرحيم
المادة: المنطق (السلم المنورق)
2026-10-17

نقول إذن هذا الأمر واضح, أليس كذلك? [نعم]، والحمد لله رب العالمين وصل اللهم على نبينا محمد وعلى آله وصحبه أجمعين، سبحانك اللهم وبحمدك نشهد أن لا إله إلا أنت نستغفرك ونتوب إليك.
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            docx_path = Path(tmpdir) / "orth.docx"
            create_docx(md, docx_path)
            report = verify_docx(docx_path)
            codes = [i.code for i in report.issues if i.severity == Severity.ERROR]
            self.assertIn("ORTHOGRAPHY_IZHAN_NUN", codes)
            self.assertIn("FORBIDDEN_PUNCTUATION", codes)


class TestVerifyDocxDialectAndDialogue(unittest.TestCase):
    def test_loads_dialect_replacements_dynamically_from_dialect_rules_md(self):
        rules = load_dialect_replacements()
        targets = {target for _, target in rules}
        # Entries from dialect-rules.md table that were previously omitted in hardcoded list
        self.assertIn("معانا", targets)
        self.assertIn("ييجي", targets)
        self.assertIn("اتنين", targets)
        self.assertIn("احنا", targets)
        self.assertIn("كدا", targets)
        self.assertIn("مفيش", targets)
        self.assertIn("ثاني", targets)
        # Bracketed placeholder row '| [اسم حاضر / طالب] | **فلان** |' must not compile spurious patterns
        self.assertNotIn("فلان", targets)
        for pat, _ in rules:
            self.assertNotIn("طالب", pat.pattern)

    def test_loads_dialect_replacements_from_backtick_free_format(self):
        backtick_free_md = """# Egyptian Colloquial Normalization Dictionary

| Spoken / Raw Phonetic | Mandatory Standardized Form | Grammatical & Orthographic Notes |
| :--- | :--- | :--- |
| كده | **كدا** | Terminal alif maqsura |

## Colloquial Negation Rules

- **Fused Negation Particles**: Single connected word: **مفيهوش**، **مالهاش**، **ملوش**، **مفيش**، **مكانوش**، **ميقفوش**.
- **Compound Verb Negation**: Write ما + فعل + ش as separate particles: **ما جتش**، **ما حصلش**، **ما حدش**.
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            rules_file = Path(tmpdir) / "dialect-rules.md"
            rules_file.write_text(backtick_free_md, encoding="utf-8")
            rules = load_dialect_replacements(rules_file)
            targets = {target for _, target in rules}
            self.assertIn("كدا", targets)
            self.assertIn("مفيهوش", targets)
            self.assertIn("ملوش", targets)
            self.assertIn("مفيش", targets)
            self.assertIn("مكانوش", targets)
            self.assertIn("ميقفوش", targets)
            self.assertIn("ما جتش", targets)
            self.assertIn("ما حصلش", targets)
            self.assertIn("ما حدش", targets)
            # Check that fused particles (including مالهاش) are not split by the general compound verb negation rule
            for pat, target in rules:
                if target == r"ما \1ش":
                    self.assertIsNone(pat.search("مافيهوش"))
                    self.assertIsNone(pat.search("مالهاش"))
                    self.assertIsNotNone(pat.search("ماكتبش"))

    def test_detects_unnormalized_egyptian_dialect_and_salawat(self):
        md = """بسم الله الرحمن الرحيم
المادة: المنطق (السلم المنورق)
2026-10-17

دعتنا إن إحنا ندرس المنطق كده عشان إنت تعرف ازاى برضو مافيش مشكلة وعلي طول وماانامش وهو معنا لما يجي اثنين وكان فيه كلام تاني وقال النبي عليه الصلاة والسلام، والحمد لله رب العالمين وصل اللهم على نبينا محمد وعلى آله وصحبه أجمعين، سبحانك اللهم وبحمدك نشهد أن لا إله إلا أنت نستغفرك ونتوب إليك.
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            docx_path = Path(tmpdir) / "dialect.docx"
            create_docx(md, docx_path)
            report = verify_docx(docx_path)
            dialect_issues = [i for i in report.issues if i.code == "DIALECT_UNNORMALIZED"]
            self.assertGreaterEqual(len(dialect_issues), 10)
            self.assertTrue(any("تاني" in i.message and "ثاني" in i.message for i in dialect_issues))
            codes = [i.code for i in report.issues]
            self.assertIn("SALAWAT_UNNORMALIZED", codes)

    def test_detects_dialogue_and_inaudible_violations(self):
        md = """بسم الله الرحمن الرحيم
المادة: المنطق (السلم المنورق)
2026-10-17

الشيخ: هذا كلام الشيخ.

طالب1: سؤال أول؟

طالب: (صوت غير مسموع).

طالب: كلمة صوت غير مسموع.

طالب: سؤال بدون علامة ترقيم في الآخر

والحمد لله رب العالمين وصل اللهم على نبينا محمد وعلى آله وصحبه أجمعين، سبحانك اللهم وبحمدك نشهد أن لا إله إلا أنت نستغفرك ونتوب إليك.
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            docx_path = Path(tmpdir) / "dialogue.docx"
            create_docx(md, docx_path)
            report = verify_docx(docx_path)
            codes = [i.code for i in report.issues if i.severity == Severity.ERROR]
            self.assertIn("SHEIKH_PREFIX_FORBIDDEN", codes)
            self.assertIn("STUDENT_NUMBERING_FORBIDDEN", codes)
            self.assertIn("INAUDIBLE_COMPLETE_PARENS_FORBIDDEN", codes)
            self.assertIn("INAUDIBLE_PARTIAL_PARENS_MISSING", codes)
            self.assertIn("STUDENT_TERMINAL_PUNCTUATION_MISSING", codes)

    def test_detects_unanonymized_attendee_names_while_allowing_fulan_titles_joha_and_hadiths(self):
        leaked_md = """بسم الله الرحمن الرحيم
المادة: رياض الصالحين
2026-10-22

طيب أخوكم معاذ بيسأل عن الاستفهام الإنكاري.

يبقى حتى لو آخر واحد كويس برضه، ولا إيه يا خالد؟

طيب أخوكم أبو معاذ بيسأل عن الحديث.

ماشي يا أبا معاذ؟

إيه يا خالد هنفصله ولا إيه؟

طيب أخوكم الوليد قال كلامًا مفيدًا، والحمد لله رب العالمين وصل اللهم على نبينا محمد وعلى آله وصحبه أجمعين، سبحانك اللهم وبحمدك نشهد أن لا إله إلا أنت نستغفرك ونتوب إليك.
"""
        clean_md = """بسم الله الرحمن الرحيم
المادة: رياض الصالحين
2026-10-22

طيب أخوكم فلان بيسأل، وأخوكم الشيخ فلان قال كذا، وأخوكم أبو فلان سأل، وولا إيه يا فلان؟ وماشي يا دكتور فلان، وماشي يا أبا فلان؟ وإيه يا فلان هنفصله ولا إيه؟ وتعدد إيه يا أبو تعدد؟ وأخونا الصعيدي زمان قال كذا، وإيه يا جحا ما جبتش؟ وماشي يا سيدي، وقال النبي صلى الله عليه وسلم: "يَا مُعَاذُ أَتَدْرِي مَا حَقُّ اللَّهِ عَلَى الْعِبَادِ"، ولما نقول مثلًا: زيد ضرب عمرو، والحمد لله رب العالمين وصل اللهم على نبينا محمد وعلى آله وصحبه أجمعين، سبحانك اللهم وبحمدك نشهد أن لا إله إلا أنت نستغفرك ونتوب إليك.
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            leaked_docx = Path(tmpdir) / "leaked_names.docx"
            create_docx(leaked_md, leaked_docx)
            rep_bad = verify_docx(leaked_docx)
            leak_paras = [i.paragraph_index for i in rep_bad.issues if i.code == "ATTENDEE_NAME_UNANONYMIZED"]
            self.assertEqual(leak_paras, [3, 4, 5, 6, 7, 8])

            clean_docx = Path(tmpdir) / "clean_names.docx"
            create_docx(clean_md, clean_docx)
            rep_ok = verify_docx(clean_docx)
            self.assertTrue(rep_ok.passed, f"Expected anonymized & non-attendee names to pass, got: {rep_ok.issues}")

    def test_loads_attendee_anonymization_ssot_dynamically_from_dialect_rules_md(self):
        default_ssot = load_attendee_anonymization_rules()
        self.assertEqual(default_ssot.exempt_names, frozenset({"زيد", "عمرو", "بكر", "هند", "جحا", "إبراهيم"}))
        self.assertTrue({"أبو", "أبا"}.issubset(default_ssot.kunya_prefixes))
        self.assertTrue({"الشيخ", "شيخ", "الدكتور", "دكتور"}.issubset(default_ssot.title_prefixes))

        custom_rules_md = """# Egyptian Colloquial Normalization Dictionary

| Spoken / Raw Phonetic | Mandatory Standardized Form | Grammatical & Orthographic Notes |
| :--- | :--- | :--- |
| [اسم حاضر / طالب] | **فلان** | Anonymize attendee personal names |

## Attendee Anonymization (فلان)

- **Preserved Titles & Kunyas**: Retain prefixes before **فلان**: أخوكم فلان، يا نقيب فلان، أبو فلان.
- **Preserved Non-Attendee Names**: Retain placeholders (أشعب، دعد).
"""
        doc_md = """بسم الله الرحمن الرحيم
المادة: رياض الصالحين
2026-10-22

إيه يا أشعب عامل إيه؟ وماشي يا نقيب فلان.

وماشي يا نقيب طارق؟

وإيه يا جحا ما جبتش؟ والحمد لله رب العالمين وصل اللهم على نبينا محمد وعلى آله وصحبه أجمعين، سبحانك اللهم وبحمدك نشهد أن لا إله إلا أنت نستغفرك ونتوب إليك.
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            rules_path = Path(tmpdir) / "custom_dialect_rules.md"
            rules_path.write_text(custom_rules_md, encoding="utf-8")
            docx_path = Path(tmpdir) / "ssot_attendee.docx"
            create_docx(doc_md, docx_path)

            rep = verify_docx(docx_path, dialect_rules_path=rules_path)
            leak_paras = [i.paragraph_index for i in rep.issues if i.code == "ATTENDEE_NAME_UNANONYMIZED"]
            self.assertEqual(leak_paras, [4, 5])

    def test_flags_nam_tafaddal_vocatives_and_al_akh_kinship_while_passing_fulan_forms(self):
        rules = load_attendee_anonymization_rules()
        self.assertTrue({"الأخ", "الأخت"}.issubset(rules.kinship_nouns))

        leaking_phrases = [
            "نعم يا معاذ؟",
            "تفضل يا معاذ",
            "الأخ معاذ سأل",
            "الأخت سارة سألت",
        ]
        for phrase in leaking_phrases:
            with self.subTest(phrase=phrase):
                self.assertTrue(rules.find_leaks(phrase), f"Expected leak for: {phrase}")

        clean_phrases = [
            "نعم يا فلان؟",
            "تفضل يا فلان",
            "الأخ فلان سأل",
            "الأخت فلان سألت",
            "نعم يا سيدي",
            "نعم يا روح أمك، قال الاستواء معلوم",
            "الأخ المصري عمال يكلمه، حتى الأخ وجاي يطلب منه، فالأخ بقى قاله",
            "فالأخ بيتساءل، ولو أن الأخت بتقول للتانية، والأخ التاني برضه",
            "وبيضرب الأخ على قفاه، والجزار أخ الأخ يعني، وجبنا الأخ واعتذر له",
            "الأخ أحد هؤلاء، وبعد كدا الأخ يبقى أقل حاجة",
            "في نهاية الاحتفال نشكر الأخ إبراهيم",
        ]
        for phrase in clean_phrases:
            with self.subTest(phrase=phrase):
                self.assertEqual(rules.find_leaks(phrase), [])

    def test_docx_flags_nam_tafaddal_and_al_akh_leaks_end_to_end(self):
        leaked_md = """بسم الله الرحمن الرحيم
المادة: رياض الصالحين
2026-10-22

نعم يا معاذ؟

تفضل يا معاذ

الأخ معاذ سأل عن الحديث.
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            docx_path = Path(tmpdir) / "nam_tafaddal.docx"
            create_docx(leaked_md, docx_path)
            rep = verify_docx(docx_path)
            leak_paras = [i.paragraph_index for i in rep.issues if i.code == "ATTENDEE_NAME_UNANONYMIZED"]
            self.assertEqual(leak_paras, [3, 4, 5])

    def test_attendee_anonymization_rules_encapsulates_customizable_stopwords(self):
        rules = load_attendee_anonymization_rules()
        self.assertTrue(hasattr(rules, "kinship_stopwords"))
        self.assertTrue(hasattr(rules, "vocative_stopwords"))
        self.assertIn("الصعيدي", rules.kinship_stopwords)
        self.assertIn("سيدي", rules.vocative_stopwords)

        # Custom stopwords allow extending or overriding leak suppression per instance
        custom_kinship = rules.kinship_stopwords | {"معين"}
        custom_vocative = rules.vocative_stopwords | {"زميل"}
        custom_rules = AttendeeAnonymizationRules(
            placeholder="فلان",
            kinship_nouns=frozenset({"أخوكم", "الأخ"}),
            kunya_prefixes=frozenset({"أبو"}),
            title_prefixes=frozenset({"الشيخ"}),
            exempt_names=frozenset(),
            kinship_stopwords=custom_kinship,
            vocative_stopwords=custom_vocative,
        )

        # Without custom stopwords, "الأخ معين" leaks; with custom stopword, it's suppressed
        default_rules = AttendeeAnonymizationRules(
            placeholder="فلان",
            kinship_nouns=frozenset({"أخوكم", "الأخ"}),
            kunya_prefixes=frozenset({"أبو"}),
            title_prefixes=frozenset({"الشيخ"}),
            exempt_names=frozenset(),
        )
        self.assertTrue(default_rules.find_leaks("الأخ معين سأل"))
        self.assertEqual(custom_rules.find_leaks("الأخ معين سأل"), [])

        # Vocative custom stopword suppression
        self.assertTrue(default_rules.find_leaks("قول يا زميل"))
        self.assertEqual(custom_rules.find_leaks("قول يا زميل"), [])

    def test_flags_bare_vocatives_and_classroom_illustrations_for_known_attendees(self):
        rules = load_attendee_anonymization_rules()
        self.assertTrue({"معاذ", "طارق", "سارة"}.issubset(rules.known_attendee_names))

        # 1. Bare vocatives without conversational triggers must leak for known attendees
        bare_vocative_leaks = [
            "يا معاذ",
            "يا معاذ اسمع",
            "يا طارق",
            "يا سارة",
            "ويا معاذ",
        ]
        for phrase in bare_vocative_leaks:
            with self.subTest(phrase=phrase):
                leaks = rules.find_leaks(phrase)
                self.assertTrue(leaks, f"Expected bare vocative leak for: {phrase}")
                self.assertEqual(leaks[0][0], "vocative")

        # 2. Classroom illustrations & third-person references must leak for known attendees
        illustration_leaks = [
            "معاذ بيعمل إيه دلوقتي؟",
            "طارق بيسأل عن المسألة",
            "سارة بتسأل سؤالًا",
            "زي ما قال معاذ",
            "يعني لما نقول مثلا: معاذ بيعمل إيه دلوقتي؟",
        ]
        for phrase in illustration_leaks:
            with self.subTest(phrase=phrase):
                leaks = rules.find_leaks(phrase)
                self.assertTrue(leaks, f"Expected illustration leak for: {phrase}")
                self.assertEqual(leaks[0][0], "reference")

        # 3. Anonymized equivalents must cleanly pass without leaks
        clean_anonymized = [
            "يا فلان",
            "يا فلان اسمع",
            "فلان بيعمل إيه دلوقتي؟",
            "زي ما قال فلان",
            "يعني لما نقول مثلا: فلان بيعمل إيه دلوقتي؟",
        ]
        for phrase in clean_anonymized:
            with self.subTest(phrase=phrase):
                self.assertEqual(rules.find_leaks(phrase), [])

        # 4. Classical/historical vocatives without triggers must cleanly pass
        classical_vocatives = [
            "يا عائشة",
            "يا موسى",
            "فقال: يا عائشة",
            "وقال: يا موسى",
        ]
        for phrase in classical_vocatives:
            with self.subTest(phrase=phrase):
                self.assertEqual(rules.find_leaks(phrase), [])

        # 5. Custom known_attendee_names override
        custom_known_rules = AttendeeAnonymizationRules(
            placeholder="فلان",
            kinship_nouns=frozenset({"أخوكم"}),
            kunya_prefixes=frozenset({"أبو"}),
            title_prefixes=frozenset({"الشيخ"}),
            exempt_names=frozenset(),
            known_attendee_names=frozenset({"سلمان"}),
        )
        self.assertTrue(custom_known_rules.find_leaks("يا سلمان"))
        self.assertTrue(custom_known_rules.find_leaks("سلمان بيعمل إيه"))
        self.assertEqual(custom_known_rules.find_leaks("يا معاذ"), [])

    def test_companion_hadith_vocatives_and_patronymics_exempt_from_bare_vocative_leaks(self):
        rules = load_attendee_anonymization_rules()
        self.assertIn("معاذ", rules.known_attendee_names)

        pass_cases = [
            "«يَا مُعَاذُ، أَتَدْرِي مَا حَقُّ اللَّهِ عَلَى الْعِبَادِ»",
            '"يا معاذ"',
            "قال النبي ﷺ: يا معاذ بن جبل",
            "يا معاذَ بنَ جبلٍ",
        ]
        for phrase in pass_cases:
            with self.subTest(phrase=phrase):
                self.assertEqual(
                    rules.find_leaks(phrase),
                    [],
                    f"Expected zero leaks for companion citation: {phrase}",
                )

        flag_cases = [
            "نعم يا معاذ",
            "يا معاذ تعالى",
            "يا معاذ داخل جملة وقال: «مرحبا»",
        ]
        for phrase in flag_cases:
            with self.subTest(phrase=phrase):
                leaks = rules.find_leaks(phrase)
                self.assertTrue(
                    leaks,
                    f"Expected vocative leak for classroom phrase: {phrase}",
                )
                self.assertEqual(leaks[0][0], "vocative")

    def test_loads_known_attendee_names_from_dialect_rules_md(self):
        custom_rules_md = """# Egyptian Colloquial Normalization Dictionary

## Attendee Anonymization (فلان)

- **Preserved Titles & Kunyas**: Retain prefixes before **فلان**: أخوكم فلان، أبو فلان، الشيخ فلان.
- **Preserved Non-Attendee Names**: Retain placeholders (زيد).
- **Known Attendee Names**: Custom attendees (سلمان، بلال).
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            rules_path = Path(tmpdir) / "custom_known.md"
            rules_path.write_text(custom_rules_md, encoding="utf-8")
            rules = load_attendee_anonymization_rules(rules_path)
            self.assertEqual(rules.known_attendee_names, frozenset({"سلمان", "بلال"}))
            self.assertTrue(rules.find_leaks("يا سلمان"))
            self.assertTrue(rules.find_leaks("بلال بيعمل إيه"))
            self.assertEqual(rules.find_leaks("يا معاذ"), [])

    def test_docx_flags_bare_vocatives_and_illustrations_end_to_end(self):
        doc_md = """بسم الله الرحمن الرحيم
المادة: الفقه (عمدة السالك)
2026-10-25

يا معاذ اسمع هذا الشرح جيدًا.

معاذ بيعمل إيه دلوقتي في هذه الحالة؟

يا فلان، وفلان بيعمل إيه دلوقتي؟

فقال: يا عائشة، وقال: يا موسى، والحمد لله رب العالمين وصل اللهم على نبينا محمد وعلى آله وصحبه أجمعين، سبحانك اللهم وبحمدك نشهد أن لا إله إلا أنت نستغفرك ونتوب إليك.
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            docx_path = Path(tmpdir) / "bare_voc_and_illustrations.docx"
            create_docx(doc_md, docx_path)
            rep = verify_docx(docx_path)
            leak_paras = [i.paragraph_index for i in rep.issues if i.code == "ATTENDEE_NAME_UNANONYMIZED"]
            self.assertEqual(leak_paras, [3, 4])

    def test_load_attendee_anonymization_rules_warns_and_falls_back_on_missing_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            missing_path = Path(tmpdir) / "non_existent_rules.md"
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                rules = load_attendee_anonymization_rules(missing_path)
                self.assertTrue(any(issubclass(w.category, UserWarning) for w in caught))
                self.assertTrue(any("not found" in str(w.message) for w in caught))
                self.assertEqual(rules.kinship_nouns, BASE_KINSHIP_NOUNS)
                self.assertEqual(rules.kunya_prefixes, BASE_KUNYA_PREFIXES)
                self.assertEqual(rules.title_prefixes, BASE_TITLE_PREFIXES)
                self.assertEqual(rules.exempt_names, BASE_EXEMPT_NAMES)
                # Leak detection still catches leaks instead of being disabled
                self.assertTrue(rules.find_leaks("أخوكم معاذ بيسأل"))
                self.assertTrue(rules.find_leaks("نعم يا معاذ؟"))

    def test_load_attendee_anonymization_rules_warns_and_falls_back_on_empty_or_renamed_sections(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_rules_path = Path(tmpdir) / "renamed_dialect_rules.md"
            bad_rules_path.write_text("# Rules without expected attendee headers\n", encoding="utf-8")
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                rules = load_attendee_anonymization_rules(bad_rules_path)
                self.assertTrue(any(issubclass(w.category, UserWarning) for w in caught))
                self.assertTrue(any("empty rule set" in str(w.message) for w in caught))
                self.assertEqual(rules.kinship_nouns, BASE_KINSHIP_NOUNS)
                self.assertEqual(rules.kunya_prefixes, BASE_KUNYA_PREFIXES)
                self.assertEqual(rules.title_prefixes, BASE_TITLE_PREFIXES)
                self.assertEqual(rules.exempt_names, BASE_EXEMPT_NAMES)
                # Leak detection still catches leaks
                self.assertTrue(rules.find_leaks("أخوكم معاذ بيسأل"))
                self.assertTrue(rules.find_leaks("نعم يا معاذ؟"))


class TestVerifyDocxCoverageAndFallbackMatn(unittest.TestCase):
    def test_detects_dropped_raw_clause(self):
        raw_md = """2026-10-17 منطق.mp3
button_magic Source guide
بسم الله والحمد لله والصلاة والسلام على رسول الله، هذا هو القسم الأول من الشرح، وهذا هو القسم الثاني المهم جدا الذي شرحه الشيخ بالتفصيل الممل في الدرس، والحمد لله رب العالمين.
"""
        # Docx drops the middle clause completely
        incomplete_md = """بسم الله الرحمن الرحيم
المادة: المنطق (السلم المنورق)
2026-10-17

بسم الله والحمد لله، والصلاة والسلام على رسول الله، هذا هو القسم الأول من الشرح، والحمد لله رب العالمين وصل اللهم على نبينا محمد وعلى آله وصحبه أجمعين، سبحانك اللهم وبحمدك نشهد أن لا إله إلا أنت نستغفرك ونتوب إليك.
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            raw_path = Path(tmpdir) / "raw.md"
            raw_path.write_text(raw_md, encoding="utf-8")
            docx_path = Path(tmpdir) / "incomplete.docx"
            create_docx(incomplete_md, docx_path)

            report = verify_docx(docx_path, raw_path=raw_path)
            codes = [i.code for i in report.issues if i.severity == Severity.ERROR]
            self.assertIn("RAW_COVERAGE_DROP", codes)

    def test_detects_hallucinated_addition_not_in_raw_transcript(self):
        raw_md = """2026-10-17 منطق.mp3
button_magic Source guide
بسم الله والحمد لله والصلاة والسلام على رسول الله، هذا هو القسم الأول من الشرح الواضح.
"""
        hallucinated_md = """بسم الله الرحمن الرحيم
المادة: المنطق (السلم المنورق)
2026-10-17

بسم الله والحمد لله، والصلاة والسلام على رسول الله، هذا هو القسم الأول من الشرح الواضح.

وهذه جملة طويلة مخترعة بالكامل لم يقلها الشيخ في التسجيل الصوتي الأصلي ولا توجد في الملف الخام إطلاقا، والحمد لله رب العالمين وصل اللهم على نبينا محمد وعلى آله وصحبه أجمعين، سبحانك اللهم وبحمدك نشهد أن لا إله إلا أنت نستغفرك ونتوب إليك.
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            raw_path = Path(tmpdir) / "raw.md"
            raw_path.write_text(raw_md, encoding="utf-8")
            docx_path = Path(tmpdir) / "hallucinated.docx"
            create_docx(hallucinated_md, docx_path)

            report = verify_docx(docx_path, raw_path=raw_path)
            codes = [i.code for i in report.issues if i.severity == Severity.ERROR]
            self.assertIn("RAW_HALLUCINATION_ADDITION", codes)

    def test_matn_alignment_verifies_primary_matn_against_source(self):
        matn_md = """# متن السلم المنورق
فَهَاكَ مِنْ أُصُولِهِ قَوَاعِدَا ... تَجْمَعُ مِنْ فُنُونِهِ فَوَائِدَا
سَمَّيْتُهُ بِالسَُّلَّمِ الْمُنَوْرَقِ ... يَرْقَى بِهِ السَّامِي لِأَوْجِ الْمَنْطِقِ
"""
        valid_md = """بسم الله الرحمن الرحيم
المادة: المنطق (السلم المنورق)
2026-10-17

**(فَهَاكَ مِنْ أُصُولِهِ قَوَاعِدَا ... تَجْمَعُ مِنْ فُنُونِهِ فَوَائِدَا)**

<!-- fallback -->
**(ما له أدراج ليتوصل به إلى سطح وشبهه، قال تعالى: (أَوْ سُلَّمًا فِي السَّمَاءِ))**

هذا شرح البيت الأول، والحمد لله رب العالمين وصل اللهم على نبينا محمد وعلى آله وصحبه أجمعين، سبحانك اللهم وبحمدك نشهد أن لا إله إلا أنت نستغفرك ونتوب إليك.
"""
        corrupted_matn_md = """بسم الله الرحمن الرحيم
المادة: المنطق (السلم المنورق)
2026-10-17

**(فَهَاكَ مِنْ فُرُوعِهِ قَوَاعِدَا ... تَجْمَعُ مِنْ فُنُونِهِ فَوَائِدَا)**

هذا شرح البيت الأول، والحمد لله رب العالمين وصل اللهم على نبينا محمد وعلى آله وصحبه أجمعين، سبحانك اللهم وبحمدك نشهد أن لا إله إلا أنت نستغفرك ونتوب إليك.
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            matn_path = Path(tmpdir) / "matn.md"
            matn_path.write_text(matn_md, encoding="utf-8")

            valid_docx = Path(tmpdir) / "valid_matn.docx"
            create_docx(valid_md, valid_docx)
            rep_ok = verify_docx(valid_docx, matn_path=matn_path)
            self.assertTrue(rep_ok.passed, f"Expected valid matn docx to pass, got: {rep_ok.issues}")

            bad_docx = Path(tmpdir) / "bad_matn.docx"
            create_docx(corrupted_matn_md, bad_docx)
            rep_bad = verify_docx(bad_docx, matn_path=matn_path)
            codes = [i.code for i in rep_bad.issues]
            self.assertIn("MATN_SOURCE_MISMATCH", codes)

    def test_matn_alignment_allows_compound_fallback_sharh_with_primary_matn_tail(self):
        matn_md = """# رياض الصالحين
فَقُلْنَا: اللَّهُ أَكْبَرُ! وَذَلِكَ أَنَّكُمْ فِي أَهْلِ الشِّرْكِ كَالشَّعْرَةِ الْبَيْضَاءِ
"""
        valid_compound_md = """بسم الله الرحمن الرحيم
المادة: رياض الصالحين
2026-10-22

**(ثم بين وجه ذلك بقوله، وَذَلِكَ)**

والحمد لله رب العالمين وصل اللهم على نبينا محمد وعلى آله وصحبه أجمعين، سبحانك اللهم وبحمدك نشهد أن لا إله إلا أنت نستغفرك ونتوب إليك.
"""
        corrupted_tail_md = """بسم الله الرحمن الرحيم
المادة: رياض الصالحين
2026-10-22

**(ثم بين وجه ذلك بقوله، وَذَلِكُمْ)**

والحمد لله رب العالمين وصل اللهم على نبينا محمد وعلى آله وصحبه أجمعين، سبحانك اللهم وبحمدك نشهد أن لا إله إلا أنت نستغفرك ونتوب إليك.
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            matn_path = Path(tmpdir) / "matn.md"
            matn_path.write_text(matn_md, encoding="utf-8")

            ok_docx = Path(tmpdir) / "compound_ok.docx"
            create_docx(valid_compound_md, ok_docx)
            rep_ok = verify_docx(ok_docx, matn_path=matn_path)
            self.assertTrue(rep_ok.passed, f"Expected compound Sharh+Matn to pass, got: {rep_ok.issues}")

            bad_docx = Path(tmpdir) / "compound_bad.docx"
            create_docx(corrupted_tail_md, bad_docx)
            rep_bad = verify_docx(bad_docx, matn_path=matn_path)
            codes = [i.code for i in rep_bad.issues]
            self.assertIn("MATN_SOURCE_MISMATCH", codes)

            vowelized_prefix_md = valid_compound_md.replace(
                "ثم بين وجه ذلك بقوله، وَذَلِكَ",
                "ثُمَّ بَيَّنَ وجه ذلك بقوله، وَذَلِكَ",
            )
            bad_prefix_docx = Path(tmpdir) / "compound_bad_prefix.docx"
            create_docx(vowelized_prefix_md, bad_prefix_docx)
            rep_prefix = verify_docx(bad_prefix_docx, matn_path=matn_path)
            self.assertIn("MATN_SOURCE_MISMATCH", [i.code for i in rep_prefix.issues])

            filler = " ".join(["كَلِمَةٌ"] * 35)
            distant_matn_path = Path(tmpdir) / "distant_matn.md"
            distant_matn_path.write_text(
                f"بِدَايَةُ الْمَتْنِ {filler} وَذَلِكَ نِهَايَةُ الْمَتْنِ",
                encoding="utf-8",
            )
            distant_compound_md = """بسم الله الرحمن الرحيم
المادة: رياض الصالحين
2026-10-22

**(بِدَايَةُ الْمَتْنِ)**

**(ثم أشار الشارح بقوله، وَذَلِكَ)**

والحمد لله رب العالمين وصل اللهم على نبينا محمد وعلى آله وصحبه أجمعين، سبحانك اللهم وبحمدك نشهد أن لا إله إلا أنت نستغفرك ونتوب إليك.
"""
            distant_docx = Path(tmpdir) / "compound_distant.docx"
            create_docx(distant_compound_md, distant_docx)
            rep_distant = verify_docx(distant_docx, matn_path=distant_matn_path)
            self.assertIn("MATN_SOURCE_MISMATCH", [i.code for i in rep_distant.issues])

    def test_detects_unbolded_fallback_matn_segments_in_explanation(self):
        # Tests general trigger rules (قالوا, فإن قلت, قال الشاعر, قلت, فصل في, قال, وأيضا)
        md = """بسم الله الرحمن الرحيم
المادة: المنطق (السلم المنورق)
2026-10-17

إنما لو حبيت تعريفه قالوا: ما له أدراج ليتوصل به إلى سطح وشبهه، يبقى ده في الحس.

فإن قلت: هذا التأليف من المنطق فكيف جعلته سلما للمنطق، هو سلم ولا هو المنطق نفسه؟

يبقى المدخل للعلم جزء منه فيكون سلما بهذا المعنى، والمنطق: الصناعة، قال الشاعر:

فهذا عليه رونق الخط وحده ... وهذا عليه رونق الخط والملك

واستشهد بالآية (أَوْ سُلَّمًا فِي السَّمَاءِ)قال: وهذا النص العربي الفصيح المبين: قال الشاعر:

يبقى هنا قلنا بقى اللي هم في الخدور، قلت في آخر البيت الثاني: ولا شك أن من حفظه وفهمه يكون له سببا في الدخول في هذا الفن، يعني كدا إيه؟ فصل في جواز الاشتغال به، ده كلام يعني في حكم الاشتغال بيه، والحمد لله رب العالمين وصل اللهم على نبينا محمد وعلى آله وصحبه أجمعين، سبحانك اللهم وبحمدك نشهد أن لا إله إلا أنت نستغفرك ونتوب إليك.
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            docx_path = Path(tmpdir) / "missed_fallback.docx"
            create_docx(md, docx_path)
            report = verify_docx(docx_path)
            fb_issues = [i for i in report.issues if i.code == "UNBOLDED_FALLBACK_MATN"]
            flagged_paras = {i.paragraph_index for i in fb_issues}
            self.assertIn(3, flagged_paras)
            self.assertIn(4, flagged_paras)
            self.assertIn(5, flagged_paras)
            self.assertIn(7, flagged_paras)
            self.assertIn(8, flagged_paras)

    def test_colloquial_narrative_after_qala_does_not_trigger_unbolded_fallback_matn(self):
        md = """بسم الله الرحمن الرحيم
المادة: رياض الصالحين
2026-10-22

رايح فين يا جحا؟ قال هشتري حمار من السوق، فلما رجع بقى قالوا له إيه يا جحا ما جبتش ليه؟ ما اشتريتش الحمار ليه؟ قال: الفلوس اتسرقت إن شاء الله، يعني هو عرف بقى إن كل حاجة بمشيئة الله، والحمد لله رب العالمين وصل اللهم على نبينا محمد وعلى آله وصحبه أجمعين، سبحانك اللهم وبحمدك نشهد أن لا إله إلا أنت نستغفرك ونتوب إليك.
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            docx_path = Path(tmpdir) / "joha_story.docx"
            create_docx(md, docx_path)
            report = verify_docx(docx_path)
            fb_issues = [i for i in report.issues if i.code == "UNBOLDED_FALLBACK_MATN"]
            self.assertEqual(fb_issues, [], f"Expected zero UNBOLDED_FALLBACK_MATN on colloquial anecdote, got: {fb_issues}")


class TestVerifyDocxCLI(unittest.TestCase):
    def test_cli_returns_zero_on_valid_and_nonzero_on_invalid_with_json(self):
        import subprocess
        import json

        script_path = Path(__file__).parent.parent / "scripts" / "verify_docx.py"
        with tempfile.TemporaryDirectory() as tmpdir:
            valid_docx = Path(tmpdir) / "valid.docx"
            create_docx(VALID_MINIMAL_MD, valid_docx)

            proc_ok = subprocess.run(
                [sys.executable, str(script_path), str(valid_docx), "--json"],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(proc_ok.returncode, 0, f"Unexpected failure: {proc_ok.stdout} {proc_ok.stderr}")
            data_ok = json.loads(proc_ok.stdout)
            self.assertTrue(data_ok["passed"])
            self.assertEqual(data_ok["error_count"], 0)

            bad_docx = Path(tmpdir) / "bad.docx"
            create_docx(VALID_MINIMAL_MD.replace("إذًا", "إذن") + "\n\nهذا سطر بدون دعاء.", bad_docx)
            proc_bad = subprocess.run(
                [sys.executable, str(script_path), str(bad_docx), "--json"],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertNotEqual(proc_bad.returncode, 0)
            data_bad = json.loads(proc_bad.stdout)
            self.assertFalse(data_bad["passed"])
            self.assertGreater(data_bad["error_count"], 0)



class TestMatnAlignmentValidator(unittest.TestCase):
    def setUp(self):
        from matn_matcher import SequentialMatnMatcher
        self.SequentialMatnMatcher = SequentialMatnMatcher
        self.sample_source = (
            "إِنَّ مَبَادِئَ كُلِّ عِلْمٍ عَشَرَهْ ... "
            "الحَدُّ وَالمَوْضُوعُ ثُمَّ الثَّمَرَهْ ... "
            "وَنِسْبَةٌ وَفَضْلُهُ وَالوَاضِعْ ... "
            "وَالِاسْمُ الِاسْتِمْدَادُ حُكْمُ الشَّارِعْ ... "
            "مَسَائِلُ وَالبَعْضُ بِالبَعْضِ اكْتَفَى ... "
            "وَمَنْ دَرَى الجَمِيعَ حَازَ الشَّرَفَا"
        )

    def test_matn_alignment_validator_does_not_mutate_matcher_cursor_state(self):
        """Validating an exported segment via validator seam must not mutate matcher cursor or history."""
        matcher = self.SequentialMatnMatcher(self.sample_source, forward_lookahead=500)
        # Advance matcher cursor by matching first segment
        res = matcher.match_segment("ان مبادئ كل علم عشره")
        cursor_before = matcher.cursor
        cursor_norm_before = matcher.cursor_norm
        history_len_before = len(matcher.history)
        active_pos_before = matcher._active_norm_pos

        self.assertGreater(cursor_before, 0)

        # Validate next segment using MatnAlignmentValidator with the matcher instance
        validator = MatnAlignmentValidator(matcher)
        is_valid = validator.verify_exported_segment("الحَدُّ وَالمَوْضُوعُ ثُمَّ الثَّمَرَهْ")
        self.assertTrue(is_valid)

        # Check matcher state was NOT mutated
        self.assertEqual(matcher.cursor, cursor_before)
        self.assertEqual(matcher.cursor_norm, cursor_norm_before)
        self.assertEqual(len(matcher.history), history_len_before)
        self.assertEqual(matcher._active_norm_pos, active_pos_before)

        # Also verify via functional helper _verify_exported_matn_segment
        is_valid_func = _verify_exported_matn_segment(
            "الحَدُّ وَالمَوْضُوعُ ثُمَّ الثَّمَرَهْ",
            matcher=matcher,
            matn_source=self.sample_source,
        )
        self.assertTrue(is_valid_func)
        self.assertEqual(matcher.cursor, cursor_before)
        self.assertEqual(matcher.cursor_norm, cursor_norm_before)
        self.assertEqual(len(matcher.history), history_len_before)
        self.assertEqual(matcher._active_norm_pos, active_pos_before)

    def test_matn_alignment_validator_verifies_primary_matn_verbatim(self):
        validator = MatnAlignmentValidator(self.sample_source)
        # Verbatim segment passes
        self.assertTrue(validator.verify_exported_segment("إِنَّ مَبَادِئَ كُلِّ عِلْمٍ عَشَرَهْ"))
        # Corrupted segment fails
        self.assertFalse(validator.verify_exported_segment("إِنَّ قَوَاعِدَ كُلِّ عِلْمٍ عَشَرَهْ"))

    def test_matn_alignment_validator_compound_sharh_matn(self):
        source = "فَقُلْنَا: اللَّهُ أَكْبَرُ! وَذَلِكَ أَنَّكُمْ فِي أَهْلِ الشِّرْكِ كَالشَّعْرَةِ الْبَيْضَاءِ"
        validator = MatnAlignmentValidator(source)
        # Valid compound Sharh-Matn with unvowelled Sharh prefix and vowelled Matn tail
        self.assertTrue(validator.verify_exported_segment("ثم بين وجه ذلك بقوله، وَذَلِكَ"))
        # Vowelled Sharh prefix is rejected
        self.assertFalse(validator.verify_exported_segment("ثُمَّ بَيَّنَ وجه ذلك بقوله، وَذَلِكَ"))
        # Corrupted Matn tail is rejected
        self.assertFalse(validator.verify_exported_segment("ثم بين وجه ذلك بقوله، وَذَلِكُمْ"))

    def test_matn_alignment_validator_fallback_unvowelled_and_citations(self):
        validator = MatnAlignmentValidator(self.sample_source)
        # Unvowelled fallback outside source passes
        self.assertTrue(validator.verify_exported_segment("هذا كلام خارج المتن تماما"))
        # Fallback with inner vowelled citation inside parentheses passes
        self.assertTrue(validator.verify_exported_segment("قال تعالى: (أَوْ سُلَّمًا فِي السَّمَاءِ)"))
        # Fallback with unverified bogus outer tashkeel is rejected
        self.assertFalse(validator.verify_exported_segment("هَذَا كَلَامٌ خَارِجَ الْمَتْنِ"))

    def test_verify_exported_matn_segment_helper_requires_source_or_matcher(self):
        with self.assertRaises(ValueError):
            _verify_exported_matn_segment("كلام")


if __name__ == "__main__":
    unittest.main()
