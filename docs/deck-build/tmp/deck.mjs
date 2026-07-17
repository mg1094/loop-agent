import {
  Presentation,
  PresentationFile,
  shape,
  table,
  text,
  image,
  layers,
} from "@oai/artifact-tool";

const COLORS = {
  ink: "#000000",
  canvas: "#FFFFFF",
  panel: "#EDEDED",
  panelDeep: "#E2E2E2",
  muted: "#555555",
  rule: "#B8BCC4",
  ruleSoft: "#D6D9DE",
  highlight: "#FF6B35",
};
const FONT = "Helvetica Neue";
const SLIDE_W = 1280;
const SLIDE_H = 720;

function F(left, top, width, height) {
  return { position: { left, top }, width, height };
}
function rect(name, left, top, width, height, fill, line) {
  return shape({
    name,
    geometry: "rect",
    fill,
    line: line || { style: "solid", fill: "none", width: 0 },
    ...F(left, top, width, height),
  });
}
function rule(name, left, top, width) {
  return rect(name, left, top, width, 1, COLORS.rule,
    { style: "solid", fill: COLORS.rule, width: 1 });
}
function vrule(name, top, height, left) {
  return rect(name, left, top, 1, height, COLORS.rule,
    { style: "solid", fill: COLORS.rule, width: 1 });
}
function tb(slide, runs, name, r, style) {
  const payload = Array.isArray(runs) && runs.length && runs[0] && runs[0].runs
    ? runs
    : [{ runs: [{ text: runs }] }];
  return text(payload, {
    name,
    ...F(r.left, r.top, r.width, r.height),
    style: { fontFamily: FONT, ...style },
  });
}
function bullets(slide, items, name, r, opts) {
  opts = opts || {};
  const lines = items.map((t) => ({ runs: [{ text: t }] }));
  return text(lines, {
    name,
    ...F(r.left, r.top, r.width, r.height),
    style: {
      fontFamily: FONT,
      fontSize: opts.fontSize || 14,
      color: opts.color || COLORS.ink,
      alignment: "left",
      lineHeight: opts.lineHeight || 1.45,
      bullet: opts.bullet === false ? undefined : { kind: "bullet", color: opts.bulletColor || COLORS.highlight },
      paraSpacingAfter: opts.paraSpacingAfter || 8,
    },
  });
}
function panel(slide, name, left, top, width, height, fill, border) {
  if (border === undefined) border = true;
  return rect(name, left, top, width, height, fill || COLORS.panel,
    border ? { style: "solid", fill: COLORS.rule, width: 1 } : undefined);
}
function footer(page, total) {
  if (total === undefined) total = 12;
  return [
    rule("footer-rule-" + page, 56, 668, 1168),
    tb(null, "loop-agent", "footer-tag-" + page,
      { left: 56, top: 678, width: 220, height: 24 },
      { fontSize: 11, color: COLORS.muted, alignment: "left" }),
    tb(null, "对外宣讲稿 · loop-agent overview", "footer-meta-" + page,
      { left: 280, top: 678, width: 540, height: 24 },
      { fontSize: 11, color: COLORS.muted, alignment: "left" }),
    tb(null, String(page).padStart(2, "0") + " / " + String(total).padStart(2, "0"),
      "footer-page-" + page,
      { left: 1170, top: 678, width: 54, height: 24 },
      { fontSize: 11, color: COLORS.muted, alignment: "right" }),
  ];
}
function titleBlock(page, eyebrow, title, lede, opts) {
  opts = opts || {};
  return [
    tb(null, eyebrow, "eyebrow-" + page,
      { left: 56, top: 56, width: 900, height: 22 },
      { fontSize: 12, bold: true, color: COLORS.highlight, alignment: "left", charSpacing: 4 }),
    tb(null, title, "title-" + page,
      { left: 56, top: 92, width: opts.titleWidth || 1168, height: opts.titleHeight || 80 },
      { fontSize: opts.titleSize || 36, bold: true, color: COLORS.ink, alignment: "left", lineHeight: 1.1 }),
    tb(null, lede, "lede-" + page,
      { left: 56, top: 176, width: opts.ledeWidth || 1168, height: opts.ledeHeight || 60 },
      { fontSize: opts.ledeSize || 17, color: COLORS.muted, alignment: "left", lineHeight: 1.4 }),
  ];
}
function arrowH(name, x1, x2, y, color, headSize) {
  if (color === undefined) color = COLORS.ink;
  if (headSize === undefined) headSize = 8;
  const nodes = [];
  const minX = Math.min(x1, x2);
  const width = Math.max(1, Math.abs(x2 - x1) - headSize);
  nodes.push(rect(name + "-line", minX, y - 1, width, 2, color));
  nodes.push(shape({
    name: name + "-head",
    geometry: "triangle",
    fill: color,
    line: { style: "solid", fill: "none", width: 0 },
    ...F(x2 - headSize, y - headSize / 2, headSize, headSize),
    rotation: 90,
  }));
  return nodes;
}
function buildSlide01(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = COLORS.canvas;
  const nodes = [];
  nodes.push(rect("cover-accent", 56, 56, 96, 6, COLORS.highlight));
  nodes.push(tb(slide, "A LIGHTWEIGHT REACT FRAMEWORK", "cover-eyebrow",
    { left: 56, top: 88, width: 800, height: 24 },
    { fontSize: 12, bold: true, color: COLORS.ink, alignment: "left", charSpacing: 4 }));
  nodes.push(tb(slide, "loop-agent", "cover-title",
    { left: 56, top: 188, width: 1168, height: 170 },
    { fontSize: 96, bold: true, color: COLORS.ink, alignment: "left", lineHeight: 1.0 }));
  nodes.push(tb(slide, "一个轻量的 ReAct 智能体框架 —— 把工具、技能和编排都变成可读的代码，而不是隐藏在图引擎里。",
    "cover-lede",
    { left: 56, top: 376, width: 1168, height: 60 },
    { fontSize: 22, color: COLORS.ink, alignment: "left", lineHeight: 1.4 }));
  nodes.push(tb(slide, "Hand-written loop  ·  Tools + Skills as data  ·  DAG-shaped orchestration",
    "cover-lede-en",
    { left: 56, top: 444, width: 1168, height: 32 },
    { fontSize: 14, color: COLORS.muted, alignment: "left" }));
  nodes.push(rule("cover-divider", 56, 510, 1168));
  const pillars = [
    { num: "01", title: "Hand-written ReAct loop", sub: "while + trace log，没有 StateGraph" },
    { num: "02", title: "Tools + Skills as data", sub: "BaseTool 自动注册，Markdown 即技能" },
    { num: "03", title: "DAG-shaped orchestration", sub: "拓扑分层、按层并行的 Supervisor" },
  ];
  pillars.forEach((p, i) => {
    const x = 56 + i * 400;
    nodes.push(tb(slide, p.num, "pillar-num-" + i,
      { left: x, top: 538, width: 56, height: 22 },
      { fontSize: 14, bold: true, color: COLORS.highlight, alignment: "left" }));
    nodes.push(tb(slide, p.title, "pillar-title-" + i,
      { left: x + 60, top: 538, width: 320, height: 22 },
      { fontSize: 14, bold: true, color: COLORS.ink, alignment: "left" }));
    nodes.push(tb(slide, p.sub, "pillar-sub-" + i,
      { left: x, top: 566, width: 380, height: 22 },
      { fontSize: 12, color: COLORS.muted, alignment: "left" }));
  });
  nodes.push(rule("cover-footer-rule", 56, 668, 1168));
  nodes.push(tb(slide, "v0.1.0  ·  MIT  ·  Python 3.11+  ·  LangChain 1.0+",
    "cover-footer-meta",
    { left: 56, top: 678, width: 600, height: 24 },
    { fontSize: 11, color: COLORS.muted, alignment: "left" }));
  nodes.push(tb(slide, "01 / 12", "cover-footer-page",
    { left: 1170, top: 678, width: 54, height: 24 },
    { fontSize: 11, color: COLORS.muted, alignment: "right" }));
  slide.compose(layers({ name: "loop-agent-cover-01", width: "fill", height: "fill" }, nodes),
    { frame: { left: 0, top: 0, width: SLIDE_W, height: SLIDE_H }, baseUnit: 1 });
  return slide;
}
function buildSlide02(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = COLORS.canvas;
  const nodes = [];
  nodes.push(...titleBlock(2, "01  ·  POSITIONING",
    "为什么需要又一个 agent 框架？",
    "已有的方案要么重到没法读，要么薄到每次都重写。loop-agent 想做中间那一档——一个下午能看完、能改、能扩展的实现。"));
  nodes.push(panel(slide, "pos-left-card", 56, 280, 540, 340, COLORS.panel, true));
  nodes.push(tb(slide, "重框架", "pos-left-eyebrow",
    { left: 80, top: 304, width: 480, height: 24 },
    { fontSize: 12, bold: true, color: COLORS.muted, alignment: "left", charSpacing: 2 }));
  nodes.push(tb(slide, "LangGraph 风格的 StateGraph", "pos-left-title",
    { left: 80, top: 332, width: 480, height: 36 },
    { fontSize: 22, bold: true, color: COLORS.ink, alignment: "left" }));
  nodes.push(bullets(slide, [
    "学习曲线陡，节点 / 边要先建模再写代码",
    "抽象层多，一个小改动跨好几个文件",
    "容易和具体运行时绑定，迁移成本高",
  ], "pos-left-bullets",
    { left: 80, top: 388, width: 480, height: 220 },
    { fontSize: 14, color: COLORS.muted, lineHeight: 1.55, bulletColor: COLORS.muted }));
  nodes.push(panel(slide, "pos-right-card", 636, 280, 588, 340, COLORS.canvas, true));
  nodes.push(rect("pos-right-accent", 636, 280, 4, 340, COLORS.highlight));
  nodes.push(tb(slide, "我们要做的", "pos-right-eyebrow",
    { left: 664, top: 304, width: 540, height: 24 },
    { fontSize: 12, bold: true, color: COLORS.highlight, alignment: "left", charSpacing: 2 }));
  nodes.push(tb(slide, "一个下午能读完的 ReAct 框架", "pos-right-title",
    { left: 664, top: 332, width: 540, height: 36 },
    { fontSize: 22, bold: true, color: COLORS.ink, alignment: "left" }));
  nodes.push(bullets(slide, [
    "AgentLoop 就是一个 while 循环 + trace log",
    "工具子类化即注册，技能就是 Markdown",
    "Provider 层统一 OpenAI 兼容接口",
    "Supervisor 把多智能体编排做成 DAG",
    "内置 trace、retry、sandbox、sessions",
  ], "pos-right-bullets",
    { left: 664, top: 388, width: 540, height: 220 },
    { fontSize: 14, color: COLORS.ink, lineHeight: 1.55, bulletColor: COLORS.highlight }));
  nodes.push(tb(slide, "灵感来源 Vibe-Trading：从金融用例里把可复用的 agent 内核抽出来",
    "pos-foot",
    { left: 56, top: 640, width: 1168, height: 22 },
    { fontSize: 11, color: COLORS.muted, alignment: "left" }));
  nodes.push(...footer(2));
  slide.compose(layers({ name: "loop-agent-cover-02", width: "fill", height: "fill" }, nodes),
    { frame: { left: 0, top: 0, width: SLIDE_W, height: SLIDE_H }, baseUnit: 1 });
  return slide;
}
function buildSlide03(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = COLORS.canvas;
  const nodes = [];
  nodes.push(...titleBlock(3, "02  ·  ARCHITECTURE",
    "一张图看完整的运行链路",
    "从 CLI / HTTP 入口出发，AgentLoop 串起一组小型组件，每一层都留有 trace 与扩展点。",
    { ledeHeight: 60 }));

  // Entry
  const eX = 56, eY = 280, eW = 200;
  nodes.push(panel(slide, "arch-entry", eX, eY, eW, 200, COLORS.panel, true));
  nodes.push(tb(slide, "ENTRY", "arch-entry-label",
    { left: eX + 16, top: eY + 16, width: eW - 32, height: 22 },
    { fontSize: 11, bold: true, color: COLORS.muted, alignment: "left", charSpacing: 3 }));
  nodes.push(tb(slide, "CLI", "arch-entry-cli",
    { left: eX + 16, top: eY + 50, width: eW - 32, height: 32 },
    { fontSize: 18, bold: true, color: COLORS.ink, alignment: "left" }));
  nodes.push(tb(slide, "loop-agent run …", "arch-entry-cli-cmd",
    { left: eX + 16, top: eY + 86, width: eW - 32, height: 22 },
    { fontSize: 11, color: COLORS.muted, alignment: "left" }));
  nodes.push(rule("arch-entry-r1", eX + 16, eY + 116, eW - 32, COLORS.ruleSoft));
  nodes.push(tb(slide, "FastAPI", "arch-entry-api",
    { left: eX + 16, top: eY + 128, width: eW - 32, height: 32 },
    { fontSize: 18, bold: true, color: COLORS.ink, alignment: "left" }));
  nodes.push(tb(slide, "POST /chat · /chat/stream", "arch-entry-api-cmd",
    { left: eX + 16, top: eY + 164, width: eW - 32, height: 22 },
    { fontSize: 11, color: COLORS.muted, alignment: "left" }));

  // AgentLoop core
  const cX = 296, cY = 280, cW = 320, cH = 200;
  nodes.push(panel(slide, "arch-core", cX, cY, cW, cH, COLORS.canvas, true));
  nodes.push(rect("arch-core-accent", cX, cY, cW, 4, COLORS.highlight));
  nodes.push(tb(slide, "AGENT LOOP", "arch-core-label",
    { left: cX + 16, top: cY + 20, width: cW - 32, height: 22 },
    { fontSize: 11, bold: true, color: COLORS.highlight, alignment: "left", charSpacing: 3 }));
  nodes.push(tb(slide, "while 循环 + ReAct", "arch-core-title",
    { left: cX + 16, top: cY + 48, width: cW - 32, height: 36 },
    { fontSize: 22, bold: true, color: COLORS.ink, alignment: "left" }));
  nodes.push(bullets(slide, [
    "build_messages() 装配 system prompt",
    "chat() → 决定工具调用或结束",
    "execute() → 拿结果 → 回到循环",
    "compact() 在 token 压力下折叠",
  ], "arch-core-bullets",
    { left: cX + 16, top: cY + 92, width: cW - 32, height: 100 },
    { fontSize: 12, color: COLORS.ink, lineHeight: 1.45, bulletColor: COLORS.highlight }));

  // arrow entry -> core
  nodes.push(rect("arch-arrow-1", eX + eW + 6, cY + cH / 2 - 1, 34, 2, COLORS.ink));
  nodes.push(shape({
    name: "arch-arrow-1-head",
    geometry: "triangle",
    fill: COLORS.ink,
    line: { style: "solid", fill: "none", width: 0 },
    ...F(eX + eW + 38, cY + cH / 2 - 7, 12, 14),
    rotation: 90,
  }));

  // Collaborators
  const oX = 656, oY = 280, oW = 568, oH = 200;
  nodes.push(panel(slide, "arch-coll", oX, oY, oW, oH, COLORS.canvas, true));
  nodes.push(tb(slide, "COLLABORATORS", "arch-coll-label",
    { left: oX + 16, top: oY + 16, width: oW - 32, height: 22 },
    { fontSize: 11, bold: true, color: COLORS.muted, alignment: "left", charSpacing: 3 }));
  const colls = [
    { name: "ContextBuilder", desc: "拼装 system prompt + 工具描述 + 技能摘要" },
    { name: "ChatLLM", desc: "统一 OpenAI 兼容接口，支持 7 家 provider" },
    { name: "ToolRegistry", desc: "BaseTool 自动注册，工具按需可沙箱" },
    { name: "SkillsLoader", desc: "YAML+Markdown，按需 load_skill() 展开" },
  ];
  colls.forEach((c, i) => {
    const col = i % 2;
    const row = Math.floor(i / 2);
    const x = oX + 16 + col * 270;
    const y = oY + 48 + row * 70;
    nodes.push(rect("coll-bullet-" + i, x, y + 6, 6, 6, COLORS.highlight));
    nodes.push(tb(slide, c.name, "coll-name-" + i,
      { left: x + 14, top: y, width: 240, height: 22 },
      { fontSize: 13, bold: true, color: COLORS.ink, alignment: "left" }));
    nodes.push(tb(slide, c.desc, "coll-desc-" + i,
      { left: x + 14, top: y + 22, width: 240, height: 36 },
      { fontSize: 11, color: COLORS.muted, alignment: "left", lineHeight: 1.35 }));
  });

  // arrow core -> coll
  nodes.push(rect("arch-arrow-2", cX + cW + 6, cY + cH / 2 - 1, 34, 2, COLORS.ink));
  nodes.push(shape({
    name: "arch-arrow-2-head",
    geometry: "triangle",
    fill: COLORS.ink,
    line: { style: "solid", fill: "none", width: 0 },
    ...F(cX + cW + 38, cY + cH / 2 - 7, 12, 14),
    rotation: 90,
  }));

  // Cross-cutting band
  const bY = 520;
  nodes.push(panel(slide, "arch-band", 56, bY, 1168, 120, COLORS.panel, false));
  nodes.push(tb(slide, "CROSS-CUTTING", "arch-band-label",
    { left: 76, top: bY + 16, width: 200, height: 22 },
    { fontSize: 11, bold: true, color: COLORS.muted, alignment: "left", charSpacing: 3 }));
  const cross = [
    { name: "TraceWriter", desc: "runs/<id>/trace.jsonl，按 iteration 落盘" },
    { name: "SessionStore", desc: "SQLite 持久化，跨请求带 history" },
    { name: "ContextCompactor", desc: "老 tool 结果压缩、摘要" },
    { name: "Tool Sandbox", desc: "read/write 仅在 cwd / runs 内" },
  ];
  cross.forEach((c, i) => {
    const x = 76 + i * 280;
    nodes.push(tb(slide, c.name, "cross-name-" + i,
      { left: x, top: bY + 48, width: 260, height: 22 },
      { fontSize: 13, bold: true, color: COLORS.ink, alignment: "left" }));
    nodes.push(tb(slide, c.desc, "cross-desc-" + i,
      { left: x, top: bY + 72, width: 260, height: 36 },
      { fontSize: 11, color: COLORS.muted, alignment: "left", lineHeight: 1.35 }));
  });
  nodes.push(...footer(3));
  slide.compose(layers({ name: "loop-agent-cover-03", width: "fill", height: "fill" }, nodes),
    { frame: { left: 0, top: 0, width: SLIDE_W, height: SLIDE_H }, baseUnit: 1 });
  return slide;
}
function buildSlide04(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = COLORS.canvas;
  const nodes = [];
  nodes.push(...titleBlock(4, "03  ·  CORE ABSTRACTIONS",
    "四个核心抽象，构成整个框架",
    "整个 codebase 围绕这四个对象展开，其他一切都是它们的协作组合。"));
  // 4 cards in 2x2 grid, card height = 196
  const cards = [
    { tag: "AGENT", title: "AgentLoop", sub: "loop_agent/agent/loop.py",
      desc: "ReAct 的最小实现：while 循环里反复问模型要不要调工具，直到模型给出最终答复或达到迭代上限。",
      pts: "MAX_ITERATIONS=30  ·  TOKEN 阈值自动压缩  ·  同步事件 → SSE" },
    { tag: "TOOL", title: "BaseTool", sub: "loop_agent/agent/tools.py",
      desc: "所有工具的基类。子类只要写好 name / desc / params / execute 就会被 ToolRegistry 自动发现。",
      pts: "subclass 即注册  ·  repeatable 控制可重复调用  ·  read/write 默认沙箱" },
    { tag: "SKILL", title: "Skill / SkillsLoader", sub: "loop_agent/agent/skills.py",
      desc: "技能是带 YAML frontmatter 的 Markdown。系统 prompt 只放摘要，agent 需要时调用 load_skill 注入正文。",
      pts: "三类：writing / coding / research  ·  可放 ~/.loop-agent/skills/user  ·  FilteredSkillsLoader 限定 worker 可见性" },
    { tag: "STATE", title: "SessionStore", sub: "loop_agent/storage/session_store.py",
      desc: "SQLite 持久化每轮 user / assistant / tool 消息，让 /chat 多次调用保持同一段历史。",
      pts: ".sessions/sessions.db 本地存储  ·  compact() 显式压缩  ·  支持 list / search 检索" },
  ];
  const gridX = 56, gridY = 264, colW = 568, rowH = 196;
  cards.forEach((c, i) => {
    const col = i % 2;
    const row = Math.floor(i / 2);
    const x = gridX + col * (colW + 16);
    const y = gridY + row * (rowH + 16);
    nodes.push(panel(slide, "card-" + i, x, y, colW, rowH, COLORS.canvas, true));
    nodes.push(rect("card-accent-" + i, x, y, 4, rowH, COLORS.highlight));
    nodes.push(tb(slide, c.tag, "card-tag-" + i,
      { left: x + 24, top: y + 20, width: 200, height: 22 },
      { fontSize: 11, bold: true, color: COLORS.highlight, alignment: "left", charSpacing: 3 }));
    nodes.push(tb(slide, c.title, "card-title-" + i,
      { left: x + 24, top: y + 44, width: colW - 48, height: 32 },
      { fontSize: 22, bold: true, color: COLORS.ink, alignment: "left" }));
    nodes.push(tb(slide, c.sub, "card-sub-" + i,
      { left: x + 24, top: y + 80, width: colW - 48, height: 20 },
      { fontSize: 11, color: COLORS.muted, alignment: "left" }));
    nodes.push(tb(slide, c.desc, "card-desc-" + i,
      { left: x + 24, top: y + 104, width: colW - 48, height: 50 },
      { fontSize: 11, color: COLORS.ink, alignment: "left", lineHeight: 1.4 }));
    nodes.push(tb(slide, c.pts, "card-pts-" + i,
      { left: x + 24, top: y + 160, width: colW - 48, height: 28 },
      { fontSize: 10, color: COLORS.muted, alignment: "left", lineHeight: 1.3 }));
  });
  nodes.push(...footer(4));
  slide.compose(layers({ name: "loop-agent-cover-04", width: "fill", height: "fill" }, nodes),
    { frame: { left: 0, top: 0, width: SLIDE_W, height: SLIDE_H }, baseUnit: 1 });
  return slide;
}
function buildSlide05(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = COLORS.canvas;
  const nodes = [];
  nodes.push(...titleBlock(5, "04  ·  TOOLS  +  SKILLS",
    "Tools 和 Skills 是两套不同的扩展机制",
    "Tools 是代码（BaseTool 子类，自动注册）；Skills 是文档（Markdown + YAML，按需加载）。两套机制共同构成 agent 与外部世界交互的全部表面。"));
  // Left: TOOLS
  const lx = 56, ly = 280, lw = 568, lh = 360;
  nodes.push(panel(slide, "tools-card", lx, ly, lw, lh, COLORS.canvas, true));
  nodes.push(rect("tools-accent", lx, ly, 4, lh, COLORS.ink));
  nodes.push(tb(slide, "TOOLS", "tools-tag",
    { left: lx + 24, top: ly + 20, width: 200, height: 22 },
    { fontSize: 11, bold: true, color: COLORS.ink, alignment: "left", charSpacing: 3 }));
  nodes.push(tb(slide, "代码就是工具", "tools-title",
    { left: lx + 24, top: ly + 44, width: lw - 48, height: 36 },
    { fontSize: 22, bold: true, color: COLORS.ink, alignment: "left" }));
  nodes.push(bullets(slide, [
    "继承 BaseTool，子类文件放进 loop_agent/tools/ 即自动注册",
    "name / description / parameters 由 JSON Schema 描述",
    "execute() 返回 string，自动塞回 tool 消息",
    "read_file / write_file 默认沙箱到 cwd 和 cwd/runs",
    "LOOP_AGENT_UNRESTRICTED_FILES=1 可关掉沙箱（opt-in）",
  ], "tools-bullets",
    { left: lx + 24, top: ly + 92, width: lw - 48, height: 200 },
    { fontSize: 13, color: COLORS.ink, lineHeight: 1.5, bulletColor: COLORS.ink }));
  // tools code snippet
  const cX = lx + 24, cY = ly + 290, cW = lw - 48, cH = 56;
  nodes.push(panel(slide, "tools-code-bg", cX, cY, cW, cH, COLORS.panel, false));
  nodes.push(tb(slide, [
      { runs: [{ text: "class ", bold: true, color: COLORS.highlight }] },
      { runs: [{ text: "GreetTool", bold: true }] },
      { runs: [{ text: "(", color: COLORS.muted }] },
      { runs: [{ text: "BaseTool", bold: true }] },
      { runs: [{ text: "):", color: COLORS.muted }] },
    ], "tools-code-1",
    { left: cX + 12, top: cY + 8, width: cW - 24, height: 22 },
    { fontSize: 12, color: COLORS.ink, alignment: "left", fontFamily: "Courier New" }));
  nodes.push(tb(slide, [
      { runs: [{ text: "    name = ", color: COLORS.muted }] },
      { runs: [{ text: '"greet"', color: COLORS.highlight }] },
      { runs: [{ text: "    execute(self, *, name): ", color: COLORS.muted }] },
      { runs: [{ text: "return ", bold: true }] },
      { runs: [{ text: "f'Hello, {name}!'", color: COLORS.highlight }] },
    ], "tools-code-2",
    { left: cX + 12, top: cY + 30, width: cW - 24, height: 22 },
    { fontSize: 12, color: COLORS.ink, alignment: "left", fontFamily: "Courier New" }));

  // Right: SKILLS
  const rx = 656, ry = 280, rw = 568, rh = 360;
  nodes.push(panel(slide, "skills-card", rx, ry, rw, rh, COLORS.canvas, true));
  nodes.push(rect("skills-accent", rx, ry, 4, rh, COLORS.highlight));
  nodes.push(tb(slide, "SKILLS", "skills-tag",
    { left: rx + 24, top: ry + 20, width: 200, height: 22 },
    { fontSize: 11, bold: true, color: COLORS.highlight, alignment: "left", charSpacing: 3 }));
  nodes.push(tb(slide, "Markdown 就是技能", "skills-title",
    { left: rx + 24, top: ry + 44, width: rw - 48, height: 36 },
    { fontSize: 22, bold: true, color: COLORS.ink, alignment: "left" }));
  nodes.push(bullets(slide, [
    "每个技能一个文件夹 + SKILL.md，带 YAML frontmatter",
    "系统 prompt 只放描述，正文用 load_skill(name) 按需加载",
    "内置三类：writing / coding / research",
    "用户技能放 ~/.loop-agent/skills/user/ 即可",
    "FilteredSkillsLoader 给 worker 限定可见集合，未授权 → PermissionError",
  ], "skills-bullets",
    { left: rx + 24, top: ry + 92, width: rw - 48, height: 200 },
    { fontSize: 13, color: COLORS.ink, lineHeight: 1.5, bulletColor: COLORS.highlight }));
  // skills snippet
  const sX = rx + 24, sY = ry + 290, sW = rw - 48, sH = 56;
  nodes.push(panel(slide, "skills-code-bg", sX, sY, sW, sH, COLORS.panel, false));
  nodes.push(tb(slide, [
      { runs: [{ text: "---", color: COLORS.muted }] },
    ], "skills-code-1",
    { left: sX + 12, top: sY + 8, width: sW - 24, height: 20 },
    { fontSize: 12, color: COLORS.ink, alignment: "left", fontFamily: "Courier New" }));
  nodes.push(tb(slide, [
      { runs: [{ text: "name: ", color: COLORS.muted }] },
      { runs: [{ text: "research", color: COLORS.highlight }] },
      { runs: [{ text: "  ·  category: ", color: COLORS.muted }] },
      { runs: [{ text: "research", color: COLORS.highlight }] },
      { runs: [{ text: "  ·  description: …", color: COLORS.muted }] },
    ], "skills-code-2",
    { left: sX + 12, top: sY + 28, width: sW - 24, height: 22 },
    { fontSize: 12, color: COLORS.ink, alignment: "left", fontFamily: "Courier New" }));

  nodes.push(...footer(5));
  slide.compose(layers({ name: "loop-agent-cover-05", width: "fill", height: "fill" }, nodes),
    { frame: { left: 0, top: 0, width: SLIDE_W, height: SLIDE_H }, baseUnit: 1 });
  return slide;
}
function buildSlide06(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = COLORS.canvas;
  const nodes = [];
  nodes.push(...titleBlock(6, "05  ·  PROVIDER LAYER",
    "统一 OpenAI 兼容接口，零代码切换 7 家 provider",
    "loop_agent/providers/llm.py 只暴露 build_llm()，运行时按环境变量 LANGCHAIN_PROVIDER 决定走哪家。ChatLLM 在上层统一处理 retry / streaming / tool calling。",
    { ledeHeight: 60 }));

  // Manual grid: 8 providers x 3 columns (name | env key | note)
  // Header row
  const gX = 56, gY = 300, gW = 1168;
  const colWs = [220, 300, 648];
  let xCursor = gX;
  const headerY = gY;
  const headerH = 36;
  // header bg
  nodes.push(rect("prov-header-bg", gX, headerY, gW, headerH, COLORS.panel, false));
  const headers = ["Provider", "Env Key", "Notes"];
  headers.forEach((h, i) => {
    nodes.push(tb(slide, h, "prov-h-" + i,
      { left: xCursor + 16, top: headerY + 8, width: colWs[i] - 32, height: 22 },
      { fontSize: 12, bold: true, color: COLORS.ink, alignment: "left", charSpacing: 2 }));
    xCursor += colWs[i];
  });
  // vertical column separators
  xCursor = gX;
  for (let i = 0; i < colWs.length - 1; i++) {
    xCursor += colWs[i];
    nodes.push(vrule("prov-csep-" + i, headerY, 8 * 30, xCursor));
  }

  // Rows
  const rows = [
    ["openai",    "OPENAI_API_KEY",     "默认 provider，包含 OpenAI 全家桶"],
    ["deepseek",  "DEEPSEEK_API_KEY",   "国产高性价比，OpenAI 兼容"],
    ["dashscope", "DASHSCOPE_API_KEY",  "通义千问 qwen-plus-latest 等"],
    ["qwen",      "DASHSCOPE_API_KEY",  "dashscope 的别名"],
    ["moonshot",  "MOONSHOT_API_KEY",   "Kimi 系列，长上下文"],
    ["gemini",    "GEMINI_API_KEY",     "Google Gemini，OpenAI 兼容网关"],
    ["groq",      "GROQ_API_KEY",       "超快推理速度"],
    ["ollama",    "—",                  "本地推理，无需 API key"],
  ];
  const rowH = 26;
  rows.forEach((r, i) => {
    const y = headerY + headerH + 2 + i * rowH;
    if (i % 2 === 1) nodes.push(rect("prov-row-" + i, gX, y - 2, gW, rowH, "#F7F7F7", false));
    xCursor = gX;
    r.forEach((cell, j) => {
      nodes.push(tb(slide, cell, "prov-cell-" + i + "-" + j,
        { left: xCursor + 16, top: y + 2, width: colWs[j] - 32, height: rowH - 6 },
        { fontSize: 12, color: COLORS.ink, alignment: "left",
          fontFamily: j === 0 ? "Courier New" : FONT }));
      xCursor += colWs[j];
    });
  });
  // horizontal bottom rule
  nodes.push(rule("prov-bottom", gX, headerY + headerH + 8 * rowH + 2, gW));

  // Capabilities strip below
  const stripY = 540;
  nodes.push(panel(slide, "chatllm-strip", 56, stripY, 1168, 100, COLORS.panel, false));
  nodes.push(tb(slide, "ChatLLM 还做这些事", "chatllm-strip-title",
    { left: 76, top: stripY + 16, width: 600, height: 24 },
    { fontSize: 13, bold: true, color: COLORS.ink, alignment: "left" }));
  const caps = [
    { title: "重试 + 退避", desc: "指数退避 + full jitter，408/429/5xx 触发" },
    { title: "流式输出", desc: "stream_chat() → SSE 通道" },
    { title: "tool_calls 解析", desc: "LangChain ToolCall → 内部格式" },
    { title: "可观测 hook", desc: "on_retry(attempt, exc, jitter)" },
  ];
  caps.forEach((c, i) => {
    const x = 76 + i * 280;
    nodes.push(rect("cap-bullet-" + i, x, stripY + 52, 6, 6, COLORS.highlight));
    nodes.push(tb(slide, c.title, "cap-title-" + i,
      { left: x + 14, top: stripY + 46, width: 240, height: 22 },
      { fontSize: 12, bold: true, color: COLORS.ink, alignment: "left" }));
    nodes.push(tb(slide, c.desc, "cap-desc-" + i,
      { left: x + 14, top: stripY + 68, width: 240, height: 24 },
      { fontSize: 11, color: COLORS.muted, alignment: "left" }));
  });

  nodes.push(...footer(6));
  slide.compose(layers({ name: "loop-agent-cover-06", width: "fill", height: "fill" }, nodes),
    { frame: { left: 0, top: 0, width: SLIDE_W, height: SLIDE_H }, baseUnit: 1 });
  return slide;
}
function buildSlide07(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = COLORS.canvas;
  const nodes = [];
  nodes.push(...titleBlock(7, "06  ·  HTTP  +  STREAMING",
    "FastAPI 服务：单轮、连续会话、SSE 流式三套端点",
    "POST /chat 返回结构化 JSON；/chat/stream 用 text/event-stream 把每一次迭代都推给前端；/sessions 支持列出 / 检索历史会话。"));

  // Left: endpoints
  const lx = 56, ly = 280, lw = 460, lh = 360;
  nodes.push(panel(slide, "endpoints-card", lx, ly, lw, lh, COLORS.canvas, true));
  nodes.push(rect("endpoints-accent", lx, ly, 4, lh, COLORS.ink));
  nodes.push(tb(slide, "ENDPOINTS", "endpoints-tag",
    { left: lx + 24, top: ly + 20, width: 200, height: 22 },
    { fontSize: 11, bold: true, color: COLORS.ink, alignment: "left", charSpacing: 3 }));
  nodes.push(tb(slide, "API 表面", "endpoints-title",
    { left: lx + 24, top: ly + 44, width: lw - 48, height: 36 },
    { fontSize: 22, bold: true, color: COLORS.ink, alignment: "left" }));
  const endpoints = [
    ["POST", "/chat",         "单轮 prompt，返回完整 JSON"],
    ["POST", "/chat/stream",  "SSE 流式，per-iteration 推送"],
    ["POST", "/chat/super",   "多智能体编排入口"],
    ["GET",  "/sessions",     "列出所有会话"],
    ["GET",  "/sessions/q",   "全文子串检索"],
    ["DEL",  "/sessions/{id}", "删除会话"],
    ["GET",  "/skills",      "枚举可用技能"],
    ["GET",  "/tools",       "枚举已注册工具"],
    ["GET",  "/health",      "健康检查"],
  ];
  endpoints.forEach((e, i) => {
    const y = ly + 92 + i * 28;
    const methodColor = e[0] === "POST" ? COLORS.highlight : e[0] === "GET" ? COLORS.ink : COLORS.muted;
    nodes.push(tb(slide, e[0], "ep-method-" + i,
      { left: lx + 24, top: y, width: 56, height: 22 },
      { fontSize: 10, bold: true, color: methodColor, alignment: "left", charSpacing: 1 }));
    nodes.push(tb(slide, e[1], "ep-path-" + i,
      { left: lx + 86, top: y, width: 220, height: 22 },
      { fontSize: 12, color: COLORS.ink, alignment: "left", fontFamily: "Courier New" }));
    nodes.push(tb(slide, e[2], "ep-desc-" + i,
      { left: lx + 320, top: y, width: 130, height: 22 },
      { fontSize: 11, color: COLORS.muted, alignment: "left" }));
  });

  // Right: SSE events
  const rx = 540, ry = 280, rw = 684, rh = 360;
  nodes.push(panel(slide, "sse-card", rx, ry, rw, rh, COLORS.canvas, true));
  nodes.push(rect("sse-accent", rx, ry, 4, rh, COLORS.highlight));
  nodes.push(tb(slide, "SSE EVENTS", "sse-tag",
    { left: rx + 24, top: ry + 20, width: 200, height: 22 },
    { fontSize: 11, bold: true, color: COLORS.highlight, alignment: "left", charSpacing: 3 }));
  nodes.push(tb(slide, "流式事件类型", "sse-title",
    { left: rx + 24, top: ry + 44, width: rw - 48, height: 36 },
    { fontSize: 22, bold: true, color: COLORS.ink, alignment: "left" }));
  const events = [
    ["run_start",       "流开始时立即触发", "携带 run_id / run_dir"],
    ["iteration_start", "每次 ReAct 循环开始", "进入新一轮工具决策"],
    ["tool_progress",   "长任务按阶段触发", "web_search / read_file / write_file"],
    ["tool_result",     "每次工具调用结束", "name + content"],
    ["final",           "run 结束时唯一", "status / content / run_id / session_id"],
    ["error",           "不可恢复异常", "其余事件停止发送"],
  ];
  events.forEach((e, i) => {
    const y = ry + 92 + i * 40;
    nodes.push(rect("ev-dot-" + i, rx + 32, y + 6, 10, 10, i === 4 ? COLORS.highlight : COLORS.ink));
    if (i < events.length - 1) {
      nodes.push(vrule("ev-line-" + i, y + 18, 30, rx + 36));
    }
    nodes.push(tb(slide, e[0], "ev-type-" + i,
      { left: rx + 60, top: y, width: 220, height: 22 },
      { fontSize: 12, bold: true, color: COLORS.ink, alignment: "left", fontFamily: "Courier New" }));
    nodes.push(tb(slide, e[1], "ev-when-" + i,
      { left: rx + 290, top: y, width: 180, height: 22 },
      { fontSize: 11, color: COLORS.muted, alignment: "left" }));
    nodes.push(tb(slide, e[2], "ev-desc-" + i,
      { left: rx + 470, top: y, width: 190, height: 22 },
      { fontSize: 11, color: COLORS.muted, alignment: "left" }));
  });
  nodes.push(...footer(7));
  slide.compose(layers({ name: "loop-agent-cover-07", width: "fill", height: "fill" }, nodes),
    { frame: { left: 0, top: 0, width: SLIDE_W, height: SLIDE_H }, baseUnit: 1 });
  return slide;
}
function buildSlide08(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = COLORS.canvas;
  const nodes = [];
  nodes.push(...titleBlock(8, "07  ·  MULTI-AGENT",
    "Supervisor 把多智能体编排做成数据，而不是写死在 prompt 里",
    "WorkerSpec 描述每个 worker 的身份（名字 / 工具 / 技能 / 系统提示），WorkflowStep 描述先后顺序，Supervisor 替你调度。每次调用仍然走同一个 AgentLoop。"));

  // Two stages
  const pY = 290;
  const stages = [
    {
      tag: "STEP 0", name: "research", role: "WorkerSpec",
      tools: "web_search",
      task: "搜索与 {task} 相关的事实、URL、日期",
      color: COLORS.ink,
    },
    {
      tag: "STEP 1", name: "writer", role: "WorkerSpec",
      tools: "read_file, write_file, echo",
      task: "基于上一步输出，撰写 ~600 字报告",
      color: COLORS.highlight,
    },
  ];
  const stageW = 480, stageH = 140, stageGap = 80;
  const totalW = stageW * 2 + stageGap;
  const startX = (SLIDE_W - totalW) / 2;
  stages.forEach((s, i) => {
    const x = startX + i * (stageW + stageGap);
    nodes.push(panel(slide, "stage-" + i, x, pY, stageW, stageH, COLORS.canvas, true));
    nodes.push(rect("stage-accent-" + i, x, pY, 4, stageH, s.color));
    nodes.push(tb(slide, s.tag, "stage-tag-" + i,
      { left: x + 24, top: pY + 16, width: 100, height: 22 },
      { fontSize: 11, bold: true, color: s.color, alignment: "left", charSpacing: 3 }));
    nodes.push(tb(slide, s.role, "stage-role-" + i,
      { left: x + stageW - 200, top: pY + 16, width: 176, height: 22 },
      { fontSize: 11, color: COLORS.muted, alignment: "right", charSpacing: 1 }));
    nodes.push(tb(slide, s.name, "stage-name-" + i,
      { left: x + 24, top: pY + 40, width: stageW - 48, height: 36 },
      { fontSize: 24, bold: true, color: COLORS.ink, alignment: "left" }));
    nodes.push(tb(slide, "tools: " + s.tools, "stage-tools-" + i,
      { left: x + 24, top: pY + 80, width: stageW - 48, height: 20 },
      { fontSize: 11, color: COLORS.muted, alignment: "left", fontFamily: "Courier New" }));
    nodes.push(tb(slide, s.task, "stage-task-" + i,
      { left: x + 24, top: pY + 104, width: stageW - 48, height: 32 },
      { fontSize: 12, color: COLORS.ink, alignment: "left" }));
    if (i < stages.length - 1) {
      const ax = x + stageW;
      const ay = pY + stageH / 2;
      nodes.push(rect("stage-arrow-" + i, ax + 8, ay - 1, stageGap - 16, 2, COLORS.ink));
      nodes.push(shape({
        name: "stage-arrow-head-" + i,
        geometry: "triangle",
        fill: COLORS.ink,
        line: { style: "solid", fill: "none", width: 0 },
        ...F(ax + stageGap - 12, ay - 8, 12, 16),
        rotation: 90,
      }));
      nodes.push(tb(slide, "{prev_output}", "stage-arrow-label-" + i,
        { left: ax + 16, top: ay - 24, width: stageGap - 32, height: 18 },
        { fontSize: 10, color: COLORS.muted, alignment: "center", fontFamily: "Courier New" }));
    }
  });

  // Data model strip
  const stripY = 470;
  nodes.push(panel(slide, "specs-strip", 56, stripY, 1168, 170, COLORS.panel, false));
  nodes.push(tb(slide, "配置即代码", "specs-strip-title",
    { left: 76, top: stripY + 16, width: 600, height: 24 },
    { fontSize: 13, bold: true, color: COLORS.ink, alignment: "left" }));
  const specs = [
    { tag: "@dataclass", name: "WorkerSpec",  fields: "name / tools / skills / system_prompt / max_iterations" },
    { tag: "@dataclass", name: "WorkflowStep", fields: "worker / task_template  · 支持 {task} {prev_output}" },
  ];
  specs.forEach((s, i) => {
    const x = 76 + i * 580;
    const y = stripY + 50;
    nodes.push(rect("spec-tag-" + i, x, y, 80, 20, COLORS.highlight));
    nodes.push(tb(slide, s.tag, "spec-tag-text-" + i,
      { left: x + 6, top: y + 2, width: 68, height: 16 },
      { fontSize: 10, bold: true, color: COLORS.canvas, alignment: "center", charSpacing: 1 }));
    nodes.push(tb(slide, s.name, "spec-name-" + i,
      { left: x + 92, top: y - 2, width: 460, height: 24 },
      { fontSize: 16, bold: true, color: COLORS.ink, alignment: "left", fontFamily: "Courier New" }));
    nodes.push(tb(slide, s.fields, "spec-fields-" + i,
      { left: x + 92, top: y + 24, width: 480, height: 40 },
      { fontSize: 11, color: COLORS.muted, alignment: "left", fontFamily: "Courier New" }));
  });
  // CLI command
  const codeY = stripY + 110;
  nodes.push(tb(slide, "CLI 一行起跑：loop-agent run-supervised \"Write a report on …\" --session-id demo",
    "spec-cli",
    { left: 76, top: codeY, width: 1100, height: 22 },
    { fontSize: 12, color: COLORS.ink, alignment: "left", fontFamily: "Courier New" }));

  nodes.push(...footer(8));
  slide.compose(layers({ name: "loop-agent-cover-08", width: "fill", height: "fill" }, nodes),
    { frame: { left: 0, top: 0, width: SLIDE_W, height: SLIDE_H }, baseUnit: 1 });
  return slide;
}
function buildSlide09(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = COLORS.canvas;
  const nodes = [];
  nodes.push(...titleBlock(9, "08  ·  DAG + PARALLEL  ·  PHASE 4",
    "Supervisor 现在支持完整的 DAG 与按层并行执行",
    "StepTemplate / StepInstance 让工作流从线性变成有向无环图。Supervisor 在拓扑分层后用 ThreadPoolExecutor 并行执行每层，最终再聚合到最深的 sink。",
    { titleSize: 32, ledeHeight: 60 }));

  // DAG canvas
  const dX0 = 420, dY0 = 300, dW = 804, dH = 340;
  nodes.push(panel(slide, "dag-frame", dX0, dY0, dW, dH, COLORS.canvas, true));
  nodes.push(rect("dag-frame-accent", dX0, dY0, dW, 4, COLORS.highlight));

  // DAG node positions (centers)
  const L0 = { cx: dX0 + 100, cy: dY0 + 170, w: 140, h: 56, name: "research", sub: "L0  root" };
  const L1 = [
    { cx: dX0 + 301, cy: dY0 + 90,  w: 140, h: 56, name: "facts",    sub: "L1  parallel" },
    { cx: dX0 + 301, cy: dY0 + 170, w: 140, h: 56, name: "quotes",   sub: "L1  parallel" },
    { cx: dX0 + 301, cy: dY0 + 250, w: 140, h: 56, name: "outline",  sub: "L1  parallel" },
  ];
  const L2 = { cx: dX0 + 502, cy: dY0 + 170, w: 140, h: 56, name: "draft",   sub: "L2  fan-in" };
  const L3 = { cx: dX0 + 703, cy: dY0 + 170, w: 140, h: 56, name: "finalize", sub: "L3  sink" };

  // Edges FIRST so they render behind nodes
  L1.forEach((n, i) => {
    nodes.push(...arrowH("e-l0-l1-" + i, L0.cx + L0.w / 2, n.cx - n.w / 2, n.cy));
  });
  L1.forEach((n, i) => {
    nodes.push(...arrowH("e-l1-l2-" + i, n.cx + n.w / 2, L2.cx - L2.w / 2, L2.cy));
  });
  nodes.push(...arrowH("e-l2-l3", L2.cx + L2.w / 2, L3.cx - L3.w / 2, L3.cy));

  // Nodes
  const drawNode = function (n, opts) {
    opts = opts || {};
    const isAccent = !!opts.accent;
    const fill = opts.fill || COLORS.canvas;
    nodes.push(panel(slide, "dag-node-" + n.name, n.cx - n.w / 2, n.cy - n.h / 2, n.w, n.h, fill, true));
    nodes.push(rect("dag-node-accent-" + n.name, n.cx - n.w / 2, n.cy - n.h / 2, 3, n.h,
      isAccent ? COLORS.highlight : COLORS.ink));
    nodes.push(tb(slide, n.sub, "dag-node-sub-" + n.name,
      { left: n.cx - n.w / 2 + 14, top: n.cy - n.h / 2 + 8, width: n.w - 28, height: 18 },
      { fontSize: 9, bold: true, color: isAccent ? COLORS.highlight : COLORS.muted,
        alignment: "left", charSpacing: 2 }));
    nodes.push(tb(slide, n.name, "dag-node-name-" + n.name,
      { left: n.cx - n.w / 2 + 14, top: n.cy - n.h / 2 + 26, width: n.w - 28, height: 24 },
      { fontSize: 14, bold: true, color: COLORS.ink, alignment: "left" }));
  };
  drawNode(L0, { accent: true });
  L1.forEach(drawNode);
  drawNode(L2);
  drawNode(L3, { accent: true });

  // Layer labels
  const layerLabels = [
    { cx: L0.cx, label: "入口" },
    { cx: L1[0].cx, label: "并行扇出" },
    { cx: L2.cx, label: "扇入聚合" },
    { cx: L3.cx, label: "终态 sink" },
  ];
  layerLabels.forEach((l, i) => {
    nodes.push(rect("layer-pip-" + i, l.cx - 3, dY0 + 18, 6, 6, COLORS.highlight));
    nodes.push(tb(slide, l.label, "layer-label-" + i,
      { left: l.cx - 60, top: dY0 + 36, width: 120, height: 22 },
      { fontSize: 11, bold: true, color: COLORS.muted, alignment: "center", charSpacing: 2 }));
  });

  // Left explanation panel
  const lxp = 56, lyp = 290;
  nodes.push(panel(slide, "dag-expl", lxp, lyp, 340, 350, COLORS.panel, false));
  nodes.push(tb(slide, "WHY IT MATTERS", "dag-expl-tag",
    { left: lxp + 20, top: lyp + 16, width: 240, height: 22 },
    { fontSize: 11, bold: true, color: COLORS.highlight, alignment: "left", charSpacing: 3 }));
  nodes.push(bullets(slide, [
    "拓扑分层 (Kahn)：独立节点进同一层",
    "每层用 ThreadPoolExecutor 并行跑",
    "depends_on + user_vars 模板渲染",
    "{prev_output} 取唯一上游，{deps} 显式访问",
    "final_instance_id 兜底扇出无扇入歧义",
  ], "dag-expl-bullets",
    { left: lxp + 20, top: lyp + 44, width: 300, height: 280 },
    { fontSize: 12, color: COLORS.ink, lineHeight: 1.55, bulletColor: COLORS.highlight }));

  nodes.push(...footer(9));
  slide.compose(layers({ name: "loop-agent-cover-09", width: "fill", height: "fill" }, nodes),
    { frame: { left: 0, top: 0, width: SLIDE_W, height: SLIDE_H }, baseUnit: 1 });
  return slide;
}
function buildSlide10(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = COLORS.canvas;
  const nodes = [];
  nodes.push(...titleBlock(10, "09  ·  OBSERVABILITY  +  RELIABILITY",
    "可观测与可靠性是默认打开的，不是事后补丁",
    "每一轮运行都自带 trace、会话持久化、重试退避与上下文压缩。复杂任务上不需要再单独接 LangSmith 之类的外部工具。"));

  // 4 metrics
  const metrics = [
    { num: "140", label: "自动化测试",     desc: "覆盖 tools / skills / loop / sessions / DAG / sandbox" },
    { num: "6",   label: "SSE 事件类型",     desc: "run_start / iteration_start / tool_result / tool_progress / final / error" },
    { num: "3+",  label: "重试 + 退避",       desc: "指数退避 + full jitter，408/429/5xx 自动重试" },
    { num: "40k", label: "Token 阈值",       desc: "超过自动折叠旧消息，long context 摘要成 handoff" },
  ];
  metrics.forEach((m, i) => {
    const x = 56 + i * 290;
    const y = 270;
    nodes.push(panel(slide, "metric-" + i, x, y, 270, 130, COLORS.canvas, true));
    nodes.push(rect("metric-accent-" + i, x, y, 4, 130, COLORS.highlight));
    nodes.push(tb(slide, m.num, "metric-num-" + i,
      { left: x + 24, top: y + 16, width: 240, height: 48 },
      { fontSize: 40, bold: true, color: COLORS.ink, alignment: "left", lineHeight: 1.0 }));
    nodes.push(tb(slide, m.label, "metric-label-" + i,
      { left: x + 24, top: y + 68, width: 240, height: 22 },
      { fontSize: 12, bold: true, color: COLORS.ink, alignment: "left", charSpacing: 2 }));
    nodes.push(tb(slide, m.desc, "metric-desc-" + i,
      { left: x + 24, top: y + 92, width: 230, height: 32 },
      { fontSize: 10, color: COLORS.muted, alignment: "left", lineHeight: 1.35 }));
  });

  // 3 reliability bands
  const bands = [
    { title: "Trace",   desc: "runs/<id>/trace.jsonl，按 iteration 落盘，可离线回放。每条记录包含 model、tool_calls、tool_result、状态切换。", tag: "DEBUG" },
    { title: "Sandbox", desc: "read_file / write_file 默认沙箱到 cwd 与 cwd/runs；解析符号链接后再校验；内置 ~/.ssh、~/.aws、~/.gnupg、~/.loop-agent/.env 的 deny-list。", tag: "SECURITY" },
    { title: "Compact", desc: "ContextCompactor 在 token 压力下折叠旧消息、长上下文摘要成 handoff；模型可主动调 compact(focus_topic=…) 触发压缩。", tag: "RELIABILITY" },
  ];
  bands.forEach((b, i) => {
    const x = 56 + i * 392;
    const y = 430;
    nodes.push(panel(slide, "band-" + i, x, y, 372, 200, COLORS.panel, false));
    nodes.push(rect("band-tag-" + i, x + 24, y + 24, 90, 22, COLORS.ink));
    nodes.push(tb(slide, b.tag, "band-tag-text-" + i,
      { left: x + 30, top: y + 26, width: 80, height: 18 },
      { fontSize: 10, bold: true, color: COLORS.canvas, alignment: "center", charSpacing: 2 }));
    nodes.push(tb(slide, b.title, "band-title-" + i,
      { left: x + 24, top: y + 56, width: 320, height: 32 },
      { fontSize: 22, bold: true, color: COLORS.ink, alignment: "left" }));
    nodes.push(tb(slide, b.desc, "band-desc-" + i,
      { left: x + 24, top: y + 96, width: 320, height: 96 },
      { fontSize: 11, color: COLORS.muted, alignment: "left", lineHeight: 1.5 }));
  });
  nodes.push(...footer(10));
  slide.compose(layers({ name: "loop-agent-cover-10", width: "fill", height: "fill" }, nodes),
    { frame: { left: 0, top: 0, width: SLIDE_W, height: SLIDE_H }, baseUnit: 1 });
  return slide;
}
function buildSlide11(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = COLORS.canvas;
  const nodes = [];
  nodes.push(...titleBlock(11, "10  ·  ROADMAP  +  TESTS",
    "四阶段路线图 + 一次 follow-up fix，全部测试通过",
    "从 ReAct 内核到 DAG 并行执行，每一个阶段都在 docs/superpowers/ 留下 plan / spec / progress 文档，并在 pytest 里有对应测试覆盖。"));

  // Timeline
  const tlY = 300;
  const phases = [
    { num: "01", title: "ReAct 内核",  date: "07-03",         bullets: ["AgentLoop while 循环", "BaseTool + SkillsLoader", "LangChain Provider 适配"], color: COLORS.ink },
    { num: "02", title: "HTTP / SSE",   date: "07-06 → 07-07", bullets: ["FastAPI + SSE 流式", "SQLite SessionStore", "文件沙箱 + 工具进度"], color: COLORS.ink },
    { num: "03", title: "Supervisor",  date: "07-07 → 07-08", bullets: ["WorkerSpec / WorkflowStep", "默认 research→writer", "FilteredSkillsLoader"], color: COLORS.ink },
    { num: "04", title: "DAG + 并行",  date: "07-09",         bullets: ["StepTemplate / StepInstance", "拓扑分层并行执行", "歧义 sink 兜底"], color: COLORS.highlight },
  ];
  const tlX0 = 56, tlW = 1168;
  const colW = (tlW - 60) / phases.length;
  // baseline
  nodes.push(rect("timeline-base", tlX0 + 16, tlY + 60, tlW - 32, 2, COLORS.rule));
  phases.forEach((p, i) => {
    const x = tlX0 + 16 + i * colW;
    const isCurrent = p.color === COLORS.highlight;
    nodes.push(rect("tl-pip-" + i, x + colW / 2 - 7, tlY + 53, 14, 14, p.color));
    if (isCurrent) nodes.push(rect("tl-pip-ring-" + i, x + colW / 2 - 14, tlY + 46, 28, 28, COLORS.highlight));
    nodes.push(panel(slide, "tl-card-" + i, x + 8, tlY - 80, colW - 16, 116, COLORS.canvas, true));
    nodes.push(rect("tl-card-accent-" + i, x + 8, tlY - 80, 4, 116, p.color));
    nodes.push(tb(slide, "PHASE " + p.num, "tl-num-" + i,
      { left: x + 24, top: tlY - 64, width: 200, height: 20 },
      { fontSize: 11, bold: true, color: p.color, alignment: "left", charSpacing: 3 }));
    nodes.push(tb(slide, p.title, "tl-title-" + i,
      { left: x + 24, top: tlY - 44, width: colW - 32, height: 32 },
      { fontSize: 18, bold: true, color: COLORS.ink, alignment: "left" }));
    nodes.push(tb(slide, p.date, "tl-date-" + i,
      { left: x + 24, top: tlY - 12, width: colW - 32, height: 20 },
      { fontSize: 11, color: COLORS.muted, alignment: "left" }));
    nodes.push(bullets(slide, p.bullets, "tl-bullets-" + i,
      { left: x + 8, top: tlY + 80, width: colW - 16, height: 110 },
      { fontSize: 11, color: COLORS.ink, lineHeight: 1.5, bulletColor: p.color }));
  });

  // Test categories — inline layout (no separate strip)
  const tY = 540;
  nodes.push(rect("tests-bar", 56, tY, 1168, 100, COLORS.panel, false));
  nodes.push(tb(slide, "测试覆盖", "tests-title",
    { left: 76, top: tY + 16, width: 120, height: 28 },
    { fontSize: 14, bold: true, color: COLORS.ink, alignment: "left" }));
  // 11 categories in 2 rows, left-aligned, simple text
  const cats = [
    "tools", "skills", "context", "loop", "compaction",
    "CLI", "API / SSE", "session", "sandbox", "DAG", "supervisor",
  ];
  cats.forEach((c, i) => {
    const col = i % 6;
    const row = Math.floor(i / 6);
    const x = 200 + col * 160;
    const y = tY + 16 + row * 28;
    nodes.push(rect("test-bul-" + i, x, y + 9, 4, 4, COLORS.highlight));
    nodes.push(tb(slide, c, "test-cat-" + i,
      { left: x + 12, top: y, width: 150, height: 22 },
      { fontSize: 12, color: COLORS.ink, alignment: "left", fontFamily: "Courier New" }));
  });

  nodes.push(...footer(11));
  slide.compose(layers({ name: "loop-agent-cover-11", width: "fill", height: "fill" }, nodes),
    { frame: { left: 0, top: 0, width: SLIDE_W, height: SLIDE_H }, baseUnit: 1 });
  return slide;
}
function buildSlide12(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = COLORS.canvas;
  const nodes = [];
  nodes.push(rect("close-accent", 56, 56, 96, 6, COLORS.highlight));
  nodes.push(tb(slide, "THANK YOU  ·  Q + A", "close-eyebrow",
    { left: 56, top: 88, width: 600, height: 24 },
    { fontSize: 12, bold: true, color: COLORS.ink, alignment: "left", charSpacing: 4 }));
  nodes.push(tb(slide, "loop-agent", "close-title",
    { left: 56, top: 144, width: 1168, height: 120 },
    { fontSize: 80, bold: true, color: COLORS.ink, alignment: "left", lineHeight: 1.0 }));
  nodes.push(tb(slide, "如果今天只能记住一句话 —— 编排应该写在你看得见的代码里，而不是埋在 prompt 或图引擎里。",
    "close-lede",
    { left: 56, top: 280, width: 1168, height: 60 },
    { fontSize: 20, color: COLORS.ink, alignment: "left", lineHeight: 1.4 }));
  nodes.push(rule("close-rule", 56, 360, 1168));

  const cols = [
    { tag: "WHAT YOU GET", title: "能拿来做什么", points: [
      "一句话跑多智能体研究 / 写作流水线",
      "Sandbox + sessions 直接接你的产品",
      "DAG 表达复杂工作流，按层并行省时间",
      "trace / 重试 / 沙箱 / 压缩 都内置",
    ] },
    { tag: "WHERE TO START", title: "怎么接入", points: [
      "pip install -e .[dev] 起一份本地副本",
      "复制 .env.example → 填 DASHSCOPE_API_KEY",
      "loop-agent run \"echo hello\" 先跑通",
      "loop-agent run-supervised \"…\" 看多智能体",
    ] },
    { tag: "WHAT'S NEXT", title: "下一阶段", points: [
      "MCP server entry（已在 Roadmap）",
      "更丰富的技能 marketplace",
      "更多 worker 工具集（SQL、浏览器）",
      "session 升级到 SQLite FTS5 全文索引",
    ] },
  ];
  cols.forEach((c, i) => {
    const x = 56 + i * 392;
    const y = 400;
    nodes.push(panel(slide, "close-col-" + i, x, y, 372, 220, COLORS.canvas, true));
    nodes.push(rect("close-col-accent-" + i, x, y, 4, 220, COLORS.highlight));
    nodes.push(tb(slide, c.tag, "close-col-tag-" + i,
      { left: x + 24, top: y + 20, width: 320, height: 22 },
      { fontSize: 11, bold: true, color: COLORS.highlight, alignment: "left", charSpacing: 3 }));
    nodes.push(tb(slide, c.title, "close-col-title-" + i,
      { left: x + 24, top: y + 44, width: 320, height: 32 },
      { fontSize: 20, bold: true, color: COLORS.ink, alignment: "left" }));
    nodes.push(bullets(slide, c.points, "close-col-bullets-" + i,
      { left: x + 24, top: y + 88, width: 320, height: 130 },
      { fontSize: 12, color: COLORS.ink, lineHeight: 1.5, bulletColor: COLORS.highlight }));
  });

  nodes.push(rule("close-footer-rule", 56, 668, 1168));
  nodes.push(tb(slide, "loop-agent  ·  MIT  ·  github.com", "close-footer-meta",
    { left: 56, top: 678, width: 600, height: 24 },
    { fontSize: 11, color: COLORS.muted, alignment: "left" }));
  nodes.push(tb(slide, "12 / 12", "close-footer-page",
    { left: 1170, top: 678, width: 54, height: 24 },
    { fontSize: 11, color: COLORS.muted, alignment: "right" }));

  slide.compose(layers({ name: "loop-agent-cover-12", width: "fill", height: "fill" }, nodes),
    { frame: { left: 0, top: 0, width: SLIDE_W, height: SLIDE_H }, baseUnit: 1 });
  return slide;
}
export {
  buildSlide01, buildSlide02, buildSlide03, buildSlide04,
  buildSlide05, buildSlide06, buildSlide07, buildSlide08,
  buildSlide09, buildSlide10, buildSlide11, buildSlide12,
};
