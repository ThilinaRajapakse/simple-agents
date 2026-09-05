"""`simple-agents record`: an answer or a decision written into the brief, stamped by the clock.

::

    simple-agents record answer used_through --text "A phone app over an HTTP API."
    simple-agents record decision pool_size --kind constant --status agreed --chose 200
    simple-agents record decision pool_size --kind constant --from-comment c6

`docs/conformance.md` §2.3 is the reference; the writing itself is
:mod:`simple_agents.conformance.writing`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..conformance.brief import SOURCES
from ..conformance.brief import STATUSES as ENTRY_STATUSES
from ..conformance.decisions import STATUSES as DECISION_STATUSES
from ..conformance.decisions import kind_names
from ..conformance.writing import CONFIRMED_DOCUMENTS, TOP_LEVEL_KEYS
from ..errors import ConfigurationError

__all__ = ["add_record_command", "run_record"]


def add_record_command(subcommands: argparse._SubParsersAction) -> None:
    """Register `record`, with its `answer` and `decision` forms, on the CLI's subcommands."""
    record = subcommands.add_parser(
        "record",
        help="write an answer or a decision into the brief, stamped from the clock",
    )
    what = record.add_subparsers(dest="what")
    _answer_form(what)
    _decision_form(what)
    _key_forms(what)


def _answer_form(what: argparse._SubParsersAction) -> None:
    """The `answer` form: a question's key, its status, and where the text comes from."""
    answer = what.add_parser("answer", help="what the builder answered, under the question's key")
    answer.add_argument("name", help="the question's key, as `simple-agents questions` prints it")
    answer.add_argument("--brief", default="brief.toml", help="the brief, instead of ./brief.toml")
    answer.add_argument(
        "--status", default="answered", choices=ENTRY_STATUSES, help="default answered"
    )
    answer.add_argument("--source", default=None, choices=SOURCES, help="who the answer came from")
    answer.add_argument(
        "--asked-at",
        default=None,
        help="the stage it was put at; required on a question every gate puts again",
    )
    answer.add_argument("--deferred-to", default=None, help="the stage a deferred entry moves to")
    answer.add_argument("--text", default=None, help="the answer; or --file")
    answer.add_argument(
        "--file", default=None, help="a file holding the answer, or - for standard input"
    )


def _decision_form(what: argparse._SubParsersAction) -> None:
    """The `decision` form: a name, one of the six kinds, and what was weighed."""
    decision = what.add_parser(
        "decision", help="what the coding agent decided, and what the builder said"
    )
    decision.add_argument("name", help="the decision's name, which heads [decisions.<name>]")
    decision.add_argument(
        "--brief", default="brief.toml", help="the brief, instead of ./brief.toml"
    )
    decision.add_argument(
        "--kind", required=True, choices=kind_names(), help="one of the six kinds"
    )
    decision.add_argument(
        "--status",
        default=None,
        choices=DECISION_STATUSES,
        help="default proposed, or agreed with --from-comment",
    )
    decision.add_argument("--chose", default=None, help="what was chosen")
    decision.add_argument(
        "--considered", action="append", default=None, help="an alternative weighed; repeatable"
    )
    decision.add_argument("--because", default=None, help="why; or --because-file")
    decision.add_argument(
        "--because-file", default=None, help="a file holding the reason, or - for standard input"
    )
    decision.add_argument(
        "--from",
        dest="rests_on",
        action="append",
        default=None,
        help="a question key the decision was derived from; repeatable",
    )
    decision.add_argument(
        "--produces",
        action="append",
        default=None,
        help="what it became in the code, by name; repeatable",
    )
    decision.add_argument("--stage", default=None, help="the stage it was decided at")
    decision.add_argument(
        "--from-comment",
        dest="from_comment",
        default=None,
        help="a comment id: what the builder said becomes `considered`, and the status `agreed`",
    )
    decision.add_argument(
        "--comments",
        default="comments.toml",
        help="the comments file --from-comment reads, instead of ./comments.toml",
    )


def _key_forms(what: argparse._SubParsersAction) -> None:
    """The forms for the keys above the tables: `set`, `confirmed`, `read-against`, `shape`."""
    setter = what.add_parser(
        "set", help="a top-level key: stage, tier, results, comments_block_gates"
    )
    setter.add_argument("key", choices=TOP_LEVEL_KEYS, help="the key")
    setter.add_argument("value", help="its value; true or false for comments_block_gates")
    setter.add_argument("--brief", default="brief.toml", help="the brief, instead of ./brief.toml")
    confirmed = what.add_parser(
        "confirmed", help="a document re-read and confirmed at a stage: idea, research or design"
    )
    confirmed.add_argument("document", choices=tuple(CONFIRMED_DOCUMENTS), help="which document")
    confirmed.add_argument("--at", required=True, help="the stage it was confirmed at")
    confirmed.add_argument(
        "--brief", default="brief.toml", help="the brief, instead of ./brief.toml"
    )
    against = what.add_parser(
        "read-against",
        help=(
            "confirmed_against: the pipeline the entries were read against, off the newest "
            "run of the pipeline the results file measured"
        ),
    )
    against.add_argument(
        "--stamp", default=None, help="a behaviour_fingerprint, instead of the one it would read"
    )
    against.add_argument("--brief", default="brief.toml", help="the brief, instead of ./brief.toml")
    shape = what.add_parser(
        "shape", help="shape_confirmed for one pipeline: the picture the builder agreed to"
    )
    shape.add_argument("pipeline", help="the name its factory registers")
    shape.add_argument(
        "--stamp", default=None, help="a graph_fingerprint, instead of the registered pipeline's"
    )
    shape.add_argument("--brief", default="brief.toml", help="the brief, instead of ./brief.toml")


def run_record(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Write an answer or a decision into the brief, stamped by the clock."""
    from ..conformance.writing import record_answer, record_decision

    if args.what is None:
        parser.parse_args(["record", "--help"])
        return 2
    if args.what in ("set", "confirmed", "read-against", "shape"):
        recorded = _record_key(args)
    elif args.what == "answer":
        recorded = record_answer(
            args.brief,
            args.name,
            answer=_text_argument(args.text, args.file),
            status=args.status,
            source=args.source,
            asked_at=args.asked_at,
            deferred_to=args.deferred_to,
        )
    else:
        clicked = _what_the_builder_said(args)
        recorded = record_decision(
            args.brief,
            args.name,
            kind=args.kind,
            status=args.status or ("agreed" if clicked else "proposed"),
            chose=args.chose,
            considered=(args.considered or ()) or ((clicked,) if clicked else ()),
            because=_text_argument(args.because, args.because_file),
            rests_on=args.rests_on or (),
            produces=args.produces or (),
            stage=args.stage,
        )
    what = "replaced" if recorded.replaced else "added"
    stamped = f", recorded_at {recorded.recorded_at}" if recorded.recorded_at else ""
    print(f"{what} [{recorded.table}] in {recorded.path}{stamped}")
    return 0


def _what_the_builder_said(args: argparse.Namespace) -> str | None:
    """The sentence a comment carries, for a decision recorded from one.

    A decision the builder settled by a click on the view has one thing weighed and one reason:
    what they said. Copying it here is what keeps the entry to that. `because` is left to
    whatever was passed, which for a decision the builder settled is usually nothing.

    Raises :class:`~simple_agents.errors.ConfigurationError` naming the ids the file holds
    where there is no such comment, since a decision recorded against a missing comment
    would say the builder settled something they never saw.
    """
    if not getattr(args, "from_comment", None):
        return None
    from ..records.comments import read_comments

    path = Path(args.comments)
    if not path.is_absolute():
        path = Path(args.brief).resolve().parent / args.comments
    comments = read_comments(path)
    thread = comments.thread(args.from_comment)
    if thread is None:
        held = ", ".join(c.id for c in comments.all if c.id) or "none"
        raise ConfigurationError(
            f"{path} holds no comment {args.from_comment!r}. The ids it holds are: {held}.\n"
            f"`simple-agents comments` lists them with what each says."
        )
    return thread.said


def _record_key(args: argparse.Namespace):
    """The four forms over the keys above the tables."""
    from ..conformance.writing import newest_run_fingerprints, record_key, record_shape

    root = Path(args.brief).resolve().parent
    if args.what == "set":
        value: str | bool = args.value
        if args.key == "comments_block_gates":
            if args.value not in ("true", "false"):
                raise ConfigurationError("comments_block_gates takes true or false.")
            value = args.value == "true"
        return record_key(args.brief, args.key, value)
    if args.what == "confirmed":
        return record_key(args.brief, CONFIRMED_DOCUMENTS[args.document], args.at)
    if args.what == "read-against":
        stamp = args.stamp or newest_run_fingerprints(root)[0]
        return record_key(args.brief, "confirmed_against", stamp)
    return record_shape(
        args.brief, args.pipeline, args.stamp or _registered_shape(root, args.pipeline)
    )


def _registered_shape(root: Path, pipeline: str) -> str:
    """The graph fingerprint of the pipeline `agent.py` registers under ``pipeline``."""
    from ..view.discovery import load_project

    loaded = load_project(root)
    if pipeline not in loaded.pipelines:
        held = ", ".join(sorted(loaded.pipelines)) or "none"
        why = f" {loaded.could_not_import}" if loaded.could_not_import else ""
        raise ConfigurationError(
            f"No pipeline registered as {pipeline!r} in {root}. Registered: {held}.{why} "
            f"Pass --stamp with the graph_fingerprint instead."
        )
    return loaded.pipelines[pipeline].graph_fingerprint()


def _text_argument(text: str | None, file: str | None) -> str | None:
    """The body of an answer or a reason: the flag, a file, or standard input as ``-``.

    Standard input is read only when asked for. A command that read it whenever it was not
    a terminal would wait forever under a harness that leaves the pipe open and writes nothing.
    """
    if text is not None and file is not None:
        raise ConfigurationError("Pass the text once: --text or --file, not both.")
    if text is not None:
        return text
    if file is None:
        return None
    if file == "-":
        return sys.stdin.read()
    return Path(file).read_text(encoding="utf-8")
