"""`simple-agents record`: an answer or a decision written into the brief, stamped by the clock.

::

    simple-agents record answer used_through --text "A phone app over an HTTP API."
    simple-agents record decision pool_size --kind constant --status agreed --chose 200

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
        "--status", default="proposed", choices=DECISION_STATUSES, help="default proposed"
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


def run_record(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Write an answer or a decision into the brief, stamped by the clock."""
    from ..conformance.writing import record_answer, record_decision

    if args.what is None:
        parser.parse_args(["record", "--help"])
        return 2
    if args.what == "answer":
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
        recorded = record_decision(
            args.brief,
            args.name,
            kind=args.kind,
            status=args.status,
            chose=args.chose,
            considered=args.considered or (),
            because=_text_argument(args.because, args.because_file),
            rests_on=args.rests_on or (),
            produces=args.produces or (),
            stage=args.stage,
        )
    what = "replaced" if recorded.replaced else "added"
    print(f"{what} [{recorded.table}] in {recorded.path}, recorded_at {recorded.recorded_at}")
    return 0


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
