async function workspaceChecks(fixtures) {
  const frame = document.createElement('iframe');
  frame.setAttribute('title', 'Disposable release checks');
  frame.style.cssText = 'position:fixed;inset:0;width:1100px;height:850px;background:white;z-index:9999;border:0';
  document.body.append(frame);
  const results = {};
  const wait = async (condition, timeout = 75000) => {
    const started = Date.now();
    while (!condition()) { if(Date.now()-started>timeout) throw new Error('The packaged workspace conversion timed out.'); await new Promise(resolve=>setTimeout(resolve,100)); }
  };
  const open = async slug => {
    const loaded = new Promise((resolve,reject) => {frame.onload=resolve;frame.onerror=reject;});
    frame.src='/tools/'+slug+'/';await loaded;
    await wait(()=>frame.contentDocument.querySelector('#document-input'));
    return frame.contentDocument;
  };
  const result = async doc => {
    await wait(()=>!doc.querySelector('#document-result').hidden||doc.querySelector('#document-status').classList.contains('is-error'));
    if(doc.querySelector('#document-result').hidden) throw new Error(doc.querySelector('#document-status').textContent);
    const bytes=new Uint8Array(await(await frame.contentWindow.fetch(doc.querySelector('#document-download').href)).arrayBuffer());
    let binary='';for(let offset=0;offset<bytes.length;offset+=16384)binary+=String.fromCharCode(...bytes.subarray(offset,offset+16384));
    return {ok:true,base64:btoa(binary),bytes:bytes.length};
  };
  try {
    for(const [name,slug] of [['text_pdf','text-to-pdf'],['json_csv','csv-json']]) {
      try {
        const doc=await open(slug);doc.querySelector('#document-text').value=name==='text_pdf'?'FileForge desktop release check. Merhaba, Grüße.':'[{"name":"Sample","count":2}]';
        doc.querySelector('#document-text').dispatchEvent(new frame.contentWindow.Event('input',{bubbles:true}));
        if(name==='json_csv')doc.querySelector('[name=format]').value='csv';
        doc.querySelector('#document-run').click();results[name]=await result(doc);
      } catch(error) {results[name]={ok:false,error:error.message};}
    }
    for(const [extension,slug] of [['docx','word-to-pdf'],['pptx','powerpoint-to-pdf']]) {
      try {
        const doc=await open(slug),window=frame.contentWindow;
        const bytes=Uint8Array.from(atob(fixtures[extension]),char=>char.charCodeAt(0));
        const transfer=new window.DataTransfer();transfer.items.add(new window.File([bytes],'release-check.'+extension));
        doc.querySelector('#document-input').files=transfer.files;doc.querySelector('#document-input').dispatchEvent(new window.Event('change',{bubbles:true}));
        await wait(()=>!doc.querySelector('#document-run').disabled);doc.querySelector('#document-run').click();
        await wait(()=>!doc.querySelector('#document-preview').hidden||doc.querySelector('#document-status').classList.contains('is-error'));
        if(doc.querySelector('#document-preview').hidden)throw new Error(doc.querySelector('#document-status').textContent);
        const pages=doc.querySelectorAll('#document-page option').length;
        doc.querySelector('#document-export').click();results[extension+'_pdf']={...await result(doc),preview_pages:pages};
      }catch(error){results[extension+'_pdf']={ok:false,error:error.message};}
    }
    if(fixtures.heic) {
      try {
        const loaded=new Promise(resolve=>{frame.onload=resolve;});frame.src='/tools/heic-to-jpg/';await loaded;
        const doc=frame.contentDocument,window=frame.contentWindow;
        await wait(()=>doc.querySelector('#finish-input'));
        const transfer=new window.DataTransfer();transfer.items.add(new window.File([Uint8Array.from(atob(fixtures.heic),c=>c.charCodeAt(0))],'release-check.heic'));
        doc.querySelector('#finish-input').files=transfer.files;doc.querySelector('#finish-input').dispatchEvent(new window.Event('change',{bubbles:true}));
        doc.querySelector('#finish-run').click();await wait(()=>!doc.querySelector('#finish-result').hidden||doc.querySelector('#finish-status').classList.contains('is-error'));
        if(doc.querySelector('#finish-result').hidden)throw new Error(doc.querySelector('#finish-status').textContent);
        const bytes=new Uint8Array(await(await window.fetch(doc.querySelector('#finish-download').href)).arrayBuffer());
        let binary='';for(let offset=0;offset<bytes.length;offset+=16384)binary+=String.fromCharCode(...bytes.subarray(offset,offset+16384));
        results.heic_jpg={ok:true,base64:btoa(binary),bytes:bytes.length};
      }catch(error){results.heic_jpg={ok:false,error:error.message};}
    }
    return results;
  }finally{frame.remove();}
}
