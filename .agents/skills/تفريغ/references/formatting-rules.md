# Formatting Standards, Orthography & Microsoft Word Integration

## 1. Zero-Spacing Rule (Parentheses & Punctuation Attachment)
- All brackets, parentheses, and quotation marks must tightly hug internal text with zero whitespace:
  - Correct: `**(نص المتن)**` and `(آية)` and `"حديث"`
  - Prohibited: `**( نص المتن )**` or `( آية )`
- This zero-spacing constraint strictly applies across all Arabic brackets, Quranic marks, and quote marks.

## 2. Microsoft Word Compatibility
- **Bold Tagging**: Enclose Matn occurrences in double asterisks and parentheses: `**(نص المتن)**`. Microsoft Word automatically parses markdown bold when pasted from modern clipboards, rendering it as native bold.
- **Paragraph Spacing**: Separate distinct paragraphs with an empty line (double newline). This ensures Word lays out paragraphs with clean, balanced spacing without overlapping.
- **Arabic Punctuation Only**: Exclusively use Arabic marks `(، . : ؟ !)`. Never output English punctuation or brackets `{}` / `[]`.
- **Absolute Ban on Ellipsis (`...`)**: Never insert consecutive dots or ellipsis (`...`, `..`) to denote vocal pauses, trailing phrases, or spoken hesitations. Translate all hesitations and pause intervals into natural Arabic commas `،` or appropriate terminal punctuation (`.`, `؟`), ensuring clean, professional typography for Microsoft Word.
- **Extreme Matn Punctuation Strategy**: Preserve the punctuation of the Matn source as-is without stripping punctuation before closing parentheses (e.g., `،)`). This prevents cognitive conflict with the absolute Blind Literalism rule.

## 3. Orthography, Tanween & Paragraph Architecture
- **Paragraph Grouping**: Structure spoken explanations into coherent, readable paragraphs (4–5 lines each for complete thoughts).
- **Periods (.)**: Place periods at the end of complete semantic units and at paragraph ends.
- **Mandatory Final Period**: The entire file must terminate with an Arabic period (`.`) after the council expiation du'a.
- **Tanween Placement**: Tanween must always be placed on the consonant preceding the alif: `شيئًا`، `قضاءً`، `شابًّا`.
- **Spelling Nuances**:
  - Write `إذًا` strictly with tanween (never with nun `إذن`).
  - Write `إذا` with an explicit kasrah on the hamza.
  - Rigorously differentiate Hamzat Wasl (e.g., `استغفار`, `اسم`, `ابن`) from Hamzat Qat' (e.g., `أحمد`, `إنما`, `أن`).
  - Strictly distinguish Ya (`ي`) from Alif Maqsura (`ى`).

## 4. Quranic Text and Prophetic Hadiths
- **The Holy Quran**: Enclose Quranic citations within single parentheses `( )`, fully vowelized (tashkeel) according to the authentic Uthmani script, **even if the Sheikh quotes a partial fragment or single word**.
- **Prophetic Hadiths**: Enclose statements of the Prophet صلى الله عليه وسلم within quotation marks `" "`.
- **Salawat**: Always write out in full: `صلى الله عليه وسلم`.

## 5. Header Architecture & Automated Metadata Extraction
- **Input Pattern Detection**: When the raw transcript begins with a filename or timestamp token (e.g., `YYYY-MM-DD [keyword].mp3`, such as `2026-09-10 سيرة.mp3`) accompanied by metadata tags (e.g., `دليل المصدر`):
  - **Date Extraction**: Extract `YYYY-MM-DD`.
  - **Keyword Mapping**: Map the subject keyword to the canonical book using the Routing Table in `CONTEXT.md`:
    - `سيرة` -> `سيرة (الرحيق المختوم)`
    - `زاد` -> `زاد المعاد`
    - `دليل` أو `معاملات` -> `دليل الطالب (كتاب البيع)`
    - `توحيد` أو `فتح الباري` -> `فتح الباري (كتاب التوحيد)`
    - `رياض` -> `رياض الصالحين`
    - `أسماء` -> `الأسماء الحسنى`
    - `لب` أو `أصول` -> `لب الأصول`
    - `ديوان` -> `ديوان الشافعي`
    - `صيد` -> `صيد الخاطر`
    - `روضة` -> `شرح مختصر الروضة`
  - **Standard Header Output**:
    ```text
    بسم الله الرحمن الرحيم
    المادة: [المادة المعتمدة فقط]
    [YYYY-MM-DD]
    ```
  - **Body Cleansing**: Completely eliminate the raw filename string and metadata tags (`2026-09-10 سيرة.mp3`, `دليل المصدر`) from the spoken body, starting transcription cleanly from the Sheikh's opening words.
  - **Automated Dual DOCX Export**:
    - **User OneDrive File**: `C:\Users\L\OneDrive\1. دوري\[mapped_folder]\[YYYY-MM-DD].docx` (strictly named by date only for user's direct work).
    - **Project Internal File**: `03_مخرجات_الوورد\[YYYY-MM-DD]_[subject].docx` (descriptively named for repo archive and continuous diff loop).

## 6. Dialogue & Speaker Attribution (Learned from Approved Lessons)
- **Active Dialogue Attribution**: Every intervention, student question, or listener interjection must be placed on its own line prefixed with `طالب: `. Never merge active audience participation into the Sheikh's speech as a rhetorical monologue.
- **Prohibition of Student Bold**: The label `طالب: ` and student speech are in regular font (never bold). Bold is strictly reserved for Matn `**(نص المتن المشكول)**`.
- **Inaudible Audio Formatting**:
  - Complete Inaudible (Total Silence): format strictly without parentheses: `طالب: صوت غير مسموع.`
  - Partial Inaudible (Cut-off/trailing speech): format with parentheses: `طالب: كلمة (صوت غير مسموع).`
  - Zero Hallucination Rule: If no conversational cue exists from the Sheikh, leave merged; user inserts `طالب: صوت غير مسموع.` in Word review to train the system.
- **Distinction Criteria**:
  - Direct answers to the Sheikh, live objections, and replies to `يا فلان` get `طالب: `.
  - Pedagogical devices (questions the Sheikh immediately answers himself, hypothetical debate "تقول لي وأقول لك") remain in the Sheikh's speech without `طالب: `.
- **Anonymization of Attendee Names**: When the Sheikh addresses an attendee by their personal name (e.g. `يا أحمد`), anonymize the name to `يا فلان`.