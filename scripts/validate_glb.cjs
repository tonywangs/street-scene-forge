'use strict';
const fs = require('node:fs');
const validator = require('gltf-validator');
(async () => {
  const [file, report] = process.argv.slice(2);
  if (!file || !report) throw new Error('usage: node scripts/validate_glb.cjs scene.glb report.json');
  const result = await validator.validateBytes(new Uint8Array(fs.readFileSync(file)), {uri: 'scene.glb', maxIssues: 10000, externalResourceFunction: () => Promise.reject(new Error('external resource forbidden'))});
  fs.writeFileSync(report, JSON.stringify(result, null, 2) + '\n');
  console.log(JSON.stringify({validator: result.validatorVersion, ...result.issues}));
  if (result.issues.numErrors) process.exitCode = 1;
})();
