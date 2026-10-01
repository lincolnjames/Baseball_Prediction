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
 * 표가 여러 페이지로 나뉘어 있으면(예: 투수 10페이지) 페이지마다 이 북마크를 눌러 표를
 * 고르고 "누적에 추가"를 누른다 — 브라우저(localStorage)에 계속 쌓이다가, 마지막 페이지까지
 * 끝나면 그 누적분이 클립보드에 있다. 다음 표 종류로 넘어가기 전엔 "누적 비우기"로 비운다.
 * 같은 줄을 두 번 추가해도 kbo_import.py 가 동일 값은 그냥 무시하므로 문제없다.
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
  var bufferedNow = localStorage.getItem('__kboPickerBuffer') || '';
  hint.textContent = '복사할 표를 클릭하세요 (Esc: 취소)' +
    (bufferedNow ? ' — 누적 중: ' + bufferedNow.split('\n').filter(function (l) { return l.trim(); }).length + '행' : '');
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

  var BUFFER_KEY = '__kboPickerBuffer';

  function countRows(text) {
    return text ? text.split('\n').filter(function (l) { return l.trim(); }).length : 0;
  }

  function copyToClipboard(text, onDone) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { onDone(true); }).catch(function () { onDone(false); });
    } else {
      onDone(false);
    }
  }

  function showResult(text) {
    var box = document.createElement('div');
    box.style.cssText = 'position:fixed;inset:10% 10%;z-index:1000000;background:#fff;' +
      'border:2px solid #333;border-radius:8px;padding:12px;display:flex;' +
      'flex-direction:column;box-shadow:0 4px 20px rgba(0,0,0,.4);';
    var label = document.createElement('div');
    label.style.cssText = 'font-family:sans-serif;font-size:13px;margin-bottom:6px;color:#222;';
    var buffered = localStorage.getItem(BUFFER_KEY) || '';
    label.textContent = countRows(text) + '행 추출됨.' +
      (buffered ? ' (현재 누적 ' + countRows(buffered) + '행 — 아직 클립보드에 안 반영됨)' : '');
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.cssText = 'flex:1;width:100%;box-sizing:border-box;font-family:monospace;font-size:12px;';
    var btnRow = document.createElement('div');
    btnRow.style.cssText = 'margin-top:8px;text-align:right;';

    function addButton(label_, onClick) {
      var btn = document.createElement('button');
      btn.textContent = label_;
      btn.style.marginLeft = '6px';
      btn.onclick = onClick;
      btnRow.appendChild(btn);
      return btn;
    }

    addButton('이번 표만 복사', function () {
      copyToClipboard(text, function (ok) {
        label.textContent = ok ? countRows(text) + '행 복사됨 (클립보드).' : '클립보드 복사 실패 — 위 textarea 에서 Ctrl+C 하세요.';
      });
    });
    addButton('누적에 추가', function () {
      var merged = buffered ? buffered + '\n' + text : text;
      localStorage.setItem(BUFFER_KEY, merged);
      buffered = merged;
      copyToClipboard(merged, function (ok) {
        label.textContent = (ok ? '클립보드에 반영됨: ' : '클립보드 복사 실패, 아래 textarea 에서 직접 복사하세요: ') +
          countRows(merged) + '행 누적. 다음 페이지에서도 같은 방법으로 이어 붙이세요.';
        ta.value = merged;
      });
    });
    addButton('누적 비우기', function () {
      localStorage.removeItem(BUFFER_KEY);
      buffered = '';
      label.textContent = '누적을 비웠습니다. 다음 표 종류부터 새로 쌓으세요.';
    });
    addButton('닫기', function () { box.remove(); });

    box.appendChild(label);
    box.appendChild(ta);
    box.appendChild(btnRow);
    document.body.appendChild(box);
    ta.focus();
    ta.select();
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
