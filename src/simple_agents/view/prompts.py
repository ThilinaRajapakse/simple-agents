"""Every prompt the project sends, as it was written and as it was sent.

The build page names each prompt and shows the function behind it; what reached the model was
on no page at all, so a value cut in half or a sentence the builder never agreed to was as
invisible on the page as it was to the checks.

The record already holds both halves. Each model call keeps ``inputs.assembly``: the fixed
text of every message, and each value's name, length, declared origin and what any cap cut
(`docs/trajectory-format.md` §4.1.6). The rendered messages sit beside it. Walking the two
together recovers which words the project wrote and which arrived at run time.

::

    held = read_prompts(".", pipelines, brief)
    held["pipelines"][0]["steps"][0]["filled"]["messages"][0]["pieces"]
    held["counts"]["unagreed"]

A step the runs have not reached yet still has its words in the code, so it shows the text
`text_written` reads out of the source.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .runs_overlay import MAX_RECORD_CHARS, _elapsed_ms

__all__ = ["read_prompts", "pieces_of", "fill_of"]


MOST_RUNS_BACK = 20
"""How many of a pipeline's runs are opened looking for a prompt each of its steps sent.

A run that took one branch made no call at the steps down the others, and the newest run of a
project can be one that called no model at all, so the newest is often not enough. The served
page offers the rest where these leave a step unfilled.
"""

VALUE_CHARS = 1_000
"""How much of one value the page carries. ``chars`` says how long it was, and the served page
reads the record behind it for the rest."""

TURNS_SHOWN = 4
"""Turns of a loop listed one by one before the tail is grouped into a single line."""

SAID_CHARS = 240
"""How much of what the model said, or a tool returned, one turn's line carries."""


_GAP = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}|(\{\{)|(\}\})")


def pieces_of(template: str) -> list[tuple[str, str]]:
    """One piece of fixed text or one named gap at a time, in order.

    ::

        pieces_of("Plan {days} days.")
        # [('fixed', 'Plan '), ('gap', 'days'), ('fixed', ' days.')]

    A doubled brace is one fixed brace, which is how the library fills a template.
    """
    out: list[tuple[str, str]] = []
    at = 0
    for found in _GAP.finditer(template):
        if found.start() > at:
            out.append(("fixed", template[at : found.start()]))
        if found.group(1):
            out.append(("gap", found.group(1)))
        else:
            out.append(("fixed", "{" if found.group(2) else "}"))
        at = found.end()
    if at < len(template):
        out.append(("fixed", template[at:]))
    return out


def _length_of(value: dict[str, Any]) -> int | None:
    """How many characters one value wrote, or ``None`` where the record does not say.

    A plain value records its own length. A section records its text and its own values, so
    its length is theirs plus its fixed text. A section built from a list records how many
    parts it has and not what they wrote, which is where this returns nothing.
    """
    if "chars" in value:
        chars = value["chars"]
        # `True` is an `int`, and a record holding one is not a length.
        return chars if isinstance(chars, int) and not isinstance(chars, bool) else None
    if "template" not in value:
        return None
    inner = {str(v.get("name")): v for v in value.get("values") or []}
    total = 0
    for kind, text in pieces_of(str(value["template"])):
        if kind == "fixed":
            total += len(text)
            continue
        held = inner.get(text)
        length = _length_of(held) if held else None
        if length is None:
            return None
        total += length
    return total


def fill_of(message: dict[str, Any], rendered: str) -> list[dict[str, Any]] | None:
    """One message split into the words the project wrote and the values that filled it.

    ::

        fill_of({"role": "user", "template": "Plan {days} days.",
                 "values": [{"name": "days", "chars": 1}]}, "Plan 4 days.")
        # [{'kind': 'fixed', 'text': 'Plan '}, {'kind': 'value', 'name': 'days', ...},
        #  {'kind': 'fixed', 'text': ' days.'}]

    ``None`` where the two do not line up, which happens when the run's redaction replaced
    text after the lengths were recorded. The caller then shows the message whole and says so:
    a message drawn with no values would read as a prompt that has none.
    """
    template = message.get("template")
    if not isinstance(template, str):
        return None
    inner = {str(v.get("name")): v for v in message.get("values") or []}
    parts = pieces_of(template)
    out: list[dict[str, Any]] = []
    at = 0
    for index, (kind, text) in enumerate(parts):
        if kind == "fixed":
            if not rendered.startswith(text, at):
                return None
            out.append({"kind": "fixed", "text": text})
            at += len(text)
            continue
        held = inner.get(text, {})
        length = _length_of(held)
        if length is None:
            length = _up_to_the_next(parts, index, rendered, at)
            if length is None:
                return None
        out.append(_a_value(text, held, rendered[at : at + length]))
        at += length
    if at != len(rendered):
        return None
    return out


def _up_to_the_next(parts: list[tuple[str, str]], index: int, rendered: str, at: int) -> int | None:
    """How far a value of unrecorded length runs: to the next fixed text, or to the end."""
    following = next((text for kind, text in parts[index + 1 :] if kind == "fixed" and text), None)
    if following is None:
        return len(rendered) - at
    found = rendered.find(following, at)
    return None if found < 0 else found - at


def _a_value(name: str, held: dict[str, Any], text: str) -> dict[str, Any]:
    """One value as the page shows it: what it wrote, how much of it, and where from."""
    return {
        "kind": "value",
        "name": name,
        "text": text[:VALUE_CHARS],
        "clipped": len(text) > VALUE_CHARS,
        "chars": len(text),
        "capped_from": held.get("capped_from"),
        "origin": held.get("origin"),
        "parts": held.get("parts"),
        "section": "template" in held,
    }


_CODE = "written in the project's code"


def _origin_of(message: dict[str, Any], pieces: list[dict[str, Any]] | None) -> str:
    """Where one message's text came from, in words rather than by colour."""
    if message.get("carried"):
        return "carried from the conversation"
    if pieces is None:
        return _CODE
    words = "".join(p["text"] for p in pieces if p["kind"] == "fixed").strip()
    values = [p for p in pieces if p["kind"] == "value"]
    if words or not values:
        return _CODE
    origin = next((p["origin"] for p in values if p.get("origin")), None)
    return f"set outside the code: {origin}" if origin else "a value the run supplied"


def _message(message: dict[str, Any], rendered: Any) -> dict[str, Any]:
    """One message of a filled prompt, as the page reads it."""
    text = rendered if isinstance(rendered, str) else ""
    if message.get("carried"):
        return {
            "role": message.get("role"),
            "origin": "carried from the conversation",
            "pieces": [{"kind": "fixed", "text": text[:VALUE_CHARS]}],
            "carried": True,
            "extra": list(message.get("extra") or []),
        }
    if "blocks" in message:
        kinds = [str(b.get("kind") or "text") for b in message.get("blocks") or []]
        return {
            "role": message.get("role"),
            "origin": _CODE,
            "pieces": [],
            "blocks": kinds,
            "extra": list(message.get("extra") or []),
        }
    pieces = fill_of(message, text)
    return {
        "role": message.get("role"),
        "origin": _origin_of(message, pieces),
        "pieces": pieces if pieces is not None else [{"kind": "fixed", "text": text}],
        "redacted": pieces is None,
        "extra": list(message.get("extra") or []),
    }


def _read_one_run(path: Path, wanted: set[str]) -> dict[str, dict[str, Any]]:
    """Every call each wanted step made in one run, from that run's trajectory.

    Returns one entry per step the run reached, holding the calls it made in order and the
    tool calls between them. A record longer than `MAX_RECORD_CHARS` is skipped: one payload
    can be megabytes, and the page is not where that is read.
    """
    trajectory = path / "trajectory.jsonl"
    if not trajectory.exists():
        return {}
    try:
        executions, calls, tools = _records_of(trajectory, wanted)
    except OSError:
        return {}
    held: dict[str, dict[str, Any]] = {}
    for record in calls:
        # The step's own calls, which are the ones whose parent is the step. A call a tool
        # made through a `ModelHandle`, or a consultation reader's, hangs under that call
        # instead and is the tool's prompt rather than this step's, which is the same line
        # the manifest draws (`docs/run-envelope.md` §2.3).
        node_id = executions.get(str(record.get("parent_id")))
        if node_id is None:
            continue
        held.setdefault(node_id, {"calls": [], "tools": []})["calls"].append(record)
    for record in tools:
        node_id = executions.get(str(record.get("parent_id")))
        if node_id in held:
            held[node_id]["tools"].append(record)
    for one in held.values():
        one["calls"].sort(key=lambda r: r.get("sequence") or 0)
        one["tools"].sort(key=lambda r: r.get("sequence") or 0)
    return held


def _records_of(
    trajectory: Path, wanted: set[str]
) -> tuple[dict[str, str], list[dict[str, Any]], list[dict[str, Any]]]:
    """One trajectory read: which record is which step, its model calls, and its answers.

    A record longer than `MAX_RECORD_CHARS` is skipped. One payload can be megabytes, and the
    page is not where that is read. Skipping a step's own record leaves its calls attached to
    nothing, and the page then reads that step's prompt from the code.
    """
    executions: dict[str, str] = {}
    calls: list[dict[str, Any]] = []
    tools: list[dict[str, Any]] = []
    with trajectory.open(encoding="utf-8") as lines:
        for line in lines:
            if len(line) > MAX_RECORD_CHARS:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            kind = record.get("record_type")
            if (
                kind == "node_execution"
                and record.get("record_id")
                and record.get("node_id") in wanted
            ):
                executions[str(record["record_id"])] = str(record["node_id"])
            elif kind == "model_call":
                calls.append(record)
            elif kind in ("tool_call", "consultation"):
                tools.append(record)
    return executions, calls, tools


def _said(record: dict[str, Any]) -> str:
    """What one model call answered, short enough for a line."""
    outputs = record.get("outputs") or {}
    content = outputs.get("content")
    return str(content)[:SAID_CHARS] if content else ""


_TOKEN_CLASSES = ("input_uncached", "input_cache_read", "input_cache_write", "output")


def _tokens(record: dict[str, Any]) -> tuple[int | None, bool]:
    """What one call was charged, and whether a class of it went unmeasured.

    A backend that reports the prompt size without the cached split records `unknown` for the
    classes it did not measure, so the total is what was measured and the flag says the rest
    is missing rather than zero.
    """
    held = record.get("tokens") or {}
    counted = [held.get(name) for name in _TOKEN_CLASSES]
    numbers = [n for n in counted if isinstance(n, int) and not isinstance(n, bool)]
    if not numbers:
        return None, True
    return sum(numbers), len(numbers) < len(counted)


def _answer(one: dict[str, Any]) -> dict[str, Any]:
    """What came back from one thing the model called, whether a tool or a person."""
    if one.get("record_type") == "consultation":
        answered = one.get("response") or one.get("chose") or one.get("resolution")
        return {
            "name": "the question it asked",
            "text": str(answered)[:SAID_CHARS] if answered else "no answer was recorded",
            "failed": False,
            "asked_a_person": True,
        }
    error = one.get("error") or {}
    return {
        "name": one.get("tool_name"),
        # A call that failed produced no output, and `None` is not what came back: the
        # error is.
        "text": str(error.get("message") or error or one.get("outputs"))[:SAID_CHARS]
        if error
        else str(one.get("outputs"))[:SAID_CHARS],
        "failed": bool(error),
        "asked_a_person": False,
    }


def _took(record: dict[str, Any]) -> float | None:
    """How long one call took, which on a replay is what the recording measured.

    A replayed call is answered from a file in no time at all, and the timestamps bracket
    that. `recorded_duration_ms` is what the live call took, carried over on the replay.
    """
    if record.get("replayed") and isinstance(record.get("recorded_duration_ms"), (int, float)):
        return float(record["recorded_duration_ms"])
    return _elapsed_ms(record.get("started_at"), record.get("ended_at"))


def _turn(record: dict[str, Any], answers: list[dict[str, Any]]) -> dict[str, Any]:
    """One turn of a loop: what the model did, what came back, and what it cost."""
    outputs = record.get("outputs") or {}
    asked = [str(c.get("name")) for c in (outputs.get("tool_calls") or []) if c.get("name")]
    tokens, partial = _tokens(record)
    return {
        "said": _said(record),
        "called": asked,
        "got": [_answer(one) for one in answers],
        "ms": _took(record),
        "tokens": tokens,
        "tokens_partial": partial,
        "sequence": record.get("sequence"),
    }


def _turns_of(calls: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
    """What the model answered this prompt with, and every turn after it.

    ``answered`` is the call the prompt was sent on: what came back, what it called and what
    it cost. ``turns`` is the loop after that, each turn carrying the tools it reached and
    what they returned. A fifty-turn loop is one line until it is opened, so the first few
    are listed and ``grouped`` carries the rest with their total time and tokens.
    """
    rows = []
    for index, record in enumerate(calls, start=1):
        at = record.get("sequence") or 0
        following = calls[index] if index < len(calls) else None
        until = (following.get("sequence") or 0) if following else None
        answers = [
            one
            for one in tools
            if (one.get("sequence") or 0) > at
            and (until is None or (one.get("sequence") or 0) < until)
        ]
        rows.append({"n": index, **_turn(record, answers)})
    if not rows:
        return {"answered": None, "turns": [], "grouped": None, "total": 0}
    first, rows = rows[0], rows[1:]
    shown, rest = rows[:TURNS_SHOWN], rows[TURNS_SHOWN:]
    return {"answered": first, "turns": shown, "grouped": _grouped(rest), "total": len(rows)}


def _grouped(rest: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The tail of a loop as one row: how many turns, what they called, what they cost."""
    if not rest:
        return None
    times = [one["ms"] for one in rest if one["ms"] is not None]
    counts = [one["tokens"] for one in rest if one["tokens"] is not None]
    return {
        "from": rest[0]["n"],
        "to": rest[-1]["n"],
        "turns": len(rest),
        "called": sum(len(one["called"]) for one in rest),
        "ms": sum(times) if len(times) == len(rest) else None,
        "tokens": sum(counts) if len(counts) == len(rest) else None,
    }


def _filled(call: dict[str, Any]) -> dict[str, Any] | None:
    """The prompt one model call sent, or ``None`` where the call recorded none.

    A call whose messages are a conversation carries no assembly, which is every turn of a
    loop after the first, and a run that kept no payloads says so in place of the text.
    """
    inputs = call.get("inputs") or {}
    if inputs.get("type") == "not_recorded":
        return {"kept_nothing": str(inputs.get("reason") or "sampling"), "messages": []}
    assembly = inputs.get("assembly")
    if not isinstance(assembly, dict):
        return None
    rendered = inputs.get("messages") or []
    held = assembly.get("messages") or []
    return {
        "instruction": assembly.get("instruction"),
        "templates": list(assembly.get("templates") or []),
        "messages": [_message(one, _content(rendered, i)) for i, one in enumerate(held)],
    }


def _content(rendered: Any, index: int) -> Any:
    """What went on the wire as one message's content, or ``""`` where nothing did."""
    if not isinstance(rendered, list) or index >= len(rendered):
        return ""
    one = rendered[index]
    return one.get("content") if isinstance(one, dict) else ""


_CALLS_A_MODEL = ("llm", "agent")

_KINDS = {
    "llm": "one model call",
    "agent": "an agent loop",
}


def _kind_words(node: dict[str, Any]) -> str:
    """What kind of step this is, in the words the rest of the page uses."""
    words = _KINDS.get(str(node.get("kind")), str(node.get("kind")))
    return f"{words} per item" if node.get("fan_out") else words


def _for_this_pipeline(handles: list[Any], card: dict[str, Any]) -> list[Any]:
    """The runs that are this pipeline's, newest first.

    Matched on the name the run records, and on the graph's fingerprint for a run written
    before manifests carried the name and for a pipeline registered under none.
    """
    name, shape = card.get("name"), card.get("fingerprint")
    return [
        handle
        for handle in handles
        if handle.pipeline == name
        or (handle.pipeline is None and handle.manifest.get("graph_fingerprint") == shape)
    ]


def _fills_for(handles: list[Any], wanted: set[str], most_runs: int) -> dict[str, Any]:
    """One filled prompt per step, from the newest run that reached it.

    Walks back through the runs until every step has one or ``most_runs`` have been opened,
    whichever comes first. ``read`` says how many were opened and ``left`` how many are still
    behind them, which is what the served page offers to keep walking through.
    """
    found: dict[str, dict[str, Any]] = {}
    read = 0
    for handle in handles:
        if not wanted - set(found):
            break
        if read >= most_runs:
            break
        read += 1
        for node_id, held in _read_one_run(handle.path, wanted).items():
            if node_id in found or not held["calls"]:
                continue
            filled = _one_step(held, handle)
            if filled is not None:
                found[node_id] = filled
    return {"steps": found, "read": read, "left": max(0, len(handles) - read)}


def _one_step(held: dict[str, Any], handle: Any) -> dict[str, Any] | None:
    """What one step sent in one run: the prompt, how many items ran, and the later turns."""
    calls = held["calls"]
    items = sorted({c.get("item_index") for c in calls}, key=lambda at: (at is not None, at))
    first = items[0]
    mine = [c for c in calls if c.get("item_index") == first]
    prompt = _filled(mine[0])
    if prompt is None:
        return None
    instructions = {
        ((c.get("inputs") or {}).get("assembly") or {}).get("instruction")
        for c in calls
        if isinstance((c.get("inputs") or {}).get("assembly"), dict)
    }
    return {
        "run": handle.run_id,
        "when": str(handle.manifest.get("started_at") or "")[:16].replace("T", " "),
        "role": handle.role,
        "rollout": str((handle.manifest.get("evaluation") or {}).get("eval_id") or "") or None,
        "sequence": mine[0].get("sequence"),
        "model": mine[0].get("request_model"),
        "item": first,
        "items": len(items) if first is not None else None,
        "one_text": len(instructions - {None}) <= 1,
        "calls": len(calls),
        **prompt,
        **_turns_of(mine, held["tools"]),
    }


def _notes(step: dict[str, Any]) -> list[dict[str, str]]:
    """What the page says about this prompt in words, by what each is about."""
    filled = step.get("filled") or {}
    return [*_value_notes(filled), *_instruction_notes(step), *_run_notes(step, filled)]


def _value_notes(filled: dict[str, Any]) -> list[dict[str, str]]:
    """What one filled prompt's own values are worth saying: a cut, and text redaction moved."""
    said: list[dict[str, str]] = []
    for message in filled.get("messages") or []:
        for piece in message.get("pieces") or []:
            if piece.get("kind") == "value" and piece.get("capped_from"):
                said.append(
                    {
                        "kind": "cut",
                        "says": f"The step's own code cuts {piece['name']} at "
                        f"{piece['chars']:,} characters. The model was sent that much of "
                        f"{piece['capped_from']:,}, and the other "
                        f"{piece['capped_from'] - piece['chars']:,} never reached it.",
                    }
                )
    hidden = sum(1 for m in filled.get("messages") or [] if m.get("redacted"))
    if hidden:
        said.append(
            {
                "kind": "redacted",
                "says": "The run's redaction replaced text in "
                + (
                    "one message, so which words are values cannot be marked there. It is "
                    "shown whole."
                    if hidden == 1
                    else f"{hidden} messages, so which words are values cannot be marked "
                    f"there. They are shown whole."
                ),
            }
        )
    return said


def _instruction_notes(step: dict[str, Any]) -> list[dict[str, str]]:
    """What the record says about this step's instruction across every run that made one."""
    said: list[dict[str, str]] = []
    if step.get("text") == "interpolated":
        said.append(
            {
                "kind": "interpolated",
                "says": "A value is formatted into the text itself, so this step sends "
                "different words every run and there is no one instruction to read, compare "
                "or agree to. The checks report it as well.",
            }
        )
    distinct = step.get("distinct")
    if not (isinstance(distinct, int) and distinct > 1):
        return said
    observed = step.get("observed") or {}
    calls = sum(observed.values())
    # The manifest lists the most-used instructions and caps the list, so a step with more
    # than it lists has calls behind digests the record does not hold.
    listed = (
        f"across {calls:,} recorded calls."
        if distinct <= len(observed)
        else f"and the {len(observed):,} the record lists were sent on {calls:,} calls."
    )
    said.append(
        {
            "kind": "varies",
            "says": f"The instruction comes from the run: {distinct:,} different ones " + listed,
        }
    )
    if step.get("decision"):
        said.append(
            {
                "kind": "agreed_but_varies",
                "says": "The agreed rule names this step, and the words it sends change "
                "from run to run, so the agreement covers text that is unread.",
            }
        )
    return said


def _run_notes(step: dict[str, Any], filled: dict[str, Any]) -> list[dict[str, str]]:
    """What the run behind this prompt is worth saying: an edit since, and a run that kept none."""
    said: list[dict[str, str]] = []
    if step.get("changed") and filled:
        said.append(
            {
                "kind": "changed",
                "says": "The words have been edited since this run, so what is shown is what "
                "the run sent and the next run sends the newer text.",
            }
        )
    if filled.get("kept_nothing"):
        said.append(
            {
                "kind": "kept_nothing",
                "says": f"This run kept no prompt text ({filled['kept_nothing']}). Another "
                f"run that kept its payloads shows the words.",
            }
        )
    return said


def _written_pieces(written: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The text read out of the code, split the way a filled prompt is."""
    out = []
    for one in written:
        template = one.get("template")
        out.append(
            {
                "role": one.get("role"),
                "how": one.get("how"),
                "pieces": (
                    [
                        {"kind": "fixed", "text": text}
                        if kind == "fixed"
                        # No run has filled this one, so it carries no length: a panel saying
                        # "0 characters" would be a measurement of nothing.
                        else {"kind": "value", "name": text, "text": "", "unfilled": True}
                        for kind, text in pieces_of(template)
                    ]
                    if isinstance(template, str)
                    else []
                ),
            }
        )
    return out


def _step_card(
    node: dict[str, Any], pipeline: str, recorded: dict[str, Any], agreed: dict[str, Any]
) -> dict[str, Any]:
    """One prompt as the page reads it, before its fill is attached."""
    held = recorded.get(node["id"]) or {}
    now = node.get("prompt_entry") or {}
    return {
        "node_id": node["id"],
        "short": node["id"].rsplit(".", 1)[-1],
        "pipeline": pipeline,
        "at": f"prompt:{pipeline}/{node['id']}",
        "kind": node.get("kind"),
        "kind_words": _kind_words(node),
        "planned": bool(node.get("planned")),
        "does": node.get("does"),
        "fan_out": node.get("fan_out"),
        "model": node.get("model"),
        "decision": agreed.get(node["id"]) or agreed.get(node["id"].rsplit(".", 1)[-1]),
        "version": now.get("version") or held.get("version"),
        "source": now.get("source") or held.get("source"),
        "text": now.get("text") or held.get("text"),
        "ran_as": held.get("version"),
        # The words moved since the newest run that recorded them, so what is on this page is
        # what the next run will send and not what the last one did.
        "changed": bool(
            held.get("version") and now.get("version") and held["version"] != now["version"]
        ),
        "observed": dict(held.get("observed") or {}),
        "distinct": held.get("distinct"),
        "written": _written_pieces(list(node.get("written_prompt") or [])),
        "filled": None,
    }


def _gaps_between(nodes: list[dict[str, Any]]) -> dict[str, int]:
    """How many steps with no prompt sit after each prompt, keyed by the prompt before them.

    A value handed on through three fixed steps has not gone straight out of one prompt into
    the next, and one line saying how many is what keeps the path honest. The key ``""`` is
    the steps before the first prompt.
    """
    gaps: dict[str, int] = {}
    at = ""
    for node in nodes:
        if node.get("kind") in _CALLS_A_MODEL:
            at = node["id"]
        else:
            gaps[at] = gaps.get(at, 0) + 1
    return gaps


def read_prompts(
    root: str | Path,
    pipelines: list[dict[str, Any]],
    brief: Any,
    recorded: dict[str, Any] | None = None,
    *,
    most_runs: int = MOST_RUNS_BACK,
) -> dict[str, Any]:
    """Every prompt the project sends, one entry per step that calls a model.

    ::

        held = read_prompts(".", pipelines, brief)
        held["pipelines"][0]["steps"][0]["filled"]["messages"]   # as sent, on one real run
        held["pipelines"][0]["steps"][0]["written"]              # as the code writes it
        held["counts"]["unagreed"]

    ``recorded`` is what the manifests said about each prompt, which `read_prompt_rules`
    reads for the same runs; passing it shares the one reading rather than making a second.

    Each step carries the run its filled prompt came from, since a run that took one branch
    made no call at the steps down the others. ``most_runs`` bounds how far back that
    looks, and each pipeline says how many runs are still behind it.
    """
    from ..envelope import runs as read_runs
    from .constants import _named_by, across_the_runs

    root = Path(root).expanduser()
    if recorded is None:
        _numbers, recorded = across_the_runs(root)
    agreed = _named_by(brief, "prompt_rule") if brief is not None else {}
    directory = root / "runs"
    handles = read_runs(directory, scripted=None) if directory.is_dir() else []
    rollouts = _rollouts_under(directory)
    held = [
        one
        for card in pipelines
        if (one := _one_pipeline(card, recorded, agreed, handles, rollouts, most_runs))
    ]
    return {"pipelines": held, "counts": _counts(held)}


def _rollouts_under(directory: Path) -> list[Any]:
    """The evaluation's rollouts, which fill a step the project's own runs never reached."""
    from ..envelope import runs as read_runs

    if not directory.is_dir():
        return []
    return [
        one
        for one in read_runs(directory, nested=True, scripted=None)
        if one.manifest.get("evaluation")
    ]


def _one_pipeline(
    card: dict[str, Any],
    recorded: dict[str, Any],
    agreed: dict[str, Any],
    handles: list[Any],
    rollouts: list[Any],
    most_runs: int,
) -> dict[str, Any] | None:
    """One pipeline's prompts, filled from its own runs. ``None`` where it sends none."""
    steps = [
        _step_card(node, card["name"], recorded, agreed)
        for node in card["nodes"]
        if node.get("kind") in _CALLS_A_MODEL
    ]
    if not steps:
        return None
    mine = _for_this_pipeline(handles, card)
    wanted = {step["node_id"] for step in steps}
    fills = _fills_for(mine, wanted, most_runs)
    # A step down a branch no ordinary run took can still have been reached by the evaluation,
    # and a rollout sent the project's own words. The figures are read apart; the text is the
    # same text, and the step says which run filled it.
    unfilled = wanted - set(fills["steps"])
    if unfilled and rollouts:
        more = _fills_for(_for_this_pipeline(rollouts, card), unfilled, most_runs)
        fills["steps"].update(more["steps"])
        fills["read"] += more["read"]
        fills["left"] += more["left"]
    for step in steps:
        step["filled"] = fills["steps"].get(step["node_id"])
        step["notes"] = _notes(step)
    newest = next(iter(mine), None)
    return {
        "name": card["name"],
        "steps": steps,
        "gaps": _gaps_between(card["nodes"]),
        "runs_read": fills["read"],
        "runs_left": fills["left"],
        # Runs were opened and none of them carried what was sent, which is every run made
        # before the library recorded it. The page says that rather than leaving the reader
        # to wonder why a step that has run is read from the code.
        "runs_carry_nothing": bool(fills["read"] and not fills["steps"]),
        "newest": _the_run(newest),
    }


def _the_run(handle: Any) -> dict[str, str] | None:
    """One run named for a reader: its id and the minute it started."""
    if handle is None:
        return None
    return {
        "run": handle.run_id,
        "when": str(handle.manifest.get("started_at") or "")[:16].replace("T", " "),
    }


def _counts(held: list[dict[str, Any]]) -> dict[str, int]:
    """What the page's title line says: how many prompts, and what wants reading."""
    steps = [s for one in held for s in one["steps"]]
    return {
        "prompts": len(steps),
        "pipelines": len(held),
        "unagreed": sum(1 for s in steps if s["decision"] is None and not s["planned"]),
        "unfilled": sum(1 for s in steps if s["filled"] is None),
        "cut": sum(1 for s in steps if any(n["kind"] == "cut" for n in s["notes"])),
        "varies": sum(1 for s in steps if any(n["kind"] == "varies" for n in s["notes"])),
        "changed": sum(1 for s in steps if s["changed"]),
    }
