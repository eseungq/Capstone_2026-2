// Execute the actual page script against a minimal DOM, without GPU/browser/network.
// Checks initialization and interaction, beyond JavaScript syntax alone.
function testRegionsPage(script) {
  let downloaded = null;
  let downloadName = null;
  class Element {
    constructor(tag) { this.tag = tag; this.children = []; this.value = ''; }
    append(...items) { this.children.push(...items); }
    replaceChildren(...items) { this.children = items; }
    getContext() { return { drawImage() {}, strokeRect() {} }; }
    getBoundingClientRect() { return { left: 0, top: 0, width: 1000, height: 500 }; }
    setPointerCapture() {}
    setAttribute() {}
    click() { if (this.download) downloadName = this.download; }
  }
  const ids = Object.fromEntries(['cases', 'message', 'export'].map(id => [id, new Element(id)]));
  const document = { createElement: tag => new Element(tag), getElementById: id => ids[id] };
  class MockImage {
    constructor() { this.naturalWidth = 1000; this.naturalHeight = 500; }
    set src(value) { this.onload(); }
  }
  const storage = {};
  const localStorage = { getItem: key => storage[key] || null, setItem: (key, value) => { storage[key] = value; } };
  const window = { addEventListener() {} };
  class MockBlob { constructor(parts) { this.text = parts.join(''); } }
  const URL = { createObjectURL: blob => { downloaded = JSON.parse(blob.text); return 'blob:test'; }, revokeObjectURL() {} };
  new Function('document', 'Image', 'localStorage', 'window', 'URL', 'Blob', 'setTimeout', script)(
    document, MockImage, localStorage, window, URL, MockBlob, fn => fn());
  if (ids.cases.children.length !== 3) throw Error('Not all three photos initialized');
  if (typeof ids.export.onclick !== 'function') throw Error('Export handler missing');
  ids.export.onclick();
  if (downloaded || !ids.message.textContent.includes('최소 1쌍')) throw Error('Incomplete export not explained');
  const pointer = (x,y) => ({clientX:x,clientY:y,pointerId:1,preventDefault(){}});
  for (const article of ids.cases.children) {
    const canvas = article.children.find(x=>x.tag==='canvas');
    const compare = article.children.find(x=>x.tag==='button' && x.textContent==='비교 위치 선택');
    const add = article.children.find(x=>x.tag==='button' && x.textContent==='쌍 추가');
    canvas.onpointerdown(pointer(100,50));
    canvas.onpointermove(pointer(200,100));
    canvas.onpointerup(pointer(200,100));
    // No extra button is required after drawing; clicking comparison must preserve target.
    canvas.onpointerdown(pointer(150,75)); canvas.onpointerup(pointer(150,75));
    add.onclick();
    if (!ids.message.textContent.includes('겹칩니다')) throw Error('Overlap reason not visible at top');
    canvas.onpointerdown(pointer(990,490)); canvas.onpointerup(pointer(990,490));
    add.onclick();
    if (!ids.message.textContent.includes('사진 밖')) throw Error('Out-of-bounds reason not visible at top');
    compare.onclick(); canvas.onpointerdown(pointer(700,350)); canvas.onpointerup(pointer(700,350));
    add.onclick();
  }
  ids.export.onclick();
  if (!downloaded || downloaded.schema!=='door-cam-regions-v2') throw Error('Export payload missing');
  if (downloaded.cases.length!==3 || downloaded.cases.some(c=>c.regions.length!==1)) throw Error('Exported regions incomplete');
  if (!downloadName?.startsWith('cam_regions_')) throw Error('Download not triggered');
  return {photos:3,regionPairs:3,incompleteExportFeedback:true,exportTriggered:true,draftStored:Object.keys(storage).length>0};
}
