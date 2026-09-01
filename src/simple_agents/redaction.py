"""Removing secrets from records before they are written.

Trajectories and cassettes store full inputs and outputs, so a tool call carrying an auth
header writes that header to disk. Redaction runs as each record is written, not as a later
pass over the file, so a run that stops partway leaves no unredacted records behind.

Three kinds of rule, applied in this order:

1. **Values of named environment variables.** An exact string match against a value the
   project declared as a secret. This is the only rule that matches a credential with no
   recognisable format.
2. **Sensitive key names.** A field named ``authorization`` or ``password`` has its value
   replaced whatever the value contains, at any depth.
3. **Patterns.** Built-in credential formats, then any the project declares.

Each substitution appends the field's path to the record's ``redactions`` array. To a reader
of the trajectory, "this field was empty" and "this field was removed" mean different things.

These rules match known credential formats and declared values. A secret in neither category
is not detected; ``secret_env`` declares one.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from .errors import ConfigurationError
from .records.trajectory import SECRET_MARKER, Record, is_secret_value, to_record_data

__all__ = ["Redaction", "BUILTIN_PATTERNS", "SENSITIVE_KEYS", "UNWALKED_FIELDS"]

# Credential formats specific enough that a match is a secret rather than ordinary text. A
# false positive replaces real data, which in a trajectory is also training data.
BUILTIN_PATTERNS: dict[str, str] = {
    "sk_prefixed_key": r"sk-[A-Za-z0-9_-]{16,}",
    "github_token": r"gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}",
    "aws_access_key_id": r"(?:AKIA|ASIA)[0-9A-Z]{16}",
    "huggingface_token": r"hf_[A-Za-z0-9]{20,}",
    "google_api_key": r"AIza[0-9A-Za-z_-]{35}",
    "slack_token": r"xox[baprs]-[A-Za-z0-9-]{10,}",
    "bearer_token": r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{16,}",
    "jwt": r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
    "private_key_block": (
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"
    ),
}

# Field names whose value is replaced whatever it contains. Matched on the whole name after
# lowercasing and folding `-` to `_`, never as a substring, so a field named `secrets_path`
# does not match.
SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "authorization",
        "proxy_authorization",
        "x_api_key",
        "api_key",
        "apikey",
        "x_auth_token",
        "auth_token",
        "access_token",
        "refresh_token",
        "client_secret",
        "cookie",
        "set_cookie",
        "password",
        "passwd",
        "secret",
    }
)

# Every field on a record is scanned except these, which the library generates itself: ids,
# sequence numbers and timestamps, plus the redaction report, which describes the scan rather
# than being subject to it.
#
# The list is what is *skipped* rather than what is covered, so a field added later is scanned
# without anyone remembering to say so. A scanner that only looks where a list tells it to
# stops protecting a record the moment someone adds a field, and the field most likely to be
# added is one holding something the library did not produce.
UNWALKED_FIELDS: frozenset[str] = frozenset(
    {
        "format_version",
        "record_type",
        "record_id",
        "run_id",
        "parent_id",
        "sequence",
        "started_at",
        "ended_at",
        "redactions",
    }
)

# Environment values shorter than this are not used as rules. A value such as "1" or "true"
# occurs throughout ordinary record content.
MIN_SECRET_LENGTH = 8

# What `at_boundary` takes beside an individual rule name.
RULE_KINDS: frozenset[str] = frozenset({"secret_env", "sensitive_keys", "builtin", "patterns"})

DEFAULT_AT_BOUNDARY: tuple[str, ...] = ("secret_env", "sensitive_keys", "builtin")
"""Rules applied to the result of a tool declaring ``redact_result``, before anything reads it.

Every rule that matches a credential. A project's own patterns are not credentials, so they are
not here: a shape matches ordinary text sometimes, and ``bearer_token`` matches "Bearer
responsibilities". A rule outside this set redacts the trajectory record and leaves the value in
the cassette, which is what lets a recording of the run replay (``docs/tools.md`` §1.6).
"""


@dataclass(slots=True)
class Redaction:
    r"""What is removed from records before they are written.

    Built-in patterns are on by default. ``Redaction.none()`` disables all rules, and the
    manifest records that they were disabled, which distinguishes an unredacted run from a
    run with nothing to redact.

    ``secret_env`` names environment variables whose values are secrets. Matching is on the
    value. The names reach the manifest; the values do not::

        redaction = Redaction(
            secret_env=["MISTRAL_API_KEY", "INTERNAL_DB_PASSWORD"],
            patterns={"employee_id": r"EMP-\d{6}"},
        )

    Pass it to the writer to apply it to every record. ``Redaction.none()`` disables all
    rules and records that it did.

    ``at_boundary`` is the subset applied to the result of a tool declaring
    ``redact_result=True`` (``docs/tools.md`` §1.6). It takes rule kinds, individual rule
    names, or both::

        Redaction(
            secret_env=["SUPPLIER_TOKEN"],
            patterns={"employee_id": r"EMP-\d{6}", "internal": r"itk_[a-z0-9]{24}"},
            at_boundary=("secret_env", "sensitive_keys", "builtin", "internal"),
        )

    The kinds are ``secret_env``, ``sensitive_keys``, ``builtin`` and ``patterns``; a name is
    any key of ``BUILTIN_PATTERNS`` or of ``patterns``. A rule outside the set, such as the
    ``employee_id`` above, still redacts the trajectory record, and the model and the cassette
    read the value. A value typed ``SecretStr`` is redacted whatever this says.
    """

    secret_env: tuple[str, ...] = ()
    patterns: Mapping[str, str] = field(default_factory=dict)
    builtin: bool = True
    enabled: bool = True
    at_boundary: tuple[str, ...] = DEFAULT_AT_BOUNDARY

    _compiled: list[tuple[str, re.Pattern[str]]] | None = field(
        default=None, init=False, repr=False, compare=False
    )
    _env_values: list[tuple[str, str]] | None = field(
        default=None, init=False, repr=False, compare=False
    )
    _unusable_env: tuple[tuple[str, str], ...] = field(
        default=(), init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        if isinstance(self.secret_env, str):
            raise TypeError(
                "Redaction(secret_env=...) takes a sequence of environment variable names, "
                f"not a single string. Pass [{self.secret_env!r}]."
            )
        self.secret_env = tuple(self.secret_env)
        if isinstance(self.at_boundary, str):
            raise TypeError(
                "Redaction(at_boundary=...) takes a sequence of rule kinds or rule names, "
                f"not a single string. Pass [{self.at_boundary!r}]."
            )
        self.at_boundary = tuple(self.at_boundary)
        known = RULE_KINDS | set(BUILTIN_PATTERNS) | set(self.patterns)
        unknown = [name for name in self.at_boundary if name not in known]
        if unknown:
            raise ConfigurationError(
                f"Redaction(at_boundary=...) names {', '.join(repr(u) for u in unknown)}, "
                f"which is neither a rule kind nor a rule this Redaction declares. A rule "
                f"that is not in force at the boundary is silently not applied there, so the "
                f"name is checked here.\n"
                f"The kinds are {', '.join(sorted(RULE_KINDS))}. The names available are "
                f"{', '.join(sorted(set(BUILTIN_PATTERNS) | set(self.patterns)))}."
            )
        for name, pattern in self.patterns.items():
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError(
                    f"Redaction pattern {name!r} is not a valid regular expression: {exc}. "
                    f"Patterns are applied to every string in every record, so an invalid "
                    f"one is refused at construction rather than during a run."
                ) from exc

    @classmethod
    def none(cls) -> Redaction:
        """Redact nothing.

        The manifest records that redaction was disabled, so a trajectory produced this way
        is identifiable as unredacted.
        """
        return cls(builtin=False, enabled=False)

    # -- rule resolution ------------------------------------------------------------------

    def _rules(self) -> list[tuple[str, re.Pattern[str]]]:
        if self._compiled is None:
            compiled: list[tuple[str, re.Pattern[str]]] = []
            if self.builtin:
                compiled.extend((name, re.compile(p)) for name, p in BUILTIN_PATTERNS.items())
            compiled.extend((name, re.compile(p)) for name, p in self.patterns.items())
            self._compiled = compiled
        return self._compiled

    def _secrets(self) -> list[tuple[str, str]]:
        """Environment values to match exactly, resolved on first use.

        Resolution is deferred so that a `Redaction` constructed before the environment is
        populated still reads the values.
        """
        if self._env_values is None:
            values: list[tuple[str, str]] = []
            unusable: list[tuple[str, str]] = []
            for name in self.secret_env:
                raw = os.environ.get(name)
                if raw is None:
                    unusable.append((name, "unset"))
                elif len(raw) < MIN_SECRET_LENGTH:
                    unusable.append((name, "too_short"))
                else:
                    values.append((name, raw))
            # Longest first, so a secret containing another as a prefix redacts fully.
            values.sort(key=lambda pair: len(pair[1]), reverse=True)
            self._env_values = values
            self._unusable_env = tuple(unusable)
        return self._env_values

    @property
    def unusable_env(self) -> tuple[tuple[str, str], ...]:
        """Declared environment variables that produced no rule, each with the reason.

        Recorded in the manifest. A variable that was unset at run time means the run was
        redacted with fewer rules than the project declared.
        """
        self._secrets()
        return self._unusable_env

    # -- application ----------------------------------------------------------------------

    def __call__(self, record: Record) -> Record:
        """Redact a trajectory record, listing what changed in its ``redactions`` array."""
        if not self.enabled:
            return record

        out = Record(record)
        found: list[str] = []
        for key in list(out):
            if key in UNWALKED_FIELDS:
                continue
            out[key], paths = self.redact(out[key], path=str(key))
            found.extend(paths)

        if found:
            existing = list(out.get("redactions") or [])
            out["redactions"] = existing + [p for p in found if p not in existing]
        return out

    def redact(self, value: Any, *, path: str = "") -> tuple[Any, list[str]]:
        """Redact any value, returning the result and the paths that changed.

        Public so that cassettes can apply the same rules to stored requests and responses.

        Anything that is not already plain data is converted first, so a credential held in a
        field of an object is scrubbed rather than passed over.
        """
        if not self.enabled:
            return value, []
        paths: list[str] = []
        walked = self._walk(to_record_data(value), path, paths, whole=False, only=None)
        return walked, paths

    def redact_for_model(self, value: Any, *, path: str = "") -> tuple[Any, list[str]]:
        """The same, with only the rules ``at_boundary`` names.

        What a tool declaring ``redact_result=True`` returns, so that the model, the node and
        the cassette are given one string and a recording of the run replays::

            redaction.redact_for_model({"authorization": "Bearer sk-live-..."})
            # ({'authorization': '[redacted:sensitive_key]'}, ['authorization'])

        A rule outside ``at_boundary`` still redacts the trajectory record.
        """
        if not self.enabled:
            return value, []
        paths: list[str] = []
        walked = self._walk(to_record_data(value), path, paths, whole=False, only=self.at_boundary)
        return walked, paths

    def _walk(
        self, value: Any, path: str, paths: list[str], *, whole: bool, only: tuple[str, ...] | None
    ) -> Any:
        if is_secret_value(value):
            paths.append(path)
            return SECRET_MARKER
        if isinstance(value, dict):
            return {
                k: self._walk(
                    v,
                    f"{path}.{k}" if path else str(k),
                    paths,
                    whole=whole or (_is_sensitive_key(k) and _keys_apply(only)),
                    only=only,
                )
                for k, v in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [
                self._walk(item, f"{path}[{i}]", paths, whole=whole, only=only)
                for i, item in enumerate(value)
            ]
        if whole:
            if value is None:
                return None
            paths.append(path)
            return "[redacted:sensitive_key]"
        if isinstance(value, str):
            replaced = self._scrub(value, only)
            if replaced != value:
                paths.append(path)
            return replaced
        return value

    def _scrub(self, text: str, only: tuple[str, ...] | None = None) -> str:
        if only is None or "secret_env" in only:
            for name, secret in self._secrets():
                if secret in text:
                    text = text.replace(secret, f"[redacted:env:{name}]")
        else:
            for name, secret in self._secrets():
                if name in only and secret in text:
                    text = text.replace(secret, f"[redacted:env:{name}]")
        for name, pattern in self._rules():
            if only is not None and not _pattern_applies(name, only, self.patterns):
                continue
            text = pattern.sub(f"[redacted:{name}]", text)
        return text

    # -- manifest -------------------------------------------------------------------------

    def to_manifest(self) -> dict[str, Any]:
        """What the run manifest records. Rule names only, never a secret value."""
        return {
            "enabled": self.enabled,
            "builtin": self.builtin,
            "at_boundary": list(self.at_boundary),
            "builtin_rules": sorted(BUILTIN_PATTERNS) if self.builtin else [],
            "declared_rules": sorted(self.patterns),
            "sensitive_keys": sorted(SENSITIVE_KEYS) if self.enabled else [],
            "secret_env": list(self.secret_env),
            "secret_env_unusable": [
                {"name": name, "reason": reason} for name, reason in self.unusable_env
            ],
        }


def _is_sensitive_key(key: Any) -> bool:
    return isinstance(key, str) and key.strip().lower().replace("-", "_") in SENSITIVE_KEYS


def _keys_apply(only: tuple[str, ...] | None) -> bool:
    """Whether the field-name rule is in force. Every rule is, where ``only`` is ``None``."""
    return only is None or "sensitive_keys" in only


def _pattern_applies(name: str, only: tuple[str, ...], declared: Mapping[str, str]) -> bool:
    """Whether one pattern is in force, by its own name or by the kind it belongs to."""
    if name in only:
        return True
    kind = "patterns" if name in declared else "builtin"
    return kind in only
