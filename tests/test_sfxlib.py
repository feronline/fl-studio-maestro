"""The CC0 recording library: catalogue search quality (offline) and one real download."""

import urllib.error
from pathlib import Path

import numpy as np
import pytest

from fl_maestro import render, sfx, sfxlib


def names(**kw):
    return [r["name"].lower() for r in sfxlib.search(limit=5, **kw)]


def test_catalogue_is_cc0_and_pinned():
    cat = sfxlib.catalog()
    assert len(cat["sounds"]) > 4000 and len(cat["commit"]) == 40
    assert all(p["license"] == "CC0-1.0" for p in cat["packs"].values())


@pytest.mark.parametrize("kw, word", [
    (dict(kind="coin"), "coin"),
    (dict(kind="footstep", material="grass"), "grass"),
    (dict(kind="footstep", material="wood"), "wood"),
    (dict(kind="footstep", material="snow"), "snow"),
    (dict(kind="footstep", material="sand"), "sand"),
    (dict(kind="water", variant="drop"), "drop"),
    (dict(kind="whoosh"), "swish"),
    (dict(kind="laser", style="scifi"), "laser"),
    (dict(kind="explosion"), "explo"),
    (dict(kind="ding"), "bell"),
    (dict(query="door creak"), "door"),
    (dict(query="sword"), "sword"),
])
def test_search_finds_the_right_recordings(kw, word):
    top = names(**kw)
    assert top and sum(word in n for n in top) >= 3, top


def test_unknown_query_finds_nothing():
    assert sfxlib.search("qwzxv blorp", limit=5) == []


def test_library_make_downloads_and_varies(tmp_path):
    try:
        out = sfx.make("coin", "coin", tmp_path, variations=3, seed=3)
    except sfxlib.LibraryError as exc:
        pytest.skip(f"offline: {exc}")
    if out["engine"] != "library":
        pytest.skip(out["note"])
    assert (tmp_path / "CREDITS.txt").exists()
    takes = [render.read_wav(Path(f["wav"])) for f in out["files"]]
    assert all(f["from"] for f in out["files"])
    n = min(t.shape[1] for t in takes)
    assert np.abs(takes[0][:, :n] - takes[1][:, :n]).mean() > 1e-3
