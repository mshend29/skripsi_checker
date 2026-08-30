import { createClient } from 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.57.4/+esm';
import { SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY } from './config.js';
import { parseProposalFile } from './proposal-parser.js';

const supabase = createClient(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY);
const DOCUMENT_BUCKET = 'thesis-documents';
const MAX_PROPOSAL_BYTES = 20 * 1024 * 1024;

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => document.querySelectorAll(selector);

const loading = $('#app-loading');
const authScreen = $('#auth-screen');
const dashboardScreen = $('#dashboard-screen');
const authAlert = $('#auth-alert');
const globalAlert = $('#global-alert');

let currentUser = null;
let studentsCache = [];
let thesesCache = [];
let detailStudentId = null;
let archiveStudentId = null;
let detailThesisId = null;
let pendingThesisStudentId = '';
let parsedProposal = null;

const studentFormModal = new bootstrap.Modal($('#studentFormModal'));
const studentDetailModal = new bootstrap.Modal($('#studentDetailModal'));
const archiveStudentModal = new bootstrap.Modal($('#archiveStudentModal'));
const thesisStartModal = new bootstrap.Modal($('#thesisStartModal'));
const proposalImportModal = new bootstrap.Modal($('#proposalImportModal'));
const thesisFormModal = new bootstrap.Modal($('#thesisFormModal'));
const thesisDetailModal = new bootstrap.Modal($('#thesisDetailModal'));

const defaultThesisSections = [
  { section_code: 'BAB I', section_title: 'Pendahuluan', section_type: 'chapter', sort_order: 10 },
  { section_code: 'BAB II', section_title: 'Kajian Pustaka', section_type: 'chapter', sort_order: 20 },
  { section_code: 'BAB III', section_title: 'Metode Penelitian', section_type: 'chapter', sort_order: 30 },
  { section_code: 'BAB IV', section_title: 'Hasil dan Pembahasan', section_type: 'chapter', sort_order: 40 },
  { section_code: 'BAB V', section_title: 'Kesimpulan', section_type: 'chapter', sort_order: 50 },
  { section_code: 'REFERENSI', section_title: 'Daftar Pustaka', section_type: 'reference', sort_order: 60 },
  { section_code: 'LAMPIRAN', section_title: 'Lampiran', section_type: 'appendix', sort_order: 70 },
];

function escapeHtml(value = '') {
  return String(value).replace(/[&<>'"]/g, (char) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    "'": '&#039;',
    '"': '&quot;'
  }[char]));
}

function showAlert(target, message, type = 'danger') {
  target.innerHTML = `<div class="alert alert-${type}" role="alert">${escapeHtml(message)}</div>`;
}

function clearAlert(target) {
  target.innerHTML = '';
}

function setButtonBusy(button, busy, busyText) {
  if (!button.dataset.defaultText) button.dataset.defaultText = button.textContent;
  button.disabled = busy;
  button.textContent = busy ? busyText : button.dataset.defaultText;
}

function valueOrDash(value) {
  const text = String(value ?? '').trim();
  return text || '-';
}

function formatDate(value) {
  if (!value) return '-';
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('id-ID', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  }).format(date);
}

function formatBytes(bytes = 0) {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / (1024 ** index)).toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function studentStatusBadge(status) {
  const labels = {
    aktif: ['Aktif', 'success'],
    lulus: ['Lulus', 'primary'],
    nonaktif: ['Nonaktif', 'secondary'],
  };
  const [label, variant] = labels[status] || [status || '-', 'secondary'];
  return `<span class="badge text-bg-${variant} fw-medium">${escapeHtml(label)}</span>`;
}

function thesisStatusBadge(status) {
  const labels = {
    draft: ['Draft', 'secondary'],
    proposal: ['Proposal', 'info'],
    under_review: ['Sedang Direview', 'warning'],
    revision: ['Revisi', 'danger'],
    ready_for_review: ['Siap Direview', 'primary'],
    approved: ['ACC', 'success'],
    completed: ['Selesai', 'dark'],
  };
  const [label, variant] = labels[status] || [status || '-', 'secondary'];
  return `<span class="badge text-bg-${variant} fw-medium">${escapeHtml(label)}</span>`;
}

function researchTypeLabel(type) {
  return ({
    quantitative: 'Kuantitatif',
    qualitative: 'Kualitatif',
    mixed: 'Mixed Method',
  })[type] || '-';
}

function normalizeIdentity(value = '') {
  return String(value).toLowerCase().replace(/[^a-z0-9]/g, '');
}

function safeFileName(name = 'proposal.docx') {
  const cleaned = name
    .normalize('NFKD')
    .replace(/[^a-zA-Z0-9._-]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '');

  return cleaned || 'proposal.docx';
}

function initPasswordToggles() {
  $$('[data-password-toggle]').forEach((button) => {
    button.addEventListener('click', () => {
      const input = document.getElementById(button.dataset.passwordToggle);
      if (!input) return;

      const isHidden = input.type === 'password';
      input.type = isHidden ? 'text' : 'password';

      const icon = button.querySelector('i');
      if (icon) {
        icon.classList.toggle('bi-eye', !isHidden);
        icon.classList.toggle('bi-eye-slash', isHidden);
      }

      const label = isHidden ? 'Sembunyikan password' : 'Tampilkan password';
      button.setAttribute('aria-label', label);
      button.setAttribute('title', label);
      button.setAttribute('aria-pressed', String(isHidden));
    });
  });
}

async function getCurrentUser() {
  const { data, error } = await supabase.auth.getUser();
  if (error) return null;
  return data.user;
}

async function loadProfile(user) {
  const { data, error } = await supabase
    .from('users')
    .select('full_name,email,institution,study_program,role,is_active')
    .eq('id', user.id)
    .single();

  if (error) throw error;
  if (!data.is_active) throw new Error('Akun Anda sedang dinonaktifkan.');
  return data;
}

async function loadDashboardStats() {
  const [students, theses, comments, ai] = await Promise.all([
    supabase
      .from('students')
      .select('*', { count: 'exact', head: true })
      .eq('status', 'aktif')
      .is('deleted_at', null),
    supabase
      .from('theses')
      .select('*', { count: 'exact', head: true })
      .in('status', ['draft', 'proposal', 'under_review', 'revision', 'ready_for_review'])
      .is('deleted_at', null),
    supabase
      .from('comments')
      .select('*', { count: 'exact', head: true })
      .in('status', ['open', 'revised', 'needs_revision'])
      .is('deleted_at', null),
    supabase
      .from('ai_findings')
      .select('*', { count: 'exact', head: true })
      .eq('status', 'pending')
      .is('deleted_at', null),
  ]);

  const errors = [students.error, theses.error, comments.error, ai.error].filter(Boolean);
  if (errors.length) throw errors[0];

  $('#stat-students').textContent = students.count ?? 0;
  $('#stat-theses').textContent = theses.count ?? 0;
  $('#stat-comments').textContent = comments.count ?? 0;
  $('#stat-ai').textContent = ai.count ?? 0;
}

function setActiveNavigation(viewName) {
  $$('[data-view-link]').forEach((link) => {
    link.classList.toggle('active', link.dataset.viewLink === viewName);
  });
}

async function showView(viewName) {
  $$('.app-view').forEach((view) => view.classList.add('d-none'));
  const target = $(`#view-${viewName}`) || $('#view-dashboard');
  target.classList.remove('d-none');
  setActiveNavigation(viewName);
  clearAlert(globalAlert);

  const offcanvasElement = $('#mobileSidebar');
  const offcanvas = bootstrap.Offcanvas.getInstance(offcanvasElement);
  if (offcanvas) offcanvas.hide();

  if (viewName === 'students') await loadStudents();
  if (viewName === 'theses') await loadTheses();
}

async function loadStudents() {
  const loader = $('#students-loading');
  const empty = $('#students-empty');
  const tableWrap = $('#students-table-wrap');

  loader.classList.remove('d-none');
  empty.classList.add('d-none');
  tableWrap.classList.add('d-none');

  const { data, error } = await supabase
    .from('students')
    .select('id,nim,full_name,email,phone,study_program,faculty,year_entry,status,notes,created_at,updated_at')
    .is('deleted_at', null)
    .order('full_name', { ascending: true });

  loader.classList.add('d-none');

  if (error) {
    showAlert(globalAlert, `Data mahasiswa gagal dimuat: ${error.message}`);
    return;
  }

  studentsCache = data || [];
  renderStudents();
}

async function ensureStudentsLoaded() {
  if (studentsCache.length) return;

  const { data, error } = await supabase
    .from('students')
    .select('id,nim,full_name,email,phone,study_program,faculty,year_entry,status,notes,created_at,updated_at')
    .is('deleted_at', null)
    .order('full_name', { ascending: true });

  if (error) throw error;
  studentsCache = data || [];
}

function getFilteredStudents() {
  const keyword = $('#student-search').value.trim().toLowerCase();
  const status = $('#student-status-filter').value;

  return studentsCache.filter((student) => {
    const haystack = [
      student.full_name,
      student.nim,
      student.study_program,
      student.faculty,
      student.email,
    ].join(' ').toLowerCase();

    return (!keyword || haystack.includes(keyword)) && (!status || student.status === status);
  });
}

function renderStudents() {
  const tbody = $('#students-table-body');
  const empty = $('#students-empty');
  const tableWrap = $('#students-table-wrap');
  const filtered = getFilteredStudents();

  if (!studentsCache.length) {
    tbody.innerHTML = '';
    tableWrap.classList.add('d-none');
    empty.classList.remove('d-none');
    return;
  }

  empty.classList.add('d-none');
  tableWrap.classList.remove('d-none');

  if (!filtered.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="text-center text-secondary py-5">Tidak ada mahasiswa yang sesuai dengan pencarian/filter.</td></tr>';
    return;
  }

  tbody.innerHTML = filtered.map((student) => `
    <tr>
      <td>
        <button class="student-name-button btn btn-link p-0 text-start text-decoration-none fw-semibold" data-student-detail="${student.id}">
          ${escapeHtml(student.full_name)}
        </button>
        <div class="text-secondary small">${escapeHtml(student.email || '')}</div>
      </td>
      <td class="text-nowrap">${escapeHtml(student.nim)}</td>
      <td>${escapeHtml(student.study_program || '-')}</td>
      <td>${studentStatusBadge(student.status)}</td>
      <td class="text-end text-nowrap">
        <button class="btn btn-sm btn-light border" data-student-detail="${student.id}" title="Detail"><i class="bi bi-eye"></i></button>
        <button class="btn btn-sm btn-light border" data-student-edit="${student.id}" title="Edit"><i class="bi bi-pencil"></i></button>
        <button class="btn btn-sm btn-light border text-danger" data-student-archive="${student.id}" title="Arsipkan"><i class="bi bi-archive"></i></button>
      </td>
    </tr>
  `).join('');
}

function resetStudentForm() {
  $('#student-form').reset();
  $('#student-id').value = '';
  $('#student-status').value = 'aktif';
  $('#student-form-title').textContent = 'Tambah Mahasiswa';
  $('#student-save-button').textContent = 'Simpan Mahasiswa';
  clearAlert($('#student-form-alert'));
}

function openAddStudent() {
  resetStudentForm();
  studentFormModal.show();
}

function findStudent(id) {
  return studentsCache.find((student) => student.id === id);
}

function openEditStudent(id) {
  const student = findStudent(id);
  if (!student) return;

  clearAlert($('#student-form-alert'));
  $('#student-form-title').textContent = 'Edit Mahasiswa';
  $('#student-save-button').textContent = 'Simpan Perubahan';
  $('#student-id').value = student.id;
  $('#student-nim').value = student.nim || '';
  $('#student-name').value = student.full_name || '';
  $('#student-email').value = student.email || '';
  $('#student-phone').value = student.phone || '';
  $('#student-study-program').value = student.study_program || '';
  $('#student-faculty').value = student.faculty || '';
  $('#student-year-entry').value = student.year_entry || '';
  $('#student-status').value = student.status || 'aktif';
  $('#student-notes').value = student.notes || '';
  studentFormModal.show();
}

async function openStudentDetail(id) {
  const student = findStudent(id);
  if (!student) return;

  detailStudentId = id;
  $('#detail-student-name').textContent = student.full_name;
  $('#detail-student-nim').textContent = `NIM: ${student.nim}`;
  $('#detail-student-email').textContent = valueOrDash(student.email);
  $('#detail-student-phone').textContent = valueOrDash(student.phone);
  $('#detail-student-study-program').textContent = valueOrDash(student.study_program);
  $('#detail-student-faculty').textContent = valueOrDash(student.faculty);
  $('#detail-student-year-entry').textContent = valueOrDash(student.year_entry);
  $('#detail-student-status').innerHTML = studentStatusBadge(student.status);
  $('#detail-student-notes').textContent = valueOrDash(student.notes);
  $('#detail-student-theses').innerHTML = '<div class="text-secondary small py-2"><span class="spinner-border spinner-border-sm me-2"></span>Memuat skripsi…</div>';

  studentDetailModal.show();
  await renderStudentTheses(id);
}

async function renderStudentTheses(studentId) {
  const container = $('#detail-student-theses');
  const { data, error } = await supabase
    .from('theses')
    .select('id,title,status,current_stage,research_type,start_date,approved_date')
    .eq('student_id', studentId)
    .is('deleted_at', null)
    .order('created_at', { ascending: false });

  if (error) {
    container.innerHTML = `<div class="alert alert-warning py-2 mb-0">${escapeHtml(error.message)}</div>`;
    return;
  }

  if (!data?.length) {
    container.innerHTML = '<div class="empty-inline">Belum ada skripsi untuk mahasiswa ini.</div>';
    return;
  }

  container.innerHTML = data.map((thesis) => `
    <button type="button" class="thesis-mini-card w-100 text-start" data-thesis-detail="${thesis.id}">
      <div class="d-flex justify-content-between align-items-start gap-3">
        <div>
          <div class="fw-semibold">${escapeHtml(thesis.title)}</div>
          <div class="text-secondary small mt-1">${escapeHtml(thesis.current_stage || 'Tahap belum ditentukan')} · ${escapeHtml(researchTypeLabel(thesis.research_type))}</div>
        </div>
        ${thesisStatusBadge(thesis.status)}
      </div>
    </button>
  `).join('');
}

function openArchiveStudent(id) {
  const student = findStudent(id);
  if (!student) return;

  archiveStudentId = id;
  $('#archive-student-name').textContent = student.full_name;
  archiveStudentModal.show();
}

async function saveStudent(event) {
  event.preventDefault();
  clearAlert($('#student-form-alert'));

  const button = $('#student-save-button');
  const id = $('#student-id').value;
  const yearEntryValue = $('#student-year-entry').value.trim();

  const payload = {
    nim: $('#student-nim').value.trim(),
    full_name: $('#student-name').value.trim(),
    email: $('#student-email').value.trim() || null,
    phone: $('#student-phone').value.trim() || null,
    study_program: $('#student-study-program').value.trim() || null,
    faculty: $('#student-faculty').value.trim() || null,
    year_entry: yearEntryValue ? Number(yearEntryValue) : null,
    status: $('#student-status').value,
    notes: $('#student-notes').value.trim() || null,
  };

  if (!payload.nim || !payload.full_name) {
    showAlert($('#student-form-alert'), 'NIM dan nama lengkap wajib diisi.');
    return;
  }

  setButtonBusy(button, true, id ? 'Menyimpan…' : 'Menambahkan…');

  let error;
  if (id) {
    ({ error } = await supabase.from('students').update(payload).eq('id', id));
  } else {
    ({ error } = await supabase.from('students').insert({ ...payload, created_by: currentUser.id }));
  }

  setButtonBusy(button, false, '');

  if (error) {
    const message = error.code === '23505'
      ? 'NIM tersebut sudah terdaftar pada daftar mahasiswa Anda.'
      : error.message;
    showAlert($('#student-form-alert'), message);
    return;
  }

  studentFormModal.hide();
  await Promise.all([loadStudents(), loadDashboardStats()]);
  await showView('students');
  showAlert(globalAlert, id ? 'Data mahasiswa berhasil diperbarui.' : 'Mahasiswa berhasil ditambahkan.', 'success');
}

async function archiveStudent() {
  if (!archiveStudentId) return;

  const button = $('#archive-confirm-button');
  setButtonBusy(button, true, 'Mengarsipkan…');

  const { error } = await supabase
    .from('students')
    .update({ deleted_at: new Date().toISOString() })
    .eq('id', archiveStudentId);

  setButtonBusy(button, false, '');

  if (error) {
    archiveStudentModal.hide();
    showAlert(globalAlert, `Mahasiswa gagal diarsipkan: ${error.message}`);
    return;
  }

  archiveStudentModal.hide();
  archiveStudentId = null;
  await Promise.all([loadStudents(), loadDashboardStats()]);
  showAlert(globalAlert, 'Mahasiswa berhasil diarsipkan.', 'success');
}

async function populateStudentSelect(select, selectedId = '') {
  await ensureStudentsLoaded();

  select.innerHTML = '<option value="">Pilih mahasiswa…</option>' + studentsCache
    .filter((student) => student.status !== 'nonaktif')
    .map((student) => `<option value="${student.id}">${escapeHtml(student.full_name)} — ${escapeHtml(student.nim)}</option>`)
    .join('');

  select.value = selectedId || '';
}

async function populateThesisStudentSelect(selectedId = '') {
  await populateStudentSelect($('#thesis-student-id'), selectedId);
}

async function loadTheses() {
  const loader = $('#theses-loading');
  const empty = $('#theses-empty');
  const tableWrap = $('#theses-table-wrap');

  loader.classList.remove('d-none');
  empty.classList.add('d-none');
  tableWrap.classList.add('d-none');

  const { data, error } = await supabase
    .from('theses')
    .select('id,student_id,title,title_en,research_type,research_field,status,current_stage,start_date,approved_date,abstract,keywords,created_at,updated_at,student:students(id,nim,full_name,study_program)')
    .is('deleted_at', null)
    .order('updated_at', { ascending: false });

  loader.classList.add('d-none');

  if (error) {
    showAlert(globalAlert, `Data skripsi gagal dimuat: ${error.message}`);
    return;
  }

  thesesCache = data || [];
  renderTheses();
}

function getFilteredTheses() {
  const keyword = $('#thesis-search').value.trim().toLowerCase();
  const status = $('#thesis-status-filter').value;

  return thesesCache.filter((thesis) => {
    const haystack = [
      thesis.title,
      thesis.title_en,
      thesis.current_stage,
      thesis.research_field,
      thesis.student?.full_name,
      thesis.student?.nim,
    ].join(' ').toLowerCase();

    return (!keyword || haystack.includes(keyword)) && (!status || thesis.status === status);
  });
}

function renderTheses() {
  const tbody = $('#theses-table-body');
  const empty = $('#theses-empty');
  const tableWrap = $('#theses-table-wrap');
  const filtered = getFilteredTheses();

  if (!thesesCache.length) {
    tbody.innerHTML = '';
    tableWrap.classList.add('d-none');
    empty.classList.remove('d-none');
    return;
  }

  empty.classList.add('d-none');
  tableWrap.classList.remove('d-none');

  if (!filtered.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="text-center text-secondary py-5">Tidak ada skripsi yang sesuai dengan pencarian/filter.</td></tr>';
    return;
  }

  tbody.innerHTML = filtered.map((thesis) => `
    <tr>
      <td class="thesis-title-cell">
        <button class="btn btn-link p-0 text-start text-decoration-none fw-semibold thesis-title-button" data-thesis-detail="${thesis.id}">
          ${escapeHtml(thesis.title)}
        </button>
        <div class="text-secondary small mt-1">${escapeHtml(researchTypeLabel(thesis.research_type))}${thesis.research_field ? ' · ' + escapeHtml(thesis.research_field) : ''}</div>
      </td>
      <td>
        <div class="fw-medium">${escapeHtml(thesis.student?.full_name || '-')}</div>
        <div class="text-secondary small">${escapeHtml(thesis.student?.nim || '')}</div>
      </td>
      <td>${escapeHtml(thesis.current_stage || '-')}</td>
      <td>${thesisStatusBadge(thesis.status)}</td>
      <td class="text-end text-nowrap">
        <button class="btn btn-sm btn-light border" data-thesis-detail="${thesis.id}" title="Detail"><i class="bi bi-eye"></i></button>
        <button class="btn btn-sm btn-light border" data-thesis-edit="${thesis.id}" title="Edit"><i class="bi bi-pencil"></i></button>
      </td>
    </tr>
  `).join('');
}

function findThesis(id) {
  return thesesCache.find((thesis) => thesis.id === id);
}

function resetThesisForm() {
  $('#thesis-form').reset();
  $('#thesis-id').value = '';
  $('#thesis-status').value = 'draft';
  $('#thesis-form-title').textContent = 'Tambah Skripsi';
  $('#thesis-save-button').textContent = 'Simpan Skripsi';
  $('#thesis-student-id').disabled = false;
  clearAlert($('#thesis-form-alert'));
}

async function openThesisStart(studentId = '') {
  pendingThesisStudentId = studentId || '';
  thesisStartModal.show();
}

async function openAddThesis(studentId = '') {
  resetThesisForm();

  try {
    await populateThesisStudentSelect(studentId);
    thesisFormModal.show();
  } catch (error) {
    showAlert(globalAlert, `Form skripsi gagal disiapkan: ${error.message}`);
  }
}

async function openEditThesis(id) {
  let thesis = findThesis(id);

  if (!thesis) {
    const { data, error } = await supabase
      .from('theses')
      .select('id,student_id,title,title_en,research_type,research_field,status,current_stage,start_date,approved_date,abstract,keywords')
      .eq('id', id)
      .single();

    if (error) {
      showAlert(globalAlert, error.message);
      return;
    }
    thesis = data;
  }

  resetThesisForm();
  await populateThesisStudentSelect(thesis.student_id);
  $('#thesis-form-title').textContent = 'Edit Skripsi';
  $('#thesis-save-button').textContent = 'Simpan Perubahan';
  $('#thesis-id').value = thesis.id;
  $('#thesis-student-id').value = thesis.student_id;
  $('#thesis-student-id').disabled = true;
  $('#thesis-title').value = thesis.title || '';
  $('#thesis-title-en').value = thesis.title_en || '';
  $('#thesis-research-type').value = thesis.research_type || '';
  $('#thesis-research-field').value = thesis.research_field || '';
  $('#thesis-status').value = thesis.status || 'draft';
  $('#thesis-current-stage').value = thesis.current_stage || '';
  $('#thesis-start-date').value = thesis.start_date || '';
  $('#thesis-approved-date').value = thesis.approved_date || '';
  $('#thesis-keywords').value = Array.isArray(thesis.keywords) ? thesis.keywords.join(', ') : '';
  $('#thesis-abstract').value = thesis.abstract || '';
  thesisFormModal.show();
}

async function saveThesis(event) {
  event.preventDefault();
  clearAlert($('#thesis-form-alert'));

  const button = $('#thesis-save-button');
  const id = $('#thesis-id').value;
  const studentId = $('#thesis-student-id').value;
  const title = $('#thesis-title').value.trim();

  if (!studentId || !title) {
    showAlert($('#thesis-form-alert'), 'Mahasiswa dan judul skripsi wajib diisi.');
    return;
  }

  const keywords = $('#thesis-keywords').value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);

  const payload = {
    student_id: studentId,
    title,
    title_en: $('#thesis-title-en').value.trim() || null,
    research_type: $('#thesis-research-type').value || null,
    research_field: $('#thesis-research-field').value.trim() || null,
    status: $('#thesis-status').value,
    current_stage: $('#thesis-current-stage').value || null,
    start_date: $('#thesis-start-date').value || null,
    approved_date: $('#thesis-approved-date').value || null,
    abstract: $('#thesis-abstract').value.trim() || null,
    keywords: keywords.length ? keywords : null,
  };

  if (!id) {
    const { data: existing, error: existingError } = await supabase
      .from('theses')
      .select('id,title,status')
      .eq('student_id', studentId)
      .neq('status', 'completed')
      .is('deleted_at', null)
      .limit(1);

    if (existingError) {
      showAlert($('#thesis-form-alert'), existingError.message);
      return;
    }

    if (existing?.length) {
      showAlert($('#thesis-form-alert'), 'Mahasiswa ini masih memiliki skripsi aktif. Selesaikan skripsi tersebut sebelum membuat skripsi baru.');
      return;
    }
  }

  setButtonBusy(button, true, id ? 'Menyimpan…' : 'Membuat…');

  if (id) {
    const { error } = await supabase.from('theses').update(payload).eq('id', id);
    setButtonBusy(button, false, '');

    if (error) {
      showAlert($('#thesis-form-alert'), error.message);
      return;
    }
  } else {
    const { data: created, error } = await supabase
      .from('theses')
      .insert(payload)
      .select('id')
      .single();

    if (error) {
      setButtonBusy(button, false, '');
      showAlert($('#thesis-form-alert'), error.message);
      return;
    }

    const sectionRows = defaultThesisSections.map((section) => ({
      thesis_id: created.id,
      ...section,
      status: 'draft',
    }));

    const { error: sectionError } = await supabase.from('thesis_sections').insert(sectionRows);
    setButtonBusy(button, false, '');

    if (sectionError) {
      showAlert($('#thesis-form-alert'), `Skripsi berhasil dibuat, tetapi struktur awal gagal dibuat: ${sectionError.message}`, 'warning');
      return;
    }
  }

  thesisFormModal.hide();
  await Promise.all([loadTheses(), loadDashboardStats()]);
  await showView('theses');
  showAlert(globalAlert, id ? 'Data skripsi berhasil diperbarui.' : 'Skripsi berhasil dibuat beserta struktur BAB awal.', 'success');
}

function resetProposalImport() {
  parsedProposal = null;
  $('#proposal-import-form').reset();
  clearAlert($('#proposal-import-alert'));
  $('#proposal-upload-step').classList.remove('d-none');
  $('#proposal-review-step').classList.add('d-none');
  $('#proposal-processing').classList.add('d-none');
  $('#proposal-save-button').classList.add('d-none');
  $('#proposal-back-button').classList.add('d-none');
  $('#proposal-detected-identity').textContent = '';
  $('#proposal-warnings').innerHTML = '';
  $('#proposal-detected-sections').innerHTML = '';
  $('#proposal-text-preview').innerHTML = '';
}

async function openProposalImport(studentId = '') {
  resetProposalImport();

  try {
    await ensureStudentsLoaded();
    await populateStudentSelect($('#proposal-student-id'), studentId);
    await populateStudentSelect($('#proposal-review-student'), studentId);
    proposalImportModal.show();
  } catch (error) {
    showAlert(globalAlert, `Import proposal gagal disiapkan: ${error.message}`);
  }
}

function matchStudentFromProposal(metadata) {
  if (!studentsCache.length) return null;

  if (metadata.nim) {
    const exactNim = studentsCache.find((student) =>
      normalizeIdentity(student.nim) === normalizeIdentity(metadata.nim)
    );
    if (exactNim) return exactNim;
  }

  if (metadata.student_name) {
    const exactName = studentsCache.find((student) =>
      normalizeIdentity(student.full_name) === normalizeIdentity(metadata.student_name)
    );
    if (exactName) return exactName;
  }

  return null;
}

function renderProposalPreview(result) {
  $('#proposal-summary-file').textContent = `${result.file.name} · ${formatBytes(result.file_size)}`;
  $('#proposal-summary-words').textContent = new Intl.NumberFormat('id-ID').format(result.word_count || 0);
  $('#proposal-summary-paragraphs').textContent = new Intl.NumberFormat('id-ID').format(result.paragraphs.length);
  $('#proposal-summary-sections').textContent = result.sections.length;

  $('#proposal-review-title').value = result.metadata.title || '';
  $('#proposal-review-type').value = result.metadata.research_type || '';
  $('#proposal-review-keywords').value = (result.metadata.keywords || []).join(', ');
  $('#proposal-review-abstract').value = result.metadata.abstract || '';

  const selectedStudentId = $('#proposal-student-id').value;
  const matchedStudent = matchStudentFromProposal(result.metadata);
  const finalStudentId = selectedStudentId || matchedStudent?.id || '';

  $('#proposal-review-student').value = finalStudentId;

  const selectedStudent = studentsCache.find((student) => student.id === finalStudentId);
  $('#proposal-review-field').value = selectedStudent?.study_program || '';

  const detectedParts = [];
  if (result.metadata.student_name) detectedParts.push(`Nama terdeteksi: ${result.metadata.student_name}`);
  if (result.metadata.nim) detectedParts.push(`NIM terdeteksi: ${result.metadata.nim}`);
  if (matchedStudent) detectedParts.push(`Cocok dengan: ${matchedStudent.full_name}`);
  $('#proposal-detected-identity').textContent = detectedParts.join(' · ') || 'Identitas mahasiswa belum terdeteksi otomatis.';

  $('#proposal-detected-sections').innerHTML = result.sections.map((section) => `
    <div class="list-group-item">
      <div class="fw-semibold">${escapeHtml(section.section_code || '')} ${section.section_code ? '—' : ''} ${escapeHtml(section.section_title)}</div>
      <div class="text-secondary small">${escapeHtml(section.section_type)}</div>
    </div>
  `).join('');

  const previewParagraphs = result.paragraphs.slice(0, 40);
  $('#proposal-text-preview').innerHTML = previewParagraphs.map((paragraph) => `
    <div class="proposal-preview-paragraph ${paragraph.paragraph_type === 'heading' ? 'is-heading' : ''}">
      ${escapeHtml(paragraph.text_content)}
    </div>
  `).join('') + (result.paragraphs.length > previewParagraphs.length
    ? `<div class="text-secondary small mt-3">…dan ${result.paragraphs.length - previewParagraphs.length} paragraf lainnya.</div>`
    : '');

  if (result.warnings?.length) {
    $('#proposal-warnings').innerHTML = `
      <div class="alert alert-warning mb-0">
        <div class="fw-semibold mb-1">Catatan parser</div>
        <ul class="mb-0 small">
          ${result.warnings.slice(0, 5).map((warning) => `<li>${escapeHtml(warning)}</li>`).join('')}
        </ul>
      </div>
    `;
  }
}

async function handleProposalFile(file) {
  clearAlert($('#proposal-import-alert'));

  if (!file) return;

  if (file.size > MAX_PROPOSAL_BYTES) {
    showAlert($('#proposal-import-alert'), 'Ukuran file melebihi batas 20 MB.');
    $('#proposal-file').value = '';
    return;
  }

  const extension = file.name.split('.').pop()?.toLowerCase();
  if (!['docx', 'pdf'].includes(extension)) {
    showAlert($('#proposal-import-alert'), 'Gunakan file DOCX atau PDF.');
    $('#proposal-file').value = '';
    return;
  }

  $('#proposal-processing').classList.remove('d-none');
  $('#proposal-processing-text').textContent = extension === 'docx'
    ? 'Membaca struktur Word, heading, paragraf, dan metadata proposal.'
    : 'Membaca teks PDF dan mendeteksi struktur berdasarkan pola dokumen.';

  try {
    parsedProposal = await parseProposalFile(file);
    renderProposalPreview(parsedProposal);

    $('#proposal-upload-step').classList.add('d-none');
    $('#proposal-review-step').classList.remove('d-none');
    $('#proposal-save-button').classList.remove('d-none');
    $('#proposal-back-button').classList.remove('d-none');
  } catch (error) {
    parsedProposal = null;
    showAlert($('#proposal-import-alert'), `Proposal gagal dibaca: ${error.message}`);
  } finally {
    $('#proposal-processing').classList.add('d-none');
  }
}

async function saveProposalImport(event) {
  event.preventDefault();
  clearAlert($('#proposal-import-alert'));

  if (!parsedProposal) {
    showAlert($('#proposal-import-alert'), 'Pilih dan baca file proposal terlebih dahulu.');
    return;
  }

  const studentId = $('#proposal-review-student').value;
  const title = $('#proposal-review-title').value.trim();

  if (!studentId || !title) {
    showAlert($('#proposal-import-alert'), 'Mahasiswa dan judul skripsi wajib dikonfirmasi.');
    return;
  }

  const { data: activeThesis, error: activeError } = await supabase
    .from('theses')
    .select('id,title,status')
    .eq('student_id', studentId)
    .neq('status', 'completed')
    .is('deleted_at', null)
    .limit(1);

  if (activeError) {
    showAlert($('#proposal-import-alert'), activeError.message);
    return;
  }

  if (activeThesis?.length) {
    showAlert($('#proposal-import-alert'), 'Mahasiswa ini sudah memiliki skripsi aktif. Gunakan modul dokumen/versioning untuk upload revisi berikutnya.');
    return;
  }

  const button = $('#proposal-save-button');
  setButtonBusy(button, true, 'Mengunggah & menyimpan…');

  const importId = crypto.randomUUID();
  const path = `${currentUser.id}/${studentId}/proposal-imports/${importId}/${safeFileName(parsedProposal.file.name)}`;

  const fallbackContentType = parsedProposal.file_type === 'pdf'
    ? 'application/pdf'
    : 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';

  const { error: uploadError } = await supabase.storage
    .from(DOCUMENT_BUCKET)
    .upload(path, parsedProposal.file, {
      cacheControl: '3600',
      upsert: false,
      contentType: parsedProposal.file.type || fallbackContentType,
    });

  if (uploadError) {
    setButtonBusy(button, false, '');
    showAlert($('#proposal-import-alert'), `Upload file gagal: ${uploadError.message}`);
    return;
  }

  const keywords = $('#proposal-review-keywords').value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);

  const { data, error } = await supabase.rpc('create_thesis_from_proposal', {
    p_student_id: studentId,
    p_title: title,
    p_title_en: null,
    p_research_type: $('#proposal-review-type').value || null,
    p_research_field: $('#proposal-review-field').value.trim() || null,
    p_abstract: $('#proposal-review-abstract').value.trim() || null,
    p_keywords: keywords.length ? keywords : null,
    p_file_name: parsedProposal.file.name,
    p_file_path: path,
    p_file_type: parsedProposal.file_type,
    p_file_size: parsedProposal.file_size,
    p_file_hash: parsedProposal.file_hash,
    p_extracted_text: parsedProposal.extracted_text,
    p_word_count: parsedProposal.word_count,
    p_sections: parsedProposal.sections,
    p_paragraphs: parsedProposal.paragraphs,
  });

  setButtonBusy(button, false, '');

  if (error) {
    await supabase.storage.from(DOCUMENT_BUCKET).remove([path]);
    showAlert($('#proposal-import-alert'), `Data skripsi gagal dibuat: ${error.message}`);
    return;
  }

  proposalImportModal.hide();
  parsedProposal = null;

  await Promise.all([loadTheses(), loadDashboardStats()]);
  await showView('theses');
  showAlert(globalAlert, 'Proposal berhasil diimport. Skripsi, struktur, dokumen Version 1, dan paragraf berhasil dibuat otomatis.', 'success');

  const thesisId = data?.thesis_id;
  if (thesisId) setTimeout(() => openThesisDetail(thesisId), 250);
}

async function loadThesisDocuments(thesisId) {
  const container = $('#detail-thesis-documents');
  container.innerHTML = '<div class="text-secondary small py-2"><span class="spinner-border spinner-border-sm me-2"></span>Memuat dokumen…</div>';

  const { data: documents, error } = await supabase
    .from('documents')
    .select('id,document_name,document_type,status,current_version_id')
    .eq('thesis_id', thesisId)
    .is('deleted_at', null)
    .order('created_at', { ascending: true });

  if (error) {
    container.innerHTML = `<div class="alert alert-warning mb-0">${escapeHtml(error.message)}</div>`;
    return;
  }

  if (!documents?.length) {
    container.innerHTML = '<div class="empty-inline">Belum ada dokumen yang diunggah.</div>';
    return;
  }

  const documentCards = [];

  for (const documentRecord of documents) {
    const { data: versions, error: versionError } = await supabase
      .from('document_versions')
      .select('id,version_number,file_name,file_path,file_type,file_size,word_count,review_status,uploaded_at')
      .eq('document_id', documentRecord.id)
      .is('deleted_at', null)
      .order('version_number', { ascending: false });

    if (versionError) continue;

    const latest = versions?.[0];

    documentCards.push(`
      <div class="document-card">
        <div class="d-flex flex-wrap justify-content-between align-items-start gap-3">
          <div>
            <div class="fw-semibold"><i class="bi bi-file-earmark-text me-2"></i>${escapeHtml(documentRecord.document_name)}</div>
            <div class="text-secondary small mt-1">
              ${latest ? `Version ${latest.version_number} · ${escapeHtml(latest.file_type.toUpperCase())} · ${formatBytes(latest.file_size || 0)} · ${new Intl.NumberFormat('id-ID').format(latest.word_count || 0)} kata` : 'Belum ada versi'}
            </div>
          </div>
          ${latest ? `
            <button type="button" class="btn btn-sm btn-outline-secondary"
              data-document-download="${escapeHtml(latest.file_path)}"
              data-document-name="${escapeHtml(latest.file_name)}">
              <i class="bi bi-download me-1"></i>Download
            </button>
          ` : ''}
        </div>
      </div>
    `);
  }

  container.innerHTML = documentCards.join('');
}

async function downloadStoredDocument(path, fileName) {
  const { data, error } = await supabase.storage.from(DOCUMENT_BUCKET).download(path);

  if (error) {
    showAlert(globalAlert, `Dokumen gagal diunduh: ${error.message}`);
    return;
  }

  const url = URL.createObjectURL(data);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = fileName || 'dokumen';
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function openThesisDetail(id) {
  detailThesisId = id;

  const { data: thesis, error } = await supabase
    .from('theses')
    .select('id,student_id,title,title_en,research_type,research_field,status,current_stage,start_date,approved_date,abstract,keywords,student:students(id,nim,full_name,study_program)')
    .eq('id', id)
    .single();

  if (error) {
    showAlert(globalAlert, `Detail skripsi gagal dimuat: ${error.message}`);
    return;
  }

  $('#detail-thesis-student').textContent = `${thesis.student?.full_name || '-'} · ${thesis.student?.nim || '-'}`;
  $('#detail-thesis-title').textContent = thesis.title;
  $('#detail-thesis-status').innerHTML = thesisStatusBadge(thesis.status);
  $('#detail-thesis-stage').textContent = valueOrDash(thesis.current_stage);
  $('#detail-thesis-type').textContent = researchTypeLabel(thesis.research_type);
  $('#detail-thesis-field').textContent = valueOrDash(thesis.research_field);
  $('#detail-thesis-start-date').textContent = formatDate(thesis.start_date);
  $('#detail-thesis-approved-date').textContent = formatDate(thesis.approved_date);
  $('#detail-thesis-keywords').textContent = Array.isArray(thesis.keywords) && thesis.keywords.length ? thesis.keywords.join(', ') : '-';
  $('#detail-thesis-title-en').textContent = valueOrDash(thesis.title_en);
  $('#detail-thesis-abstract').textContent = valueOrDash(thesis.abstract);
  $('#detail-thesis-sections').innerHTML = '<div class="text-secondary small py-3"><span class="spinner-border spinner-border-sm me-2"></span>Memuat struktur…</div>';

  thesisDetailModal.show();

  const sectionsPromise = supabase
    .from('thesis_sections')
    .select('id,section_code,section_title,section_type,sort_order,status')
    .eq('thesis_id', id)
    .is('deleted_at', null)
    .order('sort_order', { ascending: true });

  const [, sectionsResult] = await Promise.all([
    loadThesisDocuments(id),
    sectionsPromise,
  ]);

  const container = $('#detail-thesis-sections');

  if (sectionsResult.error) {
    container.innerHTML = `<div class="alert alert-warning mb-0">${escapeHtml(sectionsResult.error.message)}</div>`;
    return;
  }

  const sections = sectionsResult.data;

  if (!sections?.length) {
    container.innerHTML = '<div class="empty-inline">Struktur skripsi belum tersedia.</div>';
    return;
  }

  container.innerHTML = sections.map((section) => `
    <div class="list-group-item d-flex justify-content-between align-items-center gap-3">
      <div>
        <div class="fw-semibold">${escapeHtml(section.section_code || '')} ${section.section_code ? '—' : ''} ${escapeHtml(section.section_title)}</div>
        <div class="text-secondary small">${escapeHtml(section.section_type)}</div>
      </div>
      <span class="badge rounded-pill text-bg-light border text-secondary">${escapeHtml(section.status)}</span>
    </div>
  `).join('');
}

async function renderApp() {
  loading.classList.remove('d-none');
  authScreen.classList.add('d-none');
  dashboardScreen.classList.add('d-none');

  try {
    currentUser = await getCurrentUser();

    if (!currentUser) {
      authScreen.classList.remove('d-none');
      return;
    }

    const profile = await loadProfile(currentUser);
    $('#profile-name').textContent = profile.full_name || 'Dosen';
    $('#profile-email').textContent = profile.email || currentUser.email || '';

    dashboardScreen.classList.remove('d-none');
    await showView('dashboard');

    try {
      await loadDashboardStats();
    } catch (error) {
      showAlert(globalAlert, `Dashboard belum dapat dimuat: ${error.message}`, 'warning');
    }
  } catch (error) {
    currentUser = null;
    showAlert(authAlert, error.message || 'Terjadi kesalahan saat memuat aplikasi.');
    authScreen.classList.remove('d-none');
  } finally {
    loading.classList.add('d-none');
  }
}

$('#login-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  clearAlert(authAlert);

  const button = $('#login-button');
  setButtonBusy(button, true, 'Memproses…');

  const { error } = await supabase.auth.signInWithPassword({
    email: $('#login-email').value.trim(),
    password: $('#login-password').value,
  });

  setButtonBusy(button, false, '');

  if (error) {
    showAlert(authAlert, error.message);
    return;
  }
  await renderApp();
});

$('#register-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  clearAlert(authAlert);

  const button = $('#register-button');
  setButtonBusy(button, true, 'Membuat akun…');

  const { data, error } = await supabase.auth.signUp({
    email: $('#register-email').value.trim(),
    password: $('#register-password').value,
    options: {
      data: {
        full_name: $('#register-name').value.trim(),
        institution: $('#register-institution').value.trim(),
        study_program: $('#register-study-program').value.trim(),
      },
    },
  });

  setButtonBusy(button, false, '');

  if (error) {
    showAlert(authAlert, error.message);
    return;
  }

  if (!data.session) {
    showAlert(authAlert, 'Akun berhasil dibuat. Periksa email Anda untuk konfirmasi, lalu masuk.', 'success');
    event.target.reset();
    return;
  }

  await renderApp();
});

$('#logout-button').addEventListener('click', async () => {
  await supabase.auth.signOut();
  studentsCache = [];
  thesesCache = [];
  parsedProposal = null;
  currentUser = null;
  await renderApp();
});

$$('[data-view-link]').forEach((link) => {
  link.addEventListener('click', async (event) => {
    event.preventDefault();
    await showView(link.dataset.viewLink);
  });
});

$$('[data-add-student]').forEach((button) => button.addEventListener('click', openAddStudent));
$$('[data-add-thesis]').forEach((button) => button.addEventListener('click', () => openThesisStart()));

$('#student-form').addEventListener('submit', saveStudent);
$('#archive-confirm-button').addEventListener('click', archiveStudent);
$('#student-search').addEventListener('input', renderStudents);
$('#student-status-filter').addEventListener('change', renderStudents);
$('#student-refresh').addEventListener('click', loadStudents);

$('#thesis-form').addEventListener('submit', saveThesis);
$('#thesis-search').addEventListener('input', renderTheses);
$('#thesis-status-filter').addEventListener('change', renderTheses);
$('#thesis-refresh').addEventListener('click', loadTheses);

$('#choose-import-proposal').addEventListener('click', () => {
  thesisStartModal.hide();
  setTimeout(() => openProposalImport(pendingThesisStudentId), 180);
});

$('#choose-manual-thesis').addEventListener('click', () => {
  thesisStartModal.hide();
  setTimeout(() => openAddThesis(pendingThesisStudentId), 180);
});

$('#proposal-file').addEventListener('change', async (event) => {
  await handleProposalFile(event.target.files?.[0]);
});

$('#proposal-import-form').addEventListener('submit', saveProposalImport);

$('#proposal-back-button').addEventListener('click', () => {
  $('#proposal-review-step').classList.add('d-none');
  $('#proposal-upload-step').classList.remove('d-none');
  $('#proposal-save-button').classList.add('d-none');
  $('#proposal-back-button').classList.add('d-none');
});

$('#proposal-review-student').addEventListener('change', () => {
  const student = findStudent($('#proposal-review-student').value);
  if (student && !$('#proposal-review-field').value.trim()) {
    $('#proposal-review-field').value = student.study_program || '';
  }
});

$('#students-table-body').addEventListener('click', async (event) => {
  const detailButton = event.target.closest('[data-student-detail]');
  const editButton = event.target.closest('[data-student-edit]');
  const archiveButton = event.target.closest('[data-student-archive]');

  if (detailButton) await openStudentDetail(detailButton.dataset.studentDetail);
  if (editButton) openEditStudent(editButton.dataset.studentEdit);
  if (archiveButton) openArchiveStudent(archiveButton.dataset.studentArchive);
});

$('#theses-table-body').addEventListener('click', async (event) => {
  const detailButton = event.target.closest('[data-thesis-detail]');
  const editButton = event.target.closest('[data-thesis-edit]');

  if (detailButton) await openThesisDetail(detailButton.dataset.thesisDetail);
  if (editButton) await openEditThesis(editButton.dataset.thesisEdit);
});

$('#detail-student-theses').addEventListener('click', async (event) => {
  const button = event.target.closest('[data-thesis-detail]');
  if (!button) return;

  studentDetailModal.hide();
  setTimeout(() => openThesisDetail(button.dataset.thesisDetail), 180);
});

$('#detail-add-thesis').addEventListener('click', () => {
  if (!detailStudentId) return;
  studentDetailModal.hide();
  setTimeout(() => openThesisStart(detailStudentId), 180);
});

$('#detail-edit-student').addEventListener('click', () => {
  if (!detailStudentId) return;
  studentDetailModal.hide();
  setTimeout(() => openEditStudent(detailStudentId), 150);
});

$('#detail-edit-thesis').addEventListener('click', () => {
  if (!detailThesisId) return;
  thesisDetailModal.hide();
  setTimeout(() => openEditThesis(detailThesisId), 180);
});

$('#detail-thesis-documents').addEventListener('click', async (event) => {
  const button = event.target.closest('[data-document-download]');
  if (!button) return;
  await downloadStoredDocument(button.dataset.documentDownload, button.dataset.documentName);
});

document.addEventListener('click', (event) => {
  const comingSoon = event.target.closest('[data-coming-soon]');
  if (!comingSoon) return;

  event.preventDefault();
  showAlert(globalAlert, 'Modul ini akan kita bangun pada tahap berikutnya.', 'info');
});

supabase.auth.onAuthStateChange(() => {
  // Aksi login/logout melakukan render eksplisit agar tidak terjadi render ganda.
});

initPasswordToggles();
renderApp();
