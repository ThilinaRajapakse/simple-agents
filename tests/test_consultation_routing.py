"""Where `on_reply` looks for the reply, and what it does when it cannot find one.

`docs/tools.md` §4.6.1 says to use `field=` where the node returns "a model or a dict". It was
an attribute lookup, so over a dict it found nothing, and a missing reply was indistinguishable
from a refusal: the route silently took the `declined` branch. A field annotated `str` had the
same outcome by coercing the `Reply` and dropping `chose`.

A route that cannot find the reply refuses, which is the case the typed answer was added to
remove: a branch picked on an answer nobody read.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from simple_agents.builtins.consult import Reply, consult, on_reply
from simple_agents.errors import CallerFacingError

OPTIONS = ("express", "standard")
CHOSE = {"express": "apply", "standard": "wait"}


def reply(text: str = "express", chose: str | None = "express") -> Reply:
    return Reply(text, chose=chose, options=OPTIONS)


class Typed(BaseModel):
    """A node output holding the reply under a field typed as one."""

    answer: Reply

    model_config = {"arbitrary_types_allowed": True}


class Stringy(BaseModel):
    """The same shape with the field typed `str`, which drops `chose`."""

    answer: str


class TestOverADict:
    ROUTE = staticmethod(
        on_reply(
            CHOSE,
            field="answer",
            unmatched="amend",
            declined="stop",
            unavailable="proceed",
            shelved="proceed",
        )
    )

    def test_the_reply_under_the_named_key_is_found(self) -> None:
        assert self.ROUTE({"answer": reply()}, None) == "apply"

    def test_an_unmatched_reply_under_the_key_takes_the_unmatched_branch(self) -> None:
        unmatched = reply("make it 3 stars", chose=None)

        assert self.ROUTE({"answer": unmatched}, None) == "amend"

    def test_a_refusal_under_the_key_takes_the_declined_branch(self) -> None:
        assert self.ROUTE({"answer": None}, None) == "stop"

    def test_a_key_that_is_not_there_is_refused_rather_than_routed(self) -> None:
        with pytest.raises(CallerFacingError) as raised:
            self.ROUTE({"reply": reply()}, None)

        assert "found no 'answer'" in str(raised.value)

    def test_the_refusal_names_what_the_node_did_return(self) -> None:
        with pytest.raises(CallerFacingError) as raised:
            self.ROUTE({"reply": reply(), "question": "which fit?"}, None)

        assert "'question', 'reply'" in str(raised.value)


class TestOverAModel:
    ROUTE = staticmethod(
        on_reply(
            CHOSE,
            field="answer",
            unmatched="amend",
            declined="stop",
            unavailable="proceed",
            shelved="proceed",
        )
    )

    def test_a_field_typed_reply_is_found(self) -> None:
        assert self.ROUTE(Typed(answer=reply()), None) == "apply"

    def test_a_field_typed_str_is_refused_rather_than_routed(self) -> None:
        """Coercion keeps the text and drops `chose`, which used to read as a refusal."""
        with pytest.raises(CallerFacingError) as raised:
            self.ROUTE(Stringy(answer=reply()), None)

        assert "no `chose`" in str(raised.value)
        assert "type it `Reply`" in str(raised.value)

    def test_a_field_that_is_not_there_is_refused(self) -> None:
        with pytest.raises(CallerFacingError):
            on_reply(
                CHOSE,
                field="missing",
                unmatched="amend",
                declined="stop",
                unavailable="proceed",
                shelved="proceed",
            )(Typed(answer=reply()), None)


class TestWithNoField:
    ROUTE = staticmethod(
        on_reply(
            CHOSE, unmatched="amend", declined="stop", unavailable="proceed", shelved="proceed"
        )
    )

    def test_the_reply_itself_routes(self) -> None:
        assert self.ROUTE(reply(), None) == "apply"

    def test_none_is_a_refusal(self) -> None:
        assert self.ROUTE(None, None) == "stop"

    def test_a_dict_is_refused_rather_than_read_as_a_refusal(self) -> None:
        with pytest.raises(CallerFacingError) as raised:
            self.ROUTE({"answer": reply()}, None)

        assert "field='answer'" in str(raised.value)

    def test_a_plain_string_is_refused(self) -> None:
        with pytest.raises(CallerFacingError):
            self.ROUTE("express", None)


class TestTheRouteIsStillDescribedInTheManifest:
    def test_field_is_carried_on_the_route(self) -> None:
        route = on_reply(
            CHOSE,
            field="answer",
            unmatched="amend",
            declined="stop",
            unavailable="proceed",
            shelved="proceed",
        )

        assert route.consultation_route["field"] == "answer"


class TestTheToolHasAVersion:
    """A consult tool used to build with `version=None`, so it recorded under a null one."""

    @staticmethod
    def by_email(question, options=None, about=None):
        return "express"

    @staticmethod
    def by_stdin(question, options=None, about=None):
        return "standard, if that is still going"

    @staticmethod
    def picky(answer, options):
        return options[0] if answer else None

    def test_a_version_is_derived(self) -> None:
        assert consult(self.by_email, answered_by="end_user").version is not None

    def test_the_same_channel_derives_the_same_version(self) -> None:
        assert (
            consult(self.by_email, answered_by="end_user").version
            == consult(self.by_email, answered_by="end_user").version
        )

    def test_two_channels_derive_different_versions(self) -> None:
        assert (
            consult(self.by_email, answered_by="end_user").version
            != consult(self.by_stdin, answered_by="end_user").version
        )

    def test_a_matcher_moves_the_version(self) -> None:
        """Two tools that read one answer differently must not share a cassette entry."""
        assert (
            consult(self.by_email, answered_by="end_user").version
            != consult(self.by_email, answered_by="end_user", match=self.picky).version
        )

    def test_a_declared_version_is_kept(self) -> None:
        assert consult(self.by_email, version="v3", answered_by="end_user").version == "v3"

    def test_a_channel_with_no_readable_source_builds_with_no_version(self) -> None:
        """`None` says the library could not derive one, which `version=` is for.

        It read a version off this module's own tool function until 2026-08-15, which was the
        same string for every unreadable channel and moved whenever the library was edited
        (`F-8`).
        """
        import functools

        built = consult(functools.partial(self.by_email), answered_by="end_user")

        assert built.version is None
        assert (
            consult(functools.partial(self.by_email), answered_by="end_user", version="v3").version
            == "v3"
        )

    def test_the_version_is_the_channels_and_the_matchers_alone(self) -> None:
        """What a consultation stores is what the end user said, which no library edit alters.

        The version covered this module's own tool function until 2026-08-15, so a library
        upgrade made every recorded consultation miss, silently (`F-8`). Naming the tool
        differently is library-side too and moves nothing.
        """
        one = consult(self.by_email, answered_by="end_user")
        renamed = consult(self.by_email, answered_by="end_user", name="ask_the_buyer")
        described = consult(self.by_email, answered_by="end_user", description="Ask about fit.")

        assert one.version == renamed.version == described.version
