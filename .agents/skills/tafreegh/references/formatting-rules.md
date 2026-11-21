# Formatting Standards, Orthography & Microsoft Word Integration

## 1. Zero-Spacing Rule (Parentheses & Punctuation Attachment)

- All brackets, parentheses, and quotation marks must tightly hug internal text with zero internal whitespace:
  - Target format: **(نص المتن)** and (آية) and "حديث"
- This zero-spacing constraint strictly applies across all Arabic brackets, Quranic marks, and quote marks.

## 2. Microsoft Word Compatibility

- **Bold Tagging**: Enclose Matn occurrences in double asterisks and parentheses: **(نص المتن)**. Microsoft Word automatically parses markdown bold when pasted from modern clipboards, rendering it as native bold.
- **Paragraph Spacing**: Separate distinct paragraphs with an empty line (double newline). This ensures Word lays out paragraphs with clean, balanced spacing without overlapping.
- **Arabic Punctuation Only**: Exclusively use Arabic marks (، . : ؟ !) and standard parentheses `( )` or quotation marks `" "`.
- **Ellipsis (`...`) Scope**: Use spaced ellipsis (`...`) exclusively between the two hemistichs of a standalone poetry line: either a bolded Matn verse **(الشطر الأول ... الشطر الثاني)** or a standalone unbolded oral shahid verse quoted outside `<matn_source>` on its own line (written as الشطر الأول ... الشطر الثاني or (الشطر الأول ... الشطر الثاني)). Reserve comma-joined parentheses (الشطر الأول، الشطر الثاني) strictly for inline re-reads of previously bolded Matn verses, and represent vocal pauses, trailing phrases, and spoken hesitations with natural Arabic commas (،) or terminal punctuation (`.` / ؟).
- **Extreme Matn Punctuation Strategy**: Preserve the punctuation of the Matn source as-is without stripping punctuation before closing parentheses (e.g., ،)). This prevents cognitive conflict with the absolute Blind Literalism rule.

## 3. Orthography, Tanween & Paragraph Architecture

- **Paragraph Grouping**: Structure spoken explanations into coherent, readable paragraphs targeting 4–5 Word lines (~80–120 words per paragraph). When a continuous explanation exceeds ~100–120 words, split at natural topic transitions, rhetorical question-and-answer resets, discourse pivots (مثل: أما...، إنما...، طيب، ...، يبقى...، فبعضهم...), or right before an inline citation introducing a new sub-point, closing the preceding paragraph cleanly with `.` or an Arabic question mark (؟).
- **Paragraph-Terminal Periods (`.`) in Non-Matn Paragraphs**: Terminate every non-Matn body paragraph (both Sheikh commentary and student turns) with `.`, Arabic question mark (؟), `!`, or `:` (using `:` strictly when immediately introducing a standalone bold Matn block, block quote, or standalone poetry verse on the following line). Place full stops (`.`) strictly at the end of a paragraph (immediately before a paragraph break `^p` in Word), and keep Arabic commas (،) strictly for internal clauses within a paragraph. Question marks (؟) and exclamation marks (`!`) may appear mid-paragraph before continuing clauses. Bolded Matn blocks `**(...)**` preserve `<matn_source>` punctuation verbatim (including internal periods).
- **Minimal Disambiguation Tashkeel**: Preserve bare spoken word endings on commentary and student prose, adding minimal internal contrast harakat (ضمة، فتحة، كسرة، شدة) strictly in two disambiguation contexts: (a) when the Sheikh explicitly contrasts morphological weights, grammatical voices, or variant Qira'at/vocalizations (المرابَطة ولا المرابِطة؟، ضُمِّن فإيه؟ فضَمن، كُفِّل فكَفل، الزَبيدي / الزُبيدي، قانِت قنَت فهو قانِت); and (b) passive-voice or Form-II verbs whose unvowelized rasm is ambiguous with active Form-I (لم يُحقق، اللي حُققت، لا يُدرِّس).
- **Mandatory Final Period**: The entire file must terminate with an Arabic period (`.`) after the council expiation du'a.
- **Tanween Placement**: Tanween must always be placed on the consonant preceding the alif: شيئًا، قضاءً، شابًّا.
- **Spelling Nuances**:
  - Write إذًا strictly with tanween on the alif.
  - Write إذا with an explicit kasrah on the hamza.
  - Rigorously differentiate Hamzat Wasl (e.g., استغفار، اسم، ابن) from Hamzat Qat' (e.g., أحمد، إنما، أن).
  - Strictly distinguish Ya (ي) from Alif Maqsura (ى).

## 4. Quranic Text and Prophetic Hadiths

- **The Holy Quran**: Enclose Quranic citations within single parentheses `( )`, fully vowelized (tashkeel) according to the authentic Uthmani script, **even if the Sheikh quotes a partial fragment or single word**.
  - **Quranic Spoken Boundary Clamping**: Enclose strictly the exact Mushaf words pronounced by the Sheikh inside `( )` rather than auto-completing unuttered words, preserve spoken word or phrase repetitions verbatim in separate parentheses ((فَمَنْ زُحْزِحَ عَنِ النَّارِ)، (زُحْزِحَ عَنِ النَّارِ)), split non-adjacent fragments skipping intermediate Mushaf words into separate parentheses joined by an Arabic comma ((إِذَا تَدَايَنْتُمْ بِدَيْنٍ)، (فَاكْتُبُوهُ)), and close `)` immediately before any Sheikh verbal slip or gloss so non-Quranic words sit outside `( )` ((فَإِنَّكَ أَنْتَ) الغفور الرحيم.).
- **Consecutive Quranic Verses**:
  - **Continuous Multi-Ayah Recitation**: Enclose two or more consecutive Mushaf verses recited continuously inside a single parenthesized block separated by a spaced asterisk: (آية * آية) — e.g., (عَمَّ يَتَسَاءَلُونَ * عَنِ النَّبَإِ الْعَظِيمِ * الَّذِي هُمْ فِيهِ مُخْتَلِفُونَ) and (وَلَا تَقُولَنَّ لِشَيْءٍ إِنِّي فَاعِلٌ ذَلِكَ غَدًا * إِلَّا أَنْ يَشَاءَ اللَّهُ).
  - **Separate Citations or Paused Fragments**: Enclose non-consecutive verses or paused single-verse fragments in separate parentheses joined by an Arabic comma: (آية)، (آية) — e.g., (عَنِ النَّبَإِ)، (الْعَظِيمِ).
- **Prophetic Hadiths**: Enclose every spoken statement of the Prophet صلى الله عليه وسلم within quotation marks `" "` — including verbatim Hadiths quoted inside unvowelized Fallback Sharh blocks (**(قال النووي أيضا: قد جاء في الحديث الآخر "إن أهل الجنة 120 صفا هذه الأمة منها 80 صفا")**), short partial Hadith fragments ("ولو أن تصدق بشق تمرة"), variant riwayat or single-word lexical variants attributed to the Prophet صلى الله عليه وسلم (في رواية أخرى: "فداؤك"، في رواية: "عذبٍ"), and inline Hadiths inside commentary (splitting `"..."` around interpolated Sheikh glosses: "أما الأول فأوى إلى الله فآواه الله، وأما الثاني" الذي جلس خارج المجلس "فاستحيا فاستحيا الله منه") — while leaving non-Hadith sayings (مكتوب: الله محبة) unquoted.
- **Salawat**: Always write out in full: صلى الله عليه وسلم.

## 5. Header Architecture & Automated Metadata Extraction

- **Input Pattern Detection**: When the raw transcript begins with a filename or timestamp token (e.g., `YYYY-MM-DD [keyword].mp3`) accompanied by metadata tags (e.g., `Source guide`, `button_magic`, دليل المصدر):
  - **Date & Identity Extraction**: Extract `YYYY-MM-DD` (or the numbered lecture stem) via `lecture_identity.py`.
  - **Keyword Mapping**: Map the subject keyword to the canonical subject name using [Course Routing Map](course-routing.md) as the single source of truth.
  - **Standard Header Output**:
    ```text
    بسم الله الرحمن الرحيم
    المادة: [المادة المعتمدة فقط]
    [YYYY-MM-DD]
    ```
  - **Body Cleansing**: Completely eliminate the raw filename string and metadata tags (`.mp3`, `Source guide`, `button_magic`, دليل المصدر) from the spoken body, starting transcription cleanly from the Sheikh's opening words.
  - **Automated Dual DOCX Export**:
    - **User OneDrive File**: Exported `.docx` routed dynamically to the user's OneDrive course folder via [Course Routing Map](course-routing.md) and `lecture_identity.py`.
    - **Project Internal Baseline**: `03_AI_Outputs/[resolved_stem]_AI.md` (archived for repository verification and the continuous Diff Loop).

## 6. Dialogue & Speaker Attribution (Learned from Approved Lessons)

- **Active Dialogue Attribution**: Place every intervention, audible student reply, topic-shifting question followed by a terse Sheikh verdict (مثل: يجوز عند فاعله / لا، حسن صحيح / أنت جيت امتى؟), answer following a reading-permission prompt (أيوة يا سيدي، اتفضل، اسأل), explicit audience marker (يا شيخنا / بس كدا يا سيدنا), or listener interjection on its own line prefixed with طالب: (followed by a single space), keeping audience participation distinct from the Sheikh's speech.
- **Student Regular Weight Styling**: Render the label طالب: and student speech exclusively in regular font weight, reserving bold styling strictly for standalone Matn **(نص المتن المشكول)**.
- **Inaudible Audio Formatting**:
  - Complete Inaudible (Total Silence or Garbled ASR): format strictly without parentheses: طالب: صوت غير مسموع. Convert garbled, ungrammatical, or context-nonsensical ASR fragments from off-mic student speech and stray digits into طالب: صوت غير مسموع.
  - Partial Inaudible (Cut-off/trailing speech): format with parentheses when part of the student turn is coherent: طالب: كلمة واضحة (صوت غير مسموع).
  - Zero Hallucination Rule: When no conversational cue exists from the Sheikh, keep speech continuous in the Sheikh's paragraph so user review can insert طالب: صوت غير مسموع. in Word to train the system.
- **Distinction Criteria**:
  - Direct answers to the Sheikh, live objections, and replies to يا فلان get طالب: .
  - **Echoed Student Turn & Rapid Classroom Banter**: Treat blank lines and newline pauses in raw Gemini Notebook transcripts as microphone pauses within the Sheikh's continuous speech unless unambiguous interactive evidence indicates a student speaker. When the Sheikh asks a question, pauses, and repeats, confirms, or questions a faint 1–5 word student reply aloud (e.g., تيجي تكذيبية؟، إنكار السؤال؟، حقنا؟، سحاءُ.، جيت بدري؟، متأخر؟، العذر، يعني في شيء من العذر، ما جاش فلان، ها؟، احنا فين الأول؟، مين اللي بيقول.), emit طالب: صوت غير مسموع. on its own line for the student turn, open the Sheikh's following paragraph with the echoed phrase, and alternate every طالب: turn with an intervening Sheikh paragraph.
  - Keep self-answered pedagogical setups ending in filler-question prompts (مثل: عن الإيه؟ / بالإيه؟ / سيدنا مين؟ / يعني إيه كان هنا؟ / ده كلام الإمام مين؟ النووي.), idiomatic Sheikh illustrations (زي ما تقول...), and hypothetical debates ("تقول لي وأقول لك") continuous within the Sheikh's paragraph.
