import { parseProposalFile } from './proposal-parser.js';

function normalizeText(value = '') {
  return String(value)
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[^a-z0-9\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function tokenDice(a, b) {
  const aTokens = new Set(normalizeText(a).split(' ').filter(Boolean));
  const bTokens = new Set(normalizeText(b).split(' ').filter(Boolean));

  if (!aTokens.size && !bTokens.size) return 1;
  if (!aTokens.size || !bTokens.size) return 0;

  let intersection = 0;
  for (const token of aTokens) {
    if (bTokens.has(token)) intersection += 1;
  }

  return (2 * intersection) / (aTokens.size + bTokens.size);
}

function bigrams(text) {
  const normalized = normalizeText(text).replace(/\s+/g, ' ');
  if (normalized.length < 2) return normalized ? [normalized] : [];

  const grams = [];
  for (let index = 0; index < normalized.length - 1; index += 1) {
    grams.push(normalized.slice(index, index + 2));
  }
  return grams;
}

function bigramDice(a, b) {
  const aGrams = bigrams(a);
  const bGrams = bigrams(b);

  if (!aGrams.length && !bGrams.length) return 1;
  if (!aGrams.length || !bGrams.length) return 0;

  const counts = new Map();
  for (const gram of aGrams) counts.set(gram, (counts.get(gram) || 0) + 1);

  let intersection = 0;
  for (const gram of bGrams) {
    const count = counts.get(gram) || 0;
    if (count > 0) {
      intersection += 1;
      counts.set(gram, count - 1);
    }
  }

  return (2 * intersection) / (aGrams.length + bGrams.length);
}

function paragraphSimilarity(oldParagraph, newParagraph) {
  const oldText = normalizeText(oldParagraph.text_content);
  const newText = normalizeText(newParagraph.text_content);

  if (!oldText && !newText) return 1;
  if (oldText === newText) return 1;
  if (!oldText || !newText) return 0;

  const tokenScore = tokenDice(oldText, newText);
  const charScore = bigramDice(oldText, newText);
  let score = Math.max(tokenScore, (tokenScore * 0.65) + (charScore * 0.35));

  if (oldParagraph.paragraph_type === newParagraph.paragraph_type) score += 0.03;
  if (oldParagraph.paragraph_type === 'heading' && newParagraph.paragraph_type === 'heading') score += 0.06;

  return Math.min(1, score);
}

export function compareParagraphs(oldParagraphs, newParagraphs) {
  const rows = oldParagraphs.length + 1;
  const cols = newParagraphs.length + 1;
  const gapPenalty = -0.55;

  const scores = Array.from({ length: rows }, () => new Float32Array(cols));
  const trace = Array.from({ length: rows }, () => new Int8Array(cols));

  for (let i = 1; i < rows; i += 1) {
    scores[i][0] = scores[i - 1][0] + gapPenalty;
    trace[i][0] = 1;
  }

  for (let j = 1; j < cols; j += 1) {
    scores[0][j] = scores[0][j - 1] + gapPenalty;
    trace[0][j] = 2;
  }

  for (let i = 1; i < rows; i += 1) {
    for (let j = 1; j < cols; j += 1) {
      const similarity = paragraphSimilarity(oldParagraphs[i - 1], newParagraphs[j - 1]);
      const matchScore = similarity >= 0.45 ? (similarity * 2) - 0.35 : -1.25;

      const diagonal = scores[i - 1][j - 1] + matchScore;
      const up = scores[i - 1][j] + gapPenalty;
      const left = scores[i][j - 1] + gapPenalty;

      if (diagonal >= up && diagonal >= left) {
        scores[i][j] = diagonal;
        trace[i][j] = 0;
      } else if (up >= left) {
        scores[i][j] = up;
        trace[i][j] = 1;
      } else {
        scores[i][j] = left;
        trace[i][j] = 2;
      }
    }
  }

  const changes = [];
  let i = oldParagraphs.length;
  let j = newParagraphs.length;

  while (i > 0 || j > 0) {
    const direction = trace[i][j];

    if (i > 0 && j > 0 && direction === 0) {
      const oldParagraph = oldParagraphs[i - 1];
      const newParagraph = newParagraphs[j - 1];
      const similarity = paragraphSimilarity(oldParagraph, newParagraph);

      if (similarity >= 0.45) {
        changes.push({
          old_index: oldParagraph.paragraph_index,
          new_index: newParagraph.paragraph_index,
          change_type: similarity >= 0.985 ? 'unchanged' : 'modified',
          similarity: Number(similarity.toFixed(4)),
          old_text: oldParagraph.text_content,
          new_text: newParagraph.text_content,
        });
        i -= 1;
        j -= 1;
        continue;
      }
    }

    if (i > 0 && (j === 0 || direction === 1)) {
      const oldParagraph = oldParagraphs[i - 1];
      changes.push({
        old_index: oldParagraph.paragraph_index,
        new_index: null,
        change_type: 'deleted',
        similarity: 0,
        old_text: oldParagraph.text_content,
        new_text: '',
      });
      i -= 1;
      continue;
    }

    if (j > 0) {
      const newParagraph = newParagraphs[j - 1];
      changes.push({
        old_index: null,
        new_index: newParagraph.paragraph_index,
        change_type: 'added',
        similarity: 0,
        old_text: '',
        new_text: newParagraph.text_content,
      });
      j -= 1;
    }
  }

  changes.reverse();
  return changes;
}

export function createRevisionModule({
  supabase,
  documentBucket,
  maxBytes,
  getCurrentUser,
  escapeHtml,
  showAlert,
  clearAlert,
  onRevisionSaved,
}) {
  const $ = (selector) => document.querySelector(selector);
  const modal = new bootstrap.Modal($('#revisionUploadModal'));

  const state = {
    thesisId: '',
    documentId: '',
    documentName: '',
    currentVersion: null,
    oldParagraphs: [],
    parsedFile: null,
    changes: [],
    commentsByParagraph: new Map(),
  };

  function reset() {
    state.thesisId = '';
    state.documentId = '';
    state.documentName = '';
    state.currentVersion = null;
    state.oldParagraphs = [];
    state.parsedFile = null;
    state.changes = [];
    state.commentsByParagraph = new Map();

    $('#revision-upload-form').reset();
    clearAlert($('#revision-upload-alert'));
    $('#revision-compare-step').classList.add('d-none');
    $('#revision-save-button').classList.add('d-none');
    $('#revision-back-button').classList.add('d-none');
    $('#revision-file-step').classList.remove('d-none');
    $('#revision-processing').classList.add('d-none');
    $('#revision-change-preview').innerHTML = '';
  }

  function safeFileName(name = 'revision.docx') {
    return name
      .normalize('NFKD')
      .replace(/[^a-zA-Z0-9._-]+/g, '-')
      .replace(/-+/g, '-')
      .replace(/^-|-$/g, '') || 'revision.docx';
  }

  function formatBytes(bytes = 0) {
    if (!Number.isFinite(bytes) || bytes <= 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB'];
    const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
    return `${(bytes / (1024 ** index)).toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
  }

  function changeMeta(type) {
    return ({
      unchanged: ['Tidak berubah', 'secondary'],
      modified: ['Diubah', 'warning'],
      added: ['Ditambah', 'success'],
      deleted: ['Dihapus', 'danger'],
    })[type] || [type, 'secondary'];
  }

  function summary() {
    const counts = { unchanged: 0, modified: 0, added: 0, deleted: 0 };
    for (const change of state.changes) counts[change.change_type] += 1;
    return counts;
  }

  async function open({ thesisId, documentId, documentName }) {
    reset();
    state.thesisId = thesisId;
    state.documentId = documentId;
    state.documentName = documentName || 'Dokumen';

    $('#revision-document-name').textContent = state.documentName;
    $('#revision-current-version').textContent = 'Memuat…';

    const { data: documentRecord, error: documentError } = await supabase
      .from('documents')
      .select('id,current_version_id')
      .eq('id', documentId)
      .single();

    if (documentError || !documentRecord?.current_version_id) {
      showAlert($('#revision-upload-alert'), documentError?.message || 'Versi aktif dokumen tidak ditemukan.');
      modal.show();
      return;
    }

    const [versionResult, paragraphsResult, commentsResult] = await Promise.all([
      supabase
        .from('document_versions')
        .select('id,version_number,file_name,file_type,file_size,word_count')
        .eq('id', documentRecord.current_version_id)
        .single(),
      supabase
        .from('document_paragraphs')
        .select('id,paragraph_index,paragraph_type,text_content,style_name,word_count,section_id')
        .eq('version_id', documentRecord.current_version_id)
        .order('paragraph_index', { ascending: true }),
      supabase
        .from('comments')
        .select('id,paragraph_id,status')
        .eq('version_id', documentRecord.current_version_id)
        .is('deleted_at', null)
        .in('status', ['open', 'needs_revision']),
    ]);

    const error = versionResult.error || paragraphsResult.error || commentsResult.error;
    if (error) {
      showAlert($('#revision-upload-alert'), error.message);
      modal.show();
      return;
    }

    state.currentVersion = versionResult.data;
    state.oldParagraphs = paragraphsResult.data || [];

    for (const comment of commentsResult.data || []) {
      state.commentsByParagraph.set(
        comment.paragraph_id,
        (state.commentsByParagraph.get(comment.paragraph_id) || 0) + 1
      );
    }

    $('#revision-current-version').textContent = `Version ${state.currentVersion.version_number} · ${state.currentVersion.file_name}`;
    modal.show();
  }

  async function parseFile(file) {
    clearAlert($('#revision-upload-alert'));

    if (!file) return;
    if (file.size > maxBytes) {
      showAlert($('#revision-upload-alert'), 'Ukuran file melebihi batas 20 MB.');
      return;
    }

    $('#revision-processing').classList.remove('d-none');
    $('#revision-processing-text').textContent = 'Membaca revisi dan membandingkannya dengan versi aktif…';

    try {
      state.parsedFile = await parseProposalFile(file);
      state.changes = compareParagraphs(state.oldParagraphs, state.parsedFile.paragraphs);
      renderComparison();

      $('#revision-file-step').classList.add('d-none');
      $('#revision-compare-step').classList.remove('d-none');
      $('#revision-save-button').classList.remove('d-none');
      $('#revision-back-button').classList.remove('d-none');
    } catch (error) {
      state.parsedFile = null;
      state.changes = [];
      showAlert($('#revision-upload-alert'), `File revisi gagal dibaca: ${error.message}`);
    } finally {
      $('#revision-processing').classList.add('d-none');
    }
  }

  function impactedCommentCount() {
    let count = 0;
    const oldParagraphByIndex = new Map(state.oldParagraphs.map((paragraph) => [paragraph.paragraph_index, paragraph]));

    for (const change of state.changes) {
      if (!['modified', 'deleted'].includes(change.change_type) || change.old_index == null) continue;
      const oldParagraph = oldParagraphByIndex.get(change.old_index);
      if (oldParagraph) count += state.commentsByParagraph.get(oldParagraph.id) || 0;
    }

    return count;
  }

  function renderComparison() {
    const counts = summary();

    $('#revision-summary-from').textContent = `Version ${state.currentVersion.version_number}`;
    $('#revision-summary-to').textContent = `Version ${state.currentVersion.version_number + 1}`;
    $('#revision-summary-file').textContent = `${state.parsedFile.file.name} · ${formatBytes(state.parsedFile.file_size)}`;
    $('#revision-count-unchanged').textContent = counts.unchanged;
    $('#revision-count-modified').textContent = counts.modified;
    $('#revision-count-added').textContent = counts.added;
    $('#revision-count-deleted').textContent = counts.deleted;
    $('#revision-comments-impacted').textContent = impactedCommentCount();

    const changed = state.changes.filter((change) => change.change_type !== 'unchanged');
    const preview = changed.slice(0, 50);

    $('#revision-change-preview').innerHTML = preview.map((change) => {
      const [label, variant] = changeMeta(change.change_type);

      return `
        <article class="revision-change-card">
          <div class="d-flex justify-content-between align-items-center gap-2 mb-2">
            <span class="badge text-bg-${variant}">${escapeHtml(label)}</span>
            ${change.change_type === 'modified'
              ? `<span class="small text-secondary">Kemiripan ${Math.round(change.similarity * 100)}%</span>`
              : ''}
          </div>
          <div class="revision-diff-grid">
            <div>
              <div class="revision-diff-label">Version ${state.currentVersion.version_number}</div>
              <div class="revision-diff-text old">${escapeHtml(change.old_text || '—')}</div>
            </div>
            <div>
              <div class="revision-diff-label">Version ${state.currentVersion.version_number + 1}</div>
              <div class="revision-diff-text new">${escapeHtml(change.new_text || '—')}</div>
            </div>
          </div>
        </article>
      `;
    }).join('') || '<div class="empty-inline">Tidak ada perubahan teks yang terdeteksi.</div>';

    if (changed.length > preview.length) {
      $('#revision-change-preview').insertAdjacentHTML(
        'beforeend',
        `<div class="text-secondary small text-center py-3">…dan ${changed.length - preview.length} perubahan lainnya.</div>`
      );
    }
  }

  async function save(event) {
    event.preventDefault();
    clearAlert($('#revision-upload-alert'));

    const user = getCurrentUser();
    if (!user || !state.parsedFile || !state.currentVersion) {
      showAlert($('#revision-upload-alert'), 'Data revisi belum siap disimpan.');
      return;
    }

    const button = $('#revision-save-button');
    button.disabled = true;
    const original = button.textContent;
    button.textContent = 'Mengunggah & menyimpan…';

    const nextVersion = state.currentVersion.version_number + 1;
    const path = `${user.id}/revisions/${state.documentId}/v${nextVersion}/${crypto.randomUUID()}/${safeFileName(state.parsedFile.file.name)}`;

    const fallbackContentType = state.parsedFile.file_type === 'pdf'
      ? 'application/pdf'
      : 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';

    const { error: uploadError } = await supabase.storage
      .from(documentBucket)
      .upload(path, state.parsedFile.file, {
        cacheControl: '3600',
        upsert: false,
        contentType: state.parsedFile.file.type || fallbackContentType,
      });

    if (uploadError) {
      button.disabled = false;
      button.textContent = original;
      showAlert($('#revision-upload-alert'), `Upload revisi gagal: ${uploadError.message}`);
      return;
    }

    const payloadChanges = state.changes.map(({ old_index, new_index, change_type, similarity }) => ({
      old_index,
      new_index,
      change_type,
      similarity,
    }));

    const { data, error } = await supabase.rpc('create_document_revision', {
      p_document_id: state.documentId,
      p_file_name: state.parsedFile.file.name,
      p_file_path: path,
      p_file_type: state.parsedFile.file_type,
      p_file_size: state.parsedFile.file_size,
      p_file_hash: state.parsedFile.file_hash,
      p_extracted_text: state.parsedFile.extracted_text,
      p_word_count: state.parsedFile.word_count,
      p_paragraphs: state.parsedFile.paragraphs,
      p_changes: payloadChanges,
    });

    button.disabled = false;
    button.textContent = original;

    if (error) {
      await supabase.storage.from(documentBucket).remove([path]);
      showAlert($('#revision-upload-alert'), `Version baru gagal dibuat: ${error.message}`);
      return;
    }

    modal.hide();

    if (onRevisionSaved) {
      await onRevisionSaved({
        thesisId: state.thesisId,
        documentId: state.documentId,
        result: data,
        summary: summary(),
      });
    }

    reset();
  }

  function init() {
    $('#revision-file').addEventListener('change', async (event) => {
      await parseFile(event.target.files?.[0]);
    });

    $('#revision-upload-form').addEventListener('submit', save);

    $('#revision-back-button').addEventListener('click', () => {
      state.parsedFile = null;
      state.changes = [];
      $('#revision-compare-step').classList.add('d-none');
      $('#revision-save-button').classList.add('d-none');
      $('#revision-back-button').classList.add('d-none');
      $('#revision-file-step').classList.remove('d-none');
      $('#revision-file').value = '';
    });
  }

  return { init, open, reset };
}
