import { createClient } from 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.57.4/+esm';
import { SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY } from './config.js';

const supabase = createClient(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY);

const $ = (selector) => document.querySelector(selector);
const loading = $('#app-loading');
const authScreen = $('#auth-screen');
const dashboardScreen = $('#dashboard-screen');
const authAlert = $('#auth-alert');
const dashboardAlert = $('#dashboard-alert');

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

async function renderApp() {
  loading.classList.remove('d-none');
  authScreen.classList.add('d-none');
  dashboardScreen.classList.add('d-none');

  try {
    const user = await getCurrentUser();

    if (!user) {
      authScreen.classList.remove('d-none');
      return;
    }

    const profile = await loadProfile(user);

    $('#profile-name').textContent = profile.full_name || 'Dosen';
    $('#profile-email').textContent = profile.email || user.email || '';

    dashboardScreen.classList.remove('d-none');

    try {
      await loadDashboardStats();
    } catch (error) {
      showAlert(dashboardAlert, `Dashboard belum dapat dimuat: ${error.message}`, 'warning');
    }
  } catch (error) {
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
  await renderApp();
});

document.querySelectorAll('[data-coming-soon]').forEach((element) => {
  element.addEventListener('click', (event) => {
    event.preventDefault();
    showAlert(dashboardAlert, 'Modul ini akan kita bangun pada tahap berikutnya.', 'info');
  });
});

supabase.auth.onAuthStateChange(() => {
  // Render eksplisit dilakukan oleh aksi login/logout untuk mencegah render ganda.
});

renderApp();
