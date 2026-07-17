import { Presentation } from "@oai/artifact-tool";
import { buildSlide01, buildSlide02 } from "./deck.mjs";
import fs from "node:fs/promises";

const p = Presentation.create({ slideSize: { width: 1280, height: 720 } });
buildSlide01(p);
buildSlide02(p);

await fs.mkdir("slides", { recursive: true });
const items = p.slides.items;
for (let i = 0; i < items.length; i++) {
  const png = await p.export({ slide: items[i], format: "png", scale: 1 });
  const buf = new Uint8Array(await png.arrayBuffer());
  await fs.writeFile(`slides/test-${String(i+1).padStart(2,"0")}.png`, buf);
  console.log(`wrote slide ${i+1}`);
}
