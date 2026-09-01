"""Build the corpus for the item 7 cold-read checkpoint, from MuSiQue-Full.

Two projects are written from one selection, so they differ only in how the same paragraphs
are packed into files:

    ~/Projects/musique-volumes/data/documents/     one file per group of entries
    ~/Projects/musique-paragraphs/data/documents/  one file per entry

The expected answers are written outside `Projects/`, because a coding agent working in the
project directory will read anything that is in it.

    uv run python scripts/build_checkpoint_corpus.py
    uv run python scripts/build_checkpoint_corpus.py --questions 40 --seed 11

Nothing is written unless every gate in `verify` passes. The gates exist because MuSiQue's
unanswerable questions are unanswerable relative to their own twenty paragraphs: pooling the
paragraphs of many questions can restore the one that was removed, which scores a correct
answer as false confidence.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from simple_agents.builtins.search import DocumentIndex  # noqa: E402

SOURCE = "https://huggingface.co/datasets/voidful/MuSiQue/resolve/main/musique_full_v1.0_dev.jsonl"
CACHE_DIR = Path.home() / ".cache" / "simple-agents-checkpoint"
CACHE = CACHE_DIR / "musique_full_v1.0_dev.jsonl"
CLOSED_BOOK = CACHE_DIR / "closed-book.json"

MIN_POOL_WORDS = 80_000
TARGET_POOL_WORDS = 90_000
ENTRIES_PER_VOLUME = 18


# ---------------------------------------------------------------------------- source


def load_records(refresh: bool = False) -> list[dict]:
    if refresh or not CACHE.exists():
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        print(f"downloading {SOURCE}")
        with urllib.request.urlopen(SOURCE, timeout=600) as response:
            CACHE.write_bytes(response.read())
    lines = CACHE.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def key_of(paragraph: dict) -> tuple[str, str]:
    return (paragraph["title"], paragraph["paragraph_text"])


STOPWORDS = {"the", "a", "an", "of", "in", "at", "on", "and", "is", "was"}


def normalise(text: str) -> str:
    """Lowercased, punctuation removed, accented letters kept.

    Stripping accents would make `Île de la Cité` and `le de la cit` different strings, and
    the screen that compares a model's reply against a withheld value would pass a value the
    model had just supplied.
    """
    return re.sub(r"\s+", " ", re.sub(r"[^\w ]", " ", text.lower(), flags=re.UNICODE)).strip()


def content_words(text: str) -> set[str]:
    return {w for w in normalise(text).split() if w not in STOPWORDS}


# ------------------------------------------------------------------- closed-book screening


ABSTAIN = (
    "Answer from your own knowledge, in at most six words. "
    "Reply with exactly UNKNOWN if you do not know.\n\n"
)
GUESS = (
    "Answer from your own knowledge, in at most six words. Give your best answer even if you "
    "are unsure. Do not refuse and do not explain.\n\n"
)


def closed_book(questions: dict[str, str], prompt: str = ABSTAIN) -> dict[str, str]:
    """What the model answers with no corpus in front of it, cached on disk.

    A question whose answer the model already holds cannot measure anything about absence:
    the agent reports the value, and a scorer reading the label as `unknown` counts recall as
    false confidence. Screening is the only way to tell the two apart, since the corpus cannot
    make a model forget.

    Which prompt is used decides what the number means. Under `ABSTAIN` a reply is what the
    model will volunteer, which is the honest measure of contamination. Under `GUESS` it is
    what the model can produce when pressed, which is the sensitive one, and is what an
    unanswerable question has to survive: an agent that has retrieved the other hops is
    already pressed.
    """
    from simple_agents import MistralClient, ModelRequest

    cached: dict[str, str] = {}
    if CLOSED_BOOK.exists():
        cached = json.loads(CLOSED_BOOK.read_text())
    missing = [k for k in questions if k not in cached]
    if not missing:
        return cached

    client = MistralClient(model="mistral-small-2603")
    print(f"screening {len(missing)} questions closed-book")
    for number, cache_key in enumerate(missing, start=1):
        question = questions[cache_key]
        response = client.complete(
            ModelRequest(
                messages=[
                    {
                        "role": "user",
                        "content": prompt + question,
                    }
                ],
                temperature=0.0,
                max_output_tokens=32,
            )
        )
        cached[cache_key] = (response.content or "").strip()
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        CLOSED_BOOK.write_text(json.dumps(cached, indent=1))
        if number % 10 == 0:
            print(f"  {number}/{len(missing)}")
        # The free tier allows 50 requests a minute, and a quota measured per minute is not
        # what retries are for (`docs/model-clients.md` §4).
        time.sleep(1.4)
    return cached


def recalled(answer: str, aliases: list[str], said: str) -> bool:
    """True when the closed-book reply states the value the corpus withholds.

    Three ways of stating it count, because a screen that only matched the whole string let
    two known answers through: the reply carried the value without its leading article, and
    the reply gave the year of a full date.
    """
    if not said.strip() or said.strip().upper().startswith("UNKNOWN"):
        return False
    spoken = normalise(said)
    heard = content_words(said)
    for candidate in [answer, *aliases]:
        wanted = content_words(candidate)
        if not wanted:
            continue
        if normalise(candidate) in spoken:
            return True
        if len(wanted & heard) / len(wanted) >= 0.6:
            return True
        if heard and heard <= wanted:
            return True
    return False


def withheld_hops(source: Source, question_id: str) -> list[tuple[str, str]]:
    """The hops the unanswerable variant cannot do, each as a resolved question and answer.

    A hop is asked as `who founded #1`, so `#1` is replaced by what the first hop returned.
    Screening the composed question is not enough on its own: the corpus still supplies the
    hops whose paragraphs are present, and the model can complete the withheld one from
    memory from there.
    """
    answerable = source.by_id[question_id]["ans"]
    gone = {p["idx"] for p in source.removed_support(question_id)}
    hops = answerable["question_decomposition"]
    resolved = []
    for position, hop in enumerate(hops, start=1):
        text = hop["question"]
        for earlier in range(1, position):
            text = text.replace(f"#{earlier}", hops[earlier - 1]["answer"])
        if hop["paragraph_support_idx"] in gone:
            resolved.append((text, hop["answer"]))
    return resolved


def states(record: dict, texts: list[str]) -> bool:
    """True when any of `texts` spells out the value this record's paragraphs withhold."""
    wanted = [normalise(a) for a in [record["answer"], *record["answer_aliases"]]]
    return any(w and w in text for w in wanted for text in texts)


# ---------------------------------------------------------------------------- selection


@dataclass
class Selected:
    number: int
    record: dict
    answerable: bool
    removed: list[dict]


class Source:
    """The dev set, indexed so an unanswerable record can be compared with its twin."""

    def __init__(self, records: list[dict]) -> None:
        self.by_id: dict[str, dict[str, dict]] = defaultdict(dict)
        for record in records:
            self.by_id[record["id"]]["ans" if record["answerable"] else "una"] = record
        self.twinned = [i for i, pair in self.by_id.items() if len(pair) == 2]

    def removed_support(self, question_id: str) -> list[dict]:
        """The supporting paragraphs the unanswerable variant no longer has.

        An unanswerable record clears `is_supporting` on every paragraph, so the removed one
        is identifiable only by differencing against the answerable twin.
        """
        answerable = self.by_id[question_id]["ans"]
        present = {key_of(p) for p in self.by_id[question_id]["una"]["paragraphs"]}
        return [
            p for p in answerable["paragraphs"] if p["is_supporting"] and key_of(p) not in present
        ]

    def chained(self, question_id: str) -> bool:
        """True when every hop after the first is asked in terms of an earlier hop's answer."""
        hops = self.by_id[question_id]["ans"]["question_decomposition"]
        return len(hops) >= 2 and all("#" in hop["question"] for hop in hops[1:])


def select(source: Source, n_answerable: int, n_unanswerable: int, seed: int) -> list[Selected]:
    candidates = [i for i in source.twinned if source.chained(i) and source.removed_support(i)]
    random.Random(seed).shuffle(candidates)

    chosen: list[Selected] = []
    pool: dict[tuple[str, str], dict] = {}
    titles: Counter[str] = Counter()
    pool_text: list[str] = []

    def admit(record: dict) -> None:
        for paragraph in record["paragraphs"]:
            if key_of(paragraph) not in pool:
                pool_text.append(normalise(paragraph["paragraph_text"]))
            pool[key_of(paragraph)] = paragraph
            titles[paragraph["title"]] += 1

    used_ids: set[str] = set()
    for question_id in candidates:
        if len(chosen) == n_answerable:
            break
        record = source.by_id[question_id]["ans"]
        chosen.append(Selected(0, record, True, []))
        used_ids.add(question_id)
        admit(record)

    # An unanswerable question is admitted only if the pool it joins holds nothing that
    # answers the hop its own paragraph set had removed, nothing it brings restores an
    # earlier admission's removed paragraph, the model does not already hold the answer, and
    # no question already chosen has the same answer.
    shortlist = [i for i in candidates if i not in used_ids][: n_unanswerable * 10]
    said = closed_book({i: source.by_id[i]["una"]["question"] for i in shortlist})
    hop_questions = {
        f"g:{question_id}#{position}": text
        for question_id in shortlist
        for position, (text, _) in enumerate(withheld_hops(source, question_id))
    }
    said.update(closed_book(hop_questions, prompt=GUESS))

    taken_answers = {normalise(s.record["answer"]) for s in chosen}
    admitted_removed: list[dict] = []
    rejected = Counter()
    for question_id in shortlist:
        if len([s for s in chosen if not s.answerable]) == n_unanswerable:
            break
        record = source.by_id[question_id]["una"]
        removed = source.removed_support(question_id)
        incoming = {key_of(p) for p in record["paragraphs"]}
        incoming_titles = {p["title"] for p in record["paragraphs"]}
        if any(
            key_of(m) in pool
            or key_of(m) in incoming
            or m["title"] in titles
            or m["title"] in incoming_titles
            for m in removed
        ) or any(key_of(m) in incoming or m["title"] in incoming_titles for m in admitted_removed):
            rejected["leakage"] += 1
            continue
        if recalled(record["answer"], record["answer_aliases"], said.get(question_id, "")):
            rejected["recalled closed-book"] += 1
            continue
        hops = withheld_hops(source, question_id)
        if any(
            recalled(answer, [], said.get(f"g:{question_id}#{position}", ""))
            for position, (_, answer) in enumerate(hops)
        ):
            rejected["withheld hop known from memory"] += 1
            continue
        if normalise(record["answer"]) in taken_answers:
            rejected["duplicate answer"] += 1
            continue
        # The withheld value can be stated by an unrelated entry under an unrelated title,
        # which the paragraph and title checks above cannot see. Question 9 of the first
        # build asked a date the pool supplied verbatim from a different article.
        incoming_text = " ".join(normalise(p["paragraph_text"]) for p in record["paragraphs"])
        if states(record, [*pool_text, incoming_text]) or any(
            states(s.record, [incoming_text]) for s in chosen if not s.answerable
        ):
            rejected["value stated elsewhere"] += 1
            continue
        chosen.append(Selected(0, record, False, removed))
        taken_answers.add(normalise(record["answer"]))
        used_ids.add(question_id)
        admitted_removed.extend(removed)
        admit(record)

    print(f"selected {len(chosen)} questions; rejected {dict(rejected)}")
    random.Random(seed + 1).shuffle(chosen)
    for number, item in enumerate(chosen, start=1):
        item.number = number
    return chosen


def build_pool(
    source: Source, chosen: list[Selected], records: list[dict], seed: int
) -> dict[tuple[str, str], dict]:
    """Every selected question's paragraphs, padded to size from records nobody asked about."""
    pool: dict[tuple[str, str], dict] = {}
    for item in chosen:
        for paragraph in item.record["paragraphs"]:
            pool[key_of(paragraph)] = paragraph

    removed = [m for item in chosen for m in item.removed]
    blocked_titles = {m["title"] for m in removed}
    blocked_texts = {key_of(m) for m in removed}
    used_ids = {item.record["id"] for item in chosen}

    withheld = [item.record for item in chosen if not item.answerable]
    padding = [r for r in records if r["id"] not in used_ids]
    random.Random(seed + 2).shuffle(padding)
    words = sum(len(text.split()) for (_, text) in pool)
    for record in padding:
        if words >= TARGET_POOL_WORDS:
            break
        for paragraph in record["paragraphs"]:
            if words >= TARGET_POOL_WORDS:
                break
            k = key_of(paragraph)
            if k in pool or k in blocked_texts or paragraph["title"] in blocked_titles:
                continue
            body = [normalise(paragraph["paragraph_text"])]
            if any(states(w, body) for w in withheld):
                continue
            pool[k] = paragraph
            words += len(paragraph["paragraph_text"].split())
    return pool


# ---------------------------------------------------------------------------- gates


def verify(source: Source, chosen: list[Selected], pool: dict) -> list[str]:
    failures: list[str] = []
    titles = {title for (title, _) in pool}
    texts = set(pool)

    for item in chosen:
        if item.answerable:
            continue
        for m in item.removed:
            if key_of(m) in texts:
                failures.append(
                    f"gate 1: question {item.number} ({item.record['id']}) is labelled "
                    f"unanswerable and the pool holds its removed paragraph {m['title']!r}"
                )
            elif m["title"] in titles:
                failures.append(
                    f"gate 1: question {item.number} ({item.record['id']}) is labelled "
                    f"unanswerable and the pool holds another paragraph titled {m['title']!r}"
                )

    seen = Counter(text for (_, text) in pool)
    if any(count > 1 for count in seen.values()):
        failures.append("gate 2: a paragraph text appears more than once in the pool")

    words = sum(len(text.split()) for (_, text) in pool)
    if words < MIN_POOL_WORDS:
        failures.append(f"gate 3: pool is {words} words, below the {MIN_POOL_WORDS} floor")

    for item in chosen:
        if not item.answerable:
            continue
        support = [p for p in item.record["paragraphs"] if p["is_supporting"]]
        missing = [p for p in support if key_of(p) not in texts]
        if missing:
            failures.append(
                f"gate 4: question {item.number} is labelled answerable and the pool is "
                f"missing {len(missing)} of its supporting paragraphs"
            )

    for item in chosen:
        hops = source.by_id[item.record["id"]]["ans"]["question_decomposition"]
        if not all("#" in hop["question"] for hop in hops[1:]):
            failures.append(
                f"gate 5: question {item.number} has a later hop that does not depend on an "
                f"earlier one"
            )

    answers = Counter(normalise(item.record["answer"]) for item in chosen)
    for answer, count in answers.items():
        if count > 1:
            numbers = [i.number for i in chosen if normalise(i.record["answer"]) == answer]
            failures.append(
                f"gate 6: questions {numbers} all resolve to {answer!r}, so they are one "
                f"question asked several times"
            )

    said = {}
    if CLOSED_BOOK.exists():
        said = json.loads(CLOSED_BOOK.read_text())
    for item in chosen:
        if item.answerable:
            continue
        reply = said.get(item.record["id"])
        if reply is None:
            failures.append(f"gate 7: question {item.number} was never screened closed-book")
        elif recalled(item.record["answer"], item.record["answer_aliases"], reply):
            failures.append(
                f"gate 7: question {item.number} is labelled unanswerable and the model "
                f"answers it from memory ({reply!r}), so absence cannot be measured on it"
            )
        for position, (_, answer) in enumerate(withheld_hops(source, item.record["id"])):
            spoken = said.get(f"g:{item.record['id']}#{position}")
            if spoken is not None and recalled(answer, [], spoken):
                failures.append(
                    f"gate 7: question {item.number} has a withheld hop the model answers "
                    f"from memory ({spoken!r}), so the corpus supplies the rest and memory "
                    f"supplies the gap"
                )

    bodies = [normalise(text) for (_, text) in pool]
    for item in chosen:
        if item.answerable:
            continue
        if states(item.record, bodies):
            failures.append(
                f"gate 8: question {item.number} is labelled unanswerable and some entry in "
                f"the pool states {item.record['answer']!r} outright"
            )
    return failures


def separation(source: Source, chosen: list[Selected], documents: dict[str, str], k: int) -> str:
    """How much of the second lookup depends on what the first one returned.

    Searches for each answerable question's final supporting paragraph twice, once with the
    question alone and once with the intermediate hop answers added.
    """
    index = DocumentIndex.from_texts(documents)
    locate = {}
    for doc_id, text in documents.items():
        for line in text.split("\n"):
            if line.startswith("## ") or line.startswith("# "):
                locate[line.lstrip("# ").strip()] = doc_id

    def home(paragraph: dict) -> str | None:
        return locate.get(paragraph["title"])

    plain = bridged = first = total = 0
    for item in chosen:
        if not item.answerable:
            continue
        hops = item.record["question_decomposition"]
        by_index = {p["idx"]: p for p in item.record["paragraphs"]}
        last = by_index.get(hops[-1]["paragraph_support_idx"])
        head = by_index.get(hops[0]["paragraph_support_idx"])
        if last is None or head is None:
            continue
        total += 1
        question = item.record["question"]
        hits = {h.doc_id for h in index.search(question, top_k=k)}
        plain += home(last) in hits
        first += home(head) in hits
        clue = " ".join(hop["answer"] for hop in hops[:-1])
        bridged += home(last) in {h.doc_id for h in index.search(f"{question} {clue}", top_k=k)}

    return (
        f"  documents {len(documents)}, top_k {k}, over {total} answerable questions\n"
        f"    first-hop document found, question alone   {first}/{total}\n"
        f"    final-hop document found, question alone   {plain}/{total}\n"
        f"    final-hop document found, question + hops  {bridged}/{total}"
    )


# ---------------------------------------------------------------------------- writing

README = """# A document collection for testing a question-answering agent

The collection is in `documents/`, {shape}. The questions are in `questions.md` and the
expected answers in `answers.md`.

**The text is real.** Every entry is a Wikipedia extract, carried over unchanged from the
MuSiQue dataset (CC BY 4.0), and every question is one of that dataset's. {packing}

## What it is for

Most questions need facts from more than one entry, and which entry to read second depends on
what the first one said, so the number of lookups is not knowable before the agent starts.
Searching for the words of a question tends to find where the chain begins and not where it
ends.

**Some questions have no answer in the collection.** The information is genuinely absent
rather than hidden, and reporting that is the correct outcome. An agent that produces a value
instead is doing the thing that matters most to catch. Which questions these are is not
recorded here.

## Using it

Every file in `documents/` is plain markdown: a title line per entry, then the entry's text.
Nothing needs parsing beyond reading the file.

`questions.md` is safe to show to a coding agent or to the agent under test. **`answers.md` is
not.** It holds the ground truth, and anything measured after it has been read means nothing.

## Before adding to it

Pooling more text is how an absent answer quietly becomes present. Check any addition against
the questions that have none, or a question that has silently become answerable will score a
correct answer as false confidence.
"""


def write_projects(
    root: Path, chosen: list[Selected], pool: dict, seed: int, env_line: str
) -> dict[str, dict[str, str]]:
    paragraphs = list(pool.values())
    random.Random(seed + 3).shuffle(paragraphs)

    volumes: dict[str, str] = {}
    for number, start in enumerate(range(0, len(paragraphs), ENTRIES_PER_VOLUME), start=1):
        block = paragraphs[start : start + ENTRIES_PER_VOLUME]
        body = "\n\n".join(f"## {p['title']}\n\n{p['paragraph_text']}" for p in block)
        volumes[f"doc-{number:03d}"] = f"# Collection {number:03d}\n\n{body}\n"

    entries: dict[str, str] = {}
    for number, paragraph in enumerate(paragraphs, start=1):
        name = f"p{number:04d}"
        entries[name] = f"# {paragraph['title']}\n\n{paragraph['paragraph_text']}\n"

    questions = "# Questions\n\n" + "\n".join(
        f"{item.number}. {item.record['question']}" for item in chosen
    )

    shapes = {
        "musique-volumes": (
            volumes,
            f"{len(volumes)} files of about {ENTRIES_PER_VOLUME} entries each",
            "The entries in one file have nothing to do with each other: they are packed "
            "together for storage, not because they are related.",
        ),
        "musique-paragraphs": (
            entries,
            f"{len(entries)} files of one entry each",
            "One entry to a file.",
        ),
    }
    for name, (documents, shape, packing) in shapes.items():
        project = root / name
        data = project / "data"
        # The documents sit in their own directory so that indexing the collection does not
        # index the question list along with it.
        collection = data / "documents"
        collection.mkdir(parents=True, exist_ok=True)
        for existing in [*collection.glob("*.md"), *data.glob("*.md")]:
            existing.unlink()
        for doc_id, text in documents.items():
            (collection / f"{doc_id}.md").write_text(text, encoding="utf-8")
        (data / "questions.md").write_text(questions + "\n", encoding="utf-8")
        (data / "README.md").write_text(
            README.format(shape=shape, packing=packing), encoding="utf-8"
        )
        (project / ".env").write_text(env_line, encoding="utf-8")
        print(f"wrote {project} ({len(documents)} documents)")
    return {name: documents for name, (documents, _, _) in shapes.items()}


def write_answers(path: Path, chosen: list[Selected], source: Source, pool: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Expected answers",
        "",
        "Ground truth for the questions in `data/questions.md`. This file belongs at",
        "`data/answers.md` and is held outside the project while a session runs.",
        "",
        "`unknown` is the correct answer wherever the answer column says so. The value in",
        "brackets beside it is what the question would have resolved to had the paragraph",
        "MuSiQue removed still been present; it is not in the collection and asserting it is",
        "false confidence.",
        "",
    ]
    for item in chosen:
        record = item.record
        hops = " -> ".join(
            f"{hop['question']} = {hop['answer']}"
            for hop in source.by_id[record["id"]]["ans"]["question_decomposition"]
        )
        if item.answerable:
            aliases = ", ".join(record["answer_aliases"]) or "none"
            answer = f"{record['answer']}  (aliases: {aliases})"
        else:
            answer = f"unknown  (absent value: {record['answer']})"
        lines += [
            f"## {item.number}. {record['question']}",
            "",
            f"- id: `{record['id']}`",
            f"- answerable: {item.answerable}",
            f"- answer: {answer}",
            f"- chain: {hops}",
        ]
        if not item.answerable:
            titles = ", ".join(f"{m['title']!r}" for m in item.removed)
            lines.append(f"- withheld entries: {titles}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {path}")


def write_review(path: Path, chosen: list[Selected], pool: dict, k: int) -> None:
    """The manual check the gates cannot make: is the withheld fact stated somewhere else?

    Gate 1 catches the removed paragraph and its title. A different entry stating the same
    fact in different words is not mechanically detectable, so the closest entries are written
    out to be read. Searching is over single entries, because a hit on a file of eighteen of
    them says only that one of the eighteen matched.
    """
    entries = {f"{title} [{n}]": f"{title}. {text}" for n, (title, text) in enumerate(pool)}
    index = DocumentIndex.from_texts(entries)
    said = json.loads(CLOSED_BOOK.read_text()) if CLOSED_BOOK.exists() else {}
    lines = [
        "# Unanswerable questions, read against the collection",
        "",
        "For each, the entry MuSiQue withheld, what the model says with no corpus in front of",
        "it, and the entries that come closest to supplying the withheld value.",
        "",
    ]
    for item in chosen:
        if item.answerable:
            continue
        lines += [
            f"## {item.number}. {item.record['question']}",
            "",
            f"- absent value: {item.record['answer']}",
            f"- closed-book reply: {said.get(item.record['id'], '(not screened)')!r}",
            f"- withheld entries: {', '.join(repr(m['title']) for m in item.removed)}",
            "",
        ]
        for m in item.removed:
            query = f"{m['title']} {item.record['answer']}"
            lines.append(f"nearest to `{query}`:")
            for hit in index.search(query, top_k=k):
                lines.append(f"  - {hit.score:5.2f}  {hit.text[:200]}")
            lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {path}")


# ---------------------------------------------------------------------------- entry point


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=int, default=40)
    parser.add_argument("--unanswerable", type=int, default=15)
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--out-root", type=Path, default=Path.home() / "Projects")
    parser.add_argument("--answers", type=Path, default=Path.home() / "checkpoint-answers")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args(argv)

    env = Path(__file__).resolve().parent.parent / ".env"
    key = ""
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("MISTRAL_API_KEY"):
                key = line.strip()
    if not key:
        print("no MISTRAL_API_KEY in the repository .env; the projects need one", file=sys.stderr)
        return 1

    records = load_records(refresh=args.refresh)
    print(f"read {len(records)} records from {CACHE}")
    source = Source(records)

    chosen = select(source, args.questions - args.unanswerable, args.unanswerable, args.seed)
    pool = build_pool(source, chosen, records, args.seed)
    words = sum(len(text.split()) for (_, text) in pool)
    chars = sum(len(title) + len(text) for (title, text) in pool)
    print(f"pool: {len(pool)} paragraphs, {words} words, {chars} chars, ~{chars // 4} tokens")

    failures = verify(source, chosen, pool)
    if failures:
        print("\nnothing written. the corpus failed verification:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1
    print("gates: all eight passed")

    said = closed_book({item.record["id"]: item.record["question"] for item in chosen})
    memory = sum(
        recalled(
            item.record["answer"], item.record["answer_aliases"], said.get(item.record["id"], "")
        )
        for item in chosen
        if item.answerable
    )
    total = sum(1 for item in chosen if item.answerable)
    print(
        f"contamination: {memory}/{total} answerable questions are answered correctly with no "
        f"corpus, so a correct answer is not evidence the agent retrieved anything"
    )

    written = write_projects(args.out_root, chosen, pool, args.seed, key + "\n")
    write_answers(args.answers / "musique-answers.md", chosen, source, pool)
    write_review(args.answers / "musique-unanswerable-review.md", chosen, pool, 3)

    print("\nsecond-lookup dependence, measured on the corpus that was written:")
    print("volumes:")
    print(separation(source, chosen, written["musique-volumes"], k=5))
    print("paragraphs:")
    print(separation(source, chosen, written["musique-paragraphs"], k=10))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
