import tempfile
import unittest
from pathlib import Path
import sys
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
from verify_docx import verify_docx, Severity, load_dialect_replacements


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


if __name__ == "__main__":
    unittest.main()
