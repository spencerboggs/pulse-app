// Auth toggles login versus sign up and blocks submit until passwords match on the sign up path.
// Flask handles credential storage, this file only manages visibility and lightweight validation.

const loginBtn = document.getElementById('btn-login');
const signupBtn = document.getElementById('btn-signup');
const loginFormSection = document.getElementById('login-form');
const signupFormSection = document.getElementById('signup-form');
const signupWarning = document.getElementById('signup-warning');

// Shows the login card and styles the toggle so the active mode reads as primary.
function showLogin() {
  loginFormSection.hidden = false;
  signupFormSection.hidden = true;
  loginBtn.classList.add('btn-primary');
  loginBtn.classList.remove('btn-ghost');
  signupBtn.classList.add('btn-ghost');
  signupBtn.classList.remove('btn-primary');
}

// Shows the signup card and mirrors the button styling swap for the other mode.
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

// Default entry state presents login first per common return visitor expectations.
showLogin();

const loginForm = document.getElementById('form-login');
const signupForm = document.getElementById('form-signup');

if (loginForm) {
  loginForm.setAttribute('method', 'POST');
  loginForm.setAttribute('action', '/login');
  // Do NOT prevent default. Let the browser submit the form.
}

if (signupForm) {
  signupForm.setAttribute('method', 'POST');
  signupForm.setAttribute('action', '/signup');

  // Blocks navigation only when confirmation text differs, otherwise the POST reaches signup.
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