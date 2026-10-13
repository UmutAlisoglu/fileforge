"use strict";
const imageFormats = ".png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff,.gif";
const tools = {
  image: {title:"Image conversion",short:"Convert images",desc:"PNG, JPG, WebP or PDF",group:"Images",category:"IMAGE / CONVERT",detail:"Convert a single image or download a batch as a ZIP.",icon:"▧",number:"01",accept:imageFormats,max:100000000,count:50,drop:"Drop your images here",formats:"Up to 50 images · 100 MB each",action:"Convert images",note:"Animated images export the first frame. JPG and PDF use a white background.",keywords:"png jpg jpeg webp gif bmp tiff to pdf resize compress photos"},
  background: {title:"Remove background",short:"Remove background",desc:"Keep the subject. Change the backdrop.",group:"Images",category:"IMAGE / BACKGROUND",detail:"Create a cutout with a transparent or white background.",icon:"◐",number:"02",accept:imageFormats,max:100000000,count:1,drop:"Drop your image here",formats:"PNG, JPG, WebP, BMP, TIFF, GIF · 100 MB",action:"Remove background",note:"Review fine edges before using the result. Processing stays on your computer.",keywords:"erase remove background transparent cutout png photo"},
  trace: {title:"Image to SVG",short:"Image to SVG",desc:"Trace artwork into vector paths",group:"Images",category:"IMAGE / SVG",detail:"Turn a logo, icon or illustration into editable vector shapes.",icon:"◇",number:"03",accept:imageFormats,max:100000000,count:1,drop:"Drop your image here",formats:"PNG, JPG, WebP, BMP, TIFF, GIF · 100 MB",action:"Create SVG",note:"Best for logos and drawings. Photographs become a vector approximation.",keywords:"png jpg jpeg to svg vector vectorize trace logo drawing"},
  crop: {title:"Crop image",short:"Crop image",desc:"Keep exactly the area you need",group:"Images",category:"IMAGE / CROP",detail:"Drag a crop or enter exact coordinates in original image pixels.",icon:"⌗",number:"04",accept:".png,.jpg,.jpeg,.webp,.bmp,.gif",max:100000000,count:1,drop:"Drop your image here",formats:"PNG, JPG, WebP, BMP, GIF · 100 MB",action:"Crop image",note:"Coordinates refer to original image pixels. Animated GIFs use the first frame.",keywords:"crop trim photo picture square portrait landscape"},
  pdfimages: {title:"PDF to images",short:"PDF to images",desc:"Export selected pages as pictures",group:"PDFs",category:"PDF / IMAGES",detail:"Render pages as PNG or JPG. Multiple pages download as a ZIP.",icon:"▥",number:"05",accept:".pdf",max:250000000,count:1,drop:"Drop your PDF here",formats:"One unlocked PDF · up to 250 MB",action:"Export images",note:"Select page ranges such as 1–3, 5. The PDF is rendered locally.",keywords:"pdf to png jpg jpeg picture pages extract"},
  organize: {title:"Organize PDF",short:"Organize PDF",desc:"Reorder, rotate and select pages",group:"PDFs",category:"PDF / ORGANIZE",detail:"Build a new document from pages across one or more PDFs.",icon:"▦",number:"06",accept:".pdf",max:250000000,count:20,drop:"Drop your PDFs here",formats:"1–20 unlocked PDFs · 250 MB each · 200 pages total",action:"Export PDF",note:"Load the pages to preview them. Use the arrow buttons to set their order.",keywords:"pdf split extract reorder rearrange rotate delete pages organize"},
  merge: {title:"Merge PDFs",short:"Merge PDFs",desc:"Bring documents together",group:"PDFs",category:"PDF / MERGE",detail:"Combine documents in the order you choose.",icon:"▤",number:"07",accept:".pdf",max:250000000,count:20,drop:"Drop your PDFs here",formats:"2–20 PDF files · up to 250 MB each",action:"Merge PDFs",note:"Files are merged in the order below. Use the arrows to rearrange them.",keywords:"merge combine join pdf documents"},
  video: {title:"Video compression",short:"Compress video",desc:"Make an MP4 easier to share",group:"Video",category:"VIDEO / MP4",detail:"Choose a target size and resolution for your MP4.",icon:"▷",number:"08",accept:".mp4,.mov,.mkv,.webm,.avi,.m4v",max:2000000000,count:1,drop:"Drop your video here",formats:"MP4, MOV, MKV, WebM, AVI, M4V · up to 2 GB",action:"Compress video",note:"The original file stays unchanged. FFmpeg and FFprobe are required.",keywords:"mp4 compress reduce smaller video mov mkv webm avi"},
  spreadsheet: {title:"Excel to PDF",short:"Excel to PDF",desc:"Turn tables into a readable document",group:"Spreadsheets",category:"SPREADSHEET / PDF",detail:"Export visible worksheet data as clean tables on A4 pages.",icon:"▦",number:"09",accept:".xlsx,.csv",max:50000000,count:1,drop:"Drop your spreadsheet here",formats:"XLSX, CSV · up to 50 MB",action:"Create PDF",note:"Visible sheets are exported. Charts and Excel print layout are not retained.",keywords:"excel xlsx csv spreadsheet to pdf tables"}
};
const $ = id => document.getElementById(id);
const selections = Object.fromEntries(Object.keys(tools).map(key => [key, []]));
const settings = {};
const terminal = status => ["completed","failed","cancelled"].includes(status);
let current = "image", category = "All", videoAvailable = false, uploading = false, lastJobs = [], polling = false, lastJobSnapshot = "";
let sourceURL = null, sourceVersion = 0, cropImage = null, cropWidth = 0, cropHeight = 0, cropDrag = null;
let organizer = {pages:[],original:[],version:0,busy:false,jobId:null};
const previewedJobs = new Set();
const safe = value => String(value).replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
const size = bytes => bytes < 1000000 ? `${(bytes / 1000).toFixed(1)} KB` : `${(bytes / 1000000).toFixed(2)} MB`;
const pause = ms => new Promise(resolve => setTimeout(resolve,ms));
function error(message) { $("error-banner").textContent = message || ""; $("error-banner").hidden = !message; }
function readSettings() {
  if (current === "video") return {target_mb:Number($("target-mb").value),height:Number($("height").value),remove_audio:$("remove-audio").checked};
  if (current === "image") return {format:$("image-format").value,quality:Number($("quality").value),width:Number($("image-width").value)};
  if (current === "spreadsheet") return {orientation:$("orientation").value};
  if (current === "background") return {fill:$("background-fill").value};
  if (current === "trace") return {precision:Number($("trace-precision").value),detail:$("trace-detail").value};
  if (current === "crop") return {x:Number($("crop-x").value),y:Number($("crop-y").value),width:Number($("crop-width").value),height:Number($("crop-height").value),format:$("crop-format").value};
  if (current === "pdfimages") return {pages:$("pdf-pages").value.trim(),edge:Number($("pdf-edge").value),format:$("pdf-format").value};
  if (current === "organize") return {pages:organizer.pages.filter(page=>page.selected).map(({file_index,page_index,rotation})=>({file_index,page_index,rotation}))};
  return {};
}
function settingsHTML(key) {
  const value = settings[key] || {};
  if (key === "video") return `<div class="field"><label for="target-mb">Target file size</label><div class="input-unit"><input id="target-mb" type="number" min="0.1" max="10000" step="0.1" value="${value.target_mb || 25}" required><span>MB</span></div><div class="preset-row">${[10,25,50,100].map(n=>`<button class="preset" type="button" data-size="${n}">${n} MB</button>`).join("")}</div><p class="field-help">A smaller size can reduce picture quality. The finished file is checked against your target.</p></div><div class="field"><label for="height">Maximum resolution</label><select id="height"><option value="720">720p · good for sharing</option><option value="1080">1080p · more detail</option><option value="480">480p · smaller video</option><option value="0">Keep original resolution</option></select></div><label class="checkbox-label"><input id="remove-audio" type="checkbox"${value.remove_audio ? " checked" : ""}> Remove audio</label>`;
  if (key === "image") return `<div class="field"><label for="image-format">Output format</label><select id="image-format"><option value="webp">WebP · smaller web images</option><option value="jpg">JPG · photos</option><option value="png">PNG · keep transparency</option><option value="pdf">PDF · image document</option></select></div><div class="field"><label for="quality">Quality <span id="quality-value">${value.quality || 85}%</span></label><input id="quality" type="range" min="1" max="100" value="${value.quality || 85}"><p class="field-help" id="quality-help">Used for JPG and WebP output.</p></div><div class="field"><label for="image-width">Maximum width</label><div class="input-unit"><input id="image-width" type="number" min="0" max="12000" step="1" value="${value.width || 0}"><span>px</span></div><p class="field-help">0 keeps the original size. Aspect ratio is preserved. Multiple images download as a ZIP.</p></div>`;
  if (key === "background") return `<div class="field"><label for="background-fill">Background</label><select id="background-fill"><option value="transparent">Transparent · PNG cutout</option><option value="white">White · solid background</option></select></div><p class="field-help">The bundled model runs on your computer. First use may take a little longer while it loads.</p><p class="field-help">Hair, translucent objects and busy backgrounds can need edge cleanup. Preview the result before downloading.</p>`;
  if (key === "trace") return `<div class="field"><label for="trace-detail">Detail level</label><select id="trace-detail"><option value="simple">Simple · fewer shapes</option><option value="balanced">Balanced · everyday artwork</option><option value="fine">Fine · more detail</option></select></div><div class="field"><label for="trace-precision">Colour precision <span id="precision-value">${value.precision || 4}</span></label><input id="trace-precision" type="range" min="1" max="8" step="1" value="${value.precision || 4}"><p class="field-help">Higher precision keeps more shades and can produce a larger SVG.</p></div><p class="field-help">The output contains real vector paths. Photographs can create many shapes.</p>`;
  if (key === "crop") return `<div class="field"><label for="crop-ratio">Aspect ratio</label><select id="crop-ratio"><option value="free">Free selection</option><option value="1">Square · 1:1</option><option value="1.3333333333333333">Landscape · 4:3</option><option value="1.7777777777777777">Widescreen · 16:9</option></select></div><div class="coordinate-grid">${[["x","X position",0,0],["y","Y position",0,0],["width","Width",1,1],["height","Height",1,1]].map(([name,label,min,defaultValue])=>`<div class="field"><label for="crop-${name}">${label}</label><div class="input-unit"><input id="crop-${name}" type="number" min="${min}" step="1" value="${value[name] ?? defaultValue}" required><span>px</span></div></div>`).join("")}</div><div class="field"><label for="crop-format">Output format</label><select id="crop-format"><option value="png">PNG · keep transparency</option><option value="jpg">JPG · white background</option><option value="webp">WebP · smaller file</option></select></div>`;
  if (key === "pdfimages") return `<div class="field"><label for="pdf-pages">Pages to export</label><input id="pdf-pages" type="text" value="${safe(value.pages || "")}" placeholder="All pages, or 1-3, 5" maxlength="500"><p class="field-help">Leave blank for all pages. Use page numbers and ranges, such as 1–3, 5.</p></div><div class="field"><label for="pdf-edge">Maximum edge</label><select id="pdf-edge"><option value="1200">1,200 px · quick sharing</option><option value="2400">2,400 px · more detail</option><option value="3600">3,600 px · large image</option></select></div><div class="field"><label for="pdf-format">Output format</label><select id="pdf-format"><option value="png">PNG · crisp text</option><option value="jpg">JPG · smaller pictures</option></select></div><p class="field-help">Up to 100 selected pages. Transparent pages use a white background.</p>`;
  if (key === "organize") return `<div class="field"><label>Page selection</label><button type="button" class="secondary-button" id="load-pages">Load page previews</button><p class="field-help" id="preview-status">Add PDFs, then load their pages below. Up to 200 pages total.</p></div><p class="field-help">Choose the pages to include, move them with the arrows and rotate them in 90° steps.</p><p class="field-help">Password protected PDFs must be unlocked first. Forms and signatures may not remain interactive.</p>`;
  if (key === "spreadsheet") return `<div class="field"><label for="orientation">Page orientation</label><select id="orientation"><option value="landscape">Landscape · more room for columns</option><option value="portrait">Portrait · narrower tables</option></select></div><p class="field-help">Clean tables on A4 pages. The first data row repeats on each page. Wide sheets continue across groups of columns.</p><p class="field-help">Formula results use the values saved in Excel. If no result was saved, the formula text is shown.</p>`;
  return `<p class="field-help">Add at least two PDFs, then use the arrows beside each file to set the order.</p><p class="field-help">One PDF with all pages in order. Up to 2,500 pages total. Password protected PDFs must be unlocked first.</p>`;
}
function conversionDirection(query) {
  const conversion=query.match(/\b(png|jpe?g|webp|gif|bmp|tiff?|images?|photos?|pdf|svg|heic|avif|ico|psd|eps|xlsx?|csv|mp4|mov|mkv|webm|avi|m4v|mp3|wav|zip|rar|txt|json)\s*(?:to|→)\s*(png|jpe?g|webp|gif|bmp|tiff?|images?|photos?|pdf|svg|heic|avif|ico|psd|eps|xlsx?|csv|mp4|mov|mkv|webm|avi|m4v|mp3|wav|zip|rar|txt|json)\b/);
  if(!conversion)return null;
  const normalize=format=>format==="jpeg"?"jpg":format==="tif"?"tiff":format;
  const source=normalize(conversion[1]),output=normalize(conversion[2]);
  const raster=["png","jpg","webp","gif","bmp","tiff","image","images","photo","photos"];
  if(raster.includes(source)&&["png","jpg","webp","pdf"].includes(output))return{tool:"image",format:output};
  if(raster.includes(source)&&output==="svg")return{tool:"trace"};
  if(source==="pdf"&&["png","jpg","image","images"].includes(output))return{tool:"pdfimages",format:output==="jpg"?"jpg":"png"};
  if(["xlsx","csv"].includes(source)&&output==="pdf")return{tool:"spreadsheet"};
  if(["mp4","mov","mkv","webm","avi","m4v"].includes(source)&&output==="mp4")return{tool:"video"};
  return{tool:null};
}
function renderTools() {
  $("navigation").innerHTML = Object.entries(tools).map(([key,tool])=>`<button type="button" class="nav-button${key===current?" active":""}" data-tool="${key}" aria-pressed="${key===current}" aria-label="${tool.title}"><span class="nav-icon" aria-hidden="true">${tool.icon}</span><span class="nav-label">${tool.title}</span></button>`).join("");
  const query=$("tool-search").value.toLowerCase().trim(),words=query.split(/\s+/).filter(Boolean);
  const direction=conversionDirection(query);
  const matches = Object.entries(tools).filter(([key,tool])=>(category==="All" || tool.group===category) && (direction?key===direction.tool:words.every(word=>`${tool.title} ${tool.desc} ${tool.keywords}`.toLowerCase().includes(word))));
  $("tool-grid").innerHTML = matches.map(([key,tool])=>`<button type="button" class="tool-card palette-${key}${key===current?" active":""}" data-tool="${key}" aria-pressed="${key===current}"><span class="card-icon" aria-hidden="true">${tool.icon}</span><span class="card-arrow" aria-hidden="true">↗</span><span class="card-title">${tool.short}</span><span class="card-desc">${tool.desc}</span></button>`).join("") || '<p class="no-tools">No matching tools. Try “PDF”, “image” or “video”.</p>';
  $("search-summary").textContent = `${matches.length} ${matches.length===1?"tool":"tools"}${words.length?" matching your search":" available"}`;
  $("tool-categories").innerHTML = ["All","Images","PDFs","Video","Spreadsheets"].map(group=>`<button type="button" class="category-button${group===category?" active":""}" data-category="${group}" aria-pressed="${group===category}">${group}</button>`).join("");
  document.querySelectorAll("[data-tool]").forEach(button=>{button.disabled=uploading;button.addEventListener("click",()=>{const preset=button.classList.contains("tool-card")&&direction?.tool===button.dataset.tool&&direction.format?{format:direction.format}:undefined;selectTool(button.dataset.tool,preset);$("converter-title").scrollIntoView({block:"start"});});});
  document.querySelectorAll("[data-category]").forEach(button=>button.addEventListener("click",()=>{category=button.dataset.category;renderTools();}));
}
function selectTool(key,preset) {
  if (uploading) return;
  if ($("settings-form").children.length) settings[current]=readSettings();
  current=key;
  if(preset)settings[key]={...settings[key],...preset};
  const tool=tools[key];
  renderTools();
  for (const [id,value] of Object.entries({"breadcrumb-tool":tool.title,"converter-title":tool.short,"converter-description":tool.detail,"tool-category":tool.category,"tool-number":tool.number,"drop-title":tool.drop,"formats":tool.formats,"source-note":tool.note})) $(id).textContent=value;
  $("file-input").accept=tool.accept;
  $("file-input").multiple=tool.count>1;
  $("file-input").value="";
  $("settings-form").innerHTML=settingsHTML(key);
  if (key==="video") {
    $("height").value=String(settings[key]?.height??720);
    document.querySelectorAll("[data-size]").forEach(button=>button.addEventListener("click",()=>{$("target-mb").value=button.dataset.size;markPreset();}));
    $("target-mb").addEventListener("input",markPreset);markPreset();
  }
  if (key==="spreadsheet") $("orientation").value=settings[key]?.orientation||"landscape";
  if (key==="image") {
    $("image-format").value=settings[key]?.format||"webp";
    $("quality").addEventListener("input",()=>$("quality-value").textContent=`${$("quality").value}%`);
    $("image-format").addEventListener("change",markQuality);markQuality();
  }
  if (key==="background") $("background-fill").value=settings[key]?.fill||"transparent";
  if (key==="trace") {$("trace-detail").value=settings[key]?.detail||"balanced";$("trace-precision").addEventListener("input",()=>$("precision-value").textContent=$("trace-precision").value);}
  if (key==="pdfimages") {$("pdf-edge").value=String(settings[key]?.edge||2400);$("pdf-format").value=settings[key]?.format||"png";}
  if (key==="crop") {
    $("crop-format").value=settings[key]?.format||"png";
    ["x","y","width","height"].forEach(name=>$("crop-"+name).addEventListener("input",()=>{normalizeCrop();drawCrop();}));
    $("crop-ratio").addEventListener("change",()=>resetCrop());
  }
  if (key==="organize") $("load-pages").addEventListener("click",()=>loadPages());
  $("crop-workspace").hidden=true;
  $("organizer-workspace").hidden=key!=="organize" || !organizer.pages.length;
  if (key==="organize") renderPages();
  error(key==="video" && !videoAvailable?"Video compression needs FFmpeg and FFprobe. Install FFmpeg, then reopen FileForge.":"");
  renderFiles();
  refreshSourcePreview();
}
function markPreset() {document.querySelectorAll("[data-size]").forEach(button=>button.classList.toggle("selected",Number(button.dataset.size)===Number($("target-mb").value)));}
function markQuality() {const enabled=["jpg","webp"].includes($("image-format").value);$("quality").disabled=!enabled;$("quality-help").textContent=enabled?"Higher quality keeps more detail and creates a larger file.":"This output format uses its default quality.";}
function renderFiles() {
  $("selected-files").innerHTML=selections[current].map((file,index)=>`<div class="selected-file"><span aria-hidden="true">▤</span><div class="file-details"><span class="file-name">${safe(file.name)}</span><span class="file-size">${size(file.size)}</span></div>${current==="merge"?`<button type="button" class="small-button" data-move="${index}" data-offset="-1" aria-label="Move ${safe(file.name)} up"${index===0?" disabled":""}>↑</button><button type="button" class="small-button" data-move="${index}" data-offset="1" aria-label="Move ${safe(file.name)} down"${index===selections[current].length-1?" disabled":""}>↓</button>`:""}<button type="button" class="small-button" data-remove="${index}" aria-label="Remove ${safe(file.name)}">×</button></div>`).join("");
  document.querySelectorAll("[data-remove]").forEach(button=>{button.disabled=uploading;button.addEventListener("click",()=>{selections[current].splice(Number(button.dataset.remove),1);sourceChanged();});});
  document.querySelectorAll("[data-move]").forEach(button=>button.addEventListener("click",()=>{const index=Number(button.dataset.move),next=index+Number(button.dataset.offset);[selections[current][index],selections[current][next]]=[selections[current][next],selections[current][index]];renderFiles();}));
  $("clear-files").disabled=uploading||!selections[current].length;
  updateButton();
}
function updateButton() {
  const count=selections[current].length;
  const ready=current==="merge"?count>=2:current==="organize"?count>0 && organizer.pages.some(page=>page.selected) && !organizer.busy:current==="crop"?count===1 && !!cropImage:count>0;
  $("convert-button").disabled=uploading||!ready||(current==="video"&&!videoAvailable);
  if (!uploading) $("convert-button").innerHTML=`${tools[current].action} <span aria-hidden="true">↗</span>`;
  if ($("load-pages")) {$("load-pages").disabled=uploading||!count||organizer.busy;$("load-pages").textContent=organizer.busy?"Loading pages…":"Load page previews";}
}
function addFiles(files) {
  if (uploading) return;
  error("");
  const tool=tools[current],allowed=tool.accept.split(","),incoming=Array.from(files);
  if (!incoming.length) return;
  if (tool.count===1 && incoming.length>1) return error("Choose one file for this tool.");
  if (tool.count>1 && selections[current].length+incoming.length>tool.count) return error(`You can use up to ${tool.count} files at a time.`);
  for (const file of incoming) {
    const ext="."+file.name.split(".").pop().toLowerCase();
    if (!allowed.includes(ext)) return error(`Choose a supported file: ${allowed.join(", ")}.`);
    if (file.size>tool.max) return error(`${file.name} exceeds the ${size(tool.max)} limit.`);
    if (!file.size) return error("Empty files cannot be converted.");
  }
  if(["image","organize"].includes(current)&&[...selections[current],...incoming].reduce((total,file)=>total+file.size,0)>500000000)return error("Choose files totalling no more than 500 MB.");
  selections[current]=tool.count>1?[...selections[current],...incoming]:incoming;
  sourceChanged();
}
function sourceChanged() {if(current==="organize") clearPages();if(current==="crop") delete settings.crop;renderFiles();refreshSourcePreview();}
function releaseSource() {sourceVersion++;if(sourceURL)URL.revokeObjectURL(sourceURL);sourceURL=null;cropImage=null;$("source-image").removeAttribute("src");$("source-preview").hidden=true;$("crop-workspace").hidden=true;if(current==="crop")updateButton();}
async function refreshSourcePreview() {
  releaseSource();
  const key=current,file=selections[key][0],version=sourceVersion;
  if (!file||!tools[key]||tools[key].group!=="Images") return;
  sourceURL=URL.createObjectURL(file);
  const image=new Image();image.src=sourceURL;
  try {await image.decode();}
  catch {if(version===sourceVersion&&key==="crop")error("This image cannot be previewed. Try converting it to PNG first.");return;}
  if(version!==sourceVersion||current!==key)return;
  const pixelLimit=key==="background"?20000000:["crop","trace"].includes(key)?40000000:100000000;
  if(image.naturalWidth*image.naturalHeight>pixelLimit){error(`Choose an image below ${pixelLimit/1000000} megapixels for this tool.`);releaseSource();return;}
  cropWidth=image.naturalWidth;cropHeight=image.naturalHeight;
  if(key==="crop") {
    cropImage=image;
    const canvas=$("crop-canvas"),scale=Math.min(1,1100/Math.max(cropWidth,cropHeight));
    canvas.width=Math.round(cropWidth*scale);canvas.height=Math.round(cropHeight*scale);
    $("crop-workspace").hidden=false;
    const saved=settings.crop;
    if(saved&&saved.width>1&&saved.height>1){normalizeCrop();drawCrop();}else resetCrop();
    updateButton();
  } else {$("source-image").src=sourceURL;$("source-dimensions").textContent=`${cropWidth.toLocaleString()} × ${cropHeight.toLocaleString()} px${selections[key].length>1?" · first image in batch":""}`;$("source-preview").hidden=false;}
}
function normalizeCrop() {
  if(!cropImage||current!=="crop")return;
  const x=Math.max(0,Math.min(cropWidth-1,Math.round(Number($("crop-x").value)||0))),y=Math.max(0,Math.min(cropHeight-1,Math.round(Number($("crop-y").value)||0)));
  const width=Math.max(1,Math.min(cropWidth-x,Math.round(Number($("crop-width").value)||1))),height=Math.max(1,Math.min(cropHeight-y,Math.round(Number($("crop-height").value)||1)));
  for(const [name,value]of Object.entries({x,y,width,height})){$("crop-"+name).value=value;$("crop-"+name).max=name==="x"?cropWidth-1:name==="y"?cropHeight-1:name==="width"?cropWidth-x:cropHeight-y;}
}
function resetCrop() {
  if(!cropImage||current!=="crop")return;
  const ratio=Number($("crop-ratio").value);let width=cropWidth,height=cropHeight;
  if(ratio){width=Math.min(cropWidth,Math.floor(cropHeight*ratio));height=Math.min(cropHeight,Math.floor(width/ratio));}
  $("crop-x").value=Math.floor((cropWidth-width)/2);$("crop-y").value=Math.floor((cropHeight-height)/2);$("crop-width").value=width;$("crop-height").value=height;normalizeCrop();drawCrop();
}
function drawCrop() {
  if(!cropImage||current!=="crop")return;
  const canvas=$("crop-canvas"),ctx=canvas.getContext("2d"),sx=canvas.width/cropWidth,sy=canvas.height/cropHeight,rect=readSettings();
  ctx.clearRect(0,0,canvas.width,canvas.height);ctx.drawImage(cropImage,0,0,canvas.width,canvas.height);ctx.fillStyle="rgba(26,22,39,.52)";ctx.fillRect(0,0,canvas.width,canvas.height);
  const x=rect.x*sx,y=rect.y*sy,w=rect.width*sx,h=rect.height*sy;
  ctx.save();ctx.beginPath();ctx.rect(x,y,w,h);ctx.clip();ctx.drawImage(cropImage,0,0,canvas.width,canvas.height);ctx.restore();ctx.strokeStyle="#fff";ctx.lineWidth=2;ctx.strokeRect(x+1,y+1,Math.max(0,w-2),Math.max(0,h-2));ctx.strokeStyle="rgba(255,255,255,.5)";ctx.lineWidth=1;
  for(const fraction of [1/3,2/3]){ctx.beginPath();ctx.moveTo(x+w*fraction,y);ctx.lineTo(x+w*fraction,y+h);ctx.moveTo(x,y+h*fraction);ctx.lineTo(x+w,y+h*fraction);ctx.stroke();}
  $("crop-status").textContent=`Keeping ${rect.width.toLocaleString()} × ${rect.height.toLocaleString()} pixels from an original ${cropWidth.toLocaleString()} × ${cropHeight.toLocaleString()} image.`;
}
function cropPoint(event){const rect=$("crop-canvas").getBoundingClientRect();return{x:Math.max(0,Math.min(cropWidth-1,Math.round((event.clientX-rect.left)/rect.width*cropWidth))),y:Math.max(0,Math.min(cropHeight-1,Math.round((event.clientY-rect.top)/rect.height*cropHeight)))};}
$("crop-canvas").addEventListener("pointerdown",event=>{if(uploading||!cropImage)return;event.preventDefault();cropDrag=cropPoint(event);$("crop-canvas").setPointerCapture(event.pointerId);});
$("crop-canvas").addEventListener("pointermove",event=>{
  if(!cropDrag)return;const point=cropPoint(event);let dx=point.x-cropDrag.x,dy=point.y-cropDrag.y;const ratio=Number($("crop-ratio").value);
  if(ratio){const width=Math.min(Math.abs(dx),Math.abs(dy)*ratio);dx=Math.sign(dx||1)*width;dy=Math.sign(dy||1)*width/ratio;}
  $("crop-x").value=Math.round(Math.min(cropDrag.x,cropDrag.x+dx));$("crop-y").value=Math.round(Math.min(cropDrag.y,cropDrag.y+dy));$("crop-width").value=Math.max(1,Math.round(Math.abs(dx)));$("crop-height").value=Math.max(1,Math.round(Math.abs(dy)));normalizeCrop();drawCrop();
});
for(const type of ["pointerup","pointercancel"])$("crop-canvas").addEventListener(type,()=>cropDrag=null);
$("reset-crop").addEventListener("click",resetCrop);
function clearPages() {
  organizer.version++;for(const page of organizer.pages)if(page.url)URL.revokeObjectURL(page.url);
  organizer.pages=[];organizer.original=[];organizer.busy=false;
  if(organizer.jobId)api(`/api/jobs/${organizer.jobId}/cancel`,{method:"POST"}).catch(()=>{});
  organizer.jobId=null;$("page-grid").replaceChildren();$("organizer-workspace").hidden=true;
  if($("preview-status"))$("preview-status").textContent="Add PDFs, then load their pages below. Up to 200 pages total.";
}
function thumbnailURL(data) {const base64=data.split(",")[1];if(!base64)throw new Error("A page preview could not be read.");const bytes=Uint8Array.from(atob(base64),char=>char.charCodeAt(0));return URL.createObjectURL(new Blob([bytes],{type:"image/png"}));}
async function disposePreview(id) {
  try {let job=await api(`/api/jobs/${id}`);if(!terminal(job.status)){await api(`/api/jobs/${id}/cancel`,{method:"POST"});for(let i=0;i<100&&!terminal(job.status);i++){await pause(200);job=await api(`/api/jobs/${id}`);}}if(terminal(job.status))await api(`/api/jobs/${id}`,{method:"DELETE"});}catch{}
}
async function loadPages() {
  if(uploading||organizer.busy||!selections.organize.length)return;
  clearPages();const version=organizer.version;organizer.busy=true;updateButton();error("");
  let id;
  try {
    const body=new FormData();body.append("tool","pdfpreview");body.append("options","{}");selections.organize.forEach(file=>body.append("files",file));
    let job=await api("/api/jobs",{method:"POST",body});id=job.id;
    if(version===organizer.version)organizer.jobId=id;
    while(!terminal(job.status)){if(version!==organizer.version)return;if($("preview-status"))$("preview-status").textContent=`${job.stage} · ${job.progress}%`;await pause(400);job=await api(`/api/jobs/${id}`);}
    if(version!==organizer.version)return;
    if(job.status!=="completed")throw new Error(job.error||"Page preview was cancelled.");
    const data=await api(job.download_url);
    if(!Array.isArray(data.pages)||!data.pages.length)throw new Error("This document has no pages to organize.");
    organizer.pages=data.pages.map((page,index)=>({...page,id:index,url:thumbnailURL(page.thumbnail),rotation:0,selected:true}));
    organizer.original=organizer.pages.map(page=>({...page}));
    renderPages();
    if($("preview-status"))$("preview-status").textContent=`${organizer.pages.length} pages loaded. Arrange them below.`;
  } catch(failure) {if(version===organizer.version)error(failure.message);}
  finally {if(id)await disposePreview(id);if(version===organizer.version){organizer.busy=false;organizer.jobId=null;updateButton();}refreshJobs().catch(()=>{});}
}
function renderPages(focusId,action) {
  $("organizer-workspace").hidden=current!=="organize"||!organizer.pages.length;
  $("page-status").textContent=`${organizer.pages.filter(page=>page.selected).length} of ${organizer.pages.length} pages selected`;
  $("page-grid").innerHTML=organizer.pages.map((page,index)=>`<article class="page-card${page.selected?"":" excluded"}" data-page-id="${page.id}"><div class="page-thumbnail"><img src="${safe(page.url)}" alt="Page ${page.page_index+1} of ${safe(page.name)}" draggable="false"></div><label class="checkbox-label"><input type="checkbox" data-page-select="${page.id}"${page.selected?" checked":""}> Include page ${page.page_index+1}</label><p class="page-filename" title="${safe(page.name)}">${safe(page.name)}</p><div class="page-actions"><button type="button" class="small-button" data-page-move="${page.id}" data-offset="-1" aria-label="Move page ${page.page_index+1} earlier"${index===0?" disabled":""}>←</button><button type="button" class="small-button" data-page-move="${page.id}" data-offset="1" aria-label="Move page ${page.page_index+1} later"${index===organizer.pages.length-1?" disabled":""}>→</button><button type="button" class="small-button rotate-button" data-page-rotate="${page.id}" aria-label="Rotate page ${page.page_index+1} clockwise">↻ <span>${page.rotation}°</span></button></div></article>`).join("");
  document.querySelectorAll("[data-page-id]").forEach(card=>{const page=organizer.pages.find(item=>item.id===Number(card.dataset.pageId));card.querySelector("img").style.transform=`rotate(${page.rotation}deg)`;});
  document.querySelectorAll("[data-page-select]").forEach(input=>input.addEventListener("change",()=>{organizer.pages.find(page=>page.id===Number(input.dataset.pageSelect)).selected=input.checked;renderPages(input.dataset.pageSelect,"select");updateButton();}));
  document.querySelectorAll("[data-page-move]").forEach(button=>button.addEventListener("click",()=>{const index=organizer.pages.findIndex(page=>page.id===Number(button.dataset.pageMove)),next=index+Number(button.dataset.offset);[organizer.pages[index],organizer.pages[next]]=[organizer.pages[next],organizer.pages[index]];renderPages(button.dataset.pageMove,`move${button.dataset.offset}`);}));
  document.querySelectorAll("[data-page-rotate]").forEach(button=>button.addEventListener("click",()=>{const page=organizer.pages.find(item=>item.id===Number(button.dataset.pageRotate));page.rotation=(page.rotation+90)%360;renderPages(button.dataset.pageRotate,"rotate");}));
  if(focusId!==undefined){const card=document.querySelector(`[data-page-id="${focusId}"]`);const selector=action==="select"?"[data-page-select]":action==="rotate"?"[data-page-rotate]":`[data-page-move][data-offset="${action.replace("move","")}"]`;card?.querySelector(selector)?.focus();}
}
$("reset-pages").addEventListener("click",()=>{organizer.pages=organizer.original.map(page=>({...page}));renderPages();updateButton();});
$("clear-files").addEventListener("click",()=>{if(uploading)return;selections[current]=[];sourceChanged();error("");});
$("tool-search").addEventListener("input",renderTools);
$("dropzone").addEventListener("click",()=>{if(!uploading)$("file-input").click();});
$("dropzone").addEventListener("keydown",event=>{if(["Enter"," "].includes(event.key)){event.preventDefault();if(!uploading)$("file-input").click();}});
$("file-input").addEventListener("change",event=>{addFiles(event.target.files);event.target.value="";});
for(const type of ["dragenter","dragover"])$("dropzone").addEventListener(type,event=>{event.preventDefault();$("dropzone").classList.add("dragover");});
for(const type of ["dragleave","drop"])$("dropzone").addEventListener(type,event=>{event.preventDefault();$("dropzone").classList.remove("dragover");});
$("dropzone").addEventListener("drop",event=>addFiles(event.dataTransfer.files));
document.addEventListener("dragover",event=>event.preventDefault());document.addEventListener("drop",event=>event.preventDefault());
$("settings-form").addEventListener("submit",event=>event.preventDefault());
async function api(url,options) {const response=await fetch(url,options);let data;try{data=await response.json();}catch{throw new Error("The app returned an unreadable response. Reopen FileForge and try again.");}if(!response.ok)throw new Error(typeof data.detail==="string"?data.detail:"The request could not be completed.");return data;}
$("convert-button").addEventListener("click",async()=>{
  if($("convert-button").disabled||!$("settings-form").reportValidity())return;
  error("");settings[current]=readSettings();const key=current,body=new FormData();body.append("tool",key);body.append("options",JSON.stringify(settings[key]));selections[key].forEach(file=>body.append("files",file));
  uploading=true;updateButton();renderTools();$("clear-files").disabled=true;
  document.querySelectorAll("#selected-files button, #settings-form input, #settings-form select, #settings-form button, #page-grid input, #page-grid button, #reset-pages, #reset-crop").forEach(element=>element.disabled=true);$("convert-button").textContent="Preparing files…";
  try {
    await new Promise((resolve,reject)=>{const request=new XMLHttpRequest();request.open("POST","/api/jobs");request.upload.addEventListener("progress",event=>{if(event.lengthComputable)$("convert-button").textContent=`Sending to local worker ${Math.round(event.loaded/event.total*100)}%`;});request.addEventListener("load",()=>{try{const data=JSON.parse(request.responseText);if(request.status>=200&&request.status<300)resolve(data);else reject(new Error(typeof data.detail==="string"?data.detail:"Could not start the conversion."));}catch{reject(new Error("Could not start the conversion."));}});request.addEventListener("error",()=>reject(new Error("The app lost its connection. Reopen it and try again.")));request.send(body);});
    selections[key]=[];if(key==="organize")clearPages();if(key==="crop")delete settings.crop;releaseSource();await refreshJobs();
  } catch(failure){error(failure.message);}
  finally{uploading=false;$("reset-pages").disabled=false;$("reset-crop").disabled=false;const message=$("error-banner").textContent;selectTool(current);if(message)error(message);}
});
function renderJobs() {
  const visible=lastJobs.filter(job=>job.tool!=="pdfpreview");$("job-count").textContent=visible.length;$("clear-history").disabled=!visible.some(job=>terminal(job.status));
  if(!visible.length){$("jobs").innerHTML='<div class="empty-state"><span class="empty-icon" aria-hidden="true">↳</span><div><strong>A fresh workspace</strong><p>Your results will appear here when you start.</p></div></div>';return;}
  $("jobs").innerHTML=visible.map(job=>{
    const tool=tools[job.tool]||{short:job.tool,icon:"▤"},active=!terminal(job.status),reduction=job.output_size&&job.output_size<job.input_size?` · ${Math.round((1-job.output_size/job.input_size)*100)}% smaller`:"",meta=job.output_size?`${size(job.input_size)} → ${size(job.output_size)}${reduction}`:`${size(job.input_size)} · ${tool.short}`,canPreview=job.status==="completed"&&/\.(png|jpe?g|webp|svg)$/i.test(job.output_name||""),showPreview=canPreview&&previewedJobs.has(job.id);
    return `<div class="job-row ${safe(job.status)} palette-${safe(job.tool)}" data-job-id="${safe(job.id)}"><div class="job-icon" aria-hidden="true">${tool.icon}</div><div class="job-content"><div class="job-topline"><span class="job-name">${safe(job.filenames.join(", "))}</span><span class="job-state">${safe(job.stage)}</span></div><div class="job-meta">${safe(meta)}</div>${active?`<progress value="${job.progress}" max="100" aria-label="${safe(job.stage)}"></progress>`:""}${job.error?`<div class="job-warning job-error">${safe(job.error)}</div>`:""}${(job.warnings||[]).map(message=>`<div class="job-warning">${safe(message)}</div>`).join("")}${showPreview?`<div class="result-preview"><img src="/api/jobs/${safe(job.id)}/preview" alt="Converted result: ${safe(job.output_name)}"></div>`:""}</div><div class="job-actions">${canPreview?`<button type="button" class="text-button" data-preview="${safe(job.id)}" aria-expanded="${showPreview}">${showPreview?"Hide preview":"Preview"}</button>`:""}${job.download_url?`<a class="download-button" href="${safe(job.download_url)}" download>Download ↓</a>`:""}${active?`<button class="text-button" data-cancel="${safe(job.id)}">Cancel</button>`:`<button class="small-button" data-delete="${safe(job.id)}" aria-label="Remove conversion">×</button>`}</div></div>`;
  }).join("");
  document.querySelectorAll("[data-preview]").forEach(button=>button.addEventListener("click",()=>{const id=button.dataset.preview;if(previewedJobs.has(id))previewedJobs.delete(id);else previewedJobs.add(id);renderJobs();}));
  document.querySelectorAll("[data-cancel]").forEach(button=>button.addEventListener("click",async()=>{button.disabled=true;try{await api(`/api/jobs/${button.dataset.cancel}/cancel`,{method:"POST"});await refreshJobs();}catch(failure){error(failure.message);button.disabled=false;}}));
  document.querySelectorAll("[data-delete]").forEach(button=>button.addEventListener("click",async()=>{try{await api(`/api/jobs/${button.dataset.delete}`,{method:"DELETE"});previewedJobs.delete(button.dataset.delete);await refreshJobs();}catch(failure){error(failure.message);}}));
}
async function refreshJobs(){if(polling)return;polling=true;try{lastJobs=(await api("/api/jobs")).filter(job=>job.tool!=="pdfpreview");const snapshot=JSON.stringify(lastJobs);if(snapshot!==lastJobSnapshot){lastJobSnapshot=snapshot;renderJobs();}}finally{polling=false;}}
$("clear-history").addEventListener("click",async()=>{$("clear-history").disabled=true;try{for(const job of lastJobs.filter(job=>job.tool!=="pdfpreview"&&terminal(job.status)))await api(`/api/jobs/${job.id}`,{method:"DELETE"});previewedJobs.clear();await refreshJobs();}catch(failure){error(failure.message);}});
window.addEventListener("pagehide",()=>{releaseSource();for(const page of organizer.pages)if(page.url)URL.revokeObjectURL(page.url);});
selectTool("image");
(async()=>{try{const health=await api("/api/health");videoAvailable=health.video_available;if(current==="video"){error(videoAvailable?"":"Video compression needs FFmpeg and FFprobe. Install FFmpeg, then reopen FileForge.");updateButton();}await refreshJobs();}catch{error("The conversion service could not be reached. Reopen FileForge to reconnect.");}})();
setInterval(()=>refreshJobs().catch(()=>error("The conversion service could not be reached. Reopen FileForge to reconnect.")),2000);
