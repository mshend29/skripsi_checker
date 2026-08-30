import { createClient } from 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.57.4/+esm';
import { SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY } from './config.js';

const supabase = createClient(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY);

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => document.querySelectorAll(selector);

const loading = $('#app-loading');
const authScreen = $('#auth-screen');
const dashboardScreen = $('#dashboard-screen');
const authAlert = $('#auth-alert');
const globalAlert = $('#global-alert');

let currentUser = null;
let studentsCache = [];
let detailStudentId = null;
let archiveStudentId = null;

const studentFormModal = new bootstrap.Modal($('#studentFormModal'));
const studentDetailModal = new bootstrap.Modal($('#studentDetailModal'));
const archiveStudentModal = new bootstrap.Modal($('#archiveStudentModal'));

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
  if (!button.dataset.defaultText) {
    button.dataset.defaultText = button.textContent;
  }

  button.disabled = busy;
  button.textContent = busy ? busyText : button.dataset.defaultText;
}

function valueOrDash(value) {
  const text = String(value ?? '').trim();
  return text || '-';
}

function statusBadge(status) {
  const labels = {
    aktif: ['Aktif', 'success'],
    lulus: ['Lulus', 'primary'],
    nonaktif: ['Nonaktif', 'secondary'],
  };

  const [label, variant] = labels[status] || [status || '-', 'secondary'];
  return `<span class="badge text-bg-${variant} fw-medium">${escapeHtml(label)}</span>`;
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

  if (viewName === 'students') {
    await loadStudents();
  }
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

    const matchesKeyword = !keyword || haystack.includes(keyword);
    const matchesStatus = !status || student.status === status;

    return matchesKeyword && matchesStatus;
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
    tbody.innerHTML = `
      <tr>
        <td colspan="5" class="text-center text-secondary py-5">
          Tidak ada mahasiswa yang sesuai dengan pencarian/filter.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = filtered.map((student) => `
    <tr>
      <td>
        <button class="student-name-button btn btn-link p-0 text-start text-decoration-none fw-semibold"
          data-student-detail="${student.id}">
          ${escapeHtml(student.full_name)}
        </button>
        <div class="text-secondary small">${escapeHtml(student.email || '')}</div>
      </td>
      <td class="text-nowrap">${escapeHtml(student.nim)}</td>
      <td>${escapeHtml(student.study_program || '-')}</td>
      <td>${statusBadge(student.status)}</td>
      <td class="text-end text-nowrap">
        <button class="btn btn-sm btn-light border" data-student-detail="${student.id}" title="Detail">
          <i class="bi bi-eye"></i>
        </button>
        <button class="btn btn-sm btn-light border" data-student-edit="${student.id}" title="Edit">
          <i class="bi bi-pencil"></i>
        </button>
        <button class="btn btn-sm btn-light border text-danger" data-student-archive="${student.id}" title="Arsipkan">
          <i class="bi bi-archive"></i>
        </button>
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

function openStudentDetail(id) {
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
  $('#detail-student-status').innerHTML = statusBadge(student.status);
  $('#detail-student-notes').textContent = valueOrDash(student.notes);

  studentDetailModal.show();
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
    ({ error } = await supabase
      .from('students')
      .update(payload)
      .eq('id', id));
  } else {
    ({ error } = await supabase
      .from('students')
      .insert({
        ...payload,
        created_by: currentUser.id,
      }));
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

  const email = $('#register-email').value.trim();
  const password = $('#register-password').value;
  const metadata = {
    full_name: $('#register-name').value.trim(),
    institution: $('#register-institution').value.trim(),
    study_program: $('#register-study-program').value.trim(),
  };

  const { data, error } = await supabase.auth.signUp({
    email,
    password,
    options: { data: metadata },
  });

  setButtonBusy(button, false, '');

  if (error) {
    showAlert(authAlert, error.message);
    return;
  }

  if (!data.session) {
    showAlert(
      authAlert,
      'Akun berhasil dibuat. Periksa email Anda untuk konfirmasi, lalu masuk.',
      'success'
    );
    event.target.reset();
    return;
  }

  await renderApp();
});

$('#logout-button').addEventListener('click', async () => {
  await supabase.auth.signOut();
  studentsCache = [];
  currentUser = null;
  await renderApp();
});

$$('[data-view-link]').forEach((link) => {
  link.addEventListener('click', async (event) => {
    event.preventDefault();
    await showView(link.dataset.viewLink);
  });
});

$$('[data-add-student]').forEach((button) => {
  button.addEventListener('click', openAddStudent);
});

$('#student-form').addEventListener('submit', saveStudent);
$('#archive-confirm-button').addEventListener('click', archiveStudent);
$('#student-search').addEventListener('input', renderStudents);
$('#student-status-filter').addEventListener('change', renderStudents);
$('#student-refresh').addEventListener('click', loadStudents);

$('#students-table-body').addEventListener('click', (event) => {
  const detailButton = event.target.closest('[data-student-detail]');
  const editButton = event.target.closest('[data-student-edit]');
  const archiveButton = event.target.closest('[data-student-archive]');

  if (detailButton) openStudentDetail(detailButton.dataset.studentDetail);
  if (editButton) openEditStudent(editButton.dataset.studentEdit);
  if (archiveButton) openArchiveStudent(archiveButton.dataset.studentArchive);
});

$('#detail-edit-student').addEventListener('click', () => {
  if (!detailStudentId) return;
  studentDetailModal.hide();
  setTimeout(() => openEditStudent(detailStudentId), 150);
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
