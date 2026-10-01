/**
 * KBO 기록실 표 복사 북마클릿 (소스).
 *
 * 설치: 아래 함수를 "javascript:(function(){...})();" 한 줄로 압축해 브라우저 북마크의
 * 주소(URL)로 저장한다 (북마크 이름은 자유, 주소란에 압축한 javascript: 코드를 붙여넣기).
 * 압축은 이 파일을 고칠 때마다 다시 해야 한다 — 수동으로 하지 말고 스크립트로 한다:
 *   node -e "console.log('javascript:'+encodeURIComponent(require('fs').readFileSync('kbo_table_picker.bookmarklet.js','utf8').replace(/\/\*[\s\S]*?\*\//g,'').replace(/\s+/g,' ').trim()))"
 *
 * 사용: KBO 기록실(타자·투수·수비·주루 기록, 일정) 페이지에서 이 북마크를 클릭하면 표마다
 * 주황색으로 하이라이트되고, 원하는 표를 클릭하면 그 표의 모든 행을 탭 구분 텍스트로 뽑아
 * 클립보드에 복사한다 (복사가 막힌 사이트면 미리보기 창에서 Ctrl+C). 그 결과를
 * KWB/import/<연도>/ 안의 .txt 파일에 그대로 붙여넣고 tools/kbo_import.py 를 돌리면 된다.
 *
 * KBO 서버에 추가 요청을 보내지 않는다 — 사용자가 이미 띄워 놓은 페이지의 화면에 보이는
 * 내용을 읽을 뿐이다 (지금까지 손으로 드래그해서 복사하던 것과 같은 동작, 선택 범위만 정확해짐).
 */
(function () {
  if (window.__kboPickerActive) return;
  window.__kboPickerActive = true;

  var overlay = document.createElement('div');
  overlay.style.cssText = 'position:fixed;z-index:999999;pointer-events:none;' +
    'background:rgba(255,170,0,.35);border:2px solid #ff8c00;display:none;';
  document.body.appendChild(overlay);

  var hint = document.createElement('div');
  hint.textContent = '복사할 표를 클릭하세요 (Esc: 취소)';
  hint.style.cssText = 'position:fixed;top:8px;left:8px;z-index:999999;background:#222;' +
    'color:#fff;padding:6px 10px;border-radius:6px;font-size:13px;font-family:sans-serif;';
  document.body.appendChild(hint);

  function cleanup() {
    window.__kboPickerActive = false;
    document.removeEventListener('mousemove', onMove, true);
    document.removeEventListener('click', onClick, true);
    document.removeEventListener('keydown', onKey, true);
    overlay.remove();
    hint.remove();
  }

  function findTable(el) {
    while (el && el !== document.body) {
      if (el.tagName === 'TABLE') return el;
      el = el.parentElement;
    }
    return null;
  }

  function onMove(e) {
    var t = findTable(e.target);
    if (t) {
      var r = t.getBoundingClientRect();
      overlay.style.display = 'block';
      overlay.style.left = r.left + 'px';
      overlay.style.top = r.top + 'px';
      overlay.style.width = r.width + 'px';
      overlay.style.height = r.height + 'px';
    } else {
      overlay.style.display = 'none';
    }
  }

  function extract(table) {
    var rows = [];
    table.querySelectorAll('tr').forEach(function (tr) {
      var cells = tr.querySelectorAll('td,th');
      if (!cells.length) return;
      var line = Array.prototype.map.call(cells, function (c) {
        return c.innerText.replace(/\s+/g, ' ').trim();
      }).join('\t');
      if (line.replace(/\t/g, '').trim()) rows.push(line);
    });
    return rows.join('\n');
  }

  function showResult(text) {
    var rowCount = text ? text.split('\n').length : 0;
    var box = document.createElement('div');
    box.style.cssText = 'position:fixed;inset:10% 10%;z-index:1000000;background:#fff;' +
      'border:2px solid #333;border-radius:8px;padding:12px;display:flex;' +
      'flex-direction:column;box-shadow:0 4px 20px rgba(0,0,0,.4);';
    var label = document.createElement('div');
    label.style.cssText = 'font-family:sans-serif;font-size:13px;margin-bottom:6px;color:#222;';
    label.textContent = rowCount + '행 추출됨.';
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.cssText = 'flex:1;width:100%;box-sizing:border-box;font-family:monospace;font-size:12px;';
    var btnRow = document.createElement('div');
    btnRow.style.cssText = 'margin-top:8px;text-align:right;';
    var closeBtn = document.createElement('button');
    closeBtn.textContent = '닫기';
    closeBtn.onclick = function () { box.remove(); };
    btnRow.appendChild(closeBtn);
    box.appendChild(label);
    box.appendChild(ta);
    box.appendChild(btnRow);
    document.body.appendChild(box);
    ta.focus();
    ta.select();
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () {
        label.textContent = rowCount + '행 복사됨 (클립보드) — .txt 파일에 그대로 붙여넣으세요.';
      }).catch(function () {
        label.textContent = rowCount + '행 추출됨 — 클립보드 복사가 막혀 있어 아래에서 Ctrl+C 로 복사하세요.';
      });
    } else {
      label.textContent = rowCount + '행 추출됨 — 아래에서 Ctrl+C 로 복사하세요.';
    }
  }

  function onClick(e) {
    var t = findTable(e.target);
    if (!t) return;
    e.preventDefault();
    e.stopPropagation();
    cleanup();
    showResult(extract(t));
  }

  function onKey(e) {
    if (e.key === 'Escape') cleanup();
  }

  document.addEventListener('mousemove', onMove, true);
  document.addEventListener('click', onClick, true);
  document.addEventListener('keydown', onKey, true);
})();
