"use strict";

// ================================================================ utilidades
const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const S = {
  estado: null,
  project: null,
  file: null,
  original: null, // HTMLImageElement
  cutout: null, // HTMLImageElement
  chara: null,
  refs: {},
  stamp: Date.now(),
};

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  const type = res.headers.get("content-type") || "";
  if (!type.includes("json")) {
    if (!res.ok) throw new Error(`Error ${res.status}`);
    return res;
  }
  const data = await res.json();
  if (!res.ok || data.ok === false) throw new Error(data.error || `Error ${res.status}`);
  return data;
}
const post = (path, body) => api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

function busy(text) {
  $("#busyText").textContent = text || "Trabajando…";
  $("#busy").hidden = !text;
}
let toastTimer;
function toast(text, err = false) {
  const t = $("#toast");
  t.textContent = text;
  t.className = "toast" + (err ? " err" : "");
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), err ? 6000 : 2800);
}
async function guard(text, fn) {
  busy(text);
  try {
    return await fn();
  } catch (e) {
    console.error(e);
    toast(e.message, true);
  } finally {
    busy(null);
  }
}
function loadImage(src) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("No se pudo cargar " + src));
    img.src = src;
  });
}
const pid = () => S.project.id;
const url = (p) => `/api/proyectos/${pid()}${p}${p.includes("?") ? "&" : "?"}t=${S.stamp}`;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

function checkerPattern(ctx, size = 12, a = "#2a2a33", b = "#1f1f27") {
  const c = document.createElement("canvas");
  c.width = c.height = size * 2;
  const x = c.getContext("2d");
  x.fillStyle = a;
  x.fillRect(0, 0, size * 2, size * 2);
  x.fillStyle = b;
  x.fillRect(0, 0, size, size);
  x.fillRect(size, size, size, size);
  return ctx.createPattern(c, "repeat");
}

// ================================================================ vistas
function show(view) {
  $$(".tabs button").forEach((b) => b.classList.toggle("on", b.dataset.view === view));
  $$(".view").forEach((v) => v.classList.toggle("on", v.id === "view-" + view));
  S.view = view;
  if (view === "recorte") mask.fit();
  if (view === "charas") charas.open(S.chara || S.project.charas[0]);
  if (view === "ajustes") settings.render();
}
$$(".tabs button").forEach((b) => b.addEventListener("click", () => !b.disabled && show(b.dataset.view)));

// ================================================================ 1. imagen
async function loadEstado() {
  const { data } = await api("/api/estado");
  S.estado = data;
  $("#fighterList").innerHTML = data.luchadores.map((f) => `<option value="${f}">`).join("");
  const models = Object.entries(data.modelos).map(([k, v]) => `<option value="${k}">${v}</option>`).join("");
  $("#bgModel").innerHTML = models;
  $("#redoModel").innerHTML = models;
  $("#bgModel").value = data.modelo_defecto;
  $("#redoModel").value = (S.project && S.project.modelo) || data.modelo_defecto;
  const charasCfg = data.presets.charas;
  $("#charaChecks").innerHTML = Object.entries(charasCfg)
    .map(
      ([c, p]) => `<label class="chip" title="${p.uso}"><input type="checkbox" value="${c}" checked>
        chara_${c} · ${p.nombre} <small>${p.width}×${p.height}</small>
        <span class="badge ${p.verificado ? "ok" : "est"}">${p.verificado ? "verificado" : "estimado"}</span></label>`
    )
    .join("");
  const list = $("#projectList");
  if (data.proyectos.length) {
    list.innerHTML = data.proyectos
      .map((p) => `<div class="pitem" data-id="${p.id}"><div><b>${p.fighter}</b> · slot ${String(p.slot).padStart(2, "0")}<br><small>${p.id} · ${p.creado}</small></div><span>Abrir →</span></div>`)
      .join("");
    $$(".pitem").forEach((el) => el.addEventListener("click", () => guard("Abriendo…", () => openProject(el.dataset.id))));
  }
  if (!data.charatex) toast("No encuentro bin/charatex.exe: no se podrán crear BNTX.", true);
}

function setFile(file) {
  if (!file) return;
  S.file = file;
  const img = $("#dropPreview");
  img.src = URL.createObjectURL(file);
  img.hidden = false;
  $("#dropText").hidden = true;
  if (!$("#fighter").value) {
    const guess = file.name.replace(/\.[^.]+$/, "").toLowerCase().replace(/[^a-z0-9_]+/g, "_").replace(/^_|_$/g, "");
    $("#fighter").value = guess;
  }
}
const drop = $("#drop");
drop.addEventListener("click", () => $("#fileInput").click());
$("#fileInput").addEventListener("change", (e) => setFile(e.target.files[0]));
["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => (e.preventDefault(), drop.classList.add("hover"))));
["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => (e.preventDefault(), drop.classList.remove("hover"))));
drop.addEventListener("drop", (e) => setFile(e.dataTransfer.files[0]));

$("#createBtn").addEventListener("click", () => {
  if (!S.file) return toast("Primero elige la imagen del personaje.", true);
  const fighter = $("#fighter").value.trim().toLowerCase();
  if (!/^[a-z0-9_]+$/.test(fighter)) return toast("El nombre interno solo puede tener a-z, 0-9 y _.", true);
  const fd = new FormData();
  fd.append("imagen", S.file);
  fd.append("fighter", fighter);
  fd.append("slot", $("#slot").value || 0);
  fd.append("charas", $$("#charaChecks input:checked").map((i) => i.value).join(","));
  fd.append("fondo", $("#bgMode").value);
  fd.append("modelo", $("#bgModel").value);
  guard("Quitando el fondo y encuadrando… (la primera vez descarga el modelo, puede tardar)", async () => {
    const { data } = await api("/api/proyectos", { method: "POST", body: fd });
    await openProject(data);
    toast(`Proyecto creado · fondo: ${data.fondo}`);
    loadEstado();
  });
});

async function openProject(idOrData) {
  const data = typeof idOrData === "string" ? (await api(`/api/proyectos/${idOrData}`)).data : idOrData;
  S.project = data;
  S.stamp = Date.now();
  S.chara = data.charas[0];
  $("#projectPill").hidden = false;
  $("#projectPill").innerHTML = `<b>${data.fighter}</b> · slot ${String(data.slot).padStart(2, "0")} · ${data.id}`;
  $$(".tabs button").forEach((b) => (b.disabled = false));
  $("#bgInfo").textContent = `Fondo actual: ${data.fondo}`;
  $("#redoModel").value = data.modelo || S.estado.modelo_defecto;
  [S.original] = await Promise.all([loadImage(url("/imagen/original")), mask.load(), reloadCutout()]);
  updateHeadInfo();
  show("recorte");
}

async function reloadCutout() {
  S.cutout = await loadImage(url("/imagen/recorte"));
}

function updateHeadInfo() {
  const a = S.project.analisis;
  const [x, y, s] = a.head;
  $("#headInfo").innerHTML = `Método: <b>${a.metodo_cabeza}</b> · centro (${Math.round(x)}, ${Math.round(y)}) · tamaño ${Math.round(s)} px.<br>Si está mal, elige la herramienta <b>◎ Cabeza</b> y marca la cara: todos los charas de cara se reencuadran solos.`;
}

// ================================================================ 2. recorte
const mask = (() => {
  const canvas = $("#maskCanvas");
  const ctx = canvas.getContext("2d");
  let W = 0, H = 0;
  let m, mctx; // máscara: alfa = personaje
  let cut, cctx; // recorte (original × máscara)
  let red, rctx; // vista de máscara
  const view = { s: 1, ox: 0, oy: 0 };
  let tool = "erase", bg = "checker";
  let undo = [], redo = [];
  let drawing = null, panning = null, space = false, pointer = null, headDrag = null;
  let dirty = false;
  let pattern;

  function makeCanvas() {
    const c = document.createElement("canvas");
    c.width = W;
    c.height = H;
    return [c, c.getContext("2d")];
  }

  async function load() {
    const img = await loadImage(url("/imagen/mascara"));
    W = img.width;
    H = img.height;
    [m, mctx] = makeCanvas();
    [cut, cctx] = makeCanvas();
    [red, rctx] = makeCanvas();
    mctx.drawImage(img, 0, 0);
    const d = mctx.getImageData(0, 0, W, H);
    for (let i = 0; i < d.data.length; i += 4) {
      d.data[i + 3] = d.data[i];
      d.data[i] = d.data[i + 1] = d.data[i + 2] = 255;
    }
    mctx.putImageData(d, 0, 0);
    if (!S.original || S.original.width !== W) S.original = await loadImage(url("/imagen/original"));
    undo = [];
    redo = [];
    dirty = false;
    refresh();
    fit();
  }

  function refresh(rect) {
    const [x, y, w, h] = rect || [0, 0, W, H];
    for (const [c, draw] of [
      [cctx, () => { cctx.drawImage(S.original, 0, 0); cctx.globalCompositeOperation = "destination-in"; cctx.drawImage(m, 0, 0); }],
      [rctx, () => { rctx.fillStyle = "rgba(255,30,60,0.55)"; rctx.fillRect(0, 0, W, H); rctx.globalCompositeOperation = "destination-out"; rctx.drawImage(m, 0, 0); }],
    ]) {
      c.save();
      c.beginPath();
      c.rect(x, y, w, h);
      c.clip();
      c.clearRect(x, y, w, h);
      draw();
      c.restore();
    }
    render();
  }

  function resize() {
    const r = canvas.getBoundingClientRect();
    canvas.width = Math.round(r.width * devicePixelRatio);
    canvas.height = Math.round(r.height * devicePixelRatio);
    pattern = checkerPattern(ctx, 12 * devicePixelRatio);
  }

  function fit() {
    if (!W) return;
    resize();
    view.s = Math.min((canvas.width - 40) / W, (canvas.height - 40) / H);
    view.ox = (canvas.width - W * view.s) / 2;
    view.oy = (canvas.height - H * view.s) / 2;
    render();
  }

  function render() {
    if (!W || S.view !== "recorte") return;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.fillStyle = "#07070c";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.setTransform(view.s, 0, 0, view.s, view.ox, view.oy);
    ctx.imageSmoothingEnabled = view.s < 2;
    if (bg === "red") {
      ctx.drawImage(S.original, 0, 0);
      ctx.drawImage(red, 0, 0);
    } else {
      ctx.fillStyle = bg === "checker" ? pattern : bg === "black" ? "#000" : "#fff";
      if (bg === "checker") ctx.setTransform(1, 0, 0, 1, 0, 0), ctx.fillRect(view.ox, view.oy, W * view.s, H * view.s), ctx.setTransform(view.s, 0, 0, view.s, view.ox, view.oy);
      else ctx.fillRect(0, 0, W, H);
      ctx.drawImage(cut, 0, 0);
    }
    ctx.strokeStyle = "#444";
    ctx.lineWidth = 1 / view.s;
    ctx.strokeRect(0, 0, W, H);
    // cabeza actual
    const [hx, hy, hs] = headDrag ? headDrag.head : S.project.analisis.head;
    ctx.strokeStyle = "#00e5ff";
    ctx.lineWidth = 2 / view.s;
    ctx.setLineDash([8 / view.s, 6 / view.s]);
    ctx.beginPath();
    ctx.arc(hx, hy, hs / 2, 0, Math.PI * 2);
    ctx.stroke();
    ctx.setLineDash([]);
    // pincel
    if (pointer && (tool === "erase" || tool === "restore") && !space) {
      ctx.strokeStyle = tool === "erase" ? "#ff4d6a" : "#34d17a";
      ctx.beginPath();
      ctx.arc(pointer.x, pointer.y, brushRadius(), 0, Math.PI * 2);
      ctx.stroke();
    }
  }

  const brushRadius = () => +$("#brushSize").value / 2;
  const toImage = (e) => {
    const r = canvas.getBoundingClientRect();
    const px = (e.clientX - r.left) * devicePixelRatio;
    const py = (e.clientY - r.top) * devicePixelRatio;
    return { x: (px - view.ox) / view.s, y: (py - view.oy) / view.s, px, py };
  };

  function dab(x, y) {
    const r = brushRadius();
    const hard = +$("#brushHard").value / 100;
    const g = mctx.createRadialGradient(x, y, r * hard * 0.999, x, y, r);
    g.addColorStop(0, "rgba(255,255,255,1)");
    g.addColorStop(1, "rgba(255,255,255,0)");
    mctx.globalCompositeOperation = tool === "erase" ? "destination-out" : "source-over";
    mctx.fillStyle = g;
    mctx.beginPath();
    mctx.arc(x, y, r, 0, Math.PI * 2);
    mctx.fill();
    mctx.globalCompositeOperation = "source-over";
  }

  function strokeTo(p) {
    const last = drawing.last;
    const r = brushRadius();
    const dist = Math.hypot(p.x - last.x, p.y - last.y);
    const step = Math.max(1, r / 4);
    const n = Math.max(1, Math.ceil(dist / step));
    for (let i = 1; i <= n; i++) dab(last.x + ((p.x - last.x) * i) / n, last.y + ((p.y - last.y) * i) / n);
    const x0 = Math.floor(Math.min(p.x, last.x) - r - 2), y0 = Math.floor(Math.min(p.y, last.y) - r - 2);
    refresh([x0, y0, Math.ceil(Math.abs(p.x - last.x) + 2 * r + 4), Math.ceil(Math.abs(p.y - last.y) + 2 * r + 4)]);
    drawing.last = p;
  }

  canvas.addEventListener("pointerdown", (e) => {
    canvas.setPointerCapture(e.pointerId);
    const p = toImage(e);
    if (tool === "pan" || space || e.button === 1) {
      panning = { x: p.px, y: p.py, ox: view.ox, oy: view.oy };
      return;
    }
    if (tool === "head") {
      headDrag = { start: p, head: [p.x, p.y, 10] };
      return;
    }
    if (undo.length > 7) undo.shift();
    undo.push(mctx.getImageData(0, 0, W, H));
    redo = [];
    drawing = { last: p };
    dab(p.x, p.y);
    refresh([p.x - brushRadius() - 2, p.y - brushRadius() - 2, brushRadius() * 2 + 4, brushRadius() * 2 + 4]);
    dirty = true;
  });
  canvas.addEventListener("pointermove", (e) => {
    const p = toImage(e);
    pointer = p;
    if (panning) {
      view.ox = panning.ox + (p.px - panning.x);
      view.oy = panning.oy + (p.py - panning.y);
    } else if (headDrag) {
      const r = Math.max(4, Math.hypot(p.x - headDrag.start.x, p.y - headDrag.start.y));
      headDrag.head = [headDrag.start.x, headDrag.start.y, r * 2];
    } else if (drawing) {
      strokeTo(p);
      return;
    }
    render();
  });
  canvas.addEventListener("pointerup", async () => {
    panning = null;
    drawing = null;
    if (headDrag) {
      const head = headDrag.head;
      headDrag = null;
      if (head[2] > 12) {
        await guard("Reencuadrando con la nueva cabeza…", async () => {
          const { data } = await post(`/api/proyectos/${pid()}/cabeza`, { cabeza: head });
          S.project = data;
          updateHeadInfo();
          toast("Cabeza marcada: charas reencuadrados");
        });
      }
      render();
    }
  });
  canvas.addEventListener("pointerleave", () => ((pointer = null), render()));
  canvas.addEventListener("wheel", (e) => {
    e.preventDefault();
    const p = toImage(e);
    const f = Math.exp(-e.deltaY * 0.0015);
    const s = clamp(view.s * f, 0.02, 40);
    view.ox = p.px - p.x * s;
    view.oy = p.py - p.y * s;
    view.s = s;
    render();
  }, { passive: false });

  function setTool(t) {
    tool = t;
    $$("#maskTools button").forEach((b) => b.classList.toggle("on", b.dataset.tool === t));
    canvas.style.cursor = t === "pan" ? "grab" : t === "head" ? "crosshair" : "none";
    render();
  }
  $$("#maskTools button").forEach((b) => b.addEventListener("click", () => setTool(b.dataset.tool)));
  $$("#maskView button").forEach((b) =>
    b.addEventListener("click", () => {
      bg = b.dataset.bg;
      $$("#maskView button").forEach((x) => x.classList.toggle("on", x === b));
      render();
    })
  );
  $("#brushSize").addEventListener("input", (e) => (($("#brushSizeOut").textContent = e.target.value), render()));
  $("#fitMask").addEventListener("click", fit);
  function doUndo() {
    if (!undo.length) return;
    redo.push(mctx.getImageData(0, 0, W, H));
    mctx.putImageData(undo.pop(), 0, 0);
    dirty = true;
    refresh();
  }
  function doRedo() {
    if (!redo.length) return;
    undo.push(mctx.getImageData(0, 0, W, H));
    mctx.putImageData(redo.pop(), 0, 0);
    dirty = true;
    refresh();
  }
  $("#undoMask").addEventListener("click", doUndo);
  $("#redoMask").addEventListener("click", doRedo);

  window.addEventListener("keydown", (e) => {
    if (S.view !== "recorte" || e.target.matches("input, select")) return;
    if (e.code === "Space") { space = true; canvas.style.cursor = "grab"; e.preventDefault(); }
    if (e.key === "b") setTool("erase");
    if (e.key === "r") setTool("restore");
    if (e.key === "h") setTool("head");
    if ((e.ctrlKey || e.metaKey) && e.key === "z") (e.preventDefault(), doUndo());
    if ((e.ctrlKey || e.metaKey) && e.key === "y") (e.preventDefault(), doRedo());
  });
  window.addEventListener("keyup", (e) => {
    if (e.code === "Space") { space = false; setTool(tool); }
  });
  window.addEventListener("resize", () => S.view === "recorte" && (resize(), render()));

  async function save() {
    const out = document.createElement("canvas");
    out.width = W;
    out.height = H;
    const o = out.getContext("2d");
    o.fillStyle = "#000";
    o.fillRect(0, 0, W, H);
    o.drawImage(m, 0, 0);
    const blob = await new Promise((r) => out.toBlob(r, "image/png"));
    const fd = new FormData();
    fd.append("mascara", blob, "mascara.png");
    const { data } = await api(`/api/proyectos/${pid()}/mascara`, { method: "POST", body: fd });
    S.project = data;
    S.stamp = Date.now();
    dirty = false;
    await reloadCutout();
    updateHeadInfo();
  }

  $("#saveMask").addEventListener("click", () => guard("Guardando el recorte…", async () => (await save(), toast("Recorte guardado"))));
  $$("[data-op]").forEach((b) =>
    b.addEventListener("click", () =>
      guard("Aplicando…", async () => {
        if (dirty) await save();
        const { data } = await post(`/api/proyectos/${pid()}/mascara/ops`, JSON.parse(b.dataset.op));
        S.project = data;
        S.stamp = Date.now();
        await Promise.all([load(), reloadCutout()]);
        toast("Hecho");
      })
    )
  );
  async function redoBg(fondo) {
    await guard(fondo === "no" ? "Usando la imagen tal cual…" : "Quitando el fondo otra vez…", async () => {
      const { data, metodo } = await post(`/api/proyectos/${pid()}/fondo`, { fondo, modelo: $("#redoModel").value });
      S.project = data;
      S.stamp = Date.now();
      $("#bgInfo").textContent = `Fondo actual: ${metodo}`;
      await Promise.all([load(), reloadCutout()]);
      updateHeadInfo();
    });
  }
  $("#redoBg").addEventListener("click", () => redoBg("si"));
  $("#noBg").addEventListener("click", () => redoBg("no"));
  $("#headAuto").addEventListener("click", () =>
    guard("Detectando la cabeza…", async () => {
      const { data } = await post(`/api/proyectos/${pid()}/cabeza`, { cabeza: null });
      S.project = data;
      updateHeadInfo();
      render();
    })
  );
  $("#toCharas").addEventListener("click", async () => {
    if (dirty) await guard("Guardando el recorte…", save);
    show("charas");
  });

  return { load, fit, isDirty: () => dirty, save };
})();

// ================================================================ 3. charas
const charas = (() => {
  const canvas = $("#charaCanvas");
  const ctx = canvas.getContext("2d");
  let c = null, P = null, st = null; // chara, preset, ajustes
  let ds = 1, offX = 0, offY = 0, zoomRef = 1, bg = "checker", pattern;
  let drag = null, saveTimer = null, previewTimer = null;

  function preset() {
    return S.project.presets[c];
  }
  function shadow() {
    return st.sombra || P.sombra;
  }

  async function open(chara) {
    c = String(chara);
    S.chara = c;
    P = preset();
    st = S.project.ajustes[c];
    if (!st) {
      st = (await post(`/api/proyectos/${pid()}/chara/${c}/auto`, {})).data;
      S.project.ajustes[c] = st;
    }
    zoomRef = st.zoom;
    $("#charaKicker").textContent = `CHARA_${c} · ${P.width}×${P.height} · ${P.format}${P.verificado ? " · verificado" : " · tamaño estimado"}`;
    $("#charaName").textContent = P.nombre;
    $("#charaUse").textContent = P.uso;
    $("#fileName").textContent = S.project.nombres[c] + ".bntx";
    $("#resSize").textContent = `${P.width}×${P.height}`;
    $("#showRef").disabled = !S.project.referencias[c];
    $("#showRef").parentElement.title = S.project.referencias[c] ? "" : "Calibra con un BNTX original en Ajustes para ver la referencia";
    if (S.project.referencias[c] && !S.refs[c]) S.refs[c] = await loadImage(`/api/referencia/${c}?t=${Date.now()}`).catch(() => null);
    const idx = S.project.charas.indexOf(c);
    $("#prevChara").disabled = idx <= 0;
    $("#nextChara").disabled = idx >= S.project.charas.length - 1;
    strip();
    syncInputs();
    layout();
    refreshPreview(true);
  }

  function strip() {
    $("#charaStrip").innerHTML = S.project.charas
      .map((k) => {
        const p = S.project.presets[k];
        return `<div class="strip-item ${k === c ? "on" : ""}" data-c="${k}"><div class="thumb"><img src="${url(`/chara/${k}/preview`)}&v=${Date.now()}" alt=""></div><b>chara_${k}</b><span class="muted">${p.width}×${p.height}</span></div>`;
      })
      .join("");
    $$(".strip-item").forEach((el) => el.addEventListener("click", () => flush().then(() => open(el.dataset.c))));
  }

  function layout() {
    const r = canvas.getBoundingClientRect();
    canvas.width = Math.round(r.width * devicePixelRatio);
    canvas.height = Math.round(r.height * devicePixelRatio);
    const margin = 70 * devicePixelRatio;
    ds = Math.min((canvas.width - margin * 2) / P.width, (canvas.height - margin * 2) / P.height);
    offX = (canvas.width - P.width * ds) / 2;
    offY = (canvas.height - P.height * ds) / 2;
    pattern = checkerPattern(ctx, 10 * devicePixelRatio);
    render();
  }

  function drawCutout(alpha) {
    const img = S.cutout;
    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.translate(offX, offY);
    ctx.scale(ds, ds);
    const cx = st.x + (img.width * st.zoom) / 2;
    const cy = st.y + (img.height * st.zoom) / 2;
    ctx.translate(cx, cy);
    ctx.rotate(((st.rot || 0) * Math.PI) / 180);
    ctx.scale(st.flip ? -1 : 1, 1);
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(img, (-img.width * st.zoom) / 2, (-img.height * st.zoom) / 2, img.width * st.zoom, img.height * st.zoom);
    ctx.restore();
  }

  function guide() {
    const w = P.width * ds, h = P.height * ds;
    ctx.save();
    ctx.translate(offX, offY);
    ctx.strokeStyle = "rgba(0,229,255,0.8)";
    ctx.lineWidth = 1.5 * devicePixelRatio;
    ctx.setLineDash([6 * devicePixelRatio, 5 * devicePixelRatio]);
    ctx.beginPath();
    if (P.guia === "circulo") ctx.arc(w / 2, h / 2, Math.min(w, h) * 0.46, 0, Math.PI * 2);
    if (P.guia === "rombo") (ctx.moveTo(w / 2, 0), ctx.lineTo(w, h / 2), ctx.lineTo(w / 2, h), ctx.lineTo(0, h / 2), ctx.closePath());
    if (P.guia === "franja_ojos") (ctx.moveTo(0, h * 0.5), ctx.lineTo(w, h * 0.5), ctx.moveTo(w * 0.5, 0), ctx.lineTo(w * 0.5, h));
    ctx.moveTo(w / 2 - 8, h / 2), ctx.lineTo(w / 2 + 8, h / 2), ctx.moveTo(w / 2, h / 2 - 8), ctx.lineTo(w / 2, h / 2 + 8);
    ctx.stroke();
    ctx.restore();
  }

  function render() {
    if (!st || S.view !== "charas") return;
    const w = P.width * ds, h = P.height * ds;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.fillStyle = "#07070c";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    if ($("#showOutside").checked) drawCutout(0.22);
    ctx.save();
    ctx.beginPath();
    ctx.rect(offX, offY, w, h);
    ctx.clip();
    ctx.fillStyle = bg === "checker" ? pattern : bg === "dark" ? "#16161f" : "#e9e9ef";
    ctx.fillRect(offX, offY, w, h);
    drawCutout(1);
    const ref = S.refs[c];
    if ($("#showRef").checked && ref) {
      ctx.globalAlpha = +$("#refOpacity").value / 100;
      ctx.drawImage(ref, offX, offY, w, h);
      ctx.globalAlpha = 1;
    }
    ctx.restore();
    ctx.strokeStyle = "#ff7300";
    ctx.lineWidth = 2 * devicePixelRatio;
    ctx.strokeRect(offX - 1, offY - 1, w + 2, h + 2);
    if ($("#showGuide").checked) guide();
  }

  function syncInputs() {
    $("#posX").value = Math.round(st.x * 10) / 10;
    $("#posY").value = Math.round(st.y * 10) / 10;
    $("#rot").value = st.rot || 0;
    $("#zoomRange").value = Math.round(Math.log2(st.zoom / zoomRef) * 100);
    $("#zoomOut").textContent = `×${(st.zoom / zoomRef).toFixed(2)}`;
    const sh = shadow();
    $("#shMode").value = sh.modo;
    $("#shColor").value = sh.color || "#000000";
    $("#shOp").value = Math.round(sh.opacidad * 100);
    $("#shTh").value = Math.round(sh.grosor * 10);
    $("#shBl").value = Math.round(sh.desenfoque * 10);
    $("#shDx").value = sh.dx || 0;
    $("#shDy").value = sh.dy || 0;
    $("#shOpOut").textContent = `${Math.round(sh.opacidad * 100)}%`;
    $("#shThOut").textContent = `${sh.grosor}%`;
    $("#shBlOut").textContent = `${sh.desenfoque}%`;
    $("#shDefault").disabled = !st.sombra;
  }

  function changed() {
    syncInputs();
    render();
    clearTimeout(saveTimer);
    saveTimer = setTimeout(flush, 250);
  }

  async function flush() {
    clearTimeout(saveTimer);
    if (!st) return;
    const { data } = await post(`/api/proyectos/${pid()}/chara/${c}`, st);
    S.project.ajustes[c] = data;
    refreshPreview();
  }

  function refreshPreview(now) {
    clearTimeout(previewTimer);
    previewTimer = setTimeout(() => {
      const src = `${url(`/chara/${c}/preview`)}&v=${Date.now()}`;
      $("#resultImg").src = src;
      $("#resultReal").src = src;
      const thumb = $(`.strip-item[data-c="${c}"] img`);
      if (thumb) thumb.src = src;
    }, now ? 0 : 120);
  }

  const toChara = (e) => {
    const r = canvas.getBoundingClientRect();
    return { x: ((e.clientX - r.left) * devicePixelRatio - offX) / ds, y: ((e.clientY - r.top) * devicePixelRatio - offY) / ds };
  };
  function zoomAt(f, px, py) {
    const nz = clamp(st.zoom * f, 0.001, 100);
    st.x = px - (px - st.x) * (nz / st.zoom);
    st.y = py - (py - st.y) * (nz / st.zoom);
    st.zoom = nz;
    changed();
  }

  canvas.addEventListener("pointerdown", (e) => {
    canvas.setPointerCapture(e.pointerId);
    const p = toChara(e);
    drag = { p, x: st.x, y: st.y };
    canvas.style.cursor = "grabbing";
  });
  canvas.addEventListener("pointermove", (e) => {
    if (!drag) return;
    const p = toChara(e);
    st.x = drag.x + (p.x - drag.p.x);
    st.y = drag.y + (p.y - drag.p.y);
    syncInputs();
    render();
  });
  canvas.addEventListener("pointerup", () => {
    if (drag) changed();
    drag = null;
    canvas.style.cursor = "grab";
  });
  canvas.addEventListener("wheel", (e) => {
    e.preventDefault();
    const p = toChara(e);
    zoomAt(Math.exp(-e.deltaY * 0.0012), p.x, p.y);
  }, { passive: false });
  canvas.style.cursor = "grab";

  $("#zoomRange").addEventListener("input", (e) => {
    const nz = zoomRef * Math.pow(2, +e.target.value / 100);
    zoomAt(nz / st.zoom, P.width / 2, P.height / 2);
  });
  $("#posX").addEventListener("change", (e) => ((st.x = +e.target.value), changed()));
  $("#posY").addEventListener("change", (e) => ((st.y = +e.target.value), changed()));
  $("#rot").addEventListener("change", (e) => ((st.rot = +e.target.value), changed()));
  $("#flipBtn").addEventListener("click", () => {
    // Voltea sin mover el personaje dentro del chara.
    st.flip = !st.flip;
    changed();
  });
  $("#autoBtn").addEventListener("click", () =>
    guard(null, async () => {
      const { data } = await post(`/api/proyectos/${pid()}/chara/${c}/auto`, {});
      st = data;
      S.project.ajustes[c] = data;
      zoomRef = st.zoom;
      changed();
    })
  );
  $("#copyPrev").textContent = "Centrar cabeza";
  $("#copyPrev").addEventListener("click", () => {
    let [hx, hy] = S.project.analisis.head;
    if (st.flip) hx = S.cutout.width - hx;
    st.x = P.width / 2 - hx * st.zoom;
    st.y = P.height / 2 - hy * st.zoom;
    changed();
  });

  function setShadow(key, value) {
    st.sombra = { ...shadow(), [key]: value };
    changed();
  }
  $("#shMode").addEventListener("change", (e) => setShadow("modo", e.target.value));
  $("#shColor").addEventListener("input", (e) => setShadow("color", e.target.value));
  $("#shOp").addEventListener("input", (e) => setShadow("opacidad", +e.target.value / 100));
  $("#shTh").addEventListener("input", (e) => setShadow("grosor", +e.target.value / 10));
  $("#shBl").addEventListener("input", (e) => setShadow("desenfoque", +e.target.value / 10));
  $("#shDx").addEventListener("change", (e) => setShadow("dx", +e.target.value));
  $("#shDy").addEventListener("change", (e) => setShadow("dy", +e.target.value));
  $("#shDefault").addEventListener("click", () => ((st.sombra = null), changed()));

  $$("#charaBg button").forEach((b) =>
    b.addEventListener("click", () => {
      bg = b.dataset.bg;
      $$("#charaBg button").forEach((x) => x.classList.toggle("on", x === b));
      render();
    })
  );
  ["#showGuide", "#showRef", "#showOutside", "#refOpacity"].forEach((s) => $(s).addEventListener("input", render));

  function go(delta) {
    const list = S.project.charas;
    const i = list.indexOf(c) + delta;
    if (i >= 0 && i < list.length) flush().then(() => open(list[i]));
  }
  $("#prevChara").addEventListener("click", () => go(-1));
  $("#nextChara").addEventListener("click", () => go(1));

  function download(tipo) {
    guard("Creando el archivo…", async () => {
      await flush();
      const a = document.createElement("a");
      a.href = url(`/chara/${c}/descargar?tipo=${tipo}`);
      a.download = "";
      a.click();
      await new Promise((r) => setTimeout(r, 600));
    });
  }
  $("#dlBntx").addEventListener("click", () => download("bntx"));
  $("#dlPng").addEventListener("click", () => download("png"));
  $("#dlZip").addEventListener("click", () =>
    guard("Creando todos los BNTX…", async () => {
      await flush();
      const a = document.createElement("a");
      a.href = url("/zip");
      a.click();
      await new Promise((r) => setTimeout(r, 1500));
    })
  );
  $("#viewSheet").addEventListener("click", async (e) => {
    e.preventDefault();
    await flush();
    window.open(url("/hoja"), "_blank");
  });

  window.addEventListener("keydown", (e) => {
    if (S.view !== "charas" || e.target.matches("input, select")) return;
    const step = e.shiftKey ? 10 : 1;
    const moves = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
    if (moves[e.key]) {
      e.preventDefault();
      st.x += moves[e.key][0];
      st.y += moves[e.key][1];
      changed();
    }
    if (e.key === "+" || e.key === "=") zoomAt(1.03, P.width / 2, P.height / 2);
    if (e.key === "-") zoomAt(1 / 1.03, P.width / 2, P.height / 2);
  });
  window.addEventListener("resize", () => S.view === "charas" && layout());

  return { open };
})();

// ================================================================ ajustes
const FORMATS = ["BC7RgbaUnorm", "BC7RgbaUnormSrgb", "BC3RgbaUnorm", "BC3RgbaUnormSrgb", "BC1RgbaUnorm", "BC1RgbaUnormSrgb", "Rgba8Unorm", "Rgba8UnormSrgb"];
const settings = {
  render() {
    const cfg = S.estado.presets.charas;
    $("#presetTable").innerHTML =
      `<tr><th>Chara</th><th>Para qué es</th><th>Ancho</th><th>Alto</th><th>Formato</th><th>Mipmaps</th><th>Estado</th><th>Referencia</th></tr>` +
      Object.entries(cfg)
        .map(
          ([c, p]) => `<tr data-c="${c}">
          <td><b>chara_${c}</b><br><span class="muted">${p.nombre}</span></td>
          <td class="muted">${p.uso}</td>
          <td><input type="number" data-k="width" value="${p.width}" step="4" min="4"></td>
          <td><input type="number" data-k="height" value="${p.height}" step="4" min="4"></td>
          <td><select data-k="format">${FORMATS.map((f) => `<option ${f === p.format ? "selected" : ""}>${f}</option>`).join("")}</select></td>
          <td><input type="number" data-k="mipmaps" value="${p.mipmaps}" min="1" max="12"></td>
          <td><span class="badge ${p.verificado ? "ok" : "est"}">${p.verificado ? "verificado" : "estimado"}</span></td>
          <td>${S.estado.referencias[c] ? `<img src="/api/referencia/${c}?t=${Date.now()}" alt="">` : '<span class="muted">—</span>'}</td></tr>`
        )
        .join("");
  },
};
$("#savePresets").addEventListener("click", () =>
  guard("Guardando…", async () => {
    const charasCfg = {};
    $$("#presetTable tr[data-c]").forEach((tr) => {
      const v = {};
      tr.querySelectorAll("[data-k]").forEach((i) => (v[i.dataset.k] = i.value));
      charasCfg[tr.dataset.c] = v;
    });
    await post("/api/presets", { charas: charasCfg });
    await loadEstado();
    if (S.project) await openProjectKeepView();
    settings.render();
    toast("Configuración guardada");
  })
);
async function openProjectKeepView() {
  const { data } = await api(`/api/proyectos/${pid()}`);
  S.project = data;
}
$("#calBtn").addEventListener("click", () =>
  guard("Leyendo los BNTX originales…", async () => {
    const fd = new FormData();
    [...$("#calFiles").files].forEach((f) => fd.append("archivos", f));
    if ($("#calFolder").value.trim()) fd.append("carpeta", $("#calFolder").value.trim());
    const { data } = await api("/api/calibrar", { method: "POST", body: fd });
    const log = $("#calLog");
    log.hidden = false;
    const lines = Object.entries(data.calibrados).map(
      ([c, v]) => `chara_${c}: ${v.width}×${v.height} · ${v.format} · mipmaps ${v.mipmaps}  (${v.coinciden}/${v.archivos} archivos iguales, referencia: ${v.referencia})`
    );
    log.textContent = `Archivos leídos: ${data.archivos_leidos}\n` + (lines.join("\n") || "No se encontró ningún chara_N_*.bntx") + (data.errores.length ? `\n\nErrores:\n${data.errores.join("\n")}` : "");
    S.refs = {};
    await loadEstado();
    if (S.project) await openProjectKeepView();
    settings.render();
    toast("Calibración guardada");
  })
);
$("#calFiles").addEventListener("change", (e) => toast(`${e.target.files.length} archivo(s) elegidos`));
$("#viewBntx").addEventListener("change", (e) =>
  guard("Abriendo…", async () => {
    const f = e.target.files[0];
    const fd = new FormData();
    fd.append("archivo", f);
    const { data } = await api("/api/bntx/info", { method: "POST", body: fd });
    const fd2 = new FormData();
    fd2.append("archivo", f);
    const res = await fetch("/api/bntx/a-png", { method: "POST", body: fd2 });
    const blob = await res.blob();
    $("#bntxView").innerHTML = `<img src="${URL.createObjectURL(blob)}" alt=""><pre class="log">${JSON.stringify(data, null, 2)}</pre>`;
  })
);

loadEstado().catch((e) => toast(e.message, true));
