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
      li.innerHTML = '<div class="item-line"><a class="item-title" href="' + p.u + '">'
        + esc(p.t) + '</a><time class="item-date">' + esc(p.d) + '</time></div>'
        + '<p class="item-sum">' + esc(p.s) + '</p>';
      results.appendChild(li);
    });
  }

  load().then(function () { render(input.value); });

  var timer = null;
  input.addEventListener('input', function () {
    clearTimeout(timer);
    timer = setTimeout(function () { render(input.value); }, 120);
  });
})();
