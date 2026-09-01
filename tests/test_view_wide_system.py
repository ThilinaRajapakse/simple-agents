"""A project with many pipelines and many stores, which is what "system" in the page means.

Every fixture before this one had three pipelines at most and four stores, and both drawings
laid their contents out on a single unwrapped row. Measured in a browser on 2026-08-27 against
eight pipelines and nine stores: **four store capsules were drawn outside the system map**, from
x=-189 to x=1369 in a frame 1180 wide, and a pipeline reaching every store put **three of them
below the bottom edge of its own graph**. Nothing showed them; they were not clipped or scrolled
to, they were painted where the frame is not.

What is asserted here is that everything drawn is inside the frame that is drawn. Whether the
result reads well is a separate question, and `view_harness.mjs` running the page is what says
it survives being driven at all.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).parent
FIXTURES = HERE / "fixtures" / "view_projects"
PROJECT = FIXTURES / "wide-system"

# The two shapes the drawings lay out, by the width of the rect each is drawn as.
PIPELINE_BOX = 190
STORE_CAPSULE = 150
STORE_IN_A_GRAPH = 34  # its height; the gutter's capsules are as wide as the gutter
BUSIEST = "audit_trail"  # the pipeline in the fixture that reaches every store


def node_or_skip() -> str:
    found = shutil.which("node")
    if found is None:
        pytest.skip("no node on PATH; install Node.js to run the view's own script")
    return found


@pytest.fixture(scope="module")
def drawn(tmp_path_factory) -> dict:
    """Both drawings, as geometry, read out of the page a browser would render."""
    from simple_agents.view import generate_view

    node = node_or_skip()
    page = tmp_path_factory.mktemp("wide") / "view.html"
    generate_view(PROJECT, out=page)
    out = {}
    # The graph is measured for the pipeline that reaches every store, since the page opens
    # on the first one and that one reaches two.
    for key, which, pipe in (("sysmap", "sysmap", None), ("graph", "graph", BUSIEST)):
        done = subprocess.run(
            [node, str(HERE / "view_harness.mjs"), str(page), "--geometry", which]
            + ([pipe] if pipe else []),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if done.returncode != 0:
            pytest.fail(f"{key}: {done.stderr}")
        out[key] = json.loads(done.stdout)
    return out


def frame(held: dict) -> tuple[float, float]:
    _, _, w, h = (float(n) for n in held["viewBox"].split())
    return w, h


def outside(held: dict, width: float, height: float | None = None) -> list[dict]:
    w, h = frame(held)
    return [
        e
        for e in held["elements"]
        if e["tag"] == "rect"
        and e["w"] == width
        and (height is None or e["h"] == height)
        and (
            e["x"] < -0.5 or e["x"] + e["w"] > w + 0.5 or e["y"] < -0.5 or e["y"] + e["h"] > h + 0.5
        )
    ]


def boxes(held: dict, width: float, height: float | None = None) -> list[dict]:
    return [
        e
        for e in held["elements"]
        if e["tag"] == "rect" and e["w"] == width and (height is None or e["h"] == height)
    ]


class TestTheSystemMap:
    def test_it_draws_every_pipeline_and_every_store(self, drawn) -> None:
        held = drawn["sysmap"]
        assert len(boxes(held, PIPELINE_BOX)) == 8
        assert len(boxes(held, STORE_CAPSULE)) == 9

    def test_nothing_is_drawn_outside_the_frame(self, drawn) -> None:
        held = drawn["sysmap"]
        assert outside(held, PIPELINE_BOX) == []
        assert outside(held, STORE_CAPSULE) == []

    def test_both_rows_wrap_rather_than_running_off_the_side(self, drawn) -> None:
        """Nine stores do not fit across one row, and neither did they wrap."""
        held = drawn["sysmap"]
        rows = {round(e["y"]) for e in boxes(held, STORE_CAPSULE)}
        assert len(rows) > 1, "nine stores on one row is wider than any panel"

    def test_the_stores_sit_below_every_pipeline(self, drawn) -> None:
        held = drawn["sysmap"]
        lowest = max(e["y"] + e["h"] for e in boxes(held, PIPELINE_BOX))
        assert min(e["y"] for e in boxes(held, STORE_CAPSULE)) > lowest


class TestOnePipelinesOwnGraph:
    def test_a_store_column_taller_than_the_steps_still_fits(self, drawn) -> None:
        """`audit_trail` reaches all nine stores over two steps.

        Its frame was measured from its rows of steps alone, so the column beside them ran off
        the bottom.
        """
        held = drawn["graph"]
        capsules = [
            e for e in held["elements"] if e["tag"] == "rect" and e["h"] == STORE_IN_A_GRAPH
        ]
        assert len(capsules) == 9, f"{BUSIEST} reaches nine stores, drew {len(capsules)}"
        _, height = frame(held)
        past = [e for e in capsules if e["y"] + e["h"] > height + 0.5]
        assert not past, f"{len(past)} store(s) drawn below the frame"

    def test_the_frame_is_as_tall_as_whichever_side_is_taller(self, drawn) -> None:
        held = drawn["graph"]
        _, height = frame(held)
        lowest = max((e["y"] + e["h"] for e in held["elements"] if e["tag"] == "rect"), default=0)
        assert height >= lowest
