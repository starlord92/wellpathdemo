/* Hotkeys Solution — client-side auth (demo only, no real backend) */
var auth = {
  key: 'hk_user',
  signIn: function(email, password) {
    var allowedEmail = 'sumanths909@gmail.com';
    var allowedPassword = 'SAIsumanth@14';
    var e = (email || '').trim().toLowerCase();
    var p = (password || '').trim();
    if (e === allowedEmail && p === allowedPassword) {
      try {
        localStorage.setItem(this.key, JSON.stringify({ email: allowedEmail, at: Date.now() }));
      } catch (e) {}
      return true;
    }
    return false;
  },
  signOut: function() {
    try {
      localStorage.removeItem(this.key);
      if (typeof sessionStorage !== 'undefined') sessionStorage.removeItem('hk_marco_pw');
    } catch (e) {}
  },
  getuser: function() {
    try {
      var raw = localStorage.getItem(this.key);
      return raw ? JSON.parse(raw) : null;
    } catch (e) {
      return null;
    }
  },
  isLoggedIn: function() {
    return !!this.getuser();
  }
};
