const $ = (id) => document.getElementById(id);
const mediaUrl = $('media-url'), lyricSelect = $('lyric-select'), lyricFile = $('lyricFile');
const btnGenerate = $('btnGenerate'), terminalBox = $('terminalBox');
let pollTimer = null, running = false, rendered = 0, lineTimes = [], startedAt = 0, touched = { media: false, lyric: false };
const ALLOWED_LYRIC_EXT = new Set(['.txt', '.lrc']);

const STAGES = [
    [/Audio ready/, 20], [/Trimming audio/, 25], [/Separating vocals/, 35], [/Loading model/, 45],
    [/Fetching lyrics|Clean title/, 55], [/Aligning|transcribing/, 75], [/Verifying/, 90], [/Done:/, 100],
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
    const hint = $('hint-lyric');
    if (hint) hint.classList.toggle('hidden', lyricSelect.value !== '__none__');
}
function setRunning(on) {
    running = on;
    $('btnGenerateText').textContent = on ? 'Adding to queue...' : 'Add to Queue';
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
    const none = new Option('No lyric file (Whisper transcribe)', '__none__');
    lyricSelect.add(none);
    lyrics.forEach((n) => lyricSelect.add(new Option(n, n, false, n === selected)));
    lyricSelect.add(new Option('Import lyric file...', '__import__'));
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
    showUpload('busy', 'Uploading ' + file.name + '...');
    try {
        const json = await (await fetch('/api/upload-lyric', { method: 'POST', body: fd })).json();
        if (!json.ok) { showUpload('err', 'Failed: ' + json.error); return; }
        updateLyricOptions(json.lyrics, json.filename);
        touched.lyric = true;
        showUpload('ok', json.filename + ' uploaded successfully');
    } catch (e) {
        showUpload('err', 'Upload failed: ' + e.message);
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
        showUpload('err', 'Unsupported format: ' + file.name);
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
    setProgress(0, 'Starting...');
}
function addLine(text, idx) {
    if (lineTimes[idx] === undefined) lineTimes[idx] = Math.round((Date.now() - startedAt) / 1000);
    const row = document.createElement('div');
    row.className = 'flex gap-3';
    const t = document.createElement('span'); t.className = 'flex-none text-[#B59ADB]'; t.textContent = '[' + mmss(lineTimes[idx]) + ']';
    const m = document.createElement('span');
    m.className = /^(Error|Traceback)/i.test(text) ? 'text-[#FF9C93]' : /WARNING/.test(text) ? 'text-mari' : 'text-[#E9DDF7]';
    m.style.overflowWrap = 'anywhere'; m.textContent = text;
    row.append(t, m); terminalBox.appendChild(row);
}

let currentRunningJobId = null;

async function pollStatus() {
    let s;
    try { s = await (await fetch('/api/queue')).json(); } catch (e) { return; }

    renderQueue(s.queue);

    const runningJob = s.queue.find(j => j.status === 'running');
    if (runningJob) {
        const detail = await (await fetch('/api/queue/' + runningJob.id)).json();
        for (; rendered < detail.log.length; rendered++) addLine(detail.log[rendered], rendered);
        terminalBox.scrollTop = terminalBox.scrollHeight;
        let pct = 8;
        detail.log.forEach((l) => STAGES.forEach(([re, p]) => { if (re.test(l) && p > pct) pct = p; }));
        const last = (detail.log.slice(-1)[0] || 'Processing...');
        setStatus('run', 'Running');
        setProgress(Math.min(pct, 95), last.length > 70 ? last.slice(0, 70) + '…' : last);
        currentRunningJobId = runningJob.id;
        return;
    }

    // No running job — if we were tracking one, show its final result
    if (currentRunningJobId) {
        const finished = s.queue.find(j => j.id === currentRunningJobId);
        if (finished) {
            clearInterval(pollTimer); pollTimer = null; setRunning(false);
            if (finished.status === 'error') {
                setStatus('error', 'Failed'); setProgress(100, 'Process stopped.');
                $('errorText').textContent = finished.error || 'Process failed.'; $('errorBox').classList.remove('hidden');
            } else {
                setStatus('done', 'Done'); setProgress(100, 'TTML ready.');
                if (finished.result) showResult(finished.result);
                if ($('resultsList')) refreshResults();
            }
            currentRunningJobId = null;
            // If more jobs in queue, keep polling to show next one
            if (s.queue.some(j => j.status === 'pending')) {
                setTimeout(() => { startPolling(); }, 500);
            }
        }
    }
}
function startPolling() {
    if (pollTimer) return;
    pollTimer = setInterval(pollStatus, 800); pollStatus();
}

/* ---------- queue panel ---------- */
function shortSource(src) {
    if (!src) return '—';
    if (src.startsWith('http')) {
        const m = src.match(/(?:v=|youtu\.be\/)([\w-]{6,})/);
        return m ? 'youtu.be/' + m[1] : src.slice(0, 40);
    }
    return src.split(/[/\\]/).pop();
}
const STATUS_BADGE = {
    pending: { text: 'Queued', cls: 'bg-[#E8DFF0] text-[#5B2A86]' },
    running: { text: 'Running', cls: 'bg-[#FFE9C7] text-[#855300]' },
    done:    { text: 'Done', cls: 'bg-[#D5F0EE] text-[#0E7C7C]' },
    error:   { text: 'Failed', cls: 'bg-[#F9DAD7] text-[#B3261E]' },
};
function renderQueue(jobs) {
    const panel = $('queuePanel');
    if (!panel) return;
    const count = jobs.length;
    $('queueCount').textContent = count ? count + ' job' + (count > 1 ? 's' : '') : '';
    panel.classList.toggle('hidden', count === 0);

    const list = $('queueList');
    list.innerHTML = '';
    jobs.forEach((j) => {
        const badge = STATUS_BADGE[j.status] || STATUS_BADGE.pending;
        const row = document.createElement('div');
        row.className = 'flex items-center gap-3 border-t border-line py-3';
        const isPending = j.status === 'pending';
        row.innerHTML =
            '<div class="flex min-w-0 flex-1 items-center gap-3">'
            + '<span class="flex-none rounded-full px-2.5 py-1 text-xs font-semibold ' + badge.cls + '">' + badge.text + '</span>'
            + '<div class="min-w-0 flex-1">'
            + '<div class="truncate text-sm font-medium">' + shortSource(j.source) + '</div>'
            + '<div class="text-xs text-muted">' + (j.lyric || 'no lyric') + ' · ' + j.model + '</div>'
            + '</div></div>'
            + (isPending
                ? '<button class="qcancel flex-none rounded-full px-3 py-1.5 text-xs font-semibold text-err border border-line hover:bg-[#F9DAD7] transition">Cancel</button>'
                : j.status === 'done' && j.result
                    ? '<a class="flex-none rounded-full bg-ink px-4 py-1.5 text-xs font-semibold text-cream hover:bg-[#43275f] transition" href="/ttml/' + encodeURIComponent(j.result) + '" download="' + j.result + '">Download</a>'
                    : '')
            + (j.status === 'error'
                ? '<span class="flex-none text-xs text-err max-w-[200px] truncate" title="' + (j.error || '').replace(/"/g, '&quot;') + '">' + (j.error || '') + '</span>'
                : '');
        if (isPending) {
            row.querySelector('.qcancel').addEventListener('click', () => cancelJob(j.id));
        }
        list.appendChild(row);
    });

    const hasFinished = jobs.some(j => j.status === 'done' || j.status === 'error');
    const clearBtn = $('btnClearQueue');
    if (clearBtn) clearBtn.classList.toggle('hidden', !hasFinished);
}
async function cancelJob(id) {
    try {
        await fetch('/api/queue/' + id, { method: 'DELETE' });
        pollStatus();
    } catch (e) { /* ignore */ }
}
async function clearFinishedJobs() {
    try {
        await fetch('/api/queue/clear', { method: 'POST' });
        pollStatus();
    } catch (e) { /* ignore */ }
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
    } catch (e) { /* preview optional */ }
}
function renderResults(items) {
    const list = $('resultsList');
    if (!list) return;
    list.innerHTML = '';
    $('resultsEmpty').classList.toggle('hidden', items.length > 0);
    $('resultsCount').textContent = items.length ? items.length + ' .ttml files' : '';
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
    try { renderResults(await (await fetch('/api/results')).json()); } catch (e) { /* ignore */ }
}

/* ---------- generate (enqueue) ---------- */
btnGenerate.addEventListener('click', async () => {
    touched = { media: true, lyric: true }; updateGenerateState();
    if (btnGenerate.disabled) return;
    const lyricVal = lyricSelect.value === '__none__' ? '' : lyricSelect.value;
    const data = {
        source: mediaUrl.value.trim(), lyric: lyricVal, model: $('whisper-model').value,
        offset: $('offset-input').value.trim(), start_from: $('start-time-input').value.trim(),
        title: $('override-title').value.trim(), prompt: $('whisper-prompt').value.trim(),
        separate_vocals: $('toggle-demucs').checked,
        verify: $('toggle-verify') ? $('toggle-verify').checked : false,
        fetch_lyrics: $('toggle-fetch') ? $('toggle-fetch').checked : false,
        segmented: $('toggle-segmented') ? $('toggle-segmented').checked : false,
        merge_gap: 6.0,
    };
    setRunning(true);
    try {
        const json = await (await fetch('/api/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })).json();
        if (!json.ok) {
            setRunning(false); setStatus('error', 'Failed'); setProgress(0, 'Could not add to queue.');
            $('errorText').textContent = json.error; $('errorBox').classList.remove('hidden'); return;
        }
        // Reset form for next entry
        mediaUrl.value = '';
        if ($('override-title')) $('override-title').value = '';
        updateGenerateState();
        setRunning(false);
        setStatus('idle', 'Added to queue');
        // Start polling to show live progress + queue
        resetOutput(); startedAt = Date.now();
        startPolling();
    } catch (e) {
        setRunning(false); setStatus('error', 'Failed');
        $('errorText').textContent = 'Server did not respond: ' + e.message; $('errorBox').classList.remove('hidden');
    }
});

/* ---------- init ---------- */
const btnClearQueue = $('btnClearQueue');
if (btnClearQueue) btnClearQueue.addEventListener('click', clearFinishedJobs);
const initialResults = $('initialResults');
if (initialResults && $('resultsList')) renderResults(JSON.parse(initialResults.textContent || '[]'));
updateGenerateState();
// Resume polling if queue has active jobs on page load
fetch('/api/queue').then((r) => r.json()).then((s) => {
    if (s.queue.length > 0) {
        const hasActive = s.queue.some(j => j.status === 'running' || j.status === 'pending');
        if (hasActive) {
            startedAt = Date.now(); resetOutput(); startPolling();
        } else {
            renderQueue(s.queue);
        }
    }
}).catch(() => {});
