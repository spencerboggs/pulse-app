const loginBtn = document.getElementById('btn-login');
const signupBtn = document.getElementById('btn-signup');
const loginFormSection = document.getElementById('login-form');
const signupFormSection = document.getElementById('signup-form');
const signupWarning = document.getElementById('signup-warning');

function showLogin() {
  loginFormSection.hidden = false;
  signupFormSection.hidden = true;
  loginBtn.classList.add('btn-primary');
  loginBtn.classList.remove('btn-ghost');
  signupBtn.classList.add('btn-ghost');
  signupBtn.classList.remove('btn-primary');
}

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

showLogin();

// ---- Make forms POST to Flask ----
const loginForm = document.getElementById('form-login');
const signupForm = document.getElementById('form-signup');

if (loginForm) {
  loginForm.setAttribute('method', 'POST');
  loginForm.setAttribute('action', '/login');
  // Do NOT prevent default — let the browser submit
}

if (signupForm) {
  signupForm.setAttribute('method', 'POST');
  signupForm.setAttribute('action', '/signup');

  // Keep client-side password match check, but still submit to Flask if OK
  signupForm.addEventListener('submit', (e) => {
    if (signupWarning) signupWarning.hidden = true;

    const fd = new FormData(signupForm);
    const password = (fd.get('password') || '').toString();
    const confirm = (fd.get('confirmPassword') || '').toString();

    if (password !== confirm) {
      e.preventDefault();
      if (signupWarning) signupWarning.hidden = false;
    }
  });
}