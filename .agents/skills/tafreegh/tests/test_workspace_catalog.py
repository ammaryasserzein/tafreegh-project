"""Tests for the lazy WorkspaceConfig and unified RuleCatalog seam."""

from __future__ import annotations

import os
import subprocess
import sys
import warnings
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from tafreegh.workspace_catalog import (
    AttendeeAnonymizationRules,
    CanonicalCourseEntry,
    RuleCatalog,
    WorkspaceConfig,
    resolve_runtime_context,
)


class TestWorkspaceConfig:
    def test_explicit_parameters_override_env_and_discovery(self, tmp_path: Path):
        explicit_root = tmp_path / "explicit_repo"
        explicit_od = tmp_path / "explicit_onedrive"
        explicit_routing = tmp_path / "custom_course-routing.md"
        explicit_dialect = tmp_path / "custom_dialect.md"
        explicit_template = tmp_path / "custom_Word_base.docx"

        env = {
            "TAFREEGH_PROJECT_ROOT": str(tmp_path / "env_repo"),
            "TAFREEGH_ONEDRIVE_BASE": str(tmp_path / "env_onedrive"),
            "TAFREEGH_COURSE_ROUTING_PATH": str(tmp_path / "env_course-routing.md"),
            "TAFREEGH_DIALECT_RULES_PATH": str(tmp_path / "env_dialect.md"),
            "TAFREEGH_WORD_BASE_TEMPLATE": str(tmp_path / "env_Word_base.docx"),
        }

        cfg = WorkspaceConfig.resolve(
            project_root=explicit_root,
            onedrive_base=explicit_od,
            course_routing_path=explicit_routing,
            dialect_rules_path=explicit_dialect,
            word_base_template=explicit_template,
            env=env,
        )

        assert cfg.project_root == explicit_root
        assert cfg.onedrive_base == explicit_od
        assert cfg.matn_sources_dir == explicit_root / "01_Matn_Sources"
        assert cfg.raw_inputs_dir == explicit_root / "02_Raw_Inputs"
        assert cfg.ai_outputs_dir == explicit_root / "03_AI_Outputs"
        assert cfg.training_data_dir == explicit_root / "04_Training_Data"
        assert cfg.course_routing_path == explicit_routing
        assert cfg.dialect_rules_path == explicit_dialect
        assert cfg.word_base_template == explicit_template

        with pytest.raises(FrozenInstanceError):
            cfg.project_root = tmp_path  # type: ignore[misc]

    def test_environment_overrides_take_precedence_over_discovery(self, tmp_path: Path):
        env_root = tmp_path / "env_project"
        env_od = tmp_path / "env_od"
        env_training = tmp_path / "custom_training"
        env = {
            "TAFREEGH_PROJECT_ROOT": str(env_root),
            "TAFREEGH_ONEDRIVE_BASE": str(env_od),
            "TAFREEGH_TRAINING_DATA_DIR": str(env_training),
        }

        cfg = WorkspaceConfig.resolve(env=env)

        assert cfg.project_root == env_root
        assert cfg.onedrive_base == env_od
        assert cfg.training_data_dir == env_training
        assert cfg.matn_sources_dir == env_root / "01_Matn_Sources"
        assert cfg.raw_inputs_dir == env_root / "02_Raw_Inputs"
        assert cfg.ai_outputs_dir == env_root / "03_AI_Outputs"

    def test_discovers_project_root_from_nested_cwd_and_uses_home_onedrive_default(
        self, tmp_path: Path
    ):
        repo = tmp_path / "workspace"
        nested = repo / "02_Raw_Inputs" / "nested"
        nested.mkdir(parents=True)
        (repo / "GLOSSARY.md").write_text("# Tafreegh\n", encoding="utf-8")
        local_routing = repo / ".agents" / "skills" / "tafreegh" / "references" / "course-routing.md"
        local_routing.parent.mkdir(parents=True)
        local_routing.write_text("# Course Routing Map\n", encoding="utf-8")

        cfg = WorkspaceConfig.resolve(env={}, cwd=nested)

        assert cfg.project_root == repo
        assert cfg.course_routing_path == local_routing
        assert cfg.onedrive_base == Path.home() / "OneDrive" / "1. دوري"
        assert cfg.dialect_rules_path.name == "dialect-rules.md"
        assert cfg.dialect_rules_path.is_file()

    def test_minimal_temp_project_root_falls_back_to_repo_ssot_when_absent_locally(
        self, tmp_path: Path
    ):
        minimal_root = tmp_path / "minimal_project"
        minimal_root.mkdir()

        cfg = WorkspaceConfig.resolve(project_root=minimal_root, env={})

        assert cfg.project_root == minimal_root
        assert cfg.course_routing_path.name == "course-routing.md"
        assert cfg.course_routing_path.is_file()
        assert cfg.dialect_rules_path.name == "dialect-rules.md"
        assert cfg.dialect_rules_path.is_file()

    def test_default_test_runtime_redirects_onedrive_base_away_from_live_onedrive(self):
        live_onedrive = Path.home() / "OneDrive" / "1. دوري"

        cfg = WorkspaceConfig.resolve()

        assert "TAFREEGH_ONEDRIVE_BASE" in os.environ
        assert cfg.onedrive_base == Path(os.environ["TAFREEGH_ONEDRIVE_BASE"])
        assert cfg.onedrive_base != live_onedrive
        assert cfg.onedrive_base.is_dir()

    def test_tafreegh_onedrive_base_env_redirects_workspace_and_runtime_context(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        from tafreegh.export_docx import PublicationOrchestrator
        from tafreegh.fetch_training_data import DiffLoopAnalyzer

        scratch_onedrive = tmp_path / "staging_mock_onedrive"
        live_onedrive = Path.home() / "OneDrive" / "1. دوري"
        monkeypatch.setenv("TAFREEGH_ONEDRIVE_BASE", str(scratch_onedrive))

        cfg = WorkspaceConfig.resolve()
        runtime_ws, _ = resolve_runtime_context()
        orchestrator = PublicationOrchestrator()
        analyzer = DiffLoopAnalyzer()

        assert cfg.onedrive_base == scratch_onedrive
        assert runtime_ws.onedrive_base == scratch_onedrive
        assert orchestrator.workspace.onedrive_base == scratch_onedrive
        assert analyzer.workspace.onedrive_base == scratch_onedrive
        assert cfg.onedrive_base != live_onedrive


class TestRuleCatalogRouting:
    def test_loads_canonical_course_entries_and_immutable_routing_map_from_course_routing(self):
        catalog = RuleCatalog.load()

        assert len(catalog.courses) == 12
        assert all(isinstance(c, CanonicalCourseEntry) for c in catalog.courses)
        assert isinstance(catalog.canonical_subjects, frozenset)
        assert len(catalog.routing_map) > 30

        muamalat = catalog.resolve_course("دليل")
        assert muamalat is not None
        assert muamalat.canonical_subject == "دليل الطالب (كتاب البيع)"
        assert muamalat.primary_keyword == "معاملات"
        assert muamalat.keywords == ("معاملات", "دليل")

        tawheed = catalog.resolve_course("فتح")
        assert tawheed is not None
        assert tawheed.canonical_subject == "فتح الباري (كتاب التوحيد)"
        assert tawheed.primary_keyword == "توحيد"
        assert "فتح الباري" in tawheed.keywords

        buyu = catalog.resolve_course("خثلان")
        assert buyu is not None
        assert buyu.canonical_subject == "فقه البيوع (سعد الخثلان)"
        assert catalog.routing_map["فقه_البيوع"] == "فقه البيوع (سعد الخثلان)"

        with pytest.raises(TypeError):
            catalog.routing_map["جديد"] = "اختبار"  # type: ignore[index]
        with pytest.raises(FrozenInstanceError):
            catalog.courses = ()  # type: ignore[misc]

    def test_loads_custom_and_swapped_routing_tables_and_handles_missing_routing_file(
        self, tmp_path: Path
    ):
        custom_routing = tmp_path / "course-routing.md"
        custom_routing.write_text(
            "# Course Routing Map (توجيه المتون)\n\n"
            "## توجيه المتون (Routing Map)\n\n"
            "| المادة المعتمدة | الكلمة الدلالية |\n"
            "| --- | --- |\n"
            "| **أصول الفقه** | (أصول) / (ورقات) |\n",
            encoding="utf-8",
        )
        custom_catalog = RuleCatalog.load(course_routing_path=custom_routing)
        assert custom_catalog.routing_map["أصول"] == "أصول الفقه"
        assert custom_catalog.routing_map["ورقات"] == "أصول الفقه"
        assert custom_catalog.routing_map["الورقات"] == "أصول الفقه"
        assert custom_catalog.routing_map["أصول الفقه"] == "أصول الفقه"

        missing_catalog = RuleCatalog.load(course_routing_path=tmp_path / "missing_course-routing.md")
        assert missing_catalog.courses == ()
        assert dict(missing_catalog.routing_map) == {}
        assert missing_catalog.canonical_subjects == frozenset()

    def test_resolves_onedrive_folders_from_per_row_alias_groups(self, tmp_path: Path):
        folder_names = [
            "1. الاسماء الحسنى",
            "1. رياض الصالحين",
            "1. سيرة (الرحيق المختوم)",
            "1. معاملات",
            "2. التوحيد",
            "2. لب الاصول",
            "ديوان الشافعي",
            "زاد المعاد",
            "شرح مختصر الروضة",
            "صيد الخاطر",
            "المنطق",
            "فقه البيوع (سعد الخثلان)",
        ]
        for name in folder_names:
            (tmp_path / name).mkdir()

        catalog = RuleCatalog.load()
        assert catalog.resolve_onedrive_folder("دليل", tmp_path) == tmp_path / "1. معاملات"
        assert catalog.resolve_onedrive_folder("فتح", tmp_path) == tmp_path / "2. التوحيد"
        assert catalog.resolve_onedrive_folder("سلم", tmp_path) == tmp_path / "المنطق"
        assert catalog.resolve_onedrive_folder("رحيق", tmp_path) == tmp_path / "1. سيرة (الرحيق المختوم)"
        assert catalog.resolve_onedrive_folder("الأصول", tmp_path) == tmp_path / "2. لب الاصول"
        assert catalog.resolve_onedrive_folder("لب", tmp_path) == tmp_path / "2. لب الاصول"
        assert catalog.resolve_onedrive_folder("خثلان", tmp_path) == tmp_path / "فقه البيوع (سعد الخثلان)"
        assert catalog.resolve_onedrive_folder("فقه_البيوع", tmp_path) == tmp_path / "فقه البيوع (سعد الخثلان)"
        assert catalog.resolve_onedrive_folder("تفسير", tmp_path) == tmp_path / "تفسير"
        assert catalog.resolve_onedrive_folder("", tmp_path) == tmp_path / "عام"


class TestRuleCatalogDialectAndAnonymization:
    def test_loads_dialect_markers_replacements_and_attendee_rules_from_ssot(self):
        catalog = RuleCatalog.load()

        assert isinstance(catalog.dialect_markers, frozenset)
        for marker in {
            "بتوع",
            "الفلوس",
            "اتسرق",
            "اتسرقت",
            "اتكسر",
            "اتعمل",
            "هشتري",
            "ملوش",
            "منيش",
            "ليه",
            "كمان",
            "خليته",
            "معدي",
            "عجوزة",
            "الإيه",
            "امتى",
        }:
            assert marker in catalog.dialect_markers
        assert "واحدة" not in catalog.dialect_markers

        assert isinstance(catalog.dialect_replacements, tuple)
        targets = {target for _, target in catalog.dialect_replacements}
        assert {"معانا", "ييجي", "اتنين", "احنا", "كدا", "مفيش", "ثاني"}.issubset(targets)
        assert "فلان" not in targets

        rules = catalog.attendee_rules
        assert isinstance(rules, AttendeeAnonymizationRules)
        assert rules.exempt_names == frozenset({"زيد", "عمرو", "بكر", "هند", "جحا", "إبراهيم"})
        assert "الصعيدي" in rules.kinship_stopwords
        assert "سيدي" in rules.vocative_stopwords
        assert {"معاذ", "طارق", "سارة"}.issubset(rules.known_attendee_names)

        with pytest.raises(FrozenInstanceError):
            rules.placeholder = "آخر"  # type: ignore[misc]

    def test_loads_custom_dialect_markers_replacements_and_attendee_rules(
        self, tmp_path: Path
    ):
        custom_dialect = tmp_path / "dialect-rules.md"
        custom_dialect.write_text(
            "# Custom Dialect\n\n"
            "| Spoken | Target | Notes |\n"
            "| :--- | :--- | :--- |\n"
            "| كده | **كدا** | note |\n\n"
            "## Attendee Anonymization (فلان)\n\n"
            "- **Preserved Titles & Kunyas**: أخوكم فلان، يا نقيب فلان، أبو فلان.\n"
            "- **Preserved Non-Attendee Names**: Retain (أشعب، دعد).\n"
            "- **Known Attendee Names**: Custom (سلمان، بلال).\n\n"
            "## Colloquial Negation Rules\n\n"
            "- **Fused Negation Particles**: **مفيهوش**، **مالهاش**، **ملوش**.\n"
            "- **Compound Verb Negation**: **ما جتش**، **ما حدش**.\n\n"
            "## Colloquial Lexicon & Verbal Markers\n\n"
            "- **علامة_جديدة**، **لفظ_عامي**\n",
            encoding="utf-8",
        )

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            catalog = RuleCatalog.load(dialect_rules_path=custom_dialect)

        assert caught == []
        assert catalog.dialect_markers == frozenset({"علامة_جديدة", "لفظ_عامي"})

        targets = {target for _, target in catalog.dialect_replacements}
        assert {"كدا", "مفيهوش", "ملوش", "ما جتش", "ما حدش"}.issubset(targets)
        for pat, target in catalog.dialect_replacements:
            if target == r"ما \1ش":
                assert pat.search("مافيهوش") is None
                assert pat.search("مالهاش") is None
                assert pat.search("ماكتبش") is not None

        rules = catalog.attendee_rules
        assert rules.exempt_names == frozenset({"أشعب", "دعد"})
        assert rules.known_attendee_names == frozenset({"سلمان", "بلال"})
        assert rules.find_leaks("يا سلمان")
        assert rules.find_leaks("بلال بيعمل إيه")
        assert rules.find_leaks("وماشي يا نقيب طارق؟")
        assert rules.find_leaks("يا نقيب سلمان")
        assert rules.find_leaks("إيه يا أشعب") == []

    def test_warns_and_falls_back_on_missing_or_renamed_dialect_rules(
        self, tmp_path: Path
    ):
        missing_path = tmp_path / "missing_dialect.md"
        with warnings.catch_warnings(record=True) as caught_missing:
            warnings.simplefilter("always")
            cat_missing = RuleCatalog.load(dialect_rules_path=missing_path)

        assert any(
            issubclass(w.category, UserWarning) and "not found" in str(w.message)
            for w in caught_missing
        )
        baseline = AttendeeAnonymizationRules.baseline()
        assert cat_missing.attendee_rules == baseline
        assert "كدا" in cat_missing.dialect_markers
        assert cat_missing.dialect_replacements == ()
        assert cat_missing.attendee_rules.find_leaks("أخوكم معاذ بيسأل")

        renamed_path = tmp_path / "renamed_dialect.md"
        renamed_path.write_text("# Renamed Headings Only\n", encoding="utf-8")
        with warnings.catch_warnings(record=True) as caught_renamed:
            warnings.simplefilter("always")
            cat_renamed = RuleCatalog.load(dialect_rules_path=renamed_path)

        assert any(
            issubclass(w.category, UserWarning) and "empty rule set" in str(w.message)
            for w in caught_renamed
        )
        assert cat_renamed.attendee_rules == baseline
        assert cat_renamed.attendee_rules.find_leaks("نعم يا معاذ؟")

    @staticmethod
    def _find_dialect_matches(catalog: RuleCatalog, text: str) -> list[tuple[str, str]]:
        hits: list[tuple[str, str]] = []
        for pat, target in catalog.dialect_replacements:
            m = pat.search(text)
            if m:
                suggested = m.expand(target) if "\\" in target else target
                hits.append((m.group(0), suggested))
        return hits

    def test_dialect_rules_compile_multiword_spaced_negations_and_exempt_fused_clitics(self):
        catalog = RuleCatalog.load()

        # Multi-word table entry 'علي طول' must compile with real \s+ whitespace matching
        assert self._find_dialect_matches(catalog, "نبدأ علي طول هنا") == [("علي طول", "علطول")]
        assert self._find_dialect_matches(catalog, "نبدأ علي  طول هنا") == [("علي  طول", "علطول")]

        # Both spaceless and space-separated forms of مفيش / مفيهوش must trigger
        assert self._find_dialect_matches(catalog, "مافيش مشكلة") == [("مافيش", "مفيش")]
        assert self._find_dialect_matches(catalog, "مافيهوش حاجة") == [("مافيهوش", "مفيهوش")]
        assert self._find_dialect_matches(catalog, "ما فيش مشكلة") == [("ما فيش", "مفيش")]
        assert self._find_dialect_matches(catalog, "ما فيهوش حاجة") == [("ما فيهوش", "مفيهوش")]
        assert set(self._find_dialect_matches(catalog, "ما فيش مشكلة وما فيهوش حاجة")) == {
            ("ما فيش", "مفيش"),
            ("وما فيهوش", "ومفيهوش"),
        }

        # Expanded Fused Negation Particles must stay exempt from compound verb negation splitting
        assert self._find_dialect_matches(catalog, "ماليش دعوة وماهوش موجود و ماهياش هنا") == []

    def test_dual_form_fused_negations_allow_both_spellings_and_flag_spaced_forms(self):
        catalog = RuleCatalog.load()

        for allowed in (
            "ماليش",
            "مليش",
            "ماهوش",
            "مهوش",
            "ماهياش",
            "مهياش",
            "وماليش",
            "ومليش",
            "فماهوش",
            "فمهوش",
        ):
            assert self._find_dialect_matches(catalog, f"هو {allowed} حاجة") == []

        assert self._find_dialect_matches(catalog, "ما ليش دعوة") == [("ما ليش", "ماليش")]
        assert self._find_dialect_matches(catalog, "ما هوش موجود") == [("ما هوش", "ماهوش")]
        assert self._find_dialect_matches(catalog, "ما هياش هنا") == [("ما هياش", "ماهياش")]
        assert self._find_dialect_matches(catalog, "ما فيش مشكلة") == [("ما فيش", "مفيش")]
        assert self._find_dialect_matches(catalog, "ما فيهوش حاجة") == [("ما فيهوش", "مفيهوش")]
        assert self._find_dialect_matches(catalog, "وما ليش دعوة") == [("وما ليش", "وماليش")]
        assert self._find_dialect_matches(catalog, "وما هوش موجود") == [("وما هوش", "وماهوش")]
        assert self._find_dialect_matches(catalog, "وما هياش هنا") == [("وما هياش", "وماهياش")]

    def test_attendee_rules_catch_extended_vocatives_clitics_titles_and_guard_companions(self):
        rules = RuleCatalog.load().attendee_rules
        assert rules.exempt_names == frozenset({"زيد", "عمرو", "بكر", "هند", "جحا", "إبراهيم"})
        assert {"يعني", "طيب", "بقى"}.issubset(rules.vocative_stopwords)

        # Extended vocative triggers and clause-final vocatives
        for phrase in (
            "خد يا معاذ",
            "خذ يا طارق",
            "اديله يا سعيد",
            "وصل يا سعيد",
            "لمين يا سعيد؟",
            "أخبارك إيه يا سعيد؟",
            "اصبر يا سعيد!",
        ):
            assert rules.find_leaks(phrase), f"Expected vocative leak for: {phrase}"

        # Extended known_attendee_names patterns (clitics, الشيخ, أبو, bare student intro)
        for phrase in (
            "أنا ولؤي شركاء وهنبيعها لطارق",
            "ولؤي بيعمل إيه دلوقتي؟",
            "الشيخ طارق قال حاجة",
            "أبو معاذ وصل",
            "طالب: معاذ.",
        ):
            assert rules.find_leaks(phrase), f"Expected known-attendee leak for: {phrase}"

        clitic_leaks = rules.find_leaks("أنا ولؤي ... لطارق")
        assert len(clitic_leaks) == 2

        # Stopwords, placeholders, quotes, rhetorical echo, and non-known names must pass
        for clean_phrase in (
            "فاهم يا يعني",
            "قول يا طيب",
            "إيه يا بقى؟",
            "أخبارك إيه يا فلان؟",
            "تعدد إيه يا أبو تعدد؟",
            '"يا سعيد؟"',
            "أبو عبد الرحمن سأل",
            "سعد بن معاذ قال",
            "سيدنا معاذ قال",
            "قال الإمام معاذ",
            "مسند معاذ",
            "النبي يوسف",
            "معاذ بن جبل رضي الله عنه",
            "يا معاذ رضي الله عنه",
            "معاذ رحمه الله",
            "النبي موسى عليه السلام",
            "يا سعيد بن جبير؟",
        ):
            assert rules.find_leaks(clean_phrase) == [], f"Unexpected leak for: {clean_phrase}"

        custom_rules = AttendeeAnonymizationRules(
            known_attendee_names=frozenset({"أحمد", "يوسف", "خالد", "معاذ"}),
        )
        assert custom_rules.find_leaks("الشيخ خالد")
        assert custom_rules.find_leaks("قال الإمام أحمد") == []
        assert custom_rules.find_leaks("مسند أحمد") == []
        assert custom_rules.find_leaks("النبي يوسف قال") == []

    def test_multiword_known_attendees_and_nominal_predicates(self):
        rules = RuleCatalog.load().attendee_rules

        for multi in (
            "محمد جمال",
            "محمد صلاح",
            "محمد سالم",
            "حسن جمال",
            "أحمد عكاشة",
            "محمد عاطف",
        ):
            assert multi in rules.known_attendee_names
        assert "محمد" not in rules.known_attendee_names
        assert "أحمد" not in rules.known_attendee_names
        assert "حسن" not in rules.known_attendee_names

        for leak_phrase in (
            "محمد جمال قال كدا",
            "أحمد عكاشة جه؟",
            "معاذ شديد شوية",
            "لؤي إنسان",
            "يا محمد جمال",
        ):
            assert rules.find_leaks(leak_phrase), f"Expected leak for: {leak_phrase}"

        for clean_phrase in (
            "على نبينا محمد",
            "الإمام أحمد قال",
            "حديث حسن",
            "سعد بن معاذ قال",
        ):
            assert rules.find_leaks(clean_phrase) == [], f"Unexpected leak for: {clean_phrase}"


class TestZeroImportIoAndModulePurity:
    def test_importing_all_tafreegh_modules_performs_zero_disk_reads(self):
        scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
        pkg_dir = scripts_dir / "tafreegh"
        module_names = ["tafreegh"] + sorted(
            f"tafreegh.{py_file.stem}"
            for py_file in pkg_dir.glob("*.py")
            if py_file.stem != "__init__"
        )
        probe = f"""
import builtins
import importlib
from pathlib import Path

recorded = []

def _wrap_path(name):
    orig = getattr(Path, name)
    def wrapped(self, *args, **kwargs):
        recorded.append((name, str(self)))
        return orig(self, *args, **kwargs)
    setattr(Path, name, wrapped)

for attr in ("read_text", "read_bytes", "open", "exists", "is_file", "is_dir", "iterdir", "glob", "rglob"):
    _wrap_path(attr)

orig_open = builtins.open
def wrapped_open(file, *args, **kwargs):
    s = str(file)
    if not s.endswith((".py", ".pyc", ".pyd", ".pth")):
        recorded.append(("open", s))
    return orig_open(file, *args, **kwargs)
builtins.open = wrapped_open

modules = {module_names!r}
for mod in modules:
    importlib.import_module(mod)

assert recorded == [], f"Unexpected import-time filesystem I/O: {{recorded}}"
"""
        proc = subprocess.run(
            [sys.executable, "-B", "-c", probe],
            cwd=str(scripts_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        assert proc.returncode == 0, f"stdout={proc.stdout}\nstderr={proc.stderr}"

    def test_no_hardcoded_personal_paths_and_retired_globals_absent(self):
        pkg_dir = Path(__file__).resolve().parent.parent / "scripts" / "tafreegh"
        for py_file in sorted(pkg_dir.glob("*.py")):
            content = py_file.read_text(encoding="utf-8")
            assert r"users\l" not in content.lower() and "users/l" not in content.lower(), (
                f"Hardcoded personal path found in {py_file.name}"
            )

        from tafreegh import export_docx, fetch_training_data, lecture_identity, verify_docx

        for attr in ("load_canonical_routing", "CANONICAL_ROUTING", "from_metadata"):
            assert not hasattr(lecture_identity, attr)
        for attr in (
            "CANONICAL_SUBJECT_NAMES",
            "DEFAULT_BASE_ONEDRIVE",
            "DEFAULT_PROJECT_ROOT",
            "WORD_BASE_TEMPLATE",
            "DEFAULT_DIALECT_RULES_PATH",
            "KEYWORD_FOLDER_HINTS",
            "get_onedrive_folder",
            "BASE_DIALECT_MARKERS",
            "load_dialect_markers",
            "DIALECT_MARKERS",
            "NOTEBOOKLM_HEADER_PATTERNS",
            "parse_metadata",
            "is_header_line",
            "resolve_header_line_3",
            "resolve_document_identity",
            "standardize_transcript_header",
            "is_matching_stem",
            "DEFAULT_FONT_NAME",
            "DEFAULT_FONT_SIZE",
            "set_p_rtl",
            "set_run_font",
            "_strip_hybrid_summary",
            "read_matn_source_content",
            "create_docx",
            "export_dual_copies",
        ):
            assert not hasattr(export_docx, attr)
        for attr in (
            "DIALECT_MARKERS",
            "DEFAULT_DIALECT_RULES_PATH",
            "load_canonical_routing",
            "load_dialect_replacements",
            "load_attendee_anonymization_rules",
            "AttendeeAnonymizationRules",
            "KINSHIP_GRAMMATICAL_STOPWORDS",
            "VOCATIVE_GRAMMATICAL_STOPWORDS",
            "BASE_KINSHIP_NOUNS",
            "BASE_KUNYA_PREFIXES",
            "BASE_TITLE_PREFIXES",
            "BASE_KNOWN_ATTENDEE_NAMES",
            "BASE_EXEMPT_NAMES",
            "docx",
            "qn",
            "_is_run_bold",
            "_is_centered",
        ):
            assert not hasattr(verify_docx, attr)
        for attr in (
            "ONEDRIVE_BASE",
            "PROJECT_ROOT",
            "TRAINING_DATA_DIR",
            "AI_OUTPUTS_DIR",
            "RAW_INPUTS_DIR",
            "_find_ai_baseline",
        ):
            assert not hasattr(fetch_training_data, attr)

    def test_lecture_identity_decoupled_from_workspace_catalog(self):
        scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
        probe = """
import sys
from tafreegh.lecture_identity import (
    LectureIdentity,
    is_header_line,
    match_canonical_subject,
    resolve_document_identity,
    standardize_transcript_header,
)

assert "tafreegh.workspace_catalog" not in sys.modules
ident = LectureIdentity.from_text("2026-11-01 رياض.mp3\\nالحمد لله")
assert ident.date == "2026-11-01"
assert ident.keyword == "رياض"
assert match_canonical_subject("رياض", {"رياض": "رياض الصالحين"}) == ("رياض", "رياض الصالحين")
assert is_header_line("Source guide")
resolved = resolve_document_identity("2026-11-01 رياض.mp3\\nالحمد", routing_map={"رياض": "رياض الصالحين"})
assert resolved.subject_name == "رياض الصالحين"
clean = standardize_transcript_header("Source guide\\n2026-11-01 رياض.mp3\\n\\nالحمد", routing_map={"رياض": "رياض الصالحين"})
assert clean.startswith("بسم الله الرحمن الرحيم\\nالمادة: رياض الصالحين\\n2026-11-01")
assert "tafreegh.workspace_catalog" not in sys.modules
"""
        proc = subprocess.run(
            [sys.executable, "-B", "-c", probe],
            cwd=str(scripts_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        assert proc.returncode == 0, f"stdout={proc.stdout}\nstderr={proc.stderr}"

    def test_resolve_runtime_context_uses_workspace_and_catalog(self, tmp_path: Path):
        routing_md = tmp_path / "course-routing.md"
        routing_md.write_text(
            "## توجيه المتون (Routing Map)\n\n"
            "| الكلمة الدلالية | المادة المعتمدة | المتن ومصدره |\n"
            "| --- | --- | --- |\n"
            "| (مخصص) | **مادة مخصصة** | متن |\n",
            encoding="utf-8",
        )
        rules_md = tmp_path / "dialect-rules.md"
        rules_md.write_text(
            "## Attendee Anonymization (فلان)\n"
            "- **Preserved Titles & Kunyas**: أخوكم فلان، أبو فلان، الشيخ فلان.\n"
            "- **Preserved Non-Attendee Names**: (زيد).\n"
            "## Colloquial Lexicon & Verbal Markers\n"
            "- **مخصصة**\n",
            encoding="utf-8",
        )
        ws = WorkspaceConfig.resolve(
            project_root=tmp_path,
            course_routing_path=routing_md,
            dialect_rules_path=rules_md,
            env={},
        )
        resolved_ws, resolved_cat = resolve_runtime_context(workspace=ws)
        assert resolved_ws is ws
        assert resolved_cat.canonical_subjects == frozenset({"مادة مخصصة"})
        assert resolved_cat.dialect_markers == frozenset({"مخصصة"})

        override_cat = RuleCatalog(dialect_markers=frozenset({"علامة"}))
        same_ws, same_cat = resolve_runtime_context(workspace=ws, catalog=override_cat)
        assert same_ws is ws
        assert same_cat is override_cat


