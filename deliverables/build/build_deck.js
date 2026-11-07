// Builds deliverables/presentation.pptx from the project's result files.
// Run from the repo root: node deliverables/build/build_deck.js
// Every number on the slides is read from models/*.json or reports/results.csv at build time.
const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");
const sharp = require("sharp");

const ROOT = path.resolve(__dirname, "..", "..");
const P = (...a) => path.join(ROOT, ...a);
const readJson = (f) => JSON.parse(fs.readFileSync(P(f), "utf8"));

// ---------- numbers ----------
function parseCsv(text) {
  const rows = [];
  for (const line of text.trim().split(/\r?\n/)) {
    const out = []; let cur = ""; let q = false;
    for (const ch of line) {
      if (ch === '"') q = !q;
      else if (ch === "," && !q) { out.push(cur); cur = ""; }
      else cur += ch;
    }
    out.push(cur); rows.push(out);
  }
  const [head, ...body] = rows;
  return body.map((r) => Object.fromEntries(head.map((h, i) => [h, r[i]])));
}
const results = parseCsv(fs.readFileSync(P("reports/results.csv"), "utf8"));
const testRow = (prefix) => {
  const r = results.find((x) => x.stage === "test" && x.model.startsWith(prefix));
  if (!r) throw new Error("results.csv: no test row starting with " + prefix);
  return r;
};
const meta = readJson("models/meta.json");
const seg = readJson("models/segments.json");
const multiyearPath = P("models/multiyear.json");
const multiyear = fs.existsSync(multiyearPath) ? JSON.parse(fs.readFileSync(multiyearPath, "utf8")) : null;
const curve = readJson("models/threshold_curve.json");

const COST_PER_TEST = 20; // ASSUMPTION copied from notebook.ipynb COST_PER_TEST; not from data
const M = meta.metrics;
const prev = meta.positive_rate;
const flagFull = (M.full.recall * prev) / M.full.precision;
const flagShort = (M.short.recall * prev) / M.short.precision;
const N = {
  rowsRaw: meta.n_rows_raw,
  rows: meta.n_rows,
  dups: meta.n_rows_raw - meta.n_rows,
  nFull: meta.features_full.length,
  nShort: meta.features_short.length,
  prev,
  baselineAcc: 1 - prev,
  year: meta.data_year,
  targetRecall: meta.target_recall,
  thrFull: meta.threshold_full,
  thrShort: meta.threshold_short,
  full: M.full, short: M.short, base: M.baseline,
  hgb05: testRow("HistGradientBoosting tuned"),
  lr05: testRow("LogisticRegression tuned"),
  rf05: testRow("RandomForest tuned"),
  flagFull, flagShort,
  costPerCaseFull: COST_PER_TEST / M.full.precision,
  costPerCaseShort: COST_PER_TEST / M.short.precision,
  costPerCaseAll: COST_PER_TEST / prev,
  savingFull: 1 - flagFull,
  missedFull: 1 - M.full.recall,
};
const pct = (x, d = 1) => (100 * x).toFixed(d) + "%";
const f3 = (x) => Number(x).toFixed(3);
const int = (x) => Math.round(x).toLocaleString("en-US");
const usd = (x) => "$" + Math.round(x);

// ---------- theme ----------
const THEME = {
  name: "SugarScope",
  headFontFace: "Calibri",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "172B36", lt1: "FFFFFF", dk2: "0C3646", lt2: "F3F7F9",
    accent1: "0E7490", accent2: "22D3EE", accent3: "67E8F9",
    accent4: "CFFAFE", accent5: "5B7380", accent6: "DCE5EA",
    hlink: "0E7490", folHlink: "0C3646",
  },
};
const HEX = { navy: "0C3646", teal: "0E7490", cyan: "22D3EE", ice: "CFFAFE", grid: "DCE5EA", muted: "5B7380", text: "172B36", bg: "F3F7F9" };

async function main() {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_16x9"; // 10 x 5.625 in
  pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
  pres.title = "SugarScope: diabetes risk screening";
  pres.author = "NextGen Institute ML final project";
  const C = pres.SchemeColor;

  const logoSvg = fs.readFileSync(P("assets/logo.svg"), "utf8");
  const logoPng = await sharp(Buffer.from(logoSvg), { density: 600 }).png().toBuffer();
  const markPng = await sharp(P("assets/logo_mark.svg"), { density: 600 }).png().toBuffer();
  // white wordmark for dark slides
  const logoWhiteSvg = logoSvg
    .replace(/(<text[^>]*fill=")#0C3646"/, '$1#FFFFFF"').replace(/<tspan fill="#0E7490">/, '<tspan fill="#67E8F9">');
  const logoWhitePng = await sharp(Buffer.from(logoWhiteSvg), { density: 600 }).png().toBuffer();
  const logoAR = await sharp(logoWhitePng).metadata().then((m) => m.width / m.height);
  const b64 = (buf) => "image/png;base64," + buf.toString("base64");
  const imgSize = async (f) => { const m = await sharp(P(f)).metadata(); return m.width / m.height; };
  // Crop a region (px) of a screenshot; used to keep transient UI (slider value bubbles) out of the slides.
  const crop = async (f, left, top, width, height) =>
    ({ data: b64(await sharp(P(f)).extract({ left, top, width, height }).png().toBuffer()), ar: width / height });
  const fitImg = (slide, im, x, y, w, h, name, altText) => {
    let iw = w, ih = w / im.ar;
    if (ih > h) { ih = h; iw = h * im.ar; }
    slide.addImage({ data: im.data, x: x + (w - iw) / 2, y: y + (h - ih) / 2, w: iw, h: ih, objectName: name, altText });
  };

  // ---------- layouts ----------
  pres.defineSlideMaster({
    title: "DARK",
    background: { color: HEX.navy },
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 1.7, w: 8.8, h: 1.3, fontSize: 40, bold: true, color: C.background1, align: "left", valign: "top", margin: 0 }, text: "" } },
    ],
  });
  pres.defineSlideMaster({
    title: "CONTENT",
    background: { color: HEX.bg },
    margin: [0.5, 0.5, 0.5, 0.5],
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: 0.5, y: 0.3, w: 9.0, h: 0.75, fontSize: 26, bold: true, color: C.text2, align: "left", valign: "middle", margin: 0 }, text: "" } },
      { image: { x: 0.5, y: 5.17, w: 0.22, h: 0.22, data: b64(markPng) } },
      { text: { text: "SugarScope  |  NextGen Institute ML final project", options: { x: 0.8, y: 5.14, w: 6, h: 0.28, fontSize: 10, color: HEX.muted, margin: 0, valign: "middle" } } },
    ],
    slideNumber: { x: 9.0, y: 5.14, w: 0.5, h: 0.28, fontSize: 10, color: HEX.muted, align: "right" },
  });

  const card = (slide, x, y, w, h, name, fill = C.background1) =>
    slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x, y, w, h, rectRadius: 0.08, fill: { color: fill }, line: { color: HEX.grid, width: 0.75 }, objectName: name,
    });
  const txt = (slide, text, o) => slide.addText(text, { isTextBox: true, margin: 0, fontSize: 14, color: C.text1, valign: "top", ...o });
  const stat = (slide, x, y, w, big, label, name, bigColor = C.accent1) => {
    card(slide, x, y, w, 1.15, name + " card");
    txt(slide, big, { x: x + 0.2, y: y + 0.12, w: w - 0.4, h: 0.55, fontSize: 28, bold: true, color: bigColor, objectName: name + " value", fit: "shrink" });
    txt(slide, label, { x: x + 0.2, y: y + 0.68, w: w - 0.4, h: 0.4, fontSize: 11, color: HEX.muted, objectName: name + " label" });
  };
  const numCircle = (slide, x, y, n, name) => {
    slide.addShape(pres.shapes.OVAL, { x, y, w: 0.42, h: 0.42, fill: { color: C.accent1 }, line: { color: HEX.teal }, objectName: name + " circle" });
    txt(slide, String(n), { x, y, w: 0.42, h: 0.42, fontSize: 14, bold: true, color: C.background1, align: "center", valign: "middle", objectName: name + " number" });
  };
  const content = (title, section) => {
    const s = pres.addSlide({ masterName: "CONTENT", sectionTitle: section });
    s.addText(title, { placeholder: "title" });
    return s;
  };
  const chartText = { catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt", dataLabelFontFace: "+mn-lt", titleFontFace: "+mn-lt", legendFontFace: "+mn-lt",
    catAxisLabelColor: HEX.muted, valAxisLabelColor: HEX.muted, catAxisLabelFontSize: 10, valAxisLabelFontSize: 10, dataLabelFontSize: 10, dataLabelColor: HEX.text };

  // ---------- 1. title ----------
  pres.addSection({ title: "Opening" });
  let s = pres.addSlide({ masterName: "DARK", sectionTitle: "Opening" });
  s.addImage({ data: b64(logoWhitePng), x: 0.6, y: 0.6, w: 0.64 * logoAR, h: 0.64, objectName: "SugarScope logo" });
  s.addText("A six-question diabetes risk check", { placeholder: "title" });
  txt(s, `Built from ${int(N.rows)} CDC survey responses to find people who should get a blood-sugar test`, { x: 0.6, y: 2.95, w: 7.6, h: 0.7, fontSize: 18, color: HEX.ice, objectName: "subtitle" });
  txt(s, "NextGen Institute  |  Machine Learning final project  |  Idea 11: Diabetes Risk Screening Tool", { x: 0.6, y: 4.75, w: 8.8, h: 0.35, fontSize: 12, color: HEX.cyan, objectName: "course line" });
  s.addNotes(`Hi everyone. Our project is SugarScope, a diabetes risk screening tool. The idea is simple: a person answers six short questions, about a minute of their time, and gets a risk level that tells them whether it is worth asking for a blood-sugar test. We built it on ${int(N.rows)} responses to the CDC's Behavioral Risk Factor Surveillance System, the BRFSS health survey. In the next ten minutes we will cover the problem, the data, what the exploration taught us, the models we compared, the results, and how the short questionnaire and the app came out of that work. We will finish with our recommendation and the limits you should keep in mind. The short version: six questions keep about the same screening power as all twenty-one.`);

  // ---------- 2. problem ----------
  pres.addSection({ title: "Problem" });
  s = content("Diabetes often goes unnoticed for years", "Problem");
  const probs = [
    ["No early symptoms", "Early type 2 diabetes usually feels like nothing, so people do not ask for a test."],
    ["Testing is easy; choosing who to test is hard","An HbA1c or fasting-glucose test confirms it, but clinics cannot test everyone every year."],
    ["Risk factors are easy to ask about", "Blood pressure, cholesterol, weight, age and general health are answers people already know."],
  ];
  probs.forEach(([h, b], i) => {
    const y = 1.3 + i * 1.18;
    numCircle(s, 0.5, y, i + 1, `problem ${i + 1}`);
    txt(s, h, { x: 1.1, y: y - 0.02, w: 4.9, h: 0.35, fontSize: 16, bold: true, color: C.text2, objectName: `problem ${i + 1} head` });
    txt(s, b, { x: 1.1, y: y + 0.35, w: 4.9, h: 0.65, fontSize: 13, color: C.text1, objectName: `problem ${i + 1} body` });
  });
  card(s, 6.4, 1.3, 3.1, 3.4, "prevalence card", C.text2);
  txt(s, pct(N.prev), { x: 6.6, y: 1.55, w: 2.7, h: 0.9, fontSize: 48, bold: true, color: HEX.cyan, objectName: "prevalence value" });
  txt(s, `of ${int(N.rows)} survey respondents report diagnosed diabetes`, { x: 6.6, y: 2.5, w: 2.7, h: 0.9, fontSize: 14, color: C.background1, objectName: "prevalence label" });
  txt(s, "Goal: rank people by risk so the tests go to those most likely to have it.", { x: 6.6, y: 3.55, w: 2.7, h: 0.95, fontSize: 13, italic: true, color: HEX.ice, objectName: "goal" });
  s.addNotes(`Diabetes is common, and many people who have them do not know it. The reason is that the early stages have no clear symptoms. The diagnosis itself is not the problem: an HbA1c or fasting-glucose blood test is cheap and reliable. The hard part is deciding who should get that test, because a clinic or a community programme cannot test everyone every year. The good news is that the main risk factors are things people already know about themselves: whether a doctor told them they have high blood pressure or high cholesterol, their weight, their age, and how they rate their general health. In our data, ${pct(N.prev)} of respondents report diagnosed diabetes. So the goal of this project is ranking, not diagnosis: put the people most likely to have it at the front of the queue for a test.`);

  // ---------- 3. users + recall ----------
  s = content("Who uses it, and why recall is the metric", "Problem");
  const users = [
    ["Individual", "Should I ask my doctor for a blood-sugar test?"],
    ["Clinic or health worker", "Who in today's list should be referred for a test first?"],
    ["Programme planner", "Which cut-off fits our testing budget?"],
  ];
  users.forEach(([h, b], i) => {
    const x = 0.5 + i * 3.08;
    card(s, x, 1.25, 2.84, 1.2, `user ${i + 1} card`);
    txt(s, h, { x: x + 0.2, y: 1.4, w: 2.44, h: 0.35, fontSize: 16, bold: true, color: C.accent1, objectName: `user ${i + 1} head` });
    txt(s, b, { x: x + 0.2, y: 1.8, w: 2.44, h: 0.8, fontSize: 13, color: C.text1, objectName: `user ${i + 1} body` });
  });
  card(s, 0.5, 2.65, 9.0, 2.25, "recall card");
  txt(s, "Why recall", { x: 0.7, y: 2.8, w: 3, h: 0.35, fontSize: 16, bold: true, color: C.text2, objectName: "recall head" });
  txt(s, [
    { text: "A missed case stays undiagnosed; a false alarm costs one cheap blood test.", options: { bullet: { indent: 14 }, breakLine: true } },
    { text: `We set the decision threshold so that recall is at least ${pct(N.targetRecall, 0)}, then compare precision, PR-AUC and Brier score.`, options: { bullet: { indent: 14 }, breakLine: true } },
    { text: "Accuracy is misleading here: always answering \"no\" scores high accuracy and finds nobody.", options: { bullet: { indent: 14 } } },
  ], { x: 0.7, y: 3.2, w: 5.6, h: 1.55, fontSize: 13, color: C.text1, paraSpaceAfter: 4, objectName: "recall bullets" });
  txt(s, pct(N.baselineAcc), { x: 6.6, y: 3.05, w: 2.7, h: 0.7, fontSize: 36, bold: true, color: C.accent1, align: "left", objectName: "baseline accuracy value" });
  txt(s, `accuracy of the always-"no" baseline, with ${pct(N.base.recall, 0)} recall`, { x: 6.6, y: 3.8, w: 2.7, h: 0.6, fontSize: 12, color: HEX.muted, objectName: "baseline accuracy label" });
  s.addNotes(`There are three users. An individual wants to know whether it is worth asking a doctor for a test. A clinic or community health worker wants to know who to refer first. And a programme planner wants to choose a cut-off that fits a testing budget. All three make the same kind of decision: test or do not test. That is why we optimise recall. If we miss a person who has diabetes, they stay undiagnosed. If we flag someone who turns out to be fine, the cost is one cheap blood test. So we fixed the decision threshold to reach at least ${pct(N.targetRecall, 0)} recall and then compared models on precision, PR-AUC and calibration. Accuracy is a trap on this data: a model that always says no is ${pct(N.baselineAcc)} accurate and finds nobody.`);

  // ---------- 4. data ----------
  pres.addSection({ title: "Data" });
  s = content("Data: the CDC BRFSS health survey", "Data");
  stat(s, 0.5, 1.25, 2.1, int(N.rowsRaw), "raw survey responses", "raw rows");
  stat(s, 2.8, 1.25, 2.1, int(N.dups), "exact duplicates dropped", "duplicates");
  stat(s, 0.5, 2.6, 2.1, int(N.rows), "rows used for modelling", "rows used");
  stat(s, 2.8, 2.6, 2.1, String(N.nFull), "questions (features)", "features");
  txt(s, [
    { text: `Source: CDC BRFSS ${N.year}, via the UCI ML Repository.`, options: { bullet: { indent: 14 }, breakLine: true } },
    { text: "Target: diagnosed diabetes = 1; prediabetes counts as 0.", options: { bullet: { indent: 14 }, breakLine: true } },
    { text: "Duplicates dropped before the split, so no row is in both train and test.", options: { bullet: { indent: 14 } } },
  ], { x: 0.5, y: 3.95, w: 4.6, h: 1.1, fontSize: 12, color: C.text1, paraSpaceAfter: 3, objectName: "data notes" });
  card(s, 5.3, 1.25, 4.2, 3.6, "class balance card");
  s.addChart(pres.charts.DOUGHNUT, [{ name: "Class balance", labels: ["Diagnosed diabetes", "No diabetes"], values: [N.prev, 1 - N.prev] }], {
    x: 5.4, y: 1.35, w: 4.0, h: 3.4, holeSize: 62, chartColors: [HEX.teal, HEX.grid],
    showTitle: true, title: "Class balance", titleFontSize: 14, titleColor: HEX.navy,
    showPercent: true, showValue: false, showLegend: true, legendPos: "b", legendFontSize: 11, legendColor: HEX.text,
    ...chartText, dataLabelColor: HEX.navy, dataLabelFontSize: 12, dataLabelFontBold: true, dataLabelFormatCode: "0.0%",
    objectName: "class balance chart",
  });
  s.addNotes(`Our data is the CDC's BRFSS telephone health survey for ${N.year}, in the cleaned version published on the UCI Machine Learning Repository. It has ${int(N.rowsRaw)} responses and ${N.nFull} questions, mostly yes or no answers plus a few scales like BMI, age group and general health. The target is whether the person reports diagnosed diabetes; prediabetes is coded 0. The main cleaning step was duplicates. Because the answers are small codes, ${int(N.dups)} rows were exact copies of another row. If we kept them, the same answer pattern could appear in both the training and the test set, which inflates the test score. So we dropped them before splitting, leaving ${int(N.rows)} rows. The classes are imbalanced: ${pct(N.prev)} positive, ${pct(1 - N.prev)} negative, which drives how we trained and evaluated.`);

  // ---------- 5. EDA ----------
  s = content("What the exploration showed", "Data");
  const ordAR = await imgSize("reports/eda_rate_ordinal.png");
  const binAR = await imgSize("reports/eda_rate_binary.png");
  const ow = 5.35, oh = ow / ordAR;
  card(s, 0.5, 1.2, 5.55, oh + 0.2, "ordinal chart card");
  s.addImage({ path: P("reports/eda_rate_ordinal.png"), x: 0.6, y: 1.3, w: ow, h: oh, objectName: "positive rate by BMI, health, age, income, education", altText: "Positive rate by BMI band, general health, age, income, education and physical-health days" });
  card(s, 6.25, 1.2, 3.25, 2.45, "binary chart card");
  const bh = 2.35, bw = bh * binAR;
  s.addImage({ path: P("reports/eda_rate_binary.png"), x: 6.25 + (3.25 - bw) / 2, y: 1.25, w: bw, h: bh, objectName: "positive rate by yes-no answer", altText: "Diagnosed diabetes rate by each yes or no answer" });
  txt(s, [
    { text: "Rate climbs steadily with BMI, age and worse general health.", options: { bullet: { indent: 14 }, breakLine: true } },
    { text: "High blood pressure and high cholesterol: several times the rate.", options: { bullet: { indent: 14 }, breakLine: true } },
    { text: "Lower income and education go with higher rates.", options: { bullet: { indent: 14 } } },
  ], { x: 6.25, y: 3.75, w: 3.25, h: 1.25, fontSize: 12, color: C.text1, paraSpaceAfter: 3, objectName: "EDA insights" });
  s.addNotes(`Three things stood out in the exploration. First, on the left: the rate of diagnosed diabetes climbs almost in a straight line with BMI band, with age, and with how poorly people rate their general health. The dashed line is the overall rate, and the extremes sit far above and below it. Second, on the right, the yes or no questions: people told they have high blood pressure or high cholesterol have several times the rate of those who were not. Heart disease, stroke and difficulty walking also matter, but fewer people say yes to them. Third, there is a clear social gradient: lower income and lower education go with higher rates. These patterns told us early that a handful of questions probably carry most of the signal, which is what we later tested with the short questionnaire.`);

  // ---------- 6. approach ----------
  pres.addSection({ title: "Modelling" });
  s = content("Approach: a leak-free pipeline, tuned for screening", "Modelling");
  const steps = [
    ["Split", "Stratified 80 / 20 train-test split after de-duplication. Test set used once."],
    ["Pipeline", "Scaling lives inside the pipeline, so it is fit on training folds only."],
    ["Compare", "Dummy baseline, logistic regression, random forest, gradient boosting; each with no weighting, class weights or SMOTE."],
    ["Tune", "Randomised search with stratified cross-validation, scored on PR-AUC."],
    ["Calibrate", `Isotonic calibration, then the threshold that reaches ${pct(N.targetRecall, 0)} recall out-of-fold.`],
  ];
  const sw = 1.66, gap = 0.17;
  steps.forEach(([h, b], i) => {
    const x = 0.5 + i * (sw + gap);
    card(s, x, 1.3, sw, 2.75, `step ${i + 1} card`);
    numCircle(s, x + 0.17, 1.47, i + 1, `step ${i + 1}`);
    txt(s, h, { x: x + 0.17, y: 2.0, w: sw - 0.3, h: 0.35, fontSize: 15, bold: true, color: C.text2, objectName: `step ${i + 1} head` });
    txt(s, b, { x: x + 0.17, y: 2.38, w: sw - 0.3, h: 1.6, fontSize: 11, color: C.text1, objectName: `step ${i + 1} body` });
  });
  card(s, 0.5, 4.25, 9.0, 0.7, "leakage card", C.text2);
  txt(s, "No leakage: duplicates removed before the split, every preprocessing step fit inside cross-validation, threshold chosen on training data, test set touched once at the end.", { x: 0.7, y: 4.3, w: 8.6, h: 0.6, fontSize: 12, color: C.background1, valign: "middle", objectName: "leakage note" });
  s.addNotes(`Here is the approach in five steps. We split the de-duplicated data 80 to 20, stratified by the target, and kept the test set locked until the very end. All preprocessing, like scaling, sits inside a scikit-learn pipeline, so it is learned on the training folds only. We compared a dummy baseline with logistic regression, random forest and histogram gradient boosting, and for each one we tried three ways of handling the imbalance: nothing, class weights, and SMOTE oversampling, which runs inside the cross-validation folds. Then we tuned the main candidates with randomised search, scored on PR-AUC because that metric focuses on the positive class. Finally we calibrated the probabilities with isotonic regression and picked the threshold that reaches ${pct(N.targetRecall, 0)} recall using out-of-fold predictions on the training data, never the test set.`);

  // ---------- 7. results ----------
  pres.addSection({ title: "Results" });
  s = content("Results on the held-out test set", "Results");
  const H = (t) => ({ text: t, options: { bold: true, color: HEX.navy, fill: { color: HEX.ice } } });
  const row = (name, m, hl) => {
    const o = hl ? { bold: true, color: HEX.navy, fill: { color: "E6F6F9" } } : { color: HEX.text };
    return [name, ...["recall", "precision", "f1", "roc_auc", "pr_auc", "brier"].map((k) => f3(m[k]))].map((t) => ({ text: t, options: { ...o } }));
  };
  const tbl = [
    ["Model (threshold)", "Recall", "Precision", "F1", "ROC-AUC", "PR-AUC", "Brier"].map(H),
    row("Baseline: always \"no\"", N.base),
    row("Logistic regression (0.5)", N.lr05),
    row("Random forest (0.5)", N.rf05),
    row("Gradient boosting (0.5)", N.hgb05),
    row(`Final: boosting, calibrated (${N.thrFull.toFixed(3)})`, N.full, true),
    row(`Short, ${N.nShort} questions (${N.thrShort.toFixed(3)})`, N.short, true),
  ];
  s.addTable(tbl, { x: 0.5, y: 1.2, w: 6.3, colW: [2.3, 0.62, 0.76, 0.56, 0.72, 0.68, 0.66], fontSize: 11, fontFace: "Calibri", margin: [0.03, 0.06, 0.03, 0.06], border: { type: "solid", color: HEX.grid, pt: 0.75 }, fill: { color: "FFFFFF" }, rowH: 0.42, valign: "middle", objectName: "results table" });
  txt(s, `Test set: ${int(Math.round(N.rows * 0.2))} people, never used for training or tuning. Rows 2 to 4 use the default 0.5 cut-off.`, { x: 0.5, y: 4.3, w: 6.3, h: 0.5, fontSize: 11, italic: true, color: HEX.muted, objectName: "table note" });
  card(s, 7.0, 1.2, 2.5, 3.6, "results takeaway card", C.text2);
  txt(s, pct(N.full.recall), { x: 7.2, y: 1.35, w: 2.1, h: 0.7, fontSize: 36, bold: true, color: HEX.cyan, objectName: "final recall value" });
  txt(s, `recall of the final model, up from ${pct(N.hgb05.recall)} at the default 0.5 cut-off`, { x: 7.2, y: 2.05, w: 2.1, h: 0.85, fontSize: 12, color: C.background1, objectName: "final recall label" });
  txt(s, `PR-AUC ${f3(N.full.pr_auc)} vs ${f3(N.base.pr_auc)} for the baseline. Lower Brier = better calibrated.`, { x: 7.2, y: 3.05, w: 2.1, h: 1.7, fontSize: 12, color: HEX.ice, objectName: "results note" });
  s.addNotes(`This is the test set, used once. The baseline finds nobody, and its PR-AUC of ${f3(N.base.pr_auc)} is just the share of positives. All three tuned models rank people well, with ROC-AUC from ${f3(Math.min(N.lr05.roc_auc, N.rf05.roc_auc, N.hgb05.roc_auc))} to ${f3(Math.max(N.lr05.roc_auc, N.rf05.roc_auc, N.hgb05.roc_auc))}, but at the default 0.5 cut-off they catch only a small share of cases: gradient boosting reaches ${pct(N.hgb05.recall)} recall. The fix is the threshold, not a different model. Our final model is gradient boosting with calibrated probabilities and a cut-off of ${N.thrFull.toFixed(3)}. It reaches ${pct(N.full.recall)} recall with ${pct(N.full.precision)} precision, so roughly one in three people it flags really has diagnosed diabetes, about double the base rate. PR-AUC is ${f3(N.full.pr_auc)} and the Brier score is the lowest in the table. The last row is the six-question model, which is nearly as good.`);

  // ---------- 8. short questionnaire ----------
  s = content(`${N.nShort} questions keep almost all of the screening power`, "Results");
  const qAR = await imgSize("reports/questions_curve.png");
  card(s, 0.5, 1.2, 5.9, 3.75, "questions curve card");
  const qw = 5.7, qh = qw / qAR;
  s.addImage({ path: P("reports/questions_curve.png"), x: 0.6, y: 1.2 + (3.75 - qh) / 2, w: qw, h: qh, objectName: "questions vs performance curve", altText: "Validation ROC-AUC, PR-AUC and recall against the number of questions, with the chosen six marked" });
  const qLabels = { HighBP: "High blood pressure", HighChol: "High cholesterol", BMI: "BMI (height, weight)", GenHlth: "General health", Sex: "Sex", Age: "Age" };
  card(s, 6.6, 1.2, 2.9, 2.35, "question list card");
  txt(s, "The six questions", { x: 6.8, y: 1.3, w: 2.5, h: 0.35, fontSize: 14, bold: true, color: C.text2, objectName: "question list head" });
  txt(s, meta.features_short.map((f, i, a) => ({ text: qLabels[f] || f, options: { bullet: { indent: 14 }, breakLine: i < a.length - 1 } })), { x: 6.8, y: 1.68, w: 2.5, h: 1.8, fontSize: 12, color: C.text1, paraSpaceAfter: 2, objectName: "question list" });
  card(s, 6.6, 3.7, 2.9, 1.25, "short vs full card", C.text2);
  txt(s, `Recall ${pct(N.short.recall)} vs ${pct(N.full.recall)}`, { x: 6.8, y: 3.82, w: 2.5, h: 0.4, fontSize: 15, bold: true, color: HEX.cyan, objectName: "short recall" });
  txt(s, `ROC-AUC ${f3(N.short.roc_auc)} vs ${f3(N.full.roc_auc)}, with ${N.nShort} of ${N.nFull} questions`, { x: 6.8, y: 4.25, w: 2.5, h: 0.6, fontSize: 12, color: C.background1, objectName: "short auc" });
  s.addNotes(`This chart is the core of the product. We ranked the ${N.nFull} questions by permutation importance and retrained the model with the top one, top two, and so on, measuring validation scores each time. The curves rise fast and then go flat: after about five or six questions, extra questions add almost nothing. We chose six, the dashed line: high blood pressure, high cholesterol, BMI, general health, sex and age. On the test set, with its own threshold, the six-question model reaches ${pct(N.short.recall)} recall against ${pct(N.full.recall)} for the full model, and ROC-AUC ${f3(N.short.roc_auc)} against ${f3(N.full.roc_auc)}. In practice that means a one-minute check instead of a long form, and people are far more likely to finish it.`);

  // ---------- 9. segments + cost ----------
  s = content("Population segments and the screening cost planner", "Results");
  const segs = [...seg.segments].sort((a, b) => b.diabetes_rate - a.diabetes_rate);
  const shortName = (n) => n.replace(/^(\w+ risk): /, "$1:\n");
  card(s, 0.5, 1.2, 5.0, 3.75, "segments chart card");
  s.addChart(pres.charts.BAR, [{ name: "Diagnosed diabetes rate", labels: segs.map((x) => `${x.name.split(":")[0]} (${pct(x.size_share, 0)} of people)`), values: segs.map((x) => x.diabetes_rate) }], {
    x: 0.6, y: 1.3, w: 4.8, h: 2.75, barDir: "bar", chartColors: [HEX.teal], showLegend: false,
    showTitle: true, title: `${seg.k} segments from k-means clustering: rate of diagnosed diabetes`, titleFontSize: 12, titleColor: HEX.navy,
    showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "0%", valAxisLabelFormatCode: "0%", valAxisMaxVal: 0.4,
    valGridLine: { color: HEX.grid, size: 0.5 }, catGridLine: { style: "none" }, catAxisOrientation: "maxMin", ...chartText,
    objectName: "segment diabetes rate chart",
  });
  const top = segs[0];
  txt(s, `Highest-risk group: ${top.name.split(": ")[1]}. Suggested action: priority outreach and a blood-sugar test now.`, { x: 0.7, y: 4.1, w: 4.6, h: 0.75, fontSize: 12, color: C.text1, objectName: "segment action" });
  txt(s, `At the screening cut-off (assumed ${usd(COST_PER_TEST)} per test)`, { x: 5.7, y: 1.2, w: 3.8, h: 0.35, fontSize: 13, bold: true, color: C.text2, objectName: "cost head" });
  stat(s, 5.7, 1.6, 1.8, usd(N.costPerCaseFull), "per case found with SugarScope", "cost per case");
  stat(s, 7.7, 1.6, 1.8, usd(N.costPerCaseAll), "per case found testing everyone", "cost test all", C.text2);
  stat(s, 5.7, 2.95, 1.8, pct(N.savingFull, 0), "fewer tests than testing everyone", "test saving");
  stat(s, 7.7, 2.95, 1.8, pct(N.missedFull, 0), "of cases missed at this cut-off", "missed", C.text2);
  txt(s, "The app's planner moves the cut-off and shows cases caught against cost.", { x: 5.7, y: 4.25, w: 3.8, h: 0.6, fontSize: 12, italic: true, color: HEX.muted, objectName: "planner note" });
  s.addNotes(`Beyond individual risk we added two tools for planners. On the left, k-means clustering on ten health answers found ${seg.k} population segments. The highest-risk group, people with walking difficulty and many poor physical-health days, makes up ${pct(top.size_share, 0)} of respondents and has a ${pct(top.diabetes_rate, 0)} rate of diagnosed diabetes, so it is the natural target for priority outreach. On the right is the cost planner. With an assumed ${usd(COST_PER_TEST)} per blood test, testing everyone costs about ${usd(N.costPerCaseAll)} per case found. Testing only the people SugarScope flags costs about ${usd(N.costPerCaseFull)} per case found and needs ${pct(N.savingFull, 0)} fewer tests, at the price of missing ${pct(N.missedFull, 0)} of cases. The test price is an assumption, so the app lets planners change the cut-off and see the trade-off live.`);

  // ---------- 10. multi-year ----------
  if (!multiyear) throw new Error("models/multiyear.json is required for slide 10");
  const tv = multiyear.temporal_validation;
  const re = tv.filter((r) => r.train_years.startsWith("2015-2019"));
  const orig = tv.filter((r) => !re.includes(r));
  const origAt = (y) => orig.find((r) => r.test_year === y);
  const lastRe = re[re.length - 1], lastOrig = origAt(lastRe.test_year);
  Object.assign(N, { myYears: multiyear.years, myRows: multiyear.total_rows,
    myAuc: orig.map((r) => r.roc_auc), myRecall: orig.map((r) => r.recall), myReAuc: re.map((r) => r.roc_auc) });
  s = content("Does it hold up in later survey years?", "Results");
  card(s, 0.5, 1.2, 4.6, 3.75, "multiyear chart card");
  s.addChart(pres.charts.LINE, [
    { name: "ROC-AUC", labels: orig.map((r) => String(r.test_year)), values: orig.map((r) => r.roc_auc) },
    { name: "Recall", labels: orig.map((r) => String(r.test_year)), values: orig.map((r) => r.recall) },
  ], {
    x: 0.6, y: 1.3, w: 4.4, h: 3.55, chartColors: [HEX.navy, HEX.teal], lineSize: 2, lineDataSymbolSize: 7,
    showTitle: true, title: `Saved ${multiyear.years[0]} model, unchanged, on later years`, titleFontSize: 12, titleColor: HEX.navy,
    showLegend: true, legendPos: "b", showValue: true, dataLabelPosition: "t", dataLabelFormatCode: "0.000",
    valAxisMinVal: 0.7, valAxisMaxVal: 0.9, valAxisLabelFormatCode: "0.00",
    valGridLine: { color: HEX.grid, size: 0.5 }, catGridLine: { style: "none" }, ...chartText,
    objectName: "multiyear auc recall chart",
  });
  stat(s, 5.3, 1.2, 2.0, int(multiyear.total_rows), `rows, ${multiyear.years.length} BRFSS years`, "multiyear rows");
  stat(s, 7.5, 1.2, 2.0, f3(lastRe.roc_auc), `ROC-AUC ${lastRe.test_year}, retrained on ${re[0].train_years.slice(0, 9).replace("-", "–")}`, "multiyear retrain auc", C.text2);
  card(s, 5.3, 2.5, 4.2, 1.85, "state map card");
  const mapIm = await crop("demo/screenshots/state_map.png", 590, 486, 955, 389);
  fitImg(s, mapIm, 5.4, 2.56, 4.0, 1.5, "state map", `Map of the actual diagnosed diabetes rate by state, ${multiyear.years[multiyear.years.length - 1]}`);
  txt(s, `Actual rate by state, ${multiyear.years[multiyear.years.length - 1]} (app's state view)`, { x: 5.45, y: 4.08, w: 3.9, h: 0.22, fontSize: 9, italic: true, color: HEX.muted, objectName: "state map caption" });
  txt(s, `Retraining gives the same AUC (${f3(lastRe.roc_auc)} vs ${f3(lastOrig.roc_auc)}): the drift is in the population, not the model.`, { x: 5.3, y: 4.45, w: 4.2, h: 0.5, fontSize: 11, color: C.text1, objectName: "retrain note" });
  s.addNotes(`A model trained on one survey year can drift, so we tested it on later years. We rebuilt the same ${N.nFull} questions from the raw BRFSS files for ${multiyear.years.join(", ")}: ${int(multiyear.total_rows)} rows in total. The other years are skipped because some of the questions were not asked. The saved model, without any change, still ranks people well: ROC-AUC ${orig.map((r) => `${f3(r.roc_auc)} in ${r.test_year}`).join(", ")}. Recall at the fixed cut-off slips from ${f3(orig[0].recall)} to ${f3(lastOrig.recall)}. To see whether a newer model would do better, we retrained on ${re[0].train_years.slice(0, 9)}. It gets the same ROC-AUC, ${f3(lastRe.roc_auc)} in ${lastRe.test_year} against ${f3(lastOrig.roc_auc)}. So the drop comes from the population changing, not from the model going stale, and the practical fix is to recalibrate the cut-off on recent local data.`);

  // ---------- 11. product ----------
  pres.addSection({ title: "Product" });
  s = content("The product: SugarScope", "Product");
  card(s, 0.5, 1.2, 5.9, 3.75, "screenshot card");
  const shotDir = "demo/screenshots/";
  const shots11 = [
    [await crop(shotDir + "home.png", 352, 138, 828, 335), "Home page"],
    [await crop(shotDir + "result.png", 340, 240, 1235, 785), "Quick check with its result"],
    [await crop(shotDir + "whatif.png", 1120, 640, 444, 315), "What-if panel"],
    [await crop(shotDir + "insights.png", 352, 80, 1216, 798), "Population insights"],
  ];
  shots11.forEach(([im, alt], i) => fitImg(s, im, 0.6 + (i % 2) * 2.875, 1.3 + Math.floor(i / 2) * 1.8, 2.825, 1.75, `screenshot ${i + 1}`, `SugarScope app: ${alt}`));
  const feats = [
    ["Quick check", `${N.nShort} questions, about a minute`],
    ["Full check", `all ${N.nFull} questions, with the factors behind the result`],
    ["What-if", "see how the risk changes with lower weight or more activity"],
    ["Population insights", "segments and the screening cost planner"],
  ];
  feats.forEach(([h, b], i) => {
    const y = 1.25 + i * 0.8;
    txt(s, [{ text: h, options: { bold: true, color: C.accent1, breakLine: true } }, { text: b, options: { color: C.text1 } }], { x: 6.65, y, w: 2.85, h: 0.72, fontSize: 13, objectName: `feature ${i + 1}` });
  });
  txt(s, "Live demo: Streamlit app. Screening aid, not a diagnosis.", { x: 6.65, y: 4.5, w: 2.85, h: 0.45, fontSize: 11, italic: true, color: HEX.muted, objectName: "demo note" });
  s.addNotes(`This is SugarScope, the Streamlit app we deployed. The quick check asks the ${N.nShort} questions and takes about a minute; there is no sign-up and nothing is stored. The result shows a probability, a risk level of low, moderate or high, and the answers that pushed the risk up or down. The full check uses all ${N.nFull} questions for people who want more detail. The what-if panel lets someone move the weight slider or tick regular exercise and watch the risk change, which turns a score into something they can act on. The population insights tab holds the segments and the cost planner for clinics and planners. Every page says clearly that this is a screening aid and not a medical diagnosis. Let me show the short demo now.`);

  // ---------- 12. recommendation ----------
  pres.addSection({ title: "Close" });
  s = pres.addSlide({ masterName: "DARK", sectionTitle: "Close" });
  txt(s, "Recommendation", { x: 0.6, y: 0.45, w: 8.8, h: 0.6, fontSize: 30, bold: true, color: C.background1, objectName: "close title" });
  txt(s, `Use the ${N.nShort}-question model as a first-step screen at cut-off ${N.thrShort.toFixed(3)}: it catches ${pct(N.short.recall, 0)} of cases while sending about ${pct(N.flagShort, 0)} of people for a blood test.`, { x: 0.6, y: 1.1, w: 8.8, h: 0.75, fontSize: 16, color: HEX.ice, objectName: "recommendation" });
  const cols = [
    ["Limitations", ["Self-reported answers, one training year", "Recall much lower for young adults", "Prediabetes not captured (counted as 0)", "Test cost in the planner is an assumption", "A screening aid, never a diagnosis"]],
    ["Next steps", ["Validate across states (later years: done, slide 10)", "Recalibrate the cut-off on recent local data", "Pilot with a clinic and confirm with HbA1c tests", "Add a separate cut-off for younger age groups"]],
  ];
  cols.forEach(([h, items], i) => {
    const x = 0.6 + i * 4.5;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 2.05, w: 4.3, h: 2.55, rectRadius: 0.08, fill: { color: "134A5E" }, line: { color: "1D5C72", width: 0.75 }, objectName: `${h} card` });
    txt(s, h, { x: x + 0.25, y: 2.2, w: 3.8, h: 0.4, fontSize: 16, bold: true, color: HEX.cyan, objectName: `${h} head` });
    txt(s, items.map((t, j) => ({ text: t, options: { bullet: { indent: 14 }, breakLine: j < items.length - 1 } })), { x: x + 0.25, y: 2.65, w: 3.85, h: 2.15, fontSize: 13, color: C.background1, paraSpaceAfter: 5, objectName: `${h} list` });
  });
  s.addImage({ data: b64(logoWhitePng), x: 9.4 - 0.37 * logoAR, y: 5.05, w: 0.37 * logoAR, h: 0.37, objectName: "SugarScope logo small" });
  s.addNotes(`Our recommendation: use the ${N.nShort}-question model as the first step of a screening programme, with the cut-off at ${N.thrShort.toFixed(3)}. It catches about ${pct(N.short.recall, 0)} of people with diagnosed diabetes while sending around ${pct(N.flagShort, 0)} of those screened for a blood test, instead of everyone. There are real limits. The answers are self-reported, the model was trained on a single survey year, and prediabetes is not captured: it is coded as no diabetes. Recall is much lower for young adults, simply because diabetes is rare at that age, so a single cut-off under-serves them. The test cost in the planner is our assumption. And this is a screening aid, never a diagnosis. Next, we want to validate across states, recalibrate on recent local data, pilot it with a clinic using real HbA1c results, and consider a separate cut-off for younger people. Thank you, we are happy to take questions.`);

  const out = P("deliverables", "presentation.pptx");
  await pres.writeFile({ fileName: out });
  const theme = process.env.PPTX_SKILL ? require(path.join(process.env.PPTX_SKILL, "scripts", "apply_theme.js")) : null;
  if (theme) await theme.applyTheme(out, THEME);
  else console.warn("PPTX_SKILL not set: theme colors not applied");
  fs.writeFileSync(P("deliverables", "build", "numbers.json"), JSON.stringify(N, null, 2));
  console.log("wrote", out);
}
main().catch((e) => { console.error(e); process.exit(1); });
