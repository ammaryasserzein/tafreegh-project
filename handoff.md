# وثيقة تسليم الجلسة واستئناف العمل (Session Handoff)

## 1. الحالة الراهنة للمشروع

- **الإصدار الحالي**: `v1.3.1-remediation-phase2`
- **حالة الاختبارات والتحقق**:
  - أداة الفحص `scripts/verify_repo.py`: ناجحة بنسبة 100% (`PASSED`).
  - اختبارات الوحدة: 65/65 اختباراً ناجحاً بنسبة 100% (`pytest`):
    - `tests/test_verify_repo.py`: 9/9
    - `tafreegh-skill/tests/test_export_docx.py`: 25/25
    - `tafreegh-skill/tests/test_matn_matcher.py`: 12/12
    - `tafreegh-skill/tests/test_diff_inline_matn.py`: 4/4
    - `tafreegh-skill/tests/test_export_paragraph_breaks.py`: 3/3
    - `tafreegh-skill/scripts/test_diff_cues.py`: 8/8
    - `tafreegh-skill/tests/test_read_docx.py`: 3/3
    - `tafreegh-skill/tests/test_fetch_training_data.py`: 1/1
- **المعمارية المنجزة بالكامل وفق ADR 0002**:
  - **المهمة 0 (تنظيف الملفات المنزاحة)**: نُقلت مسودات الذكاء الاصطناعي المنزاحة إلى `03_AI_Outputs/` وحُذف ملف الأرشفة القديم.
  - **المهمة 1 (تكييف ترويسة البداية)**: كاشف صريح لوسوم NotebookLM (`المصادر`، `دليل المصدر`، `Source guide`، اسم ملف الصوت) واستبعادها التام من متن الوورد ومسودة الأساس، وتوحيد الترويسة القياسية ثلاثية الأسطر عبر `standardize_transcript_header()`.
  - **المهمة 2 (الأرشفة الذرية)**: تنفيذ `archive_processed_inputs(date, keyword)` لنقل المدخلات المستهلكة آلياً إلى `processed/` وحذف مجلدات `_مقاطع/`، وتحديث `verify_repo.py` لاعتماد `processed/` كمجلد فرعي رسمي.
  - **المهمة 3 (المتن الهجين الديناميكي)**: تنفيذ `SequentialMatnMatcher` بمؤشر تتابعي وبحث أمامي (~2000 حرف) وبحث في النطاق المقروء كاملاً (0 → المؤشر) لإعادة القراءة، مع وسم `<!-- fallback -->`، وقاعدة الشك المحافظ السياقية (Sandwiched vs Isolated)، وتوليد تقرير الملخص.
  - **المهمة 4 (ضبط حلقة الفروقات لنقولات المتن)**: تنفيذ `classify_matn_diffs()` في `diff_inline_matn.py` لتصنيف الفروقات بدقة إلى `fallback_correction`، `oral_citation` (متن شفهي عارض / نقل مستقل)، و `matn_copy_error`.

---

## 2. المسار التنفيذي التالي (Next Milestone)

الآن وقد اكتملت بنية خط الإنتاج آلياً واختُبرت بـ 50 اختبار وحدة:

- **المحطة القادمة**: معالجة مسودات `02_Raw_Inputs/` المتراكمة عبر مهارة `/tafreegh`:
  - `2026-10-01 سيرة.md` (مقابل `01_Matn_Sources/2026-10-01__سيرة.md`)
  - `2026-10-01 رياض.md` (مقابل `01_Matn_Sources/2026-10-01__رياض.md`)
  - `2026-10-03 معاملات.md` (مقابل `01_Matn_Sources/2026-10-03__معاملات.md`)
  - `2026-10-03 منطق.md` (مقابل `01_Matn_Sources/2026-10-03__منطق..md`)
  - `2026-10-06 زاد.md` (مقابل `01_Matn_Sources/2026-10-06__زاد.md`)

---

## 3. Suggested Skills for Next Agent

- `/tafreegh`: لمعالجة المحاضرات الخام وإنتاج ملفات Word في OneDrive ومسودات الأساس في `03_AI_Outputs/`.
