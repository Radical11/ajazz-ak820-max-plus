"""Tests for app.profiles: profile store, macro library and keymap application.

Every test redirects the store to a temp directory, so the real %APPDATA% data
is never read or written.
"""

import pytest

from app import profiles as PR
from app import protocol as P
from app import storage as S


@pytest.fixture
def store_dir(tmp_path, monkeypatch):
    root = tmp_path / "AK820Studio"
    profiles_dir = root / "profiles"
    profiles_dir.mkdir(parents=True)
    monkeypatch.setattr(S, "ROOT", str(root))
    monkeypatch.setattr(S, "PROFILES_DIR", str(profiles_dir))
    monkeypatch.setattr(PR, "PROFILES_DIR", str(profiles_dir))
    monkeypatch.setattr(PR, "MACROS_FILE", str(root / "macros.json"))
    monkeypatch.setattr(PR, "SETTINGS_FILE", str(root / "settings.json"))
    return root


@pytest.fixture
def store(store_dir):
    return PR.Store()


class FakeKB:
    """Records every call the keymap code makes instead of talking to HID."""

    def __init__(self):
        self.calls = []

    def reset_keymap(self):
        self.calls.append(("reset",))

    def assign_key(self, layer, src, dst):
        self.calls.append(("key", layer, src, dst))

    def assign_macro(self, layer, src, events, repeat):
        self.calls.append(("macro", layer, src, events, repeat))


# ── default profile and creation ───────────────────────────────────────

def test_default_profile_is_created_on_first_run(store):
    ids = [p["id"] for p in store.list_profiles()]
    assert ids == ["default"]
    d = store.get_profile("default")
    assert d["name"] == "Default"
    assert d["keymap"] == {"1": {}, "2": {}}


def test_default_profile_not_recreated_when_present(store_dir):
    first = PR.Store()
    first.save_profile({"id": "default", "name": "Custom Name"})
    second = PR.Store()
    assert second.get_profile("default")["name"] == "Custom Name"


def test_create_profile_makes_unique_slugs(store):
    a = store.create_profile("Game")
    b = store.create_profile("Game")
    c = store.create_profile("Game")
    assert a["id"] == "game"
    assert b["id"] == "game-2"
    assert c["id"] == "game-3"
    assert {p["id"] for p in store.list_profiles()} == {"default", "game", "game-2", "game-3"}


def test_create_profile_slugifies_name(store):
    p = store.create_profile("My  Cool!! Profile")
    assert p["id"] == "my-cool-profile"
    assert p["name"] == "My  Cool!! Profile"


def test_create_profile_copies_base_but_clears_apps(store):
    base = store.create_profile("Base")
    store.save_profile({**base, "apps": ["game.exe"], "lighting": {**base["lighting"], "brightness": 2}})
    copy = store.create_profile("Copy", base=base["id"])
    assert copy["apps"] == []
    assert copy["lighting"]["brightness"] == 2


# ── delete ─────────────────────────────────────────────────────────────

def test_delete_default_raises(store):
    with pytest.raises(ValueError):
        store.delete_profile("default")
    assert store.get_profile("default") is not None


def test_delete_active_profile_falls_back_to_default(store):
    p = store.create_profile("Temp")
    store.update_settings(active_profile=p["id"])
    store.delete_profile(p["id"])
    assert store.get_profile(p["id"]) is None
    assert store.settings["active_profile"] == "default"


# ── app binding ────────────────────────────────────────────────────────

def test_profile_for_app_is_case_insensitive(store):
    p = store.create_profile("Editor")
    store.save_profile({**p, "apps": ["Code.EXE"]})
    found = store.profile_for_app("CODE.exe")
    assert found is not None and found["id"] == "editor"
    assert store.profile_for_app("code.exe")["id"] == "editor"


def test_profile_for_app_no_match_returns_none(store):
    assert store.profile_for_app("unknown.exe") is None
    assert store.profile_for_app("") is None
    assert store.profile_for_app(None) is None


# ── macros ─────────────────────────────────────────────────────────────

def _macro_events(n):
    return [{"code": 4, "up": i % 2 == 1, "delay": 10} for i in range(n)]


def test_save_macro_rejects_more_than_27_events(store):
    with pytest.raises(ValueError):
        store.save_macro({"id": "big", "name": "Big", "events": _macro_events(28)})
    assert store.macro("big") is None


def test_save_macro_accepts_exactly_27_events(store):
    m = store.save_macro({"id": "max", "name": "Max", "events": _macro_events(27)})
    assert len(m["events"]) == 27
    assert store.macro("max") is not None


def test_save_macro_persists_across_store_instances(store, store_dir):
    store.save_macro({"id": "m1", "name": "Hello", "repeat": 3, "events": _macro_events(2)})
    again = PR.Store()
    m = again.macro("m1")
    assert m["name"] == "Hello" and m["repeat"] == 3 and len(m["events"]) == 2


# ── apply_keymap ───────────────────────────────────────────────────────

def test_apply_keymap_resets_first_then_sends_each_action(store, monkeypatch):
    monkeypatch.setattr(PR.time, "sleep", lambda s: None)
    store.save_macro({"id": "m1", "name": "M", "repeat": 2,
                      "events": [{"code": 4, "up": False, "delay": 10}]})
    m = store.macro("m1")
    profile = {"keymap": {
        "1": {
            "20": {"type": "key", "code": 4},
            "21": {"type": "media", "code": 0xEE},
            "22": {"type": "disabled"},
            "23": {"type": "default"},
            "24": {"type": "shortcut", "codes": [0xE0, 0x04]},
            "25": {"type": "macro", "macro_id": "m1"},
        },
        "2": {"0x17": {"type": "key", "code": 0x14}},
    }}
    kb = FakeKB()
    warnings = PR.apply_keymap(kb, profile, store)

    assert warnings == []
    assert kb.calls[0] == ("reset",)
    assert kb.calls[1:] == [
        ("key", 1, 20, 4),
        ("key", 1, 21, 0xEE),
        ("key", 1, 22, P.KEY_DISABLED),
        ("key", 1, 23, P.KEY_DEFAULT),
        ("macro", 1, 24, P.shortcut_events([0xE0, 0x04]), 1),
        ("macro", 1, 25, m["events"], 2),
        ("key", 2, 0x17, 0x14),
    ]


def test_apply_keymap_reports_unknown_action_as_warning(store, monkeypatch):
    monkeypatch.setattr(PR.time, "sleep", lambda s: None)
    profile = {"keymap": {"1": {"20": {"type": "teleport"}}, "2": {}}}
    kb = FakeKB()
    warnings = PR.apply_keymap(kb, profile, store)
    assert len(warnings) == 1
    assert "20" in warnings[0] and "teleport" in warnings[0]
    # the failing action sent nothing, but the reset still happened
    assert kb.calls == [("reset",)]


def test_apply_keymap_continues_after_failure(store, monkeypatch):
    monkeypatch.setattr(PR.time, "sleep", lambda s: None)
    profile = {"keymap": {
        "1": {"20": {"type": "macro", "macro_id": "missing"},
              "21": {"type": "key", "code": 4}},
        "2": {},
    }}
    kb = FakeKB()
    warnings = PR.apply_keymap(kb, profile, store)
    assert len(warnings) == 1 and "no longer exists" in warnings[0]
    assert ("key", 1, 21, 4) in kb.calls
