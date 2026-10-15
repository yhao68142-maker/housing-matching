const fs=require('node:fs'),path=require('node:path');
fs.mkdirSync('dist/vendor',{recursive:true});
for(const name of ['index.html','style.css','housing-data.js','matcher.js','step-features.js','app.js','cloud-config.js','library.js','cad-worker.js','README.md'])fs.copyFileSync(name,path.join('dist',name));
for(const name of ['occt-import-js.js','occt-import-js.wasm'])fs.copyFileSync(path.join('node_modules/occt-import-js/dist',name),path.join('dist/vendor',name));
fs.copyFileSync('node_modules/occt-import-js/LICENSE.md','dist/vendor/LICENSE.md');
fs.writeFileSync('dist/.nojekyll','');
fs.mkdirSync('dist/backend',{recursive:true});
fs.copyFileSync('backend/DEPLOY.md','dist/backend/DEPLOY.md');
console.log('Static site built in dist/');
