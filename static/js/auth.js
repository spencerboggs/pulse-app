// Controls and sections
const loginBtn = document.getElementById('btn-login');
const signupBtn = document.getElementById('btn-signup');
const loginFormSection = document.getElementById('login-form');
const signupFormSection = document.getElementById('signup-form');
const signupWarning = document.getElementById('signup-warning');

// Switch to login view
function showLogin() {
  loginFormSection.hidden = false;
  signupFormSection.hidden = true;
  loginBtn.classList.add('btn-primary');
  loginBtn.classList.remove('btn-ghost');
  signupBtn.classList.add('btn-ghost');
  signupBtn.classList.remove('btn-primary');
}

// Switch to signup view
function showSignup() {
  loginFormSection.hidden = true;
  signupFormSection.hidden = false;
  signupBtn.classList.add('btn-primary');
  signupBtn.classList.remove('btn-ghost');
  loginBtn.classList.add('btn-ghost');
  loginBtn.classList.remove('btn-primary');
}

loginBtn?.addEventListener('click', () => showLogin());
signupBtn?.addEventListener('click', () => showSignup());

// Default to login on load
showLogin();

// Login submit
document.getElementById('form-login')?.addEventListener('submit', (e) => {
  e.preventDefault();
  const data = Object.fromEntries(new FormData(e.currentTarget).entries());
  console.log('[Pulse] Login submit:', data);
  alert('database not set up yet btw');
  window.location.href = '/home';
});

// Signup submit
document.getElementById('form-signup')?.addEventListener('submit', (e) => {
  e.preventDefault();
  const data = Object.fromEntries(new FormData(e.currentTarget).entries());
  console.log('[Pulse] Signup submit:', data);
  if (signupWarning) signupWarning.hidden = true;
  const password = data.password || '';
  const confirm = data.confirmPassword || '';
  if (password !== confirm) {
    if (signupWarning) signupWarning.hidden = false;
    return;
  }
  alert('database not set up yet btw');
  window.location.href = '/home';
});


