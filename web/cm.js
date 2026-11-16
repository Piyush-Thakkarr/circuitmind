/* Shared by app.html and designs.html: Supabase client, sign-in helpers and the
   build-guide renderer. Plain script, no build step. */
(function(){
  var CM = window.CM = {};

  /* Public Supabase values. The anon key is meant for browsers; row-level security
     in the database is what keeps one user's designs away from another. */
  CM.SUPABASE_URL = 'https://aihjvcqxfesivapwwqkk.supabase.co';
  CM.SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFpaGp2Y3F4ZmVzaXZhcHd3cWtrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzM4MjM0MjUsImV4cCI6MjA4OTM5OTQyNX0.bIbHuiA0Pf2HCq_SdUldR8P5hi4ZO_FmjKZ_cSJrFrs';

  var _sb = null;
  CM.sb = function(){
    if (_sb) return _sb;
    if (!window.supabase) return null;
    _sb = window.supabase.createClient(CM.SUPABASE_URL, CM.SUPABASE_ANON_KEY);
    return _sb;
  };

  CM.esc = function(s){ return String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;'); };
  CM.toast = function(msg){ var t=document.createElement('div'); t.className='toast'; t.textContent=msg; document.body.appendChild(t); setTimeout(function(){ t.remove(); }, 2400); };

  /* Who the user is, in a few words, for the header. */
  CM.whoLabel = function(user){
    if (!user) return '';
    if (user.is_anonymous) return 'guest';
    return user.email || 'signed in';
  };

  CM.minutes = function(ms){ return Math.round(ms/60000*10)/10; };

  /* The guide for a result object from the engine (job.result) or a saved row
     turned back into the same shape. Writes into `body`. */
  CM.renderGuide = function(res, body, opts){
    opts = opts || {};
    var esc = CM.esc;
    if (!res || !res.passed){
      var f=(res && res.failure) || {attempts:[], suggestion:'', examples:[]};
      var n = res && res.attempts ? (res.attempts.length || res.attempts) : '';
      var html='<div class="verdict no">Not verified<small>'+(n ? n+' attempt(s)' : '')+'</small></div>';
      if (f.attempts && f.attempts.length) html+='<div class="sec"><h3>What happened</h3><ul class="notes">'+f.attempts.map(function(a){return '<li>'+esc(a.sentence)+'</li>';}).join('')+'</ul></div>';
      if (f.suggestion) html+='<div class="sec"><h3>What to try</h3><p style="margin:0;color:var(--ink2)">'+esc(f.suggestion)+'</p></div>';
      if (f.examples && f.examples.length && opts.onExample){
        html+='<div class="sec"><h3>Or try an example that is known to pass</h3><div class="chips" data-examples>'+
          f.examples.map(function(p){return '<button class="chip" type="button">'+esc(p)+'</button>';}).join('')+'</div></div>';
      }
      body.innerHTML=html;
      var ex=body.querySelector('[data-examples]');
      if (ex) ex.addEventListener('click', function(e){ if(e.target.classList.contains('chip')) opts.onExample(e.target.textContent); });
      return;
    }
    var g=res.guide, d=res.design;
    var simulated=!!res.simulation;
    var label = simulated ? 'Verified in simulation' : 'Unverified: passed the free checks, not simulated';
    var meta = (res.model||'') + (res.tokens ? ' · '+res.tokens.in+' in / '+res.tokens.out+' out' : '');
    var html='<div class="verdict '+(simulated ? 'ok' : 'warn')+'">'+label+'<small>'+esc(meta)+'</small></div>';
    if (res.notice) html+='<p class="notice">'+esc(res.notice)+'</p>';
    if (simulated && res.checks && res.checks.length){
      html+='<div class="sec"><h3>What the simulator checked</h3><ul class="notes">'+res.checks.map(function(c){return '<li>'+esc(c)+'</li>';}).join('')+
        '</ul><p style="color:var(--ink3);font-size:13px;margin:6px 0 0">Nothing beyond this list was tested. Timing, brightness and anything the prompt implied but did not state were not checked.</p></div>';
    }
    if (g.summary) html+='<p style="margin:0 0 6px">'+esc(g.summary)+'</p>';
    html+='<div class="sec"><h3>Wiring, in order</h3><ol class="steps">'+g.wiring.map(function(s){return '<li>'+esc(s)+'</li>';}).join('')+'</ol></div>';
    html+='<div class="sec"><h3>Parts</h3><table><tr><th>Part</th><th class="n">Qty</th><th class="n">Approx ₹</th></tr>'+
      g.parts.map(function(p){return '<tr><td>'+esc(p.name)+'</td><td class="n">'+p.qty+'</td><td class="n">'+p.approx_inr+'</td></tr>';}).join('')+
      '<tr><td><b>Total</b></td><td></td><td class="n"><b>'+g.total_inr+'</b></td></tr></table></div>';
    html+='<div class="sec"><h3>Before you build</h3><ul class="notes">'+g.notes.map(function(n){return '<li>'+esc(n)+'</li>';}).join('')+'</ul></div>';
    html+='<div class="sec"><h3>Firmware</h3><pre class="code" data-fw>'+esc(g.firmware)+'</pre>'+
      '<div class="toolbar"><button class="btn" type="button" data-copy>Copy code</button>'+
      '<button class="btn" type="button" data-dl-ino>Download sketch.ino</button>'+
      '<button class="btn" type="button" data-dl-diag>Download diagram.json</button>'+
      '<a class="btn" href="https://wokwi.com/projects/new/esp32" target="_blank" rel="noopener">Open Wokwi</a></div>'+
      '<p style="color:var(--ink3);font-size:13px;margin:8px 0 0">In Wokwi: new ESP32 project, replace diagram.json and the sketch with the downloads, press play. It prints <code>'+esc(g.status_line)+'</code> when it works.</p></div>';
    body.innerHTML=html;
    body.querySelector('[data-copy]').addEventListener('click', function(){ navigator.clipboard.writeText(g.firmware).then(function(){CM.toast('Copied');}); });
    function dl(name, text){ var a=document.createElement('a'); a.href=URL.createObjectURL(new Blob([text],{type:'text/plain'})); a.download=name; a.click(); }
    body.querySelector('[data-dl-ino]').addEventListener('click', function(){ dl('sketch.ino', g.firmware); });
    body.querySelector('[data-dl-diag]').addEventListener('click', function(){ dl('diagram.json', typeof res.diagram_json === 'string' ? res.diagram_json : JSON.stringify(res.diagram_json || d, null, 2)); });
  };

  /* A saved row from the designs table, in the shape renderGuide expects. */
  CM.rowToResult = function(row){
    return {
      passed: row.status === 'verified' || row.status === 'free_checks',
      simulation: row.status === 'verified' ? {passed:true} : null,
      notice: row.status === 'free_checks' ? 'This design was not run in the simulator.' : '',
      guide: row.guide, design: row.design, diagram_json: row.diagram,
      checks: row.checks || [], model: row.model || '', tokens: null,
      attempts: row.attempts, failure: row.failure
    };
  };
})();

/* Sign-in: one modal and one session, shared by every page. */
(function(){
  var CM = window.CM;
  var state = { session: null, listeners: [] };

  var MODAL_HTML =
    '<div class="box">'+
      '<h3 id="signinTitle">Sign in</h3>'+
      '<p>Runs are limited to a few per person a day so the free simulator budget lasts the month. Your designs are saved to your account.</p>'+
      '<div class="choice">'+
        '<button class="btn" type="button" data-google><svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path fill="#EA4335" d="M8 6.5v3h4.2c-.2 1-1.3 3-4.2 3a4.5 4.5 0 1 1 0-9c1.3 0 2.1.5 2.6 1l1.8-1.8A7 7 0 0 0 8 1a7 7 0 1 0 0 14c4 0 6.7-2.8 6.7-6.8 0-.5 0-.8-.1-1.2H8z"/></svg>Continue with Google</button>'+
        '<div class="or">or get a sign-in link by email</div>'+
        '<form data-email-form><label for="signinEmail">Email</label><input id="signinEmail" type="email" placeholder="you@example.com" autocomplete="email" required>'+
        '<div class="row" style="justify-content:flex-start"><button class="btn primary" type="submit">Send link</button></div></form>'+
        '<div class="or">or</div>'+
        '<button class="btn" type="button" data-guest>Continue as a guest</button>'+
        '<p style="color:var(--ink3);font-size:12.5px;margin:0">A guest account lives in this browser only; its designs are lost when the browser data is cleared.</p>'+
      '</div>'+
      '<div class="msg" data-msg></div>'+
      '<div class="row"><button class="btn" type="button" data-close>Close</button></div>'+
    '</div>';

  function modal(){
    var m = document.getElementById('signinModal');
    if (m) return m;
    m = document.createElement('div');
    m.className='modal'; m.id='signinModal'; m.hidden=true;
    m.setAttribute('role','dialog'); m.setAttribute('aria-modal','true'); m.setAttribute('aria-labelledby','signinTitle');
    m.innerHTML = MODAL_HTML;
    document.body.appendChild(m);
    var sb = CM.sb();
    var msg = m.querySelector('[data-msg]');
    function say(t, bad){ msg.textContent=t; msg.className='msg'+(bad?' bad':''); }
    var back = location.origin + location.pathname + location.search;
    m.querySelector('[data-close]').addEventListener('click', function(){ m.hidden=true; });
    m.addEventListener('click', function(e){ if (e.target===m) m.hidden=true; });
    m.querySelector('[data-google]').addEventListener('click', function(){
      say('Opening Google…');
      sb.auth.signInWithOAuth({provider:'google', options:{redirectTo: back}}).then(function(r){ if (r.error) say(r.error.message, true); });
    });
    m.querySelector('[data-email-form]').addEventListener('submit', function(e){
      e.preventDefault();
      var email = m.querySelector('#signinEmail').value.trim();
      say('Sending…');
      sb.auth.signInWithOtp({email: email, options:{emailRedirectTo: back}}).then(function(r){
        if (r.error) say(r.error.message, true); else say('Link sent. Open the email on this device and click it.');
      });
    });
    m.querySelector('[data-guest]').addEventListener('click', function(){
      say('Creating a guest account…');
      sb.auth.signInAnonymously().then(function(r){
        if (r.error) say(r.error.message + (/(anonymous|disabled)/i.test(r.error.message) ? ' (guest sign-in is switched off on the server; use Google or email)' : ''), true);
        else { say('Signed in as a guest.'); setTimeout(function(){ m.hidden=true; }, 600); }
      });
    });
    return m;
  }

  CM.auth = {
    ready: function(){ return !!CM.sb(); },
    session: function(){ return state.session; },
    user: function(){ return state.session ? state.session.user : null; },
    token: function(){ return state.session ? state.session.access_token : null; },
    onChange: function(fn){ state.listeners.push(fn); },
    open: function(){ var m = modal(); m.hidden=false; var i=m.querySelector('#signinEmail'); if (i) i.focus(); },
    close: function(){ var m = document.getElementById('signinModal'); if (m) m.hidden=true; },
    signOut: function(){ return CM.sb().auth.signOut(); },
    init: function(){
      var sb = CM.sb();
      if (!sb) return;
      function emit(){ state.listeners.forEach(function(fn){ fn(state.session); }); }
      sb.auth.onAuthStateChange(function(_e, s){ state.session = s; if (s) CM.auth.close(); emit(); });
      sb.auth.getSession().then(function(r){ state.session = r.data.session; emit(); });
    },
    /* Header widget: sign-in button, or who you are with My designs and Sign out. */
    renderHeader: function(el){
      var u = CM.auth.user();
      if (!u){ el.innerHTML='<button class="btn primary" type="button" data-signin>Sign in</button>'; el.querySelector('[data-signin]').addEventListener('click', CM.auth.open); return; }
      el.innerHTML='<span class="who" title="'+CM.esc(u.email||'')+'">'+CM.esc(CM.whoLabel(u))+'</span>'+
        '<a class="btn" href="designs.html">My designs</a><button class="btn" type="button" data-signout>Sign out</button>';
      el.querySelector('[data-signout]').addEventListener('click', function(){ CM.auth.signOut(); });
    },
    /* Rows this user started since midnight UTC, which is what the engine counts. */
    runsToday: function(){
      var sb = CM.sb(); var d = new Date(); d.setUTCHours(0,0,0,0);
      return sb.from('designs').select('id',{count:'exact', head:true}).gte('created_at', d.toISOString()).then(function(r){ return r.error ? null : r.count; });
    }
  };
})();
