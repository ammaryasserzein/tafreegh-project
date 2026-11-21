# Egyptian Colloquial Normalization Dictionary

When Egyptian dialect expressions occur in the speaker's explanation, normalize their spelling strictly according to this canonical table:

| Spoken / Raw Phonetic | Mandatory Standardized Form | Grammatical & Orthographic Notes   |
| :-------------------- | :-------------------------- | :--------------------------------- |
| إنت / انت             | **أنت**                     | Explicit open Hamzat Qat'          |
| ازاى                  | **ازاي**                    | Terminal ya with two dots          |
| إحنا                  | **احنا**                    | Colloquial wasl alif               |
| كده                   | **كدا**                     | Terminal alif maqsura              |
| دا                    | **ده**                      | Terminal ha                        |
| واما                  | **وإما**                    | Explicit kasrah hamza              |
| ايوه / أيوه           | **أيوة**                    | Open hamza and ta marbuta          |
| أه / آه               | **اه**                      | Plain alif and ha without hamzas   |
| معنا                  | **معانا**                   | Medial alif                        |
| برضو                  | **برضه**                    | Terminal ha                        |
| علي طول               | **علطول**                   | Single connected word              |
| أمال / امال           | **أومال**                   | Hamza with dammah followed by waw  |
| يجي                   | **ييجي**                    | Double ya                          |
| ميه / مية             | **ماية**                    | Medial alif and ya                 |
| اثنين / اتنين         | **اتنين**                   | In casual spoken contexts          |
| تلاتة / ثلاثة         | **ثلاثة**                   | Preserve classical tha in numbers  |
| تاني / ثاني           | **ثاني**                    | Preserve classical tha in ordinals |
| تانية / ثانية         | **ثانية**                   | Preserve classical tha in ordinals |
| [اسم حاضر / طالب]     | **فلان**                    | Anonymize attendee personal names  |

## Preposition & Existential في vs. Pronominal فيه

- **في (Preposition & Colloquial Existential)**: Write **في** both for the standard preposition (_in / about_: في دراسة التركيبات، جه في مرة) and for the colloquial existential particle meaning _there is / there are_ (replaceable by يوجد or هناك: طب في سؤال إنكاري، لقى في واحد بيجاوب، في ناس عارفة، وفي هدايا، بس كان في مشركين).
- **فيه (Preposition + Masculine Pronoun Only)**: Write **فيه** exclusively when هاء الضمير refers back to a specific masculine antecedent (_in it / therein_, replaceable by في داخله or في هذا الشيء: السؤال فيه بشرى، السند فيه حاجة، العلم يبحث فيه، يوم القيامة وما يكون فيه).

## Attendee Anonymization (فلان)

- **Role-Independent Anonymization**: Replace every live lecture attendee's first name, full name, or classroom nickname with **فلان** across every grammatical position:
  - Direct vocative address (including ASR-truncated vocatives): يا فلان، ولا إيه يا فلان؟، يا خال -> يا فلان.
  - Clitic-prefixed coordination and prepositions: وفلان، ففلان، لفلان (e.g., أنا وفلان شركاء ... يبيعها لفلان).
  - Third-person classroom references: طيب أخوكم فلان بيسأل، الشيخ فلان، فلان جه؟، فلان شديد شوية، زي ما قال فلان.
  - Nominal logic syllogisms and hypothetical classroom examples anchored to present attendees: فلان إنسان، يعني لما نقول مثلًا: أنا وفلان، فلان بيعمل إيه دلوقتي؟
  - Live attendee names vs. classical figures: keep a live attendee's personal name anchored to **فلان** even when phonetically similar to a classical honorific (such as live attendee إسلام -> فلان rather than شيخ الإسلام، or multi-word attendee names like عبد الرحمن صابر / محمد صلاح / أحمد عكاشة -> فلان), while preserving Companions, narrators, and classical scholars (سيدنا معاذ، خالد بن الوليد، الإمام أحمد، شيخ الإسلام ابن تيمية).
- **Preserved Titles & Kunyas**: Retain relational, scholarly, or kunya prefixes before **فلان**: أخوكم فلان، الشيخ فلان، يا دكتور فلان، أبو فلان، يا أبا فلان، الأخ فلان، الأخت فلان، and suffixes such as فلان بيه.
  - Collapse multi-word attendee names and surnames into a single **فلان** while retaining the title or kunya (الشيخ عبد الرحمن صابر -> الشيخ فلان، محمد صلاح -> فلان، أحمد عكاشة -> فلان).
- **Preserved Non-Attendee Names**: Retain classical textbook hypothetical placeholders (زيد، عمرو، بكر، هند), historical or narrative figures (جحا)، the fixed ceremonial thank-you name (إبراهيم), and scholars or Companions.
- **Known Attendee Names**: Unambiguous recurring classroom names flagged automatically (معاذ، طارق، سارة، لؤي، حسني، هاني، بيدو، حامد، مصطفى، عاطف، عكاشة، محمد جمال، محمد صلاح، محمد سالم، حسن جمال، أحمد عكاشة، محمد عاطف).

## Colloquial Negation Rules

- **Fused Negation Particles**: Single connected word: **مفيهوش**، **مالهاش**، **ملوش**، **مفيش**، **مكانوش**، **ميقفوش**، **منيش**، **ماليش**، **مليش**، **ماهوش**، **مهوش**، **ماهياش**، **مهياش** (e.g., **منيش شايف**).
- **Compound Verb Negation**: Write ما + فعل + ش as separate particles: **ما جتش**، **ما حصلش**، **ما حدش**، **ما فيهاش**.

## Context-Sensitive Homographs & Bare Spoken Endings

- **Spoken mayya vs. Classical ماء ("water")**: Normalize spoken Egyptian _mayya_ (even when raw ASR classicized it as ماء) to **ماية** in colloquial speech, while retaining authentic Classical Arabic ماء (مثل: لا ماء، ماء عذب).
- **Spoken حاجة vs. Classical حاجة**: Keep colloquial phrases (مثل: في حاجة / أي حاجة) as Egyptian commentary, while retaining Classical Arabic حاجة (مثل: فلا حاجة لنا) as Classical Arabic.
- **معانا ("with us") vs. معنى ("meaning / abstract concept")**: Write **معانا** for the preposition + 1st-person plural pronoun (_with us_: هو معانا حريم هنا) and **معنى** for the noun meaning _abstract concept/meaning_ (ما هو ربنا معنى؟ يعني المحبة).
- **Temporal أما ("when") vs. Disjunctive وإما ("or / either")**: Retain open-hamza **أما** (or **لما**) for temporal _when_ (هي القدرة أما تكون واحدة) and kasrah-hamza **إما / وإما** for disjunctive _either/or_.
- **Colloquial Prepositional, Complementizer & Bare Spoken Forms**: Preserve spoken **ليه** (_for him_: هيبقى ليه في البيت), kasrah-hamza **إن** / **وإن** / **إنه** as the Egyptian colloquial complementizer after colloquial predicates (معناه إن، الظاهر إن، واضح إن، إن ده، إن هي، يعني الله من صفاته إنه يحب ... وإنه), colloquial **كإن** (_as if_, distinct from past-tense كان), authentic Egyptian lexicon items (مثل: إزازة rather than hyper-correcting to قزازة), and bare spoken endings on predicates and verbal nouns verbatim as uttered in the raw transcript (تحرز أن يقول شمال، والخطأ هنا يكون فاحش).

## Colloquial Lexicon & Verbal Markers

Colloquial markers, vocabulary, and verbal forms identifying non-classical commentary:

- **Colloquial Particles & Vocabulary**: **كدا**، **كده**، **ده**، **دا**، **دي**، **ايه**، **إيه**، **الإيه**، **ازاي**، **ازاى**، **امتى**، **ليه**، **كمان**، **احنا**، **إحنا**، **برضه**، **برضو**، **علطول**، **أومال**، **امال**، **مش**، **عشان**، **علشان**، **بقى**، **حد**، **تاني**، **قوي**، **خالص**، **يلا**، **طب**، **طيب**، **يعني**، **بتاع**، **بتوع**، **اللي**، **دلوقتي**، **شوية**، **طبعا**، **أهو**، **اهو**، **يبقى**، **ماشي**، **ولواحد**، **الفلوس**، **معدي**، **عجوزة**، **عجوزه**، **مين**، **معلش**.
- **Colloquial Verbal Forms & Prefixes**:
  - Present and continuous verbs with بـ: **بيقول**، **يقولوا**، **تلاقي**، **بقول**، **بتعرف**، **بتستعمله**، **بيمشوا**.
  - Future verbs with prefix هـ: **هشتري**.
  - Passive verbs with prefix اتـ: **اتسرق**، **اتسرقت**، **اتكسر**، **اتعمل**.
  - Colloquial narrative verbs: **خليته**، **جابه**، **جالك**، **نخليه**.
  - Volitional particles: **عاوز**، **عايز**، **عايزة**.
- **Colloquial Negation**: **مفيش**، **مافيش**، **مكانش**، **ماكانش**، **ملوش**، **منيش**.

## Laughter, Fillers, Repetitions & Affirmations

- **Laughter**: Always record as ههههه.
- **Stutters & Vocal Fillers**: Auditory hesitations (آآ، ا، أ) are stripped automatically.
- **Affirmative Fillers**: Words like نعم، صحيح، أيوة، اه must be strictly retained as part of the speech flow.
- **Spoken Word Repetition**: Retain consecutive repeated words verbatim separated by an Arabic comma: الكلمة، الكلمة (e.g., إما بمعنى الذي، الذي قدمت يداه / يعني إثبات، إثبات شيء / هو أنت مثلا، مثلا؟ / اجتهد، اجتهد). Keep fixed lexicalized colloquial adverbial reduplications space-separated without a comma (كدا كدا، واحدة واحدة، شوية شوية).
- **Cut-Off Definite Articles**: Retain a spoken cut-off definite article before a self-interruption or restart followed by an Arabic comma (e.g., لم يأتوا بها بصيغة ال، اكتبوا الفائدة، and preserve cut-off أم ال، verbatim rather than collapsing it into أومال).
