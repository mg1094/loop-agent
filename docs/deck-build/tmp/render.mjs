import { Presentation, PresentationFile } from "@oai/artifact-tool";
import {
  buildSlide01, buildSlide02, buildSlide03, buildSlide04,
  buildSlide05, buildSlide06, buildSlide07, buildSlide08,
  buildSlide09, buildSlide10, buildSlide11, buildSlide12,
} from "./deck.mjs";
import fs from "node:fs/promises";

const p = Presentation.create({ slideSize: { width: 1280, height: 720 } });
const builders = [
  buildSlide01, buildSlide02, buildSlide03, buildSlide04,
  buildSlide05, buildSlide06, buildSlide07, buildSlide08,
  buildSlide09, buildSlide10, buildSlide11, buildSlide12,
];
builders.forEach((b) => b(p));

await fs.mkdir("/Users/mac/code/loop-agent/docs/deck-build/tmp/slides", { recursive: true});
for (let i = 0; i < p.slides.items.length; i++) {
  const png = await p.export({ slide: p.slides.items[i], format: "png", scale: 1 });
  const buf = new Uint8Array(await png.arrayBuffer());
  await fs.writeFile(`/Users/mac/code/loop-agent/docs/deck-build/tmp/slides/slide-${String(i+1).padStart(2,"0")}.png`, buf);
  console.log(`wrote slide ${i+1}`);
}

const pptx = await PresentationFile.exportPptx(p);
const out = "/Users/mac/code/loop-agent/docs/deck-build/loop-agent-deck.pptx";
await pptx.save(out);
console.log(`pptx saved: ${out}`);
