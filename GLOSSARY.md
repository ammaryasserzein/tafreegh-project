# Tafreegh (تفريغ الدروس الشرعية)

Scholarly transcription and canonical-alignment pipeline for Arabic Islamic lectures in The Curriculum, converting raw automated drafts into publication-ready deliverables.

## Language

**The Curriculum** (الدوري):
The recurring Islamic lecture series delivered by Sheikh Osama, where each course corresponds to a dedicated canonical text and delivery destination.
_Avoid_: The program, lecture series, subject list, Al-Dawri

**Blind Literalism**:
The core transcription principle: copy matn text exactly as it appears in the canonical source, preserving every diacritic, orthographic mark, and footnote marker without alteration — even if the speaker mispronounces a word.
_Avoid_: Faithful copying, exact transcription

**Matn Source**:
The per-lecture vowelized canonical text the Sheikh reads from, extracted verbatim from the relevant pages of the source book.
_Avoid_: Reference text, source file, book file

**Primary Mode**:
Matn matching mode that treats the Matn Source as absolute authority, replacing identified spoken readings with the canonical text and its full tashkeel.
_Avoid_: Standard Mode, Branch A, normal mode

**Fallback Mode**:
Matn matching mode used when no Matn Source is available. Reading boundaries are detected via linguistic cues (fusha vs colloquial shift), and Matn is transcribed without tashkeel.
_Avoid_: Single-input mode, Branch B, no-matn mode

**Dynamic Fallback Interleaving**:
Hybrid matching strategy for an incomplete Matn Source, applying Primary Mode to passages present in the source and switching to Fallback Mode for spoken book passages absent from it.
_Avoid_: Hybrid Mode, mixed mode, partial matching

**Fallback Correction**:
A Diff Loop classification for reviewer edits to passages processed in Fallback Mode, distinguished from canonical copy errors to preserve learning signal fidelity.
_Avoid_: Fallback diff, correction type

**Sequential Cursor**:
The active reading position tracked within the Matn Source during alignment, advancing across matched passages with forward look-ahead and full-range look-behind for skips and re-reads.
_Avoid_: Read pointer, position marker

**Markdown Leakage**:
A transcription failure mode in which non-semantic markup characters from formatting instructions (such as backticks or code fences) appear literally in the produced lecture text.
_Avoid_: Prompt pollution, syntax leakage, literal backticks

**Numbered Lecture Stem**:
A sequential lecture identifier used for undated courses instead of a Gregorian calendar date, pairing mirrored lecture numbers with the course's canonical keyword token to align a lecture's raw draft and Matn Source.
_Avoid_: Date stem, unnumbered lecture, arbitrary filename

**Lecture Identity**:
The canonical identifying record of a single lecture — combining its date or sequential lecture number, course keyword, canonical subject name, and stem — that unifies document headers, course routing, and artifact pairing.
_Avoid_: Identity primitives, metadata tuple, stem dict

**Known Cue**:
A Sheikh utterance pattern that reliably signals an inaudible student turn, triggering proactive insertion of طالب: صوت غير مسموع. at a thought boundary and refined continuously via the Diff Loop.
_Avoid_: Trigger phrase, prompt word, signal

**Rhetorical Suffix**:
A sentence-final particle (ها؟ or إيه؟) the Sheikh uses as a pedagogical device to prompt class engagement rather than a genuine student-turn boundary, excluded from Known Cue nomination in the Diff Loop.
_Avoid_: Excluded cue, blacklisted cue, suppressed phrase

**Anchor Expiry**:
Decay of a bolded Matn block's reference status after an extended stretch of commentary or a mid-lecture break, turning subsequent clause re-reads that resume explanation back into standalone primary anchors.
_Avoid_: Distant bolding, page-distance rule, re-bold threshold

**Attendee Anonymization**:
Substitution of فلان for any live lecture participant's personal name across all grammatical positions while retaining titles, kunyas, classical textbook placeholders, and historical figures.
_Avoid_: Student masking, vocative replacement, name redaction

**Echoed Student Turn**:
An inaudible attendee utterance whose words are inferred only because the Sheikh repeats them aloud with questioning or evaluative intonation.
_Avoid_: Repeated student answer, guessed student turn

**Seam Repetition**:
A consecutive word repetition straddling the boundary between the final token of a book reading and the opening token of the Sheikh's immediate lexical gloss.
_Avoid_: Boundary duplicate, split repetition

**Compound Sharh-Matn**:
A single bold block preserving an unvowelized commentator lead-in ending in بقوله، / في قوله، / قوله: flowing directly into a vowelized canonical Matn clause from the primary text.
_Avoid_: Sharh-to-Matn Continuity, compound blocks, hybrid Sharh-Matn

**Conservative Doubt**:
The classification boundary requiring unambiguous linguistic or positional evidence before isolating an unmatched Classical Arabic passage as a book reading rather than keeping it inside commentary prose.
_Avoid_: Aggressive matching, strict doubt, fallback guessing

**Sandwiched Context**:
Positional evidence where an unmatched Classical Arabic passage is bounded immediately before and after by verified Primary Mode matches from the same lecture's text.
_Avoid_: Gap context, surrounding matches

**Oral Citation** (متن شفهي عارض):
A short canonical verse, Hadith, or classical quote spoken from memory outside the lecture's primary text and elevated to standalone Matn during human review.
_Avoid_: Spoken quote, side citation, unscripted matn

**Diff Loop**:
The continuous-learning feedback cycle that compares archived AI baselines against human-reviewed deliverables to classify edits, discover dialect or cue rules, and expand golden benchmarks.
_Avoid_: Training loop, feedback cycle, word diff
