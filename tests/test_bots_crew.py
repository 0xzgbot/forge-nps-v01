from pathlib import Path

from core.hermes.bots.crew import CREW_BY_KEY, LEGACY_HIDDEN, crew_keys
from core.hermes.bots.routines import create_routine, list_routines
from core.hermes.bots.runtime import BotRuntime, parse_mentions
from core.hermes.bots.store import BotStore
from core.hermes.produce.service import ProduceService


def test_ensure_crew_writes_bot_profiles(tmp_path: Path):
    store = BotStore(tmp_path)
    store.ensure_crew()
    for key in crew_keys():
        path = store.profile_dir(key)
        assert (path / "SOUL.md").is_file()
        assert (path / "profile.yaml").is_file()
        assert (path / "config.yaml").is_file()
        soul = (path / "SOUL.md").read_text(encoding="utf-8")
        assert f"cinesmith-crew:{key}" in soul
        meta = (path / "profile.yaml").read_text(encoding="utf-8")
        assert "hermes-bots" in meta


def test_roster_matches_tasks_and_hides_legacy(tmp_path: Path):
    store = BotStore(tmp_path)
    legacy = store.profile_dir("director_planner")
    legacy.mkdir(parents=True)
    (legacy / "SOUL.md").write_text("# old\n", encoding="utf-8")
    roster = store.list_roster()
    names = [row["name"] for row in roster]
    assert names[:6] == ["producer", "story", "script", "storyboard", "video", "editor"]
    assert "character" in names
    assert "director_planner" not in names
    hidden = store.list_roster(include_hidden=True)
    hidden_names = {row["name"] for row in hidden}
    assert "director_planner" in hidden_names
    assert any(row["hidden"] for row in hidden if row["name"] == "director_planner")


def test_produce_starts_producer_bot_chat(tmp_path: Path):
    service = ProduceService(tmp_path)
    snap = service.start("a wet city walk", profile="producer")
    assert snap["profile"] == "producer"
    assert (service.job_dir(snap["job_id"]) / "prompt.md").is_file()
    argv = service.runtime.chat_argv(
        "producer",
        tmp_path / "q.txt",
        model="local-model",
    )
    joined = " ".join(argv)
    assert "-p" in argv
    assert "producer" in argv
    assert "Bot Chat" in argv
    assert "--create-if-missing" in argv
    assert "--query-file" in joined
    assert "--provider" in argv


def test_mentions_and_routines(tmp_path: Path):
    assert parse_mentions("ask @story then @script, ignore @user") == ["story", "script"]
    store = BotStore(tmp_path)
    store.ensure_crew()
    row = create_routine(
        store.profile_dir("story"),
        "story",
        title="morning",
        prompt="Read yesterday's drafts",
        schedule="every 1d",
    )
    assert row["name"].startswith("[bot:story]")
    listed = list_routines(store.profile_dir("story"), "story")
    assert listed[0]["title"] == "morning"


def test_last_active_ignores_soul_writes(tmp_path: Path):
    store = BotStore(tmp_path)
    store.ensure_crew()
    assert store.last_active("story") == 0
    store.append_chat("story", "user", "hello")
    assert store.last_active("story") > 0


def test_legacy_keys_still_resolve():
    from core.hermes.pipeline.profile_registry import profile_label

    assert "NVIDIA" not in profile_label("director_planner")
    assert profile_label("story") == "Story"
    assert "producer" in CREW_BY_KEY
    assert "trading" in LEGACY_HIDDEN
