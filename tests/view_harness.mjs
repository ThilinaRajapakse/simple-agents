/* Run one rendered `view.html` the way a browser would, and report what it drew.
 *
 * The page is about 3,000 lines of JavaScript shipped inside a Python package, and the suite
 * could only ever read it as text. A measure control that hid the one measure a project had
 * sat in front of a green 3,353-test run, because rendering the markup and grepping it cannot
 * tell whether the script throws or what it decides.
 *
 * Usage:
 *
 *     node tests/view_harness.mjs <path to view.html>
 *     node tests/view_harness.mjs <path to view.html> --geometry sysmap|graph [pipeline]
 *
 * The first reports what the page drew and survived. The second reports where each shape in
 * one drawing was put, which is how a test says that everything drawn is inside the frame
 * that is drawn: both drawings laid their contents on one unwrapped row, and on a system of
 * eight pipelines and nine stores some of them landed outside it.
 *
 * It prints one JSON object on stdout and exits 0, or prints the error and exits 1. The DOM
 * below is the smallest one the page runs against: enough for it to build its SVG and its
 * sections, and no more. It is not a browser, so it proves the script runs and decides
 * correctly, never that the result looks right.
 *
 * `runPage` is importable (tests/view_comments_e2e.mjs runs the page against a live server
 * through it, with `fetchImpl` carrying requests to a real socket).
 */

import fs from "node:fs";

/* The page's script is one IIFE, so nothing inside it is reachable from outside. The harness
   hands itself a handle on the few functions an interaction goes through, by appending one
   line inside that closure. The shipped template is not touched. */
const HANDLE = `
globalThis.__page = {
  selectPipe, showStep, showResource, drawSystem, drawGraph, renderSections, showPage,
  select, refresh, setBrowserFilter, renderStory, lightStep,
  oneClick, agreeToDecision,
  storyCursor: () => storyCursor,
  openFigure: name => { openFigure = name; renderSections(); },
  openCell: key => { openCell = key; renderSections(); },
  filter: () => browserFilter ? {kind: browserFilter.kind, value: browserFilter.value,
                                 examples: [...browserFilter.examples]} : null,
  shadeRung: (of, file) => {
    const ladder = ((DATA.measured || {}).ladders || []).find(l => l.of === of);
    const rung = ladder && ladder.rungs.find(r => r.file === file);
    rungShown = rung && !rung.whole ? {key: of + ":" + file,
      has: id => rung.nodes.includes(id) || rung.nodes.some(p => id.startsWith(p + "."))} : null;
    drawGraph(); renderSections();
  },
  post: (path, payload) => post(path, payload),
  walkTo: run => { walking = run; walkOpen = null; showPage(pageFor('build')); },
  data: () => DATA,
  pipelines: () => DECLARED,
  resources: () => DATA.resources || [],
  stages: () => stageSet(),
  page: () => shownStage,
  set: (what, value) => { if (what === "measure") measure = value; else population = value; },
  reading: () => ({measure, population}),
};
`;

export function runPage(pageText, {fetchImpl} = {}) {
  const script = [...pageText.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]).join("\n");
  const embedded = pageText.match(
    /<script id="view-data" type="application\/json">([\s\S]*?)<\/script>/,
  );
  if (!script || !embedded) {
    throw new Error("the page carries no script block or no view-data block");
  }
  const DATA = JSON.parse(embedded[1]);
  const runnable = script.replace(/\n\}\)\(\);\s*$/, `\n${HANDLE}\n})();\n`);
  if (runnable === script) {
    throw new Error("the script does not end in the expected closure; the harness needs updating");
  }

  // -- the DOM -----------------------------------------------------------------------------
  const everything = [];

  function node(tag) {
    const self = {
      tag, children: [], attrs: {}, dataset: {}, style: {}, textContent: "",
      hidden: false, value: "", disabled: false,
      classList: {add() {}, remove() {}, contains: () => false, toggle() {}},
      onclick: null, onchange: null, oninput: null, ontoggle: null,
      setAttribute(key, value) { this.attrs[key] = String(value); },
      getAttribute(key) { return key in this.attrs ? this.attrs[key] : null; },
      removeAttribute(key) { delete this.attrs[key]; },
      appendChild(child) { this.children.push(child); everything.push(child); return child; },
      insertBefore(child) { return this.appendChild(child); },
      removeChild() {}, remove() {},
      addEventListener() {}, removeEventListener() {}, dispatchEvent() {},
      querySelector: () => node("div"),
      querySelectorAll: () => [],
      closest: () => node("div"),
      getBoundingClientRect: () => ({width: 900, height: 600, top: 0, left: 0}),
      scrollIntoView() {}, focus() {}, blur() {}, click() {},
    };
    /* Assigning `innerHTML` replaces what a holder contains, so the stub has to drop the
       children too. Without this a redraw adds to the last one and every count is a running
       total, which hides exactly the kind of defect this file exists to catch. */
    let markup = "";
    Object.defineProperty(self, "innerHTML", {
      get: () => markup,
      set(value) { markup = String(value); self.children.length = 0; },
    });
    return self;
  }

  const byId = {};
  globalThis.document = {
    getElementById(id) {
      if (!byId[id]) {
        byId[id] = node("div");
        if (id === "view-data") byId[id].textContent = JSON.stringify(DATA);
      }
      return byId[id];
    },
    createElement: tag => node(tag),
    createElementNS: (_ns, tag) => node(tag),
    querySelector: () => node("div"),
    querySelectorAll: () => [],
    addEventListener() {},
    documentElement: node("html"),
    body: node("body"),
  };
  globalThis.matchMedia = () => ({matches: false, addEventListener() {}, addListener() {}});
  globalThis.window = {
    matchMedia: globalThis.matchMedia, addEventListener() {}, scrollTo() {}, scrollY: 0,
    location: {href: "", search: "", pathname: "/", hash: ""},
  };
  globalThis.getComputedStyle = () => ({getPropertyValue: () => "#000000"});
  globalThis.localStorage = {getItem: () => null, setItem() {}, removeItem() {}};
  globalThis.setInterval = () => 0;
  globalThis.setTimeout = () => 0;
  globalThis.requestAnimationFrame = fn => { fn(0); return 0; };
  globalThis.fetch = fetchImpl
    || (async () => ({ok: true, json: async () => DATA, text: async () => ""}));

  // -- run it ------------------------------------------------------------------------------
  new Function(runnable)();
  const page = globalThis.__page;

  /* The smallest type the drawing was written at. It is what a reader meets, and it was a
     regression once. */
  function drawnType(...holders) {
    let smallest = Infinity;
    const walk = element => {
      if (element.tag === "text") {
        const size = parseFloat(element.attrs["font-size"]);
        if (size && element.textContent.trim()) smallest = Math.min(smallest, size);
      }
      element.children.forEach(walk);
    };
    holders.forEach(h => h.children.forEach(walk));
    return smallest === Infinity ? null : smallest;
  }

  function look() {
    const svg = document.getElementById("sysmap");
    const graph = document.getElementById("graph");
    const count = (holder, tag) => holder.children.filter(c => c.tag === tag).length;
    const words = id => document.getElementById(id).innerHTML.replace(/<[^>]+>/g, " ")
      .replace(/\s+/g, " ").trim();
    return {
      system_shown: !document.getElementById("system").hidden,
      system_links: count(svg, "path"),
      system_boxes: count(svg, "g"),
      system_dials: words("sysdials"),
      system_note: document.getElementById("sysnote").textContent,
      graph_nodes: count(graph, "g"),
      graph_drawn: graph.children.length > 0,
      step_card: words("stepcard"),
      story: document.getElementById("storywrap").hidden ? "" : words("story"),
      sections: [words("lead"), words("sections")].filter(Boolean).join(" "),
      findings: words("eyes"),
      standing: document.getElementById("t-standing").textContent,
      smallest_type: drawnType(svg, graph),
    };
  }

  /* Where every shape in one drawing was put, in the drawing's own coordinates. */
  function geometry(which) {
    const svg = document.getElementById(which);
    const out = {viewBox: svg.getAttribute("viewBox"), elements: []};
    const walk = element => {
      const a = element.attrs;
      if (element.tag === "rect") {
        out.elements.push({tag: "rect", x: +a.x, y: +a.y, w: +a.width, h: +a.height});
      } else if (element.tag === "text") {
        out.elements.push({tag: "text", x: +a.x, y: +a.y, size: +a["font-size"] || 16,
                           text: element.textContent});
      } else if (element.tag === "path") {
        out.elements.push({tag: "path", d: a.d || "", sw: +a["stroke-width"] || 1});
      }
      element.children.forEach(walk);
    };
    svg.children.forEach(walk);
    return out;
  }

  return {page, look, geometry};
}

// -- the command ---------------------------------------------------------------------------

if (process.argv[1] && process.argv[1].endsWith("view_harness.mjs")) {
  try {
    const {page, look, geometry} = runPage(fs.readFileSync(process.argv[2], "utf8"));
    if (process.argv[3] === "--geometry") {
      /* The page opens on the first pipeline, so a drawing is measured for whichever one is
         asked for. Without this a check on the busiest pipeline measured the quietest and
         passed by measuring nothing. */
      const which = process.argv[5];
      if (which) {
        if (!page.pipelines().some(p => p.name === which)) {
          console.error(`no pipeline named ${which}`);
          process.exit(1);
        }
        page.selectPipe(which);
      }
      console.log(JSON.stringify(geometry(process.argv[4])));
      process.exit(0);
    }
    const first = look();
    first.stage_pages = page.stages();
    first.opened_on = page.page();

    /* Every stage page is shown once, so a page that throws on switching cannot ship, and
       what each renders is reported. */
    const perPage = {};
    for (const s of page.stages()) {
      page.showPage(s);
      perPage[s] = {sections: look().sections, story: look().story,
        board: document.getElementById("map").className !== "boardless",
        graph_drawn: document.getElementById("graph").children.length > 0};
    }
    first.pages = perPage;
    page.showPage(first.opened_on);

    /* Then the interactions, because a page that renders once and throws on the first click
       is not a working page. Each is what a control on it does. */
    const visited = [];
    for (const p of page.pipelines()) {
      page.selectPipe(p.name);
      for (const step of p.nodes) page.showStep(step.id);
      visited.push(p.name);
    }
    for (const r of page.resources()) page.showResource(r.name);
    const measures = ["cost", "ms", "model_calls", "items"];
    for (const m of measures) { page.set("measure", m); page.drawSystem(); page.drawGraph(); }
    for (const pop of ["runs", "rollouts"]) {
      page.set("population", pop); page.drawSystem(); page.drawGraph();
    }
    page.renderSections();

    console.log(JSON.stringify({
      ...first,
      pipelines_selected: visited,
      resources_opened: page.resources().map(r => r.name),
      after_every_control: look(),
    }));
  } catch (error) {
    console.error(`${error.name}: ${error.message}\n${error.stack || ""}`);
    process.exit(1);
  }
}
