/* 主题切换 + 站内搜索 */
(function () {
  var root = document.documentElement;

  function apply(theme) {
    root.dataset.theme = theme;
    try { localStorage.setItem('tl128-theme', theme); } catch (e) {}
  }

  var btn = document.getElementById('theme-toggle');
  if (btn) {
    if (!root.dataset.theme) {
      var prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
      apply(prefersDark ? 'dark' : 'light');
    }
    btn.addEventListener('click', function () {
      apply(root.dataset.theme === 'dark' ? 'light' : 'dark');
    });
  }

  /* 回到顶部悬浮按钮（全站） */
  var toTop = document.getElementById('to-top');
  if (toTop) {
    var toggleTop = function () {
      var y = window.pageYOffset || document.documentElement.scrollTop || 0;
      if (y > 420) toTop.classList.add('show');
      else toTop.classList.remove('show');
    };
    window.addEventListener('scroll', toggleTop, { passive: true });
    toTop.addEventListener('click', function () {
      try { window.scrollTo({ top: 0, behavior: 'smooth' }); }
      catch (e) { window.scrollTo(0, 0); }
    });
    toggleTop();
  }

  /* 文章页顶部阅读进度条 */
  if (document.querySelector('article.post')) {
    var bar = document.createElement('div');
    bar.className = 'progress';
    document.body.appendChild(bar);
    var tick = function () {
      var h = document.documentElement;
      var max = h.scrollHeight - h.clientHeight;
      bar.style.width = (max > 0 ? ((h.scrollTop || document.body.scrollTop) / max) * 100 : 0) + '%';
    };
    window.addEventListener('scroll', tick, { passive: true });
    tick();
  }

  /* 字号调节（记忆在本地） */
  var ctrl = document.querySelector('.font-ctrl');
  if (ctrl) {
    var LEVELS = { '0': '17.5px', '1': '19px', '2': '20.5px' };
    var KEY = 'tl128-fs';
    var applyFs = function (lv) {
      var size = LEVELS[String(lv)] || LEVELS['0'];
      document.documentElement.style.setProperty('--reading-size', size);
      try { localStorage.setItem(KEY, String(lv)); } catch (e) {}
    };
    var level = 0;
    try { level = parseInt(localStorage.getItem(KEY) || '0', 10) || 0; } catch (e) {}
    applyFs(level);
    ctrl.addEventListener('click', function (ev) {
      var b = ev.target.closest('button[data-fs]');
      if (!b) return;
      var act = b.getAttribute('data-fs');
      if (act === 'up') level = Math.min(2, level + 1);
      else if (act === 'down') level = Math.max(0, level - 1);
      else level = 0;
      applyFs(level);
    });
  }

  /* 图片灯箱 */
  var prose = document.querySelector('.prose');
  if (prose) {
    prose.addEventListener('click', function (ev) {
      var img = ev.target;
      if (img.tagName !== 'IMG') return;
      ev.preventDefault();
      var box = document.createElement('div');
      box.className = 'lightbox';
      var big = document.createElement('img');
      big.src = img.getAttribute('src');
      big.alt = img.getAttribute('alt') || '';
      box.appendChild(big);
      var close = function () {
        box.remove();
        document.removeEventListener('keydown', onKey);
      };
      var onKey = function (e) { if (e.key === 'Escape') close(); };
      box.addEventListener('click', close);
      document.addEventListener('keydown', onKey);
      document.body.appendChild(box);
    });
  }

  var input = document.getElementById('q');
  if (!input) return;

  var results = document.getElementById('results');
  var hint = document.getElementById('hint');
  var index = null;

  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }

  function load() {
    if (index) return Promise.resolve(index);
    return fetch('search.json').then(function (r) { return r.json(); }).then(function (data) {
      index = data;
      return index;
    });
  }

  function render(q) {
    var kw = q.trim().toLowerCase();
    results.innerHTML = '';
    if (!kw) { hint.textContent = '共 ' + index.length + ' 篇，输入即搜。'; return; }
    var hits = index.filter(function (p) {
      return (p.t + ' ' + p.g.join(' ') + ' ' + p.c).toLowerCase().indexOf(kw) >= 0;
    });
    hint.textContent = hits.length ? '找到 ' + hits.length + ' 篇' : '没有匹配的文章';
    hits.slice(0, 40).forEach(function (p) {
      var li = document.createElement('li');
      li.className = 'item';
      var tags = (p.g || []).map(function (t) {
        return '<a class="tag" href="tag/' + encodeURIComponent(t) + '.html">' + esc(t) + '</a>';
      }).join('');
      li.innerHTML = '<div class="item-row"><a class="item-title" href="' + p.u + '">'
        + esc(p.t) + '</a><span class="item-right">' + tags
        + '<time class="item-date">' + esc(p.d) + '</time></span></div>'
        + '<p class="item-sum">' + esc(p.s) + '</p>';
      results.appendChild(li);
    });
  }

  load().then(function () {
    var initial = '';
    try { initial = new URLSearchParams(location.search).get('q') || ''; } catch (e) {}
    if (initial && !input.value) input.value = initial;
    render(input.value);
  });

  var timer = null;
  input.addEventListener('input', function () {
    clearTimeout(timer);
    timer = setTimeout(function () {
      render(input.value);
      try {
        var u = new URL(location.href);
        if (input.value.trim()) u.searchParams.set('q', input.value.trim());
        else u.searchParams.delete('q');
        history.replaceState(null, '', u.toString());
      } catch (e) {}
    }, 120);
  });
})();
