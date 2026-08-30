export function createReviewModule({
  supabase,
  getCurrentUser,
  escapeHtml,
  showAlert,
  clearAlert,
  refreshDashboardStats,
}) {
  const $ = (selector) => document.querySelector(selector);

  const state = {
    thesisId: '',
    documentId: '',
    versionId: '',
    version: null,
    sections: [],
    paragraphs: [],
    comments: [],
    selectedParagraphId: '',
    selectedText: '',
    thesisOptions: [],
    documentOptions: [],
  };

  const commentModal = new bootstrap.Modal($('#reviewCommentModal'));

  function resetSelection() {
    state.selectedParagraphId = '';
    state.selectedText = '';
    $('#review-add-comment').disabled = true;
    $('#review-selection-status').textContent = 'Klik paragraf atau blok teks untuk memberi komentar.';
    document.querySelectorAll('.review-paragraph.is-selected').forEach((element) => {
      element.classList.remove('is-selected');
    });
  }

  function resetWorkspace() {
    state.thesisId = '';
    state.documentId = '';
    state.versionId = '';
    state.version = null;
    state.sections = [];
    state.paragraphs = [];
    state.comments = [];
    state.documentOptions = [];
    resetSelection();

    $('#review-document-select').innerHTML = '<option value="">Pilih dokumen…</option>';
    $('#review-document-select').disabled = true;
    $('#review-version-label').textContent = '-';
    $('#review-empty').classList.remove('d-none');
    $('#review-workspace').classList.add('d-none');
    $('#review-sections').innerHTML = '';
    $('#review-document-content').innerHTML = '';
    $('#review-comments').innerHTML = '';
    $('#review-comment-count').textContent = '0 komentar';
    clearAlert($('#review-alert'));
  }

  function severityMeta(severity) {
    return ({
      minor: ['Minor', 'secondary'],
      moderate: ['Moderate', 'warning'],
      major: ['Major', 'danger'],
      critical: ['Critical', 'dark'],
    })[severity] || [severity || '-', 'secondary'];
  }

  function statusMeta(status) {
    return ({
      open: ['Belum Diperbaiki', 'danger'],
      needs_revision: ['Perlu Revisi Lagi', 'warning'],
      revised: ['Sudah Direvisi', 'info'],
      verified: ['Diperiksa Dosen', 'primary'],
      closed: ['Selesai', 'success'],
    })[status] || [status || '-', 'secondary'];
  }

  function paragraphById(id) {
    return state.paragraphs.find((paragraph) => paragraph.id === id);
  }

  function commentsForParagraph(id) {
    return state.comments.filter((comment) => comment.paragraph_id === id && comment.status !== 'closed');
  }

  async function loadTheses(preselectId = '') {
    clearAlert($('#review-alert'));

    const { data, error } = await supabase
      .from('theses')
      .select('id,title,status,student:students(id,nim,full_name)')
      .is('deleted_at', null)
      .order('updated_at', { ascending: false });

    if (error) {
      showAlert($('#review-alert'), `Daftar skripsi gagal dimuat: ${error.message}`);
      return;
    }

    state.thesisOptions = data || [];
    const select = $('#review-thesis-select');

    select.innerHTML = '<option value="">Pilih skripsi…</option>' + state.thesisOptions
      .map((thesis) => `
        <option value="${thesis.id}">
          ${escapeHtml(thesis.student?.full_name || 'Mahasiswa')} — ${escapeHtml(thesis.title)}
        </option>
      `)
      .join('');

    const targetId = preselectId || state.thesisId;
    if (targetId && state.thesisOptions.some((thesis) => thesis.id === targetId)) {
      select.value = targetId;
      await selectThesis(targetId);
    } else if (!state.thesisId) {
      resetWorkspace();
    }
  }

  async function selectThesis(thesisId) {
    state.thesisId = thesisId;
    state.documentId = '';
    state.versionId = '';
    state.version = null;
    state.sections = [];
    state.paragraphs = [];
    state.comments = [];
    resetSelection();

    const documentSelect = $('#review-document-select');
    documentSelect.innerHTML = '<option value="">Memuat dokumen…</option>';
    documentSelect.disabled = true;
    $('#review-version-label').textContent = '-';
    $('#review-empty').classList.remove('d-none');
    $('#review-workspace').classList.add('d-none');

    if (!thesisId) {
      resetWorkspace();
      return;
    }

    const { data: documents, error } = await supabase
      .from('documents')
      .select('id,document_name,document_type,status,current_version_id')
      .eq('thesis_id', thesisId)
      .is('deleted_at', null)
      .order('created_at', { ascending: true });

    if (error) {
      showAlert($('#review-alert'), `Dokumen gagal dimuat: ${error.message}`);
      return;
    }

    const usableDocuments = (documents || []).filter((documentRecord) => documentRecord.current_version_id);
    state.documentOptions = usableDocuments;

    if (!usableDocuments.length) {
      documentSelect.innerHTML = '<option value="">Belum ada dokumen</option>';
      showAlert($('#review-alert'), 'Skripsi ini belum memiliki versi dokumen yang dapat direview.', 'warning');
      return;
    }

    documentSelect.innerHTML = usableDocuments
      .map((documentRecord) => `
        <option value="${documentRecord.id}">
          ${escapeHtml(documentRecord.document_name)}
        </option>
      `)
      .join('');

    documentSelect.disabled = false;

    const preferred = usableDocuments.find((documentRecord) => documentRecord.document_type === 'proposal')
      || usableDocuments[0];

    documentSelect.value = preferred.id;
    await selectDocument(preferred.id);
  }

  async function selectDocument(documentId) {
    resetSelection();
    state.documentId = documentId;

    const documentRecord = state.documentOptions.find((item) => item.id === documentId);
    if (!documentRecord?.current_version_id) return;

    state.versionId = documentRecord.current_version_id;

    $('#review-empty').classList.add('d-none');
    $('#review-workspace').classList.remove('d-none');
    $('#review-document-title').textContent = documentRecord.document_name;
    $('#review-document-meta').textContent = 'Memuat versi dokumen…';
    $('#review-document-content').innerHTML = '<div class="review-loading"><span class="spinner-border spinner-border-sm me-2"></span>Memuat paragraf…</div>';
    $('#review-comments').innerHTML = '<div class="review-loading"><span class="spinner-border spinner-border-sm me-2"></span>Memuat komentar…</div>';

    const [versionResult, sectionsResult, paragraphsResult, commentsResult] = await Promise.all([
      supabase
        .from('document_versions')
        .select('id,version_number,file_name,file_type,file_size,word_count,review_status,uploaded_at')
        .eq('id', state.versionId)
        .single(),
      supabase
        .from('thesis_sections')
        .select('id,section_code,section_title,section_type,sort_order,status')
        .eq('thesis_id', state.thesisId)
        .is('deleted_at', null)
        .order('sort_order', { ascending: true }),
      supabase
        .from('document_paragraphs')
        .select('id,section_id,paragraph_index,paragraph_type,text_content,style_name,word_count')
        .eq('version_id', state.versionId)
        .order('paragraph_index', { ascending: true }),
      supabase
        .from('comments')
        .select('id,thesis_id,version_id,paragraph_id,selected_text,comment_text,category,severity,status,source,created_at,resolved_at')
        .eq('version_id', state.versionId)
        .is('deleted_at', null)
        .order('created_at', { ascending: false }),
    ]);

    const error = versionResult.error || sectionsResult.error || paragraphsResult.error || commentsResult.error;
    if (error) {
      showAlert($('#review-alert'), `Workspace review gagal dimuat: ${error.message}`);
      return;
    }

    state.version = versionResult.data;
    state.sections = sectionsResult.data || [];
    state.paragraphs = paragraphsResult.data || [];
    state.comments = commentsResult.data || [];

    $('#review-version-label').textContent = `Version ${state.version.version_number}`;
    $('#review-document-meta').textContent = [
      state.version.file_name,
      state.version.file_type?.toUpperCase(),
      state.version.word_count ? `${new Intl.NumberFormat('id-ID').format(state.version.word_count)} kata` : null,
    ].filter(Boolean).join(' · ');

    renderSections();
    renderDocument();
    renderComments();
  }

  function renderSections() {
    const container = $('#review-sections');
    $('#review-section-count').textContent = state.sections.length;

    const introCount = state.paragraphs.filter((paragraph) => !paragraph.section_id).length;
    const items = [];

    if (introCount) {
      items.push(`
        <button type="button" class="review-section-link" data-review-section="">
          <span>Awal Dokumen</span>
          <span class="review-section-paragraph-count">${introCount}</span>
        </button>
      `);
    }

    for (const section of state.sections) {
      const count = state.paragraphs.filter((paragraph) => paragraph.section_id === section.id).length;
      items.push(`
        <button type="button" class="review-section-link" data-review-section="${section.id}">
          <span>
            <span class="d-block fw-semibold">${escapeHtml(section.section_code || '')}</span>
            <span class="review-section-title">${escapeHtml(section.section_title)}</span>
          </span>
          <span class="review-section-paragraph-count">${count}</span>
        </button>
      `);
    }

    container.innerHTML = items.join('') || '<div class="text-secondary small">Struktur belum tersedia.</div>';
  }

  function renderDocument() {
    const container = $('#review-document-content');

    if (!state.paragraphs.length) {
      container.innerHTML = '<div class="empty-inline">Teks hasil ekstraksi belum tersedia.</div>';
      return;
    }

    container.innerHTML = state.paragraphs.map((paragraph) => {
      const activeComments = commentsForParagraph(paragraph.id);
      const typeClass = paragraph.paragraph_type === 'heading'
        ? 'is-heading'
        : paragraph.paragraph_type === 'list'
          ? 'is-list'
          : '';

      return `
        <article
          id="review-paragraph-${paragraph.id}"
          class="review-paragraph ${typeClass} ${activeComments.length ? 'has-comments' : ''}"
          data-review-paragraph="${paragraph.id}"
          data-section-id="${paragraph.section_id || ''}"
          tabindex="0"
        >
          <div class="review-paragraph-index">${paragraph.paragraph_index + 1}</div>
          <div class="review-paragraph-text">${escapeHtml(paragraph.text_content)}</div>
          ${activeComments.length ? `
            <button type="button" class="review-comment-badge" data-scroll-comment="${activeComments[0].id}" title="Lihat komentar">
              <i class="bi bi-chat-left-text"></i> ${activeComments.length}
            </button>
          ` : ''}
        </article>
      `;
    }).join('');
  }

  function filteredComments() {
    const filter = $('#review-comment-filter').value;

    if (filter === 'closed') {
      return state.comments.filter((comment) => comment.status === 'closed');
    }

    if (filter === 'active') {
      return state.comments.filter((comment) => comment.status !== 'closed');
    }

    return state.comments;
  }

  function renderComments() {
    const container = $('#review-comments');
    const comments = filteredComments();
    const activeCount = state.comments.filter((comment) => comment.status !== 'closed').length;

    $('#review-comment-count').textContent = `${activeCount} aktif · ${state.comments.length} total`;

    if (!comments.length) {
      container.innerHTML = `
        <div class="review-comments-empty">
          <i class="bi bi-chat-square-text"></i>
          <div class="fw-semibold mt-2">Belum ada komentar</div>
          <div class="small text-secondary">Pilih paragraf lalu tambahkan catatan review.</div>
        </div>
      `;
      return;
    }

    container.innerHTML = comments.map((comment) => {
      const [severityLabel, severityVariant] = severityMeta(comment.severity);
      const [statusLabel, statusVariant] = statusMeta(comment.status);
      const paragraph = paragraphById(comment.paragraph_id);

      return `
        <article id="review-comment-${comment.id}" class="review-comment-card" data-comment-paragraph="${comment.paragraph_id || ''}">
          <div class="d-flex flex-wrap gap-1 mb-2">
            <span class="badge text-bg-${severityVariant}">${escapeHtml(severityLabel)}</span>
            <span class="badge text-bg-${statusVariant}">${escapeHtml(statusLabel)}</span>
            <span class="badge text-bg-light border text-dark">${escapeHtml(comment.category || '-')}</span>
          </div>
          ${comment.selected_text ? `
            <div class="review-comment-quote">“${escapeHtml(comment.selected_text)}”</div>
          ` : paragraph ? `
            <div class="review-comment-quote">${escapeHtml(paragraph.text_content.slice(0, 160))}${paragraph.text_content.length > 160 ? '…' : ''}</div>
          ` : ''}
          <div class="review-comment-text">${escapeHtml(comment.comment_text)}</div>
          <div class="d-flex justify-content-between align-items-center gap-2 mt-3">
            <button type="button" class="btn btn-link btn-sm p-0 text-decoration-none" data-comment-goto="${comment.paragraph_id || ''}">
              <i class="bi bi-box-arrow-up-right me-1"></i>Ke paragraf
            </button>
            <button type="button" class="btn btn-sm ${comment.status === 'closed' ? 'btn-outline-secondary' : 'btn-outline-success'}"
              data-comment-toggle="${comment.id}" data-comment-status="${comment.status}">
              ${comment.status === 'closed' ? 'Buka Lagi' : 'Selesai'}
            </button>
          </div>
        </article>
      `;
    }).join('');
  }

  function selectParagraph(paragraphId, selectedText = '') {
    const paragraph = paragraphById(paragraphId);
    if (!paragraph) return;

    state.selectedParagraphId = paragraphId;
    state.selectedText = selectedText.trim();

    document.querySelectorAll('.review-paragraph.is-selected').forEach((element) => {
      element.classList.remove('is-selected');
    });

    const element = document.getElementById(`review-paragraph-${paragraphId}`);
    element?.classList.add('is-selected');

    $('#review-add-comment').disabled = false;
    $('#review-selection-status').textContent = state.selectedText
      ? `Teks dipilih: “${state.selectedText.slice(0, 90)}${state.selectedText.length > 90 ? '…' : ''}”`
      : `Paragraf ${paragraph.paragraph_index + 1} dipilih.`;
  }

  function captureTextSelection(paragraphElement) {
    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0 || selection.isCollapsed) {
      return '';
    }

    const text = selection.toString().trim();
    if (!text) return '';

    const anchorNode = selection.anchorNode;
    const focusNode = selection.focusNode;

    if (!paragraphElement.contains(anchorNode) || !paragraphElement.contains(focusNode)) {
      return '';
    }

    return text.slice(0, 4000);
  }

  function openCommentForm() {
    if (!state.selectedParagraphId || !state.versionId || !state.thesisId) return;

    const paragraph = paragraphById(state.selectedParagraphId);
    clearAlert($('#review-comment-alert'));
    $('#review-comment-form').reset();
    $('#review-comment-paragraph-id').value = state.selectedParagraphId;
    $('#review-comment-severity').value = 'moderate';
    $('#review-comment-category').value = 'Bahasa';
    $('#review-comment-selected-text').textContent = state.selectedText || paragraph?.text_content || '-';
    commentModal.show();
  }

  async function saveComment(event) {
    event.preventDefault();
    clearAlert($('#review-comment-alert'));

    const user = getCurrentUser();
    if (!user) {
      showAlert($('#review-comment-alert'), 'Sesi login tidak tersedia.');
      return;
    }

    const paragraphId = $('#review-comment-paragraph-id').value;
    const commentText = $('#review-comment-text').value.trim();

    if (!paragraphId || !commentText) {
      showAlert($('#review-comment-alert'), 'Paragraf dan catatan revisi wajib diisi.');
      return;
    }

    const button = $('#review-comment-save');
    button.disabled = true;
    const defaultText = button.textContent;
    button.textContent = 'Menyimpan…';

    const { error } = await supabase.from('comments').insert({
      thesis_id: state.thesisId,
      version_id: state.versionId,
      paragraph_id: paragraphId,
      created_by: user.id,
      selected_text: state.selectedText || null,
      comment_text: commentText,
      category: $('#review-comment-category').value,
      severity: $('#review-comment-severity').value,
      status: 'open',
      source: 'manual',
    });

    button.disabled = false;
    button.textContent = defaultText;

    if (error) {
      showAlert($('#review-comment-alert'), error.message);
      return;
    }

    commentModal.hide();
    await reloadComments();
    renderDocument();
    restoreSelectedParagraph();
    if (refreshDashboardStats) await refreshDashboardStats();
  }

  async function reloadComments() {
    const { data, error } = await supabase
      .from('comments')
      .select('id,thesis_id,version_id,paragraph_id,selected_text,comment_text,category,severity,status,source,created_at,resolved_at')
      .eq('version_id', state.versionId)
      .is('deleted_at', null)
      .order('created_at', { ascending: false });

    if (error) {
      showAlert($('#review-alert'), `Komentar gagal diperbarui: ${error.message}`);
      return;
    }

    state.comments = data || [];
    renderComments();
  }

  function restoreSelectedParagraph() {
    if (!state.selectedParagraphId) return;
    document.getElementById(`review-paragraph-${state.selectedParagraphId}`)?.classList.add('is-selected');
  }

  async function toggleCommentStatus(commentId, currentStatus) {
    const closing = currentStatus !== 'closed';

    const { error } = await supabase
      .from('comments')
      .update({
        status: closing ? 'closed' : 'open',
        resolved_at: closing ? new Date().toISOString() : null,
      })
      .eq('id', commentId);

    if (error) {
      showAlert($('#review-alert'), `Status komentar gagal diperbarui: ${error.message}`);
      return;
    }

    await reloadComments();
    renderDocument();
    restoreSelectedParagraph();
    if (refreshDashboardStats) await refreshDashboardStats();
  }

  function gotoParagraph(paragraphId) {
    if (!paragraphId) return;
    const element = document.getElementById(`review-paragraph-${paragraphId}`);
    if (!element) return;

    element.scrollIntoView({ behavior: 'smooth', block: 'center' });
    selectParagraph(paragraphId);
    element.classList.add('review-pulse');
    setTimeout(() => element.classList.remove('review-pulse'), 1000);
  }

  function gotoSection(sectionId) {
    const paragraph = state.paragraphs.find((item) => (item.section_id || '') === sectionId);
    if (paragraph) gotoParagraph(paragraph.id);
  }

  function scrollToComment(commentId) {
    const element = document.getElementById(`review-comment-${commentId}`);
    element?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  function init() {
    $('#review-thesis-select').addEventListener('change', async (event) => {
      await selectThesis(event.target.value);
    });

    $('#review-document-select').addEventListener('change', async (event) => {
      await selectDocument(event.target.value);
    });

    $('#review-add-comment').addEventListener('click', openCommentForm);
    $('#review-comment-form').addEventListener('submit', saveComment);
    $('#review-comment-filter').addEventListener('change', renderComments);

    $('#review-document-content').addEventListener('click', (event) => {
      const badge = event.target.closest('[data-scroll-comment]');
      if (badge) {
        event.stopPropagation();
        scrollToComment(badge.dataset.scrollComment);
        return;
      }

      const paragraphElement = event.target.closest('[data-review-paragraph]');
      if (!paragraphElement) return;

      selectParagraph(paragraphElement.dataset.reviewParagraph);
    });

    $('#review-document-content').addEventListener('mouseup', (event) => {
      const paragraphElement = event.target.closest('[data-review-paragraph]');
      if (!paragraphElement) return;

      const text = captureTextSelection(paragraphElement);
      selectParagraph(paragraphElement.dataset.reviewParagraph, text);
    });

    $('#review-sections').addEventListener('click', (event) => {
      const button = event.target.closest('[data-review-section]');
      if (!button) return;
      gotoSection(button.dataset.reviewSection);
    });

    $('#review-comments').addEventListener('click', async (event) => {
      const gotoButton = event.target.closest('[data-comment-goto]');
      if (gotoButton) {
        gotoParagraph(gotoButton.dataset.commentGoto);
        return;
      }

      const toggleButton = event.target.closest('[data-comment-toggle]');
      if (toggleButton) {
        await toggleCommentStatus(toggleButton.dataset.commentToggle, toggleButton.dataset.commentStatus);
      }
    });
  }

  return {
    init,
    loadTheses,
    reset: resetWorkspace,
    async openThesis(thesisId) {
      await loadTheses(thesisId);
    },
  };
}
