'use strict';
const $ = id => document.getElementById(id);
let state = { tracks: [], username: '', job: { running: false }, configured: false };
let csrf = '', busy = false, demo = false, filter = 'all', page = 0, selected = new Set(), pendingFiles = [], confirmCallback, resolveId, resolveAccount;
const PAGE_SIZE = 50;
const labels = {pending: 'Ready', accepted: 'Scrobbled', sending: 'Sending', ignored: 'Ignored', uncertain: 'Uncertain', expired: 'Too old'};
const profile = () => state.username ? `https://www.last.fm/user/${encodeURIComponent(state.username)}/library` : 'https://www.last.fm';

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

async function api(path, body) {
  const response = await fetch(path, body === undefined ? {cache: 'no-store'} : {
    method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF': csrf}, body: JSON.stringify(body)
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'The local app could not complete that action.');
  return result;
}

async function refresh() {
  const fresh = await api('/api/state');
  csrf = fresh.csrf;
  if (demo) fresh.tracks = state.tracks;
  state = fresh;
  const valid = new Set(state.tracks.filter(t => t.status === 'pending').map(t => t.id));
  selected = new Set([...selected].filter(id => valid.has(id)));
  render();
}

function notify(message, type = '') {
  $('notice').textContent = message;
  $('notice').className = `notice ${type}`;
  $('notice').hidden = !message;
}

async function run(task, dialog) {
  if (busy) return;
  busy = true;
  render();
  if (dialog) dialog.querySelector('.dialog-error').textContent = '';
  try { await task(); }
  catch (error) {
    if (dialog && dialog.open) dialog.querySelector('.dialog-error').textContent = error.message;
    else notify(error.message, 'error');
  } finally { busy = false; render(); }
}

function showDialog(id) {
  const dialog = $(id);
  dialog.querySelector('.dialog-error').textContent = '';
  if (!dialog.open) dialog.showModal();
}

function switchView(name) {
  for (const view of ['queue', 'guide', 'privacy']) $(`${view}-view`).hidden = view !== name;
  document.querySelectorAll('.nav-item[data-view]').forEach(button => button.classList.toggle('active', button.dataset.view === name));
  $('page-label').textContent = {queue:'Your queue', guide:'How it works', privacy:'Privacy & storage'}[name];
  window.scrollTo({top: 0, behavior: 'smooth'});
}

function filteredTracks() {
  const query = $('search').value.trim().toLocaleLowerCase();
  return state.tracks.filter(track => {
    const category = filter === 'all' || track.status === filter || filter === 'attention' && ['uncertain', 'ignored', 'expired'].includes(track.status);
    return category && (!query || `${track.artist} ${track.track} ${track.album}`.toLocaleLowerCase().includes(query));
  });
}

function render() {
  const locked = busy || state.job.running;
  const ready = state.tracks.filter(t => t.status === 'pending');
  $('nav-count').textContent = ready.length;
  $('queue-count').textContent = state.tracks.length;
  $('ready-count').textContent = ready.length;
  $('account-label').textContent = state.username || 'Connect Last.fm';
  $('account-button').classList.toggle('connected', !!state.username);
  $('connection-badge').textContent = state.username ? 'Connected' : 'Not connected';
  $('connection-badge').classList.toggle('connected', !!state.username);
  $('connection-title').textContent = state.username ? `Hello, ${state.username}.` : 'A home for every listen.';
  $('connection-description').textContent = state.username ? 'Your account is connected. Review your queue, then send the listens you want to keep.' : 'Connect your Last.fm account to add your offline listening to your music history.';
  $('connect-button').replaceChildren(document.createTextNode(state.username ? 'Open your Last.fm library ↗' : 'Connect Last.fm →'));
  $('step-connect').classList.toggle('current', !!state.username);
  $('step-send').classList.toggle('current', !!state.username && !!ready.length);
  $('storage-path').textContent = state.storage || '';
  $('guide-profile').href = profile();
  for (const id of ['choose-file', 'demo-button', 'settings-button', 'account-button', 'connect-button']) $(id).disabled = locked;
  $('clear-button').disabled = locked || !state.tracks.length;
  $('submit-button').disabled = locked || demo || !state.username || !selected.size;
  $('submit-button').title = demo ? 'Sample plays cannot be submitted.' : !state.username ? 'Connect Last.fm to submit your selected plays.' : '';
  $('selection-label').textContent = demo ? 'Sample preview · submitting is disabled' : selected.size ? `${selected.size.toLocaleString()} ${selected.size === 1 ? 'play' : 'plays'} selected` : 'No plays selected';
  $('job-panel').hidden = !state.job.message;
  $('job-message').textContent = state.job.message || '';
  $('job-count').textContent = state.job.total ? `${state.job.done} / ${state.job.total}` : '';
  $('job-progress').max = state.job.total || 1;
  $('job-progress').value = state.job.done || 0;
  document.querySelectorAll('.filter').forEach(button => button.classList.toggle('active', button.dataset.filter === filter));
  const tracks = filteredTracks();
  page = Math.min(page, Math.max(0, Math.ceil(tracks.length / PAGE_SIZE) - 1));
  const slice = tracks.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const tbody = $('track-rows');
  tbody.replaceChildren();
  for (const track of slice) {
    const row = element('tr');
    const checkCell = element('td', 'check-col');
    const check = element('input');
    check.type = 'checkbox';
    check.checked = selected.has(track.id);
    check.disabled = locked || track.status !== 'pending';
    check.setAttribute('aria-label', `Select ${track.track} by ${track.artist}`);
    check.addEventListener('change', () => {if (check.checked) selected.add(track.id); else selected.delete(track.id); render();});
    checkCell.append(check);
    const title = element('td');
    title.append(element('div', 'track-title', track.track), element('div', 'track-artist', track.artist));
    title.title = `${track.track} — ${track.artist}`;
    const album = element('td');
    album.append(element('div', 'album-name', track.album || '—'));
    album.title = track.album;
    const dateCell = element('td', 'play-date');
    const date = new Date(track.timestamp * 1000);
    dateCell.append(document.createTextNode(date.toLocaleDateString(undefined, {month:'short', day:'numeric', year:'numeric'})), element('small', '', date.toLocaleTimeString(undefined, {hour:'2-digit', minute:'2-digit'})));
    dateCell.title = `${date.toISOString()} · ${track.filename}`;
    if (track.date_adjusted) {
      const original = new Date(track.original_timestamp * 1000);
      dateCell.append(element('small', 'adjusted-date', `Adjusted · originally ${original.toLocaleString()}`));
      dateCell.title += ` · Original: ${original.toISOString()}`;
    }
    const status = element('td');
    const badge = element('span', `status-tag ${track.status}`, labels[track.status] || track.status);
    badge.title = track.message || 'Treated as at least 50% listened. Original listening time preserved.';
    status.append(badge);
    if (track.status === 'uncertain') {
      const resolve = element('button', 'check-outcome', 'Check outcome');
      resolve.disabled = locked;
      resolve.addEventListener('click', () => {
        resolveId = track.id;
        resolveAccount = state.username;
        $('resolve-description').textContent = `${track.track} by ${track.artist} · ${date.toLocaleString()}`;
        $('resolve-profile').href = profile();
        $('resolve-confirmed').checked = false;
        $('resolve-retry').disabled = $('resolve-accepted').disabled = true;
        showDialog('resolve-dialog');
      });
      status.append(resolve);
    }
    row.append(checkCell, title, album, dateCell, status);
    tbody.append(row);
  }
  $('empty-state').hidden = tracks.length > 0;
  $('empty-state').querySelector('h3').textContent = state.tracks.length ? 'No plays match this view.' : 'Good music leaves a trail.';
  $('empty-state').querySelector('p').textContent = state.tracks.length ? 'Try a different filter or search.' : 'Import your listening log to see your plays here. Your original file will stay exactly as it is.';
  $('pagination').hidden = tracks.length <= PAGE_SIZE;
  $('page-info').textContent = `${page * PAGE_SIZE + 1}–${Math.min((page + 1) * PAGE_SIZE, tracks.length)} of ${tracks.length.toLocaleString()} plays`;
  $('previous-page').disabled = page === 0;
  $('next-page').disabled = (page + 1) * PAGE_SIZE >= tracks.length;
  const eligible = tracks.filter(t => t.status === 'pending');
  $('select-all').checked = eligible.length > 0 && eligible.every(t => selected.has(t.id));
  $('select-all').indeterminate = eligible.some(t => selected.has(t.id)) && !$('select-all').checked;
  $('select-all').disabled = locked || !eligible.length;
}

function confirm(title, description, actionLabel, callback) {
  $('confirm-title').textContent = title;
  $('confirm-description').textContent = description;
  $('confirm-action').textContent = actionLabel;
  confirmCallback = callback;
  showDialog('confirm-dialog');
}

function settings() {
  $('api-key').value = $('api-secret').value = '';
  $('remember').checked = state.remember || false;
  $('configured-note').hidden = !state.configured;
  $('remap-outdated').checked = !!state.preferences?.remap_outdated;
  showDialog('settings-dialog');
}

async function connect() {
  if (state.username) {window.open(profile(), '_blank', 'noopener,noreferrer'); return;}
  if (!state.configured) {settings(); return;}
  await run(async () => {
    const result = await api('/api/auth/start', {});
    $('auth-link').href = result.url;
    showDialog('auth-dialog');
    await refresh();
  });
}

function prepareImport(files) {
  if (busy || state.job.running || !files.length) return;
  if (files.length > 20) {notify('Choose at most 20 files at once.', 'error'); return;}
  if (files.some(file => file.size > 8 * 1024 * 1024)) {notify('Choose log files smaller than 8 MB each.', 'error'); return;}
  pendingFiles = files;
  $('import-filenames').textContent = files.map(file => file.name).join(', ');
  $('time-offset').value = '0';
  showDialog('import-dialog');
}

document.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click', () => switchView(button.dataset.view)));
document.querySelectorAll('.close-dialog').forEach(button => button.addEventListener('click', () => {if (!busy) button.closest('dialog').close();}));
document.querySelectorAll('dialog').forEach(dialog => dialog.addEventListener('cancel', event => {if (busy) event.preventDefault();}));
$('settings-button').addEventListener('click', settings);
$('save-history-settings').addEventListener('click', () => run(async () => {
  const result = await api('/api/preferences', {remap_outdated:$('remap-outdated').checked});
  await refresh();
  $('settings-dialog').close();
  notify(state.preferences.remap_outdated ? `Date adjustment enabled. ${result.adjusted} outdated plays now have recent submission dates. Review the adjusted dates before sending.` : 'Two-week cutoff restored. Outdated plays remain in your local queue and are held back from submission.');
}, $('settings-dialog')));
$('account-button').addEventListener('click', () => {
  if (!state.username) {connect(); return;}
  confirm('Disconnect this account?', `Remove the local credentials for ${state.username}? Your queue and submission receipts stay on this PC. You can also revoke access in Last.fm’s application settings.`, 'Disconnect', async () => {
    await api('/api/disconnect', {}); await refresh(); notify('Disconnected. Saved account credentials have been removed.');
  });
});
$('connect-button').addEventListener('click', connect);
$('settings-form').addEventListener('submit', event => {
  event.preventDefault();
  run(async () => {
    await api('/api/settings', {api_key: $('api-key').value, secret: $('api-secret').value, remember: $('remember').checked});
    $('api-key').value = $('api-secret').value = '';
    $('settings-dialog').close();
    await refresh();
    notify('Credentials configured. Click Connect Last.fm to authorize your account.');
  }, $('settings-dialog'));
});
$('finish-auth').addEventListener('click', () => run(async () => {
  await api('/api/auth/finish', {}); $('auth-dialog').close(); await refresh(); notify(`Connected as ${state.username}. Review and select your plays before submitting.`);
}, $('auth-dialog')));
$('choose-file').addEventListener('click', () => $('file-input').click());
$('file-input').addEventListener('change', event => {prepareImport([...event.target.files]); event.target.value = '';});
for (const eventName of ['dragenter', 'dragover']) $('drop-zone').addEventListener(eventName, event => {event.preventDefault(); if (!busy && !state.job.running) $('drop-zone').classList.add('dragging');});
for (const eventName of ['dragleave', 'drop']) $('drop-zone').addEventListener(eventName, event => {event.preventDefault(); $('drop-zone').classList.remove('dragging');});
$('drop-zone').addEventListener('drop', event => prepareImport([...event.dataTransfer.files]));
window.addEventListener('dragover', event => event.preventDefault());
window.addEventListener('drop', event => event.preventDefault());
$('import-action').addEventListener('click', () => run(async () => {
  const offset = Number($('time-offset').value);
  if (!Number.isFinite(offset) || offset < -24 || offset > 24 || !Number.isInteger(offset * 4)) throw new Error('Use a time correction between -24 and +24 hours in 15-minute steps.');
  let added = 0, duplicates = 0, excluded = 0;
  const issues = [], failures = [];
  demo = false;
  selected.clear();
  for (const file of pendingFiles) {
    try {
      const content = new TextDecoder('utf-8', {fatal: true}).decode(await file.arrayBuffer());
      const result = await api('/api/import', {content, filename: file.name, offset});
      added += result.added; duplicates += result.duplicates; excluded += result.excluded;
      for (const issue of result.issues) issues.push({filename: file.name, ...issue});
    } catch (error) {failures.push(`${file.name}: ${error.message}`);}
  }
  $('import-dialog').close();
  page = 0; filter = 'all'; $('search').value = '';
  await refresh();
  $('import-report').hidden = !issues.length && !failures.length;
  $('report-summary').textContent = `Import details · ${excluded} excluded ${excluded === 1 ? 'line' : 'lines'}${failures.length ? ` · ${failures.length} failed files` : ''}`;
  $('report-content').replaceChildren();
  for (const failure of failures) $('report-content').append(element('p', '', failure));
  for (const issue of issues) $('report-content').append(element('p', '', `${issue.filename}, line ${issue.line}: ${issue.reason}`));
  if (excluded > issues.length) $('report-content').append(element('p', '', `Showing the first ${issues.length} excluded-line details.`));
  const outdated = state.tracks.filter(track => track.status === 'expired').length;
  notify(`${added} new plays imported · ${duplicates} already in your queue · ${excluded} excluded.${outdated ? ` ${outdated} outdated plays are held back; enable date adjustment in Settings to include them.` : ''}${failures.length ? ' Some files could not be imported; see details below.' : ''} Check listening times and select the plays you want to send.`, failures.length ? 'error' : '');
  pendingFiles = [];
  render();
}, $('import-dialog')));
$('demo-button').addEventListener('click', () => {
  demo = true; selected.clear(); filter = 'all'; page = 0; $('search').value = '';
  const songs = [ ['Khruangbin', 'A Love International', 'A LA SALA'], ['Air', 'La femme d’argent', 'Moon Safari'], ['Nujabes', 'Feather', 'Modal Soul'], ['Men I Trust', 'Show Me How', 'Show Me How'], ['Bonobo', 'Kerala', 'Migration'], ['Massive Attack', 'Teardrop', 'Mezzanine'] ];
  state.tracks = songs.map(([artist, track, album], index) => ({id:`demo-${index}`, artist, track, album, timestamp: Math.floor(Date.now()/1000) - 3600 - index * 300, status:'pending', message:'Sample preview', filename:'Sample — not saved'}));
  $('import-report').hidden = true;
  notify('You’re viewing sample plays. They are not saved and cannot be submitted. Import a real log or clear the sample to return to your queue.', 'demo');
  render();
});
$('clear-button').addEventListener('click', () => {
  if (demo) {demo = false; selected.clear(); run(async () => {await refresh(); notify('Sample closed. Your saved queue is unchanged.');}); return;}
  confirm('Clear your local queue?', 'Remove the imported track metadata from this PC? Submission fingerprints remain to prevent repeats. Your original logs and Last.fm profile stay unchanged.', 'Clear queue', async () => {
    await api('/api/clear', {}); selected.clear(); await refresh(); $('import-report').hidden = true; notify('Queue cleared. Your original files were kept.');
  });
});
$('search').addEventListener('input', () => {page = 0; render();});
document.querySelectorAll('[data-filter]').forEach(button => button.addEventListener('click', () => {filter = button.dataset.filter; page = 0; render();}));
$('select-all').addEventListener('change', event => {
  const checked = event.target.checked;
  for (const track of filteredTracks()) if (track.status === 'pending') {if (checked) selected.add(track.id); else selected.delete(track.id);}
  render();
});
$('previous-page').addEventListener('click', () => {page--; render();});
$('next-page').addEventListener('click', () => {page++; render();});
$('submit-button').addEventListener('click', () => {
  const ids = [...selected];
  const account = state.username;
  const tracks = state.tracks.filter(track => selected.has(track.id));
  const adjusted = tracks.filter(track => track.date_adjusted).length;
  const timestamps = Object.fromEntries(tracks.map(track => [track.id, track.timestamp]));
  confirm('Ready to scrobble?', `Send ${ids.length} ${ids.length === 1 ? 'play' : 'plays'} to ${account} on Last.fm using the listening times shown in your queue?${adjusted ? ` ${adjusted} plays will appear on Last.fm with adjusted recent dates, rather than their original listening dates.` : ''} Last.fm may filter some entries.`, `Send ${ids.length} ${ids.length === 1 ? 'play' : 'plays'}`, async () => {
    await api('/api/submit', {ids, account, timestamps, confirmed: true}); selected.clear(); await refresh(); notify('Submission started. Keep the app open while it sends your plays.');
  });
});
$('confirm-action').addEventListener('click', () => run(async () => {await confirmCallback(); $('confirm-dialog').close();}, $('confirm-dialog')));
$('resolve-confirmed').addEventListener('change', event => {$('resolve-retry').disabled = $('resolve-accepted').disabled = !event.target.checked;});
for (const [id, action] of [['resolve-retry','retry'], ['resolve-accepted','accepted']]) $(id).addEventListener('click', () => run(async () => {
  if (!$('resolve-confirmed').checked) throw new Error('Check your Last.fm history first.');
  await api('/api/resolve', {ids:[resolveId], account:resolveAccount, action, confirmed:true}); $('resolve-dialog').close(); await refresh();
  notify(action === 'retry' ? 'This play is ready for you to select and submit again.' : 'Marked as received. This play will not be submitted again.');
}, $('resolve-dialog')));

refresh().then(() => {if (state.warning) notify(state.warning, 'error');}).catch(error => notify(`Cannot reach the local app. Keep its terminal open, then launch it again. ${error.message}`, 'error'));
setInterval(async () => {
  if (busy || document.hidden || document.querySelector('dialog[open]')) return;
  try {await refresh();} catch (_) {notify('The local app has stopped. Reopen Start Akis Rockbox Scrobbler.cmd to continue.', 'error');}
}, 3000);
