(() => {
  'use strict';

  const INDEX = window.AUDIO_INDEX || { tree: { folders: {}, tracks: [] }, flat: [], banner_images: [] };

  const state = {
    path: [],
    search: '',
    sort: 'name',
    playlist: [],
    currentIdx: -1,
  };

  const $ = (id) => document.getElementById(id);
  const view = $('view');
  const breadcrumb = $('breadcrumb');
  const audio = $('audio');
  const player = $('player');

  function getNode(path) {
    let node = INDEX.tree;
    for (const p of path) {
      if (!node.folders[p]) return { folders: {}, tracks: [] };
      node = node.folders[p];
    }
    return node;
  }

  function sortTracks(tracks) {
    const copy = [...tracks];
    if (state.sort === 'duration') copy.sort((a, b) => a.duration - b.duration);
    else if (state.sort === 'size') copy.sort((a, b) => a.size - b.size);
    else copy.sort((a, b) => a.nom.localeCompare(b.nom, 'fr', { sensitivity: 'base' }));
    return copy;
  }

  function render() {
    renderBreadcrumb();
    if (state.search) renderSearch();
    else renderFolder();
  }

  function renderBreadcrumb() {
    breadcrumb.innerHTML = '';
    const mkBtn = (label, idx) => {
      const b = document.createElement('button');
      b.textContent = label;
      b.onclick = () => { state.path = state.path.slice(0, idx); state.search = ''; $('search').value = ''; render(); };
      return b;
    };
    breadcrumb.appendChild(mkBtn('🏠 Accueil', 0));
    state.path.forEach((part, i) => {
      const sep = document.createElement('span');
      sep.className = 'sep';
      sep.textContent = '›';
      breadcrumb.appendChild(sep);
      breadcrumb.appendChild(mkBtn(part, i + 1));
    });
    if (state.search) {
      const sep = document.createElement('span');
      sep.className = 'sep';
      sep.textContent = '›';
      breadcrumb.appendChild(sep);
      const span = document.createElement('span');
      span.textContent = `🔍 "${state.search}"`;
      breadcrumb.appendChild(span);
    }
  }

  function renderFolder() {
    const node = getNode(state.path);
    view.innerHTML = '';
    const folderNames = Object.keys(node.folders).sort((a, b) => a.localeCompare(b, 'fr'));

    folderNames.forEach(name => {
      view.appendChild(makeFolderCard(name));
    });

    const tracks = sortTracks(node.tracks);
    tracks.forEach(t => view.appendChild(makeTrackCard(t, tracks)));

    if (!folderNames.length && !tracks.length) {
      const empty = document.createElement('div');
      empty.className = 'empty';
      empty.textContent = 'Dossier vide. Lance convert.py pour générer l\'index.';
      view.appendChild(empty);
    }
  }

  function renderSearch() {
    const q = state.search.toLowerCase();
    const results = sortTracks(INDEX.flat.filter(t => t.nom.toLowerCase().includes(q)));
    view.innerHTML = '';
    if (!results.length) {
      const empty = document.createElement('div');
      empty.className = 'empty';
      empty.textContent = `Aucun résultat pour "${state.search}".`;
      view.appendChild(empty);
      return;
    }
    results.forEach(t => view.appendChild(makeTrackCard(t, results)));
  }

  function makeFolderCard(name) {
    const card = document.createElement('div');
    card.className = 'card folder';
    card.innerHTML = `
      <div class="thumb">📁</div>
      <div class="body">
        <div class="title">${escapeHtml(name)}</div>
        <div class="meta"><span>Tiroir</span></div>
      </div>`;
    card.onclick = () => { state.path.push(name); render(); };
    return card;
  }

  function makeTrackCard(track, playlist) {
    const card = document.createElement('div');
    card.className = 'card track';
    card.dataset.hash = track.hash;
    card.innerHTML = `
      <div class="thumb"><img src="${track.thumb_out}" alt="" loading="lazy"></div>
      <div class="body">
        <div class="title">${escapeHtml(track.nom)}</div>
        <div class="meta">
          <span>${track.duration_fmt}</span>
          <span>${track.size_fmt}</span>
        </div>
      </div>`;
    card.onclick = () => playTrack(track, playlist);
    if (state.currentIdx >= 0 && state.playlist[state.currentIdx]?.hash === track.hash) {
      card.classList.add('playing');
    }
    return card;
  }

  function playTrack(track, playlist) {
    state.playlist = playlist;
    state.currentIdx = playlist.findIndex(t => t.hash === track.hash);
    loadAndPlay(track);
    updatePlayingHighlight();
  }

  function loadAndPlay(track) {
    audio.src = track.audio_out;
    audio.play().catch(e => console.warn('play blocked', e));
    player.hidden = false;
    $('p-thumb').src = track.thumb_out;
    $('p-title').textContent = track.nom;
    $('p-path').textContent = track.source_rel;
    $('p-total').textContent = track.duration_fmt;
    preloadNext();
  }

  function preloadNext() {
    const next = state.playlist[state.currentIdx + 1];
    if (!next) return;
    const link = document.createElement('link');
    link.rel = 'preload';
    link.as = 'audio';
    link.href = next.audio_out;
    link.id = 'preload-next';
    const old = document.getElementById('preload-next');
    if (old) old.remove();
    document.head.appendChild(link);
  }

  function updatePlayingHighlight() {
    document.querySelectorAll('.card.track').forEach(c => c.classList.remove('playing'));
    const current = state.playlist[state.currentIdx];
    if (!current) return;
    const el = document.querySelector(`.card.track[data-hash="${current.hash}"]`);
    if (el) el.classList.add('playing');
  }

  function next() {
    if (state.currentIdx < state.playlist.length - 1) {
      state.currentIdx++;
      loadAndPlay(state.playlist[state.currentIdx]);
      updatePlayingHighlight();
    }
  }

  function prev() {
    if (state.currentIdx > 0) {
      state.currentIdx--;
      loadAndPlay(state.playlist[state.currentIdx]);
      updatePlayingHighlight();
    }
  }

  function togglePlay() {
    if (audio.paused) audio.play(); else audio.pause();
  }

  function formatTime(s) {
    if (!isFinite(s)) return '0:00';
    const total = Math.floor(s);
    const m = Math.floor(total / 60);
    const sec = total % 60;
    return `${m}:${sec.toString().padStart(2, '0')}`;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
  }

  function renderBanner() {
    const b = $('banner');
    if (!INDEX.banner_images?.length) { b.hidden = true; return; }
    const track = document.createElement('div');
    track.className = 'banner-track';
    const imgs = [...INDEX.banner_images, ...INDEX.banner_images];
    imgs.forEach(src => {
      const img = document.createElement('img');
      img.src = src;
      img.loading = 'lazy';
      img.alt = '';
      track.appendChild(img);
    });
    b.appendChild(track);
  }

  // Events
  audio.addEventListener('play', () => { $('p-play').textContent = '⏸'; });
  audio.addEventListener('pause', () => { $('p-play').textContent = '▶'; });
  audio.addEventListener('ended', () => next());
  audio.addEventListener('timeupdate', () => {
    const seek = $('p-seek');
    if (audio.duration) seek.value = (audio.currentTime / audio.duration) * 1000;
    $('p-current').textContent = formatTime(audio.currentTime);
  });

  $('p-play').onclick = togglePlay;
  $('p-next').onclick = next;
  $('p-prev').onclick = prev;
  $('p-seek').oninput = (e) => {
    if (audio.duration) audio.currentTime = (e.target.value / 1000) * audio.duration;
  };
  $('p-volume').oninput = (e) => { audio.volume = e.target.value / 100; };
  audio.volume = 0.8;

  $('search').addEventListener('input', (e) => {
    state.search = e.target.value.trim();
    render();
  });
  $('sort').addEventListener('change', (e) => {
    state.sort = e.target.value;
    render();
  });
  $('theme-toggle').onclick = () => {
    document.body.classList.toggle('theme-dark');
    document.body.classList.toggle('theme-light');
    const btn = $('theme-toggle');
    btn.textContent = document.body.classList.contains('theme-dark') ? '☾' : '☀';
    try { localStorage.setItem('theme', document.body.classList.contains('theme-light') ? 'light' : 'dark'); } catch {}
  };

  try {
    const saved = localStorage.getItem('theme');
    if (saved === 'light') {
      document.body.classList.remove('theme-dark');
      document.body.classList.add('theme-light');
      $('theme-toggle').textContent = '☀';
    }
  } catch {}

  renderBanner();
  render();
})();
