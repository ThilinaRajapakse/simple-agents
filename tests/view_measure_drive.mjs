/* Drive the measure page's drill-downs: an outcome, a criterion or a group lights the rollouts
 * behind the number in the example grid, a figure opens to its numbers, a rollout opens to
 * what it answered, and a rung shades the drawing.
 *
 *     node tests/view_measure_drive.mjs <path to view.html>
 */
import fs from "node:fs";
import {runPage} from "./view_harness.mjs";

const {page, look} = runPage(fs.readFileSync(process.argv[2], "utf8"));
page.showPage("measure");
const m = page.data().measured || {};
const out = {};

const outcome = Object.keys(m.by_outcome || {}).find(k => k !== "correct") || Object.keys(m.by_outcome || {})[0];
page.setBrowserFilter("outcome", outcome, (m.by_outcome || {})[outcome]);
out.after_outcome = {filter: page.filter(), sections: look().sections};
page.setBrowserFilter("outcome", outcome, (m.by_outcome || {})[outcome]);   // the same again clears it
out.cleared = page.filter();

const keys = Object.keys((m.groups || {}).keys || {});
if (keys.length) {
  const cell = m.groups.keys[keys[0]][0];
  page.setBrowserFilter("group", cell.value, cell.example_ids);
  out.after_group = {filter: page.filter(), examples: cell.example_ids};
}

const figure = (m.metrics || [])[0];
if (figure) {
  page.openFigure(figure.name);
  out.after_figure = {name: figure.name, sections: look().sections};
  page.openFigure(null);
}
const row = (m.browser || []).find(r => r.rollouts.length);
if (row) {
  page.openCell(`${row.example}:${row.rollouts[0].rollout}`);
  out.after_cell = {example: row.example, answer: row.rollouts[0].answer, sections: look().sections};
  page.openCell(null);
}

const ladder = (m.ladders || [])[0];
if (ladder) {
  const rung = ladder.rungs.find(r => !r.whole);
  page.shadeRung(ladder.of, rung.file);
  const graph = document.getElementById("graph");
  const shaded = graph.children.filter(g => g.attrs.opacity === "0.3").map(g => g.attrs["data-node"]);
  const drawn = graph.children.filter(g => g.tag === "g" && g.attrs["data-node"]).map(g => g.attrs["data-node"]);
  out.after_rung = {nodes: rung.nodes, shaded, drawn};
}
/* A rollout opened from the grid is walked on the build page, which is where the walk lives.
   It is the evaluation's run rather than the project's, and the region says which. */
const walks = (page.data().walks || {}).walks || {};
const wrong = (m.browser || []).flatMap(r => r.rollouts).find(x => x.run && walks[x.run]);
if (wrong) {
  page.walkTo(wrong.run);
  out.after_walk = {run: wrong.run, page: page.page(), sections: look().sections};
}

console.log(JSON.stringify(out));
