"""What the page is legible at: its colours, its type sizes, and the lines in its drawings.

An unreadable page goes unused, and none of this was checked. Measured in a real
browser on 2026-08-27, against the page as it then stood: the graph was scaled to 0.78 of its
size on a 1440 screen so its 9.5px labels rendered at 7.4px, `--faint` sat at 3.85:1 on dark
and 2.61:1 on light against a 4.5:1 requirement, and the lines a reader follows from step to
step were drawn in the border colour at 1.3:1.

The floors here are the ones that measurement produced. Text is held to WCAG AA's 4.5:1, and a
line in a drawing to 3:1, which is what that standard asks of a shape rather than a letter.
The palettes are parsed out of the stylesheet, so a new theme is checked by being added.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

TEMPLATE = (
    Path(__file__).parent.parent / "src" / "simple_agents" / "view" / "template.html"
).read_text(encoding="utf-8")

# The smallest type in either drawing. Below this a label stops being readable at arm's length,
# and the drawing is no longer allowed to scale far enough to take it under.
TYPE_FLOOR = 11
TEXT_CONTRAST = 4.5
LINE_CONTRAST = 3.0


def channel(value: float) -> float:
    value /= 255
    return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4


def luminance(colour: str) -> float:
    hexed = colour.lstrip("#")
    r, g, b = (int(hexed[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(one: str, other: str) -> float:
    a, b = luminance(one) + 0.05, luminance(other) + 0.05
    return round(max(a, b) / min(a, b), 2)


def palettes() -> dict[str, dict[str, str]]:
    """Every theme in the stylesheet, by name, with its tokens.

    ``system`` is the bare ``:root``, which is what a reader sees before choosing one.
    """
    found: dict[str, dict[str, str]] = {}
    for head, body in re.findall(r"(:root(?:\[data-theme=\"[a-z]+\"\])?)\{([^}]*)\}", TEMPLATE):
        name = re.search(r'data-theme="([a-z]+)"', head)
        tokens = dict(re.findall(r"--([a-z-]+):(#[0-9A-Fa-f]{6})", body))
        if tokens:
            found[name.group(1) if name else "system"] = tokens
    return found


PAIRS = [
    ("ink", "surface", TEXT_CONTRAST),
    ("ink", "ground", TEXT_CONTRAST),
    ("ink", "sunk", TEXT_CONTRAST),
    ("muted", "surface", TEXT_CONTRAST),
    ("muted", "ground", TEXT_CONTRAST),
    ("faint", "surface", TEXT_CONTRAST),
    ("faint", "ground", TEXT_CONTRAST),
    ("accent", "surface", TEXT_CONTRAST),
    ("accent", "accent-soft", TEXT_CONTRAST),
    ("attention", "surface", TEXT_CONTRAST),
    ("note", "surface", TEXT_CONTRAST),
    ("edge", "surface", LINE_CONTRAST),
    ("edge", "sunk", LINE_CONTRAST),
    ("edge-soft", "surface", LINE_CONTRAST),
]


class TestEveryPaletteIsReadable:
    def test_the_stylesheet_carries_the_themes_the_picker_offers(self) -> None:
        block = re.search(r"const THEMES = \[(.*?)\];", TEMPLATE, re.S).group(1)
        offered = set(re.findall(r'\["([a-z]+)", "[A-Z]', block))
        assert {"paper", "dawn", "forest", "slate", "midnight"} <= offered
        assert offered <= set(palettes())

    @pytest.mark.parametrize("theme", sorted(palettes()))
    def test_it_carries_every_token_the_page_draws_with(self, theme: str) -> None:
        held = palettes()[theme]
        for token, _, _ in PAIRS:
            assert token in held, f"{theme} declares no --{token}"

    @pytest.mark.parametrize("theme", sorted(palettes()))
    def test_nothing_a_reader_meets_is_below_its_floor(self, theme: str) -> None:
        held = palettes()[theme]
        under = [
            (f"{fg} on {bg}", contrast(held[fg], held[bg]), floor)
            for fg, bg, floor in PAIRS
            if contrast(held[fg], held[bg]) < floor
        ]
        assert not under, f"{theme}: {under}"


class TestTheDrawingsType:
    def test_nothing_in_either_drawing_is_written_below_the_floor(self) -> None:
        # Two forms: the attribute an `el()` call passes, and the one a drawing written as
        # markup carries. The second was unchecked, and every drawing added after the first
        # two is written that way.
        sizes = [float(s) for s in re.findall(r'"font-size": ([0-9.]+)', TEMPLATE)]
        sizes += [float(s) for s in re.findall(r'font-size="([0-9.]+)"', TEMPLATE)]
        assert sizes, "no drawn type found; the check needs updating"
        assert min(sizes) >= TYPE_FLOOR, f"smallest is {min(sizes)}px"

    def test_the_drawing_is_never_scaled_far_enough_to_undo_that(self) -> None:
        """Scaling the drawing scales its labels, so the floor holds only if the scale does.

        At 0.72, which is what this was, an 11px label renders at 7.9px.
        """
        [limit] = re.findall(r"const scaled = !fits && room / W >= ([0-9.]+);", TEMPLATE)
        assert float(limit) >= 0.9
        assert TYPE_FLOOR * float(limit) >= 9.9

    def test_no_hardcoded_size_in_the_stylesheet_goes_under_the_floor(self) -> None:
        css = TEMPLATE[TEMPLATE.index("<style>") : TEMPLATE.index("</style>")]
        under = [s for s in re.findall(r"font-size:([0-9.]+)px", css) if float(s) < TYPE_FLOOR]
        assert not under, f"{under} below {TYPE_FLOOR}px"


class TestTheLinesAReaderFollows:
    def arrows(self) -> list[str]:
        """Every stroke that belongs to a path carrying an arrowhead.

        Matched around the stroke rather than by brace, since these calls interpolate and a
        template literal closes a brace long before the call does.
        """
        found = []
        for hit in re.finditer(r"stroke: css\(([^)]*)\)", TEMPLATE):
            near = TEMPLATE[hit.start() : hit.start() + 420]
            near = near[: near.find("el(") if near.find("el(") > 40 else len(near)]
            if "marker-end" in near or "marker-start" in near:
                found.append(hit.group(1))
        return found

    def test_the_edge_tokens_exist_and_are_what_an_arrow_is_drawn_in(self) -> None:
        """`--line` and `--line-strong` are borders and sit near their background.

        A line carrying meaning between two things reads as a foreground, so it takes
        `--edge` or `--edge-soft`, which the palette test holds to 3:1. A box outline and a
        container's frame stay on the border colours, which is what they are.
        """
        for where in ("--edge", "--edge-soft"):
            assert f'css("{where}")' in TEMPLATE
        drawn = self.arrows()
        assert len(drawn) >= 2, "no arrowed paths found; the check needs updating"
        for stroke in drawn:
            assert "--line" not in stroke, f"an arrow borrows a border colour: {stroke}"

    def test_a_hairline_to_a_store_is_an_edge_too(self) -> None:
        """It has no arrowhead and it is still a line between two things."""
        assert 'stroke: css("--edge-soft"), "stroke-width": 1.4' in TEMPLATE

    def test_an_arrowhead_is_one_size_whatever_it_ends(self) -> None:
        """In the default units a head is a multiple of its line's width.

        Edge width here means traffic, so the busiest link drew a head about four times the
        size of the quietest one's, sitting well clear of the step it pointed at.
        """
        heads = re.findall(r'el\("marker", \{([^;]*?)\}\)', TEMPLATE)
        assert len(heads) == 2, "expected one marker maker per drawing"
        for body in heads:
            assert 'markerUnits: "userSpaceOnUse"' in body, body

    def test_an_arm_nothing_has_taken_carries_no_words(self) -> None:
        """The dotted hairline says it and the key says what that means.

        Writing it on the arm as well said it a third time, and said it wrongly: "never"
        reads as a route the design cannot take rather than one no run has taken so far.
        """
        [body] = re.findall(r"function edgeLabel\(.*?\n\}", TEMPLATE, re.S)
        said = re.findall(r"return ([^;]*);", body)
        assert not any("never" in s or "not yet" in s for s in said), said
        assert '"not taken yet");' in TEMPLATE, "the key must still carry the meaning once"

    def test_an_arrowhead_matches_the_line_it_ends(self) -> None:
        heads = re.findall(r'"M0 0 L8 4 L0 8 z", fill: css\("([^"]+)"\)', TEMPLATE)
        assert heads and all(h in ("--edge", "--edge-soft") for h in heads), heads
