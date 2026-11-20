const $ = (id) => document.getElementById(id);
const mediaUrl = $('media-url'), lyricSelect = $('lyric-select'), lyricFile = $('lyricFile');
const btnGenerate = $('btnGenerate'), terminalBox = $('terminalBox');
let pollTimer = null, running = false, rendered = 0, lineTimes = [], startedAt = 0, touched = { media: false, lirik: false };
const ALLOWED_LYRIC_EXT = new Set(['.txt', '.lrc']);

const STAGES = [
    [/Audio siap/, 25], [/Memotong audio/, 30], [/Memisahkan vokal/, 40], [/Memuat model/, 55],
    [/Menyelaraskan|AI menebak/, 75], [/Selesai:/, 100],
];

/* ---------- state helpers ---------- */
function setStatus(kind, text) {
    const dot = $('statusDot');
    dot.className = 'h-2.5 w-2.5 rounded-full ' + ({
        idle: 'bg-[#9A8CA8]', run: 'bg-mari animate-pulse', done: 'bg-turq', error: 'bg-err',
    }[kind]);
    $('statusText').textContent = text;
}
function setProgress(pct, label) {
    $('progressBar').style.width = pct + '%';
    $('progressPct').textContent = pct + '%';
    $('progressTrack').setAttribute('aria-valuenow', pct);
    if (label) $('progressLabel').textContent = label;
}
function mmss(sec) {
    return String(Math.floor(sec / 60)).padStart(2, '0') + ':' + String(sec % 60).padStart(2, '0');
}
function updateGenerateState() {
    const missMedia = !mediaUrl.value.trim();
    $('err-media').classList.toggle('hidden', !(touched.media && missMedia));
    mediaUrl.classList.toggle('field-err', touched.media && missMedia);
    btnGenerate.disabled = running || missMedia;
    // Show/hide hint about whisper transcribe mode
    const hint = $('hint-lirik');
    if (hint) hint.classList.toggle('hidden', lyricSelect.value !== '__none__');
}
function setRunning(on) {
    running = on;
    $('btnGenerateText').textContent = on ? 'Generating...' : 'Generate TTML';
    $('btnGenerateIcon').classList.toggle('hidden', on);
    $('btnSpinner').classList.toggle('hidden', !on);
    updateGenerateState();
}

/* ---------- lyric dropdown + upload ---------- */
function isLyricFile(file) {
    return file && ALLOWED_LYRIC_EXT.has(file.name.slice(file.name.lastIndexOf('.')).toLowerCase());
}
function showUpload(kind, text) {
    const box = $('uploadStatus');
    box.classList.remove('hidden'); box.classList.add('flex');
    box.className = 'flex items-center gap-2 text-sm ' + (kind === 'ok' ? 'text-turq-t' : kind === 'err' ? 'text-err' : 'text-muted');
    $('upSpin').classList.toggle('hidden', kind !== 'busy');
    $('upOk').classList.toggle('hidden', kind !== 'ok');
    $('uploadStatusText').textContent = text;
}
function updateLyricOptions(lyrics, selected) {
    lyricSelect.innerHTML = '';
    const none = new Option('Tanpa lirik (Whisper transcribe)', '__none__');
    lyricSelect.add(none);
    lyrics.forEach((n) => lyricSelect.add(new Option(n, n, false, n === selected)));
    lyricSelect.add(new Option('Import file lirik...', '__import__'));
    if (selected) lyricSelect.value = selected;
    else none.selected = true;
}
let lastLyric = '__none__';
lyricSelect.addEventListener('focus', () => { lastLyric = lyricSelect.value; });
lyricSelect.addEventListener('change', () => {
    if (lyricSelect.value === '__import__') {
        lyricSelect.value = lastLyric && lastLyric !== '__import__' ? lastLyric : '__none__';
        lyricFile.click();
    }
    updateGenerateState();
});
async function uploadLyricFile(file) {
    const fd = new FormData();
    fd.append('file', file);
    showUpload('busy', 'Mengunggah ' + file.name + '...');
    try {
        const json = await (await fetch('/api/upload-lyric', { method: 'POST', body: fd })).json();
        if (!json.ok) { showUpload('err', 'Gagal: ' + json.error); return; }
        updateLyricOptions(json.lyrics, json.filename);
        touched.lirik = true;
        showUpload('ok', json.filename + ' berhasil diunggah');
    } catch (e) {
        showUpload('err', 'Gagal mengunggah: ' + e.message);
    }
    updateGenerateState();
}
lyricFile.addEventListener('change', async () => {
    if (!lyricFile.files.length) return;
    await uploadLyricFile(lyricFile.files[0]);
    lyricFile.value = '';
});
['dragenter', 'dragover', 'dragleave', 'drop'].forEach((ev) => {
    lyricSelect.addEventListener(ev, (e) => { e.preventDefault(); e.stopPropagation(); });
});
['dragenter', 'dragover'].forEach((ev) => {
    lyricSelect.addEventListener(ev, () => { lyricSelect.classList.add('ring-4', 'ring-mari/45', 'border-ink'); });
});
['dragleave', 'drop'].forEach((ev) => {
    lyricSelect.addEventListener(ev, () => { lyricSelect.classList.remove('ring-4', 'ring-mari/45', 'border-ink'); });
});
lyricSelect.addEventListener('drop', (e) => {
    const files = e.dataTransfer.files;
    if (!files.length) return;
    const file = files[0];
    if (!isLyricFile(file)) {
        showUpload('err', 'Format tidak didukung: ' + file.name);
        return;
    }
    uploadLyricFile(file);
});
/* ---------- auto-clean YouTube URL on paste ---------- */
function cleanYTUrl(raw) {
    try {
        const u = new URL(raw);
        if (u.hostname.includes('youtube.com') && u.pathname === '/watch' && u.searchParams.has('v')) {
            return u.origin + u.pathname + '?v=' + u.searchParams.get('v');
        }
        if (u.hostname.includes('youtu.be')) {
            return u.origin + u.pathname;
        }
    } catch (_) {}
    return raw;
}
mediaUrl.addEventListener('paste', (e) => {
    e.preventDefault();
    const pasted = (e.clipboardData || window.clipboardData).getData('text').trim();
    mediaUrl.value = cleanYTUrl(pasted);
    touched.media = true;
    updateGenerateState();
});
mediaUrl.addEventListener('input', updateGenerateState);
mediaUrl.addEventListener('blur', () => { touched.media = true; updateGenerateState(); });

/* ---------- log + progress ---------- */
function resetOutput() {
    terminalBox.innerHTML = ''; rendered = 0; lineTimes = [];
    $('resultBox').classList.add('hidden'); $('errorBox').classList.add('hidden');
    setProgress(0, 'Memulai...');
}
function addLine(text, idx) {
    if (lineTimes[idx] === undefined) lineTimes[idx] = Math.round((Date.now() - startedAt) / 1000);
    const row = document.createElement('div');
    row.className = 'flex gap-3';
    const t = document.createElement('span'); t.className = 'flex-none text-[#B59ADB]'; t.textContent = '[' + mmss(lineTimes[idx]) + ']';
    const m = document.createElement('span');
    m.className = /^(Error|Traceback)/i.test(text) ? 'text-[#FF9C93]' : /PERINGATAN/.test(text) ? 'text-mari' : 'text-[#E9DDF7]';
    m.style.overflowWrap = 'anywhere'; m.textContent = text;
    row.append(t, m); terminalBox.appendChild(row);
}
async function pollStatus() {
    let s;
    try { s = await (await fetch('/api/status')).json(); } catch (e) { return; }
    for (; rendered < s.log.length; rendered++) addLine(s.log[rendered], rendered);
    terminalBox.scrollTop = terminalBox.scrollHeight;
    let pct = 8;
    s.log.forEach((l) => STAGES.forEach(([re, p]) => { if (re.test(l) && p > pct) pct = p; }));
    const last = (s.log.slice(-1)[0] || 'Memproses...');
    if (s.running) { setStatus('run', 'Sedang berjalan'); setProgress(Math.min(pct, 95), last.length > 70 ? last.slice(0, 70) + '…' : last); return; }
    clearInterval(pollTimer); pollTimer = null; setRunning(false);
    if (s.error) {
        setStatus('error', 'Gagal'); setProgress(pct, 'Proses berhenti.');
        $('errorText').textContent = s.error; $('errorBox').classList.remove('hidden');
    } else {
        setStatus('done', 'Selesai'); setProgress(100, 'TTML siap.');
        if (s.result) showResult(s.result);
        if ($('resultsList')) refreshResults();
    }
}
function startPolling() {
    if (pollTimer) return;
    pollTimer = setInterval(pollStatus, 800); pollStatus();
}

/* ---------- result + list ---------- */
async function showResult(name) {
    $('resultTitle').textContent = name.replace('.ttml', '');
    $('downloadLink').href = '/ttml/' + encodeURIComponent(name);
    $('downloadLink').setAttribute('download', name);
    $('resultBox').classList.remove('hidden');
    const box = $('resultPreview'); box.innerHTML = '';
    try {
        const text = await (await fetch('/ttml/' + encodeURIComponent(name))).text();
        let n = 0;
        for (const m of text.matchAll(/<p begin="([^"]+)" end="([^"]+)"[^>]*>([^<]*)<\/p>/g)) {
            if (n++ >= 8) break;
            const row = document.createElement('div'); row.className = 'flex gap-3';
            const a = document.createElement('span'); a.className = 'w-24 flex-none text-muted'; a.textContent = m[1];
            const b = document.createElement('span'); b.textContent = m[3];
            row.append(a, b); box.appendChild(row);
        }
    } catch (e) { /* preview opsional */ }
}
function renderResults(items) {
    const list = $('resultsList');
    if (!list) return;
    list.innerHTML = '';
    $('resultsEmpty').classList.toggle('hidden', items.length > 0);
    $('resultsCount').textContent = items.length ? items.length + ' berkas .ttml' : '';
    items.forEach((it) => {
        const row = document.createElement('div');
        row.className = 'flex items-center gap-3.5 border-t border-line py-3.5';
        row.innerHTML = '<svg width="30" height="30" viewBox="0 0 30 30" aria-hidden="true" class="flex-none"><circle cx="15" cy="15" r="14" fill="#F59E0B"/><circle cx="15" cy="15" r="8" fill="none" stroke="#E48A06" stroke-width="2"/><circle cx="15" cy="15" r="3" fill="#FFF6E5"/></svg>'
            + '<div class="min-w-0 flex-1"><div class="name text-base font-medium [overflow-wrap:anywhere]"></div><div class="date text-[13px] text-muted"></div></div>'
            + '<a class="dl flex h-11 w-11 flex-none items-center justify-center rounded-full border border-line transition hover:bg-cream"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 4v11M7 11l5 5 5-5M5 20h14"/></svg></a>';
        row.querySelector('.name').textContent = it.name;
        row.querySelector('.date').textContent = it.date;
        const dl = row.querySelector('.dl');
        dl.href = '/ttml/' + encodeURIComponent(it.name); dl.setAttribute('download', it.name); dl.setAttribute('aria-label', 'Download ' + it.name);
        list.appendChild(row);
    });
}
async function refreshResults() {
    if (!$('resultsList')) return;
    try { renderResults(await (await fetch('/api/results')).json()); } catch (e) { /* abaikan */ }
}

/* ---------- generate ---------- */
btnGenerate.addEventListener('click', async () => {
    touched = { media: true, lirik: true }; updateGenerateState();
    if (btnGenerate.disabled) return;
    const lirikVal = lyricSelect.value === '__none__' ? '' : lyricSelect.value;
    const data = {
        sumber: mediaUrl.value.trim(), lirik: lirikVal, model: $('whisper-model').value,
        offset: $('offset-input').value.trim(), mulai_dari: $('start-time-input').value.trim(),
        judul: $('override-title').value.trim(), prompt: $('whisper-prompt').value.trim(),
        pisah_vokal: $('toggle-demucs').checked,
    };
    setRunning(true); resetOutput(); startedAt = Date.now(); setStatus('run', 'Sedang berjalan');
    try {
        const json = await (await fetch('/api/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })).json();
        if (!json.ok) {
            setRunning(false); setStatus('error', 'Gagal'); setProgress(0, 'Tidak bisa memulai.');
            $('errorText').textContent = json.error; $('errorBox').classList.remove('hidden'); return;
        }
        startPolling();
    } catch (e) {
        setRunning(false); setStatus('error', 'Gagal');
        $('errorText').textContent = 'Server tidak merespons: ' + e.message; $('errorBox').classList.remove('hidden');
    }
});

/* ---------- init ---------- */
const initialResults = $('initialResults');
if (initialResults && $('resultsList')) renderResults(JSON.parse(initialResults.textContent || '[]'));
updateGenerateState();
fetch('/api/status').then((r) => r.json()).then((s) => {   // lanjutkan tampilan jika halaman di-reload saat proses jalan
    if (s.running) { startedAt = Date.now(); resetOutput(); setRunning(true); setStatus('run', 'Sedang berjalan'); startPolling(); }
}).catch(() => {});
