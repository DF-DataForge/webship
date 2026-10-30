// node record_slides.js [NN ...]  — film every slide NN_sKK into out/NN/sKK.mp4
const { Recorder } = require('./rec');
const fs = require('fs');
(async () => {
  const lengths = JSON.parse(fs.readFileSync('/opt/rec/slides/lengths.json'));
  const only = process.argv.slice(2);
  const r = new Recorder('/opt/rec/out'); await r.launch();
  for (const [name, len] of Object.entries(lengths)) {
    const [nn, scene] = name.split('_');
    if (only.length && !only.includes(nn)) continue;
    r.outDir = '/opt/rec/out/' + nn; fs.mkdirSync(r.outDir, { recursive: true });
    await r.page.goto('about:blank');
    await r.startScene(scene);
    await r.page.goto('file:///opt/rec/slides/' + name + '.html');
    await r.wait(len + 1.2);
    console.log(await r.endScene(0.2));
  }
  await r.close();
})().catch(e => { console.error(e); process.exit(1); });
