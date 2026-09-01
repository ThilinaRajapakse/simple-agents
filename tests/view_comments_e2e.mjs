/* Drive the served page's own comment loop against a live `simple-agents view --serve`.
 *
 *     node tests/view_comments_e2e.mjs <base url> say <the words>
 *     node tests/view_comments_e2e.mjs <base url> read
 *     node tests/view_comments_e2e.mjs <base url> agree
 *     node tests/view_comments_e2e.mjs <base url> agree-decision <name>
 *
 * `say` loads the page from the server, selects the project, sends the words through the
 * page's own POST path, refreshes the way the page does, and prints what the conversation
 * section then shows. `read` loads the page fresh and prints the same, which is how a reply
 * the coding agent wrote is seen arriving. `agree` presses the one click the `shape` page
 * offers on a design nobody has agreed to, and `agree-decision` the one it offers on a
 * decision, each through the page's own function rather than through words typed here. The
 * DOM is the harness stub, so what this proves is the page's script against the real server
 * and the real file, never how it looks.
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
  page.showPage("ship");   // the conversation lives on the ship page
  const threads = (page.data().comments || []).map(c => ({
    id: c.id, at: c.at, said: c.said, status: c.status,
    replies: (c.replies || []).map(r => ({by: r.by, said: r.said})),
  }));
  console.log(JSON.stringify({live: page.data().live, threads, sections: look().sections}));
} catch (error) {
  console.error(`${error.name}: ${error.message}\n${error.stack || ""}`);
  process.exit(1);
}
