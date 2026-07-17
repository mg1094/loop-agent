import { Presentation, PresentationFile } from "/Users/mac/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs";
import { buildSlide01, buildSlide02, buildSlide03, buildSlide04, buildSlide05, buildSlide06, buildSlide07, buildSlide08, buildSlide09, buildSlide10, buildSlide11, buildSlide12 } from "/Users/mac/code/loop-agent/docs/deck-build/tmp/deck.mjs";

const p = Presentation.create({ slideSize: { width: 1280, height: 720 } });
for (const b of [buildSlide01, buildSlide02, buildSlide03, buildSlide04, buildSlide05, buildSlide06]) {
  b(p);
}
try {
  const pptx = await PresentationFile.exportPptx(p);
  await pptx.save("/tmp/group1.pptx");
  console.log("group1 OK");
} catch (e) {
  console.log("group1 FAIL:", e.message);
}
