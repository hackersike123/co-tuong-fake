import importlib.util
from pathlib import Path
import sys

import pytest

smoke_path = Path(__file__).resolve().parents[1] / "scripts" / "smoke-compose.py"
smoke_spec = importlib.util.spec_from_file_location("smoke_compose", smoke_path)
assert smoke_spec is not None and smoke_spec.loader is not None
smoke_compose = importlib.util.module_from_spec(smoke_spec)
smoke_spec.loader.exec_module(smoke_compose)


def test_smoke_cleanup_knows_room_id_when_exercise_fails_after_room_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["smoke-compose"])
    monkeypatch.setattr(
        smoke_compose,
        "seed_accounts",
        lambda _env_files: {"prefix": "test-prefix", "accounts": []},
    )
    cleaned: list[int | None] = []
    monkeypatch.setattr(
        smoke_compose,
        "remove_smoke_data",
        lambda _env_files, _prefix, room_id: cleaned.append(room_id),
    )

    async def fail_after_room_creation(_base_url, _accounts, on_room_created=None):
        if on_room_created is not None:
            on_room_created(91)
        raise RuntimeError("smoke test failed after room creation")

    monkeypatch.setattr(smoke_compose, "exercise", fail_after_room_creation)

    with pytest.raises(RuntimeError, match="after room creation"):
        smoke_compose.main()

    assert cleaned == [91]
