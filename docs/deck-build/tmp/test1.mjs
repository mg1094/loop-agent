import { Presentation, PresentationFile } from "/Users/mac/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs";
import { buildSlide01 } from "/Users/mac/code/loop-agent/docs/deck-build/tmp/deck.mjs";

const p = Presentation.create({ slideSize: { width: 1280, height: 720 } });
buildSlide01(p);
try {
  const pptx = await PresentationFile.exportPptx(p);
  await pptx.save("/tmp/s1.pptx");
  console.log("OK");
} catch (e) {
  console.log("FAIL: " + e.message);
}
