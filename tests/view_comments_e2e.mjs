/* Drive the served page's own comment loop against a live `simple-agents view --serve`.
 *
 *     node tests/view_comments_e2e.mjs <base url> say <the words>
 *     node tests/view_comments_e2e.mjs <base url> read
 *     node tests/view_comments_e2e.mjs <base url> agree
 *     node tests/view_comments_e2e.mjs <base url> agree-decision <name>
 *     node tests/view_comments_e2e.mjs <base url> select-words <the words>
 *
 * `say` loads the page from the server, selects the project, sends the words through the
 * page's own POST path, refreshes the way the page does, and prints what the conversation
 * section then shows. `read` loads the page fresh and prints the same, which is how a reply
 * the coding agent wrote is seen arriving. `agree` presses the one click the `shape` page
 * offers on a design that is unconfirmed, and `agree-decision` the one it offers on a
 * decision, each through the page's own function rather than through words typed here.
 * `select-words` drags across words in the first prompt on the prompts page and sends the
 * comment the way the page does, which is what carries the words, the run and the
 * instruction's digest into the thread.
 *
 * The DOM is the harness stub, so what this proves is the page's script against the real
 * server and the real file, never how it looks.
 */

import {runPage} from "./view_harness.mjs";

const [base, mode, ...words] = process.argv.slice(2);
const said = words.join(" ");

/* Captured before `runPage` replaces the global with this very function. */
const realFetch = globalThis.fetch;
const carried = (path, options) => realFetch(new URL(path, base), options);

const response = await fetch(new URL("/", base));
if (!response.ok) {
  console.error(`the server did not serve the page: ${response.status}`);
  process.exit(1);
}
const {page, look} = runPage(await response.text(), {fetchImpl: carried});

try {
  if (mode === "say") {
    page.select("project", "the whole project", "comment");
    await page.post("/api/comment", {at: "project", said, kind: "comment"});
    await page.refresh();
  }
  if (mode === "agree") {
    page.showPage("shape");
    const held = (page.data().findings || []).find(f => (f.actions || []).length);
    if (!held) { console.error("no finding carries an action to press"); process.exit(1); }
    await page.oneClick(held.actions[0]);
  }
  if (mode === "agree-decision") {
    page.showPage("shape");
    await page.agreeToDecision(said);
  }
  if (mode === "select-words") {
    page.showPage("prompts");
    const first = page.prompts.steps()[0];
    const picked = page.prompts.words(first.key, said);
    await page.post("/api/comment", {at: picked.address, said: `Reword this: ${said}`,
                                     kind: "comment", quoted: picked.quoted,
                                     run: picked.run, instruction: picked.instruction});
    await page.refresh();
  }
  page.showPage("ship");   // the conversation lives on the ship page
  const threads = (page.data().comments || []).map(c => ({
    id: c.id, at: c.at, said: c.said, status: c.status, about: c.about,
    quoted: c.quoted, run: c.run, instruction: c.instruction,
    replies: (c.replies || []).map(r => ({by: r.by, said: r.said})),
  }));
  console.log(JSON.stringify({live: page.data().live, threads, sections: look().sections}));
} catch (error) {
  console.error(`${error.name}: ${error.message}\n${error.stack || ""}`);
  process.exit(1);
}
