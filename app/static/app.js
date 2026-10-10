"use strict";
const tools = {
  video: {title: "Video compression", short: "Compress video", desc: "Set your target file size", category: "VIDEO / MP4", detail: "A smaller MP4, ready for sharing.", icon: "▷", number: "01", accept: ".mp4,.mov,.mkv,.webm,.avi,.m4v", drop: "Drop your video here", formats: "MP4, MOV, MKV, WEBM, AVI, M4V · up to 2 GB", action: "Compress video", note: "The original file stays unchanged."},
  spreadsheet: {title: "Excel to PDF", short: "Excel to PDF", desc: "Tables made shareable", category: "SPREADSHEET / PDF", detail: "Turn visible worksheet data into a readable PDF.", icon: "▦", number: "02", accept: ".xlsx,.csv", drop: "Drop your spreadsheet here", formats: "XLSX, CSV · up to 50 MB", action: "Create PDF", note: "Visible sheets are exported. Charts and Excel print layout are not retained."},
  image: {title: "Image conversion", short: "Convert images", desc: "A new format or a smaller image", category: "IMAGE / CONVERT", detail: "Change format, resize, and adjust image quality.", icon: "▧", number: "03", accept: ".png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff,.gif", drop: "Drop your image here", formats: "PNG, JPG, WEBP, BMP, TIFF, GIF · up to 100 MB", action: "Convert image", note: "Animated images export the first frame. JPG and PDF use a white background."},
  merge: {title: "Merge PDFs", short: "Merge PDFs", desc: "Bring your documents together", category: "DOCUMENT / PDF", detail: "Combine documents in the order you choose.", icon: "▤", number: "04", accept: ".pdf", drop: "Drop your PDFs here", formats: "2–20 PDF files · up to 250 MB each", action: "Merge PDFs", note: "Files are merged in the order below. Use the arrows to rearrange them."}
};
const $ = (id) => document.getElementById(id);
const selections = Object.fromEntries(Object.keys(tools).map(key => [key, []]));
const settings = {};
let current = "video", videoAvailable = false, uploading = false, lastJobs = [], polling = false;
function safe(value) { return String(value).replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char])); }
function size(bytes) { return bytes < 1000000 ? `${(bytes / 1000).toFixed(1)} KB` : `${(bytes / 1000000).toFixed(2)} MB`; }
function error(message) { $("error-banner").textContent = message || ""; $("error-banner").hidden = !message; }
function readSettings() {
  if (current === "video") return {target_mb: Number($("target-mb").value), height: Number($("height").value), remove_audio: $("remove-audio").checked};
  if (current === "image") return {format: $("image-format").value, quality: Number($("quality").value), width: Number($("image-width").value)};
  if (current === "spreadsheet") return {orientation: $("orientation").value};
  return {};
}
function settingsHTML(key) {
  const value = settings[key] || {};
  if (key === "video") return `<div class="field"><label for="target-mb">Target file size</label><div class="input-unit"><input id="target-mb" type="number" min="0.1" max="10000" step="0.1" value="${value.target_mb || 25}" required><span>MB</span></div><div class="preset-row">${[10,25,50,100].map(n => `<button class="preset" type="button" data-size="${n}">${n} MB</button>`).join("")}</div><p class="field-help">The finished file is checked against your target.<br>A smaller size can reduce picture quality.</p></div><div class="field"><label for="height">Maximum resolution</label><select id="height"><option value="720">720p · good for sharing</option><option value="1080">1080p · more detail</option><option value="480">480p · smaller video</option><option value="0">Keep original resolution</option></select></div><label class="checkbox-label"><input id="remove-audio" type="checkbox"${value.remove_audio ? " checked" : ""}> Remove audio to save space</label>`;
  if (key === "spreadsheet") return `<div class="field"><label for="orientation">Page orientation</label><select id="orientation"><option value="landscape">Landscape · more room for columns</option><option value="portrait">Portrait · narrower tables</option></select></div><div class="field"><label>Export style</label><p class="field-help">Clean tables on A4 pages. The first data row repeats on each page. Wide sheets continue across groups of columns.</p><p class="field-help">Formula results use the values saved in Excel. If no result was saved, the formula text is shown.</p></div>`;
  if (key === "image") return `<div class="field"><label for="image-format">Output format</label><select id="image-format"><option value="webp">WEBP · smaller web images</option><option value="jpg">JPG · photos</option><option value="png">PNG · keep transparency</option><option value="pdf">PDF · image document</option></select></div><div class="field"><label for="quality">Quality <span id="quality-value">${value.quality || 85}%</span></label><input id="quality" type="range" min="1" max="100" value="${value.quality || 85}"><p class="field-help" id="quality-help">Used for JPG and WEBP output.</p></div><div class="field"><label for="image-width">Maximum width</label><div class="input-unit"><input id="image-width" type="number" min="0" max="12000" step="1" value="${value.width || 0}"><span>px</span></div><p class="field-help">0 keeps the original size. Aspect ratio is preserved.</p></div>`;
  return `<div class="field"><label>Document order</label><p class="field-help">Add at least two PDFs, then use the arrows beside each file to set the order.</p></div><div class="field"><label>Output</label><p class="field-help">One PDF with all pages in order.<br>Up to 2,500 pages total. Password protected PDFs must be unlocked first.</p></div>`;
}
function renderTools() {
  $("navigation").innerHTML = Object.entries(tools).map(([key, tool]) => `<button type="button" class="nav-button${key === current ? " active" : ""}" data-tool="${key}" aria-pressed="${key === current}" aria-label="${tool.title}"><span class="nav-icon" aria-hidden="true">${tool.icon}</span><span class="nav-label">${tool.title}</span>${key === current ? '<span class="nav-arrow" aria-hidden="true">↗</span>' : ""}</button>`).join("");
  $("tool-grid").innerHTML = Object.entries(tools).map(([key, tool]) => `<button type="button" class="tool-card palette-${key}${key === current ? " active" : ""}" data-tool="${key}" aria-pressed="${key === current}"><span class="card-icon" aria-hidden="true">${tool.icon}</span><span class="card-arrow" aria-hidden="true">↗</span><span class="card-title">${tool.short}</span><span class="card-desc">${tool.desc}</span></button>`).join("");
  document.querySelectorAll("[data-tool]").forEach(button => {
    button.disabled = uploading;
    button.addEventListener("click", () => selectTool(button.dataset.tool));
  });
}
function selectTool(key) {
  if (uploading) return;
  if ($("settings-form").children.length) settings[current] = readSettings();
  current = key;
  const tool = tools[key];
  renderTools();
  $("breadcrumb-tool").textContent = tool.title;
  $("converter-title").textContent = tool.short;
  $("converter-description").textContent = tool.detail;
  $("tool-category").textContent = tool.category;
  $("tool-number").textContent = tool.number;
  $("drop-title").textContent = tool.drop;
  $("formats").textContent = tool.formats;
  $("source-note").textContent = tool.note;
  $("file-input").accept = tool.accept;
  $("file-input").multiple = key === "merge";
  $("file-input").value = "";
  $("settings-form").innerHTML = settingsHTML(key);
  if (key === "video") {
    $("height").value = String(settings[key]?.height ?? 720);
    document.querySelectorAll("[data-size]").forEach(button => button.addEventListener("click", () => {
      $("target-mb").value = button.dataset.size;
      markPreset();
    }));
    $("target-mb").addEventListener("input", markPreset);
    markPreset();
  }
  if (key === "spreadsheet") $("orientation").value = settings[key]?.orientation || "landscape";
  if (key === "image") {
    $("image-format").value = settings[key]?.format || "webp";
    $("quality").addEventListener("input", () => $("quality-value").textContent = `${$("quality").value}%`);
    $("image-format").addEventListener("change", markQuality);
    markQuality();
  }
  error(key === "video" && !videoAvailable ? "Video compression needs FFmpeg and FFprobe. Install FFmpeg, then reopen FileForge." : "");
  renderFiles();
}
function markPreset() { document.querySelectorAll("[data-size]").forEach(button => button.classList.toggle("selected", Number(button.dataset.size) === Number($("target-mb").value))); }
function markQuality() {
  const enabled = ["jpg","webp"].includes($("image-format").value);
  $("quality").disabled = !enabled;
  $("quality-help").textContent = enabled ? "Higher quality keeps more detail and creates a larger file." : "This output format uses its default quality.";
}
function renderFiles() {
  $("selected-files").innerHTML = selections[current].map((file,index) => `<div class="selected-file"><span aria-hidden="true">▤</span><div class="file-details"><span class="file-name">${safe(file.name)}</span><span class="file-size">${size(file.size)}</span></div>${current === "merge" ? `<button type="button" class="small-button" data-move="${index}" data-offset="-1" aria-label="Move ${safe(file.name)} up"${index === 0 ? " disabled" : ""}>↑</button><button type="button" class="small-button" data-move="${index}" data-offset="1" aria-label="Move ${safe(file.name)} down"${index === selections[current].length - 1 ? " disabled" : ""}>↓</button>` : ""}<button type="button" class="small-button" data-remove="${index}" aria-label="Remove ${safe(file.name)}">×</button></div>`).join("");
  document.querySelectorAll("[data-remove]").forEach(button => button.addEventListener("click", () => { selections[current].splice(Number(button.dataset.remove),1); renderFiles(); }));
  document.querySelectorAll("[data-move]").forEach(button => button.addEventListener("click", () => {
    const index = Number(button.dataset.move), next = index + Number(button.dataset.offset);
    [selections[current][index],selections[current][next]] = [selections[current][next],selections[current][index]];
    renderFiles();
  }));
  updateButton();
}
function updateButton() {
  const count = selections[current].length;
  $("convert-button").disabled = uploading || (current === "video" && !videoAvailable) || (current === "merge" ? count < 2 : count !== 1);
  if (!uploading) $("convert-button").innerHTML = `${tools[current].action} <span aria-hidden="true">↗</span>`;
}
function addFiles(files) {
  if (uploading) return;
  error("");
  const allowed = tools[current].accept.split(",");
  const max = {video:2000000000,spreadsheet:50000000,image:100000000,merge:250000000}[current];
  const incoming = Array.from(files);
  if (current !== "merge" && incoming.length > 1) return error("Choose one file for this tool.");
  if (current === "merge" && selections[current].length + incoming.length > 20) return error("You can merge up to 20 PDFs at a time.");
  for (const file of incoming) {
    const ext = "." + file.name.split(".").pop().toLowerCase();
    if (!allowed.includes(ext)) return error(`Choose a supported file: ${allowed.join(", ")}.`);
    if (file.size > max) return error(`${file.name} exceeds the ${size(max)} limit.`);
    if (!file.size) return error("Empty files cannot be converted.");
  }
  selections[current] = current === "merge" ? [...selections[current],...incoming] : incoming;
  renderFiles();
}
$("dropzone").addEventListener("click", () => { if (!uploading) $("file-input").click(); });
$("dropzone").addEventListener("keydown", event => { if (["Enter"," "].includes(event.key)) { event.preventDefault(); if (!uploading) $("file-input").click(); } });
$("file-input").addEventListener("change", event => { addFiles(event.target.files); event.target.value = ""; });
["dragenter","dragover"].forEach(type => $("dropzone").addEventListener(type, event => { event.preventDefault(); $("dropzone").classList.add("dragover"); }));
["dragleave","drop"].forEach(type => $("dropzone").addEventListener(type, event => { event.preventDefault(); $("dropzone").classList.remove("dragover"); }));
$("dropzone").addEventListener("drop", event => addFiles(event.dataTransfer.files));
document.addEventListener("dragover", event => event.preventDefault());
document.addEventListener("drop", event => event.preventDefault());
$("settings-form").addEventListener("submit", event => event.preventDefault());
async function api(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "The request could not be completed.");
  return data;
}
$("convert-button").addEventListener("click", async () => {
  if (!$("settings-form").reportValidity()) return;
  error("");
  settings[current] = readSettings();
  const body = new FormData();
  body.append("tool",current);
  body.append("options",JSON.stringify(settings[current]));
  selections[current].forEach(file => body.append("files",file));
  uploading = true;
  updateButton();
  renderTools();
  document.querySelectorAll("#selected-files button, #settings-form input, #settings-form select, #settings-form button").forEach(element => element.disabled = true);
  $("convert-button").textContent = "Uploading…";
  try {
    await new Promise((resolve,reject) => {
      const request = new XMLHttpRequest();
      request.open("POST","/api/jobs");
      request.upload.addEventListener("progress", event => {
        if (event.lengthComputable) $("convert-button").textContent = `Uploading ${Math.round(event.loaded / event.total * 100)}%`;
      });
      request.addEventListener("load", () => {
        try {
          const data = JSON.parse(request.responseText);
          if (request.status >= 200 && request.status < 300) resolve(data);
          else reject(new Error(typeof data.detail === "string" ? data.detail : "Could not start the conversion."));
        } catch { reject(new Error("Could not start the conversion.")); }
      });
      request.addEventListener("error", () => reject(new Error("The app lost its connection. Reopen it and try again.")));
      request.send(body);
    });
    selections[current] = [];
    await refreshJobs();
  } catch (failure) { error(failure.message); }
  finally {
    uploading = false;
    const message = $("error-banner").textContent;
    selectTool(current);
    if (message) error(message);
  }
});
function renderJobs() {
  $("job-count").textContent = lastJobs.length;
  $("clear-history").disabled = !lastJobs.some(job => ["completed","failed","cancelled"].includes(job.status));
  if (!lastJobs.length) {
    $("jobs").innerHTML = '<div class="empty-state"><span class="empty-icon" aria-hidden="true">↳</span><div><strong>A fresh workspace</strong><p>Your conversions will appear here when you start.</p></div></div>';
    return;
  }
  $("jobs").innerHTML = lastJobs.map(job => {
    const tool = tools[job.tool], active = !["completed","failed","cancelled"].includes(job.status);
    const reduction = job.output_size && job.output_size < job.input_size ? ` · ${Math.round((1 - job.output_size / job.input_size) * 100)}% smaller` : "";
    const meta = job.output_size ? `${size(job.input_size)} → ${size(job.output_size)}${reduction}` : `${size(job.input_size)} · ${tool.short}`;
    return `<div class="job-row ${safe(job.status)} palette-${job.tool}"><div class="job-icon" aria-hidden="true">${tool.icon}</div><div class="job-content"><div class="job-topline"><span class="job-name">${safe(job.filenames.join(", "))}</span><span class="job-state">${safe(job.stage)}</span></div><div class="job-meta">${safe(meta)}</div>${active ? `<progress value="${job.progress}" max="100" aria-label="${safe(job.stage)}"></progress>` : ""}${job.error ? `<div class="job-warning job-error">${safe(job.error)}</div>` : ""}${job.warnings.map(message => `<div class="job-warning">${safe(message)}</div>`).join("")}</div><div class="job-actions">${job.download_url ? `<a class="download-button" href="${job.download_url}" download>Download ↓</a>` : ""}${active ? `<button class="text-button" data-cancel="${job.id}">Cancel</button>` : `<button class="small-button" data-delete="${job.id}" aria-label="Remove conversion">×</button>`}</div></div>`;
  }).join("");
  document.querySelectorAll("[data-cancel]").forEach(button => button.addEventListener("click", async () => {
    button.disabled = true;
    try { await api(`/api/jobs/${button.dataset.cancel}/cancel`,{method:"POST"}); await refreshJobs(); }
    catch (failure) { error(failure.message); button.disabled = false; }
  }));
  document.querySelectorAll("[data-delete]").forEach(button => button.addEventListener("click", async () => {
    try { await api(`/api/jobs/${button.dataset.delete}`,{method:"DELETE"}); await refreshJobs(); }
    catch (failure) { error(failure.message); }
  }));
}
async function refreshJobs() {
  if (polling) return;
  polling = true;
  try { lastJobs = await api("/api/jobs"); renderJobs(); }
  finally { polling = false; }
}
$("clear-history").addEventListener("click", async () => {
  $("clear-history").disabled = true;
  try {
    for (const job of lastJobs.filter(job => ["completed","failed","cancelled"].includes(job.status))) await api(`/api/jobs/${job.id}`,{method:"DELETE"});
    await refreshJobs();
  } catch (failure) { error(failure.message); }
});
selectTool("video");
(async () => {
  try {
    const health = await api("/api/health");
    videoAvailable = health.video_available;
    if (current === "video") {
      error(videoAvailable ? "" : "Video compression needs FFmpeg and FFprobe. Install FFmpeg, then reopen FileForge.");
      updateButton();
    }
    await refreshJobs();
  } catch { error("The conversion service could not be reached. Reopen FileForge to reconnect."); }
})();
setInterval(() => refreshJobs().catch(() => error("The conversion service could not be reached. Reopen FileForge to reconnect.")),2000);
