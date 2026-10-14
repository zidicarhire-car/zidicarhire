/* Car photo manager: drop several photos to upload (with progress), drag to reorder, set cover, delete. */
(function () {
  const { api, esc } = window.ZCH;
  const root = document.getElementById('photo-manager');
  if (!root) return;

  const input = document.getElementById('photo-input');
  const dropzone = document.getElementById('dropzone');
  const uploads = document.getElementById('upload-list');
  const grid = document.getElementById('photo-grid');
  const empty = document.getElementById('photo-empty');
  const counter = document.querySelector('[data-photo-count]');
  const maxBytes = Number(root.dataset.maxMb) * 1024 * 1024;
  const TYPES = ['image/jpeg', 'image/png', 'image/webp'];
  const csrf = () => document.querySelector('meta[name="csrf-token"]')?.content || '';
  const queue = [];
  let uploading = false;

  function render(photos) {
    grid.innerHTML = photos.map((p, i) => `
      <li class="photo-tile${p.is_cover ? ' is-cover' : ''}" draggable="true" data-id="${p.id}">
        <img src="${esc(p.thumb)}" alt="Photo ${i + 1}" loading="lazy" width="300" height="188">
        ${p.is_cover ? '<span class="cover-tag">Cover</span>' : ''}
        <div class="photo-actions">
          <button type="button" class="btn btn-ghost btn-sm" data-move="-1" aria-label="Move photo ${i + 1} earlier">&larr;</button>
          <button type="button" class="btn btn-ghost btn-sm" data-move="1" aria-label="Move photo ${i + 1} later">&rarr;</button>
          ${p.is_cover ? '' : '<button type="button" class="btn btn-ghost btn-sm" data-cover>Make cover</button>'}
          <button type="button" class="btn btn-danger btn-sm" data-delete>Delete</button>
        </div>
      </li>`).join('');
    empty.hidden = photos.length > 0;
    if (counter) counter.textContent = photos.length;
  }

  /* ---------- uploads ---------- */
  function addFiles(files) {
    [...files].forEach((file) => {
      const li = document.createElement('li');
      li.className = 'upload-item';
      const preview = TYPES.includes(file.type) ? URL.createObjectURL(file) : '';
      li.innerHTML = `${preview ? `<img src="${preview}" alt="">` : '<span class="upload-noimg" aria-hidden="true"></span>'}
        <span class="upload-name">${esc(file.name)}</span>
        <progress max="100" value="0" aria-label="Uploading ${esc(file.name)}"></progress>
        <span class="upload-status">Waiting…</span>`;
      uploads.appendChild(li);
      const status = li.querySelector('.upload-status');
      if (!TYPES.includes(file.type)) { fail(li, 'Not a JPEG, PNG or WebP photo.'); return; }
      if (file.size > maxBytes) { fail(li, `Over ${root.dataset.maxMb} MB. Choose a smaller photo.`); return; }
      status.textContent = 'Waiting…';
      queue.push({ file, li });
    });
    next();
  }

  function fail(li, message) {
    li.classList.add('is-error');
    li.querySelector('progress').remove();
    li.querySelector('.upload-status').textContent = message;
  }

  function next() {
    if (uploading || !queue.length) return;
    uploading = true;
    const { file, li } = queue.shift();
    const bar = li.querySelector('progress');
    const status = li.querySelector('.upload-status');
    const xhr = new XMLHttpRequest();
    const form = new FormData();
    form.append('image', file);
    xhr.open('POST', root.dataset.uploadUrl);
    xhr.setRequestHeader('X-CSRFToken', csrf());
    xhr.upload.addEventListener('progress', (e) => {
      if (e.lengthComputable) { bar.value = Math.round((e.loaded / e.total) * 100); status.textContent = `${bar.value}%`; }
    });
    xhr.addEventListener('load', () => {
      let data = {};
      try { data = JSON.parse(xhr.responseText); } catch (e) { /* not JSON */ }
      if (xhr.status === 201) {
        li.classList.add('is-done');
        bar.value = 100;
        status.textContent = 'Uploaded';
        render(data.photos);
        setTimeout(() => li.remove(), 2500);
      } else {
        fail(li, data.error || `Upload failed (error ${xhr.status}). Try again.`);
      }
      uploading = false;
      next();
    });
    xhr.addEventListener('error', () => { fail(li, 'Upload failed. Check your connection and try again.'); uploading = false; next(); });
    status.textContent = 'Uploading…';
    xhr.send(form);
  }

  input.addEventListener('change', () => { addFiles(input.files); input.value = ''; });
  ['dragenter', 'dragover'].forEach((type) => dropzone.addEventListener(type, (e) => {
    if (!e.dataTransfer?.types?.includes('Files')) return;
    e.preventDefault();
    dropzone.classList.add('is-over');
  }));
  ['dragleave', 'drop'].forEach((type) => dropzone.addEventListener(type, () => dropzone.classList.remove('is-over')));
  dropzone.addEventListener('drop', (e) => {
    if (!e.dataTransfer?.files?.length) return;
    e.preventDefault();
    addFiles(e.dataTransfer.files);
  });

  /* ---------- order, cover, delete ---------- */
  async function saveOrder() {
    const order = [...grid.querySelectorAll('.photo-tile')].map((li) => Number(li.dataset.id));
    try { render((await api(root.dataset.orderUrl, { method: 'POST', body: { order } })).photos); }
    catch (err) { alert(`The new order wasn't saved: ${err.message}`); }
  }

  let dragged = null;
  grid.addEventListener('dragstart', (e) => {
    dragged = e.target.closest('.photo-tile');
    if (!dragged) return;
    dragged.classList.add('is-dragging');
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', dragged.dataset.id);
  });
  grid.addEventListener('dragover', (e) => {
    const over = e.target.closest('.photo-tile');
    if (!dragged || !over || over === dragged) return;
    e.preventDefault();
    const box = over.getBoundingClientRect();
    const after = (e.clientX - box.left) > box.width / 2;
    grid.insertBefore(dragged, after ? over.nextSibling : over);
  });
  grid.addEventListener('drop', (e) => { if (dragged) e.preventDefault(); });
  grid.addEventListener('dragend', () => {
    if (!dragged) return;
    dragged.classList.remove('is-dragging');
    dragged = null;
    saveOrder();
  });

  grid.addEventListener('click', async (e) => {
    const tile = e.target.closest('.photo-tile');
    if (!tile) return;
    const id = tile.dataset.id;
    const move = e.target.closest('[data-move]');
    if (move) {
      const sibling = move.dataset.move === '-1' ? tile.previousElementSibling : tile.nextElementSibling;
      if (!sibling) return;
      grid.insertBefore(tile, move.dataset.move === '-1' ? sibling : sibling.nextSibling);
      await saveOrder();
      grid.querySelector(`[data-id="${id}"] [data-move="${move.dataset.move}"]`)?.focus();
      return;
    }
    try {
      if (e.target.closest('[data-cover]')) {
        render((await api(`${root.dataset.baseUrl}${id}/cover/`, { method: 'POST', body: {} })).photos);
      } else if (e.target.closest('[data-delete]')) {
        if (!confirm('Delete this photo? This cannot be undone.')) return;
        render((await api(`${root.dataset.baseUrl}${id}/delete/`, { method: 'POST', body: {} })).photos);
      }
    } catch (err) { alert(err.message); }
  });
})();
