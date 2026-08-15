/* تقویم جلالی — بدون هیچ وابستگی.
 *
 * به هر <input class="jdate"> یک تقویم فارسی وصل می‌کند. مقدار نوشته‌شده در
 * ورودی همیشه به شکل ۱۴۰۵/۰۵/۳۱ است؛ تبدیل به میلادی سمت سرور انجام می‌شود.
 */
(function () {
  "use strict";

  var MONTHS = ["فروردین","اردیبهشت","خرداد","تیر","مرداد","شهریور",
                "مهر","آبان","آذر","دی","بهمن","اسفند"];
  var WEEKDAYS = ["ش","ی","د","س","چ","پ","ج"];
  var FA = "۰۱۲۳۴۵۶۷۸۹";

  function fa(n) { return String(n).replace(/\d/g, function (d) { return FA[+d]; }); }
  function en(s) { return String(s).replace(/[۰-۹]/g, function (d) { return FA.indexOf(d); }); }
  function div(a, b) { return ~~(a / b); }

  // ---- تبدیل میلادی ↔ جلالی
  function toJalali(gy, gm, gd) {
    var gdm = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334];
    var jy = gy <= 1600 ? 0 : 979;
    gy -= gy <= 1600 ? 621 : 1600;
    var gy2 = gm > 2 ? gy + 1 : gy;
    var days = 365 * gy + div(gy2 + 3, 4) - div(gy2 + 99, 100) + div(gy2 + 399, 400)
             - 80 + gd + gdm[gm - 1];
    jy += 33 * div(days, 12053);
    days %= 12053;
    jy += 4 * div(days, 1461);
    days %= 1461;
    if (days > 365) { jy += div(days - 1, 365); days = (days - 1) % 365; }
    var jm = days < 186 ? 1 + div(days, 31) : 7 + div(days - 186, 30);
    var jd = 1 + (days < 186 ? days % 31 : (days - 186) % 30);
    return [jy, jm, jd];
  }

  function toGregorian(jy, jm, jd) {
    var gy = jy <= 979 ? 621 : 1600;
    jy -= jy <= 979 ? 0 : 979;
    var days = 365 * jy + div(jy, 33) * 8 + div((jy % 33) + 3, 4) + 78 + jd
             + (jm < 7 ? (jm - 1) * 31 : (jm - 7) * 30 + 186);
    gy += 400 * div(days, 146097);
    days %= 146097;
    if (days > 36524) {
      gy += 100 * div(--days, 36524);
      days %= 36524;
      if (days >= 365) days++;
    }
    gy += 4 * div(days, 1461);
    days %= 1461;
    if (days > 365) { gy += div(days - 1, 365); days = (days - 1) % 365; }
    var gd = days + 1;
    var leap = (gy % 4 === 0 && gy % 100 !== 0) || gy % 400 === 0;
    var lens = [0, 31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    var gm = 0;
    for (gm = 1; gm <= 12 && gd > lens[gm]; gm++) gd -= lens[gm];
    return [gy, gm, gd];
  }

  function jMonthLength(jy, jm) {
    if (jm <= 6) return 31;
    if (jm <= 11) return 30;
    // اسفند: با تبدیل ۱ فروردین سال بعد تشخیص داده می‌شود
    var next = toGregorian(jy + 1, 1, 1);
    var d = new Date(next[0], next[1] - 1, next[2]);
    d.setDate(d.getDate() - 1);
    return toJalali(d.getFullYear(), d.getMonth() + 1, d.getDate())[2];
  }

  function todayJalali() {
    var n = new Date();
    return toJalali(n.getFullYear(), n.getMonth() + 1, n.getDate());
  }

  function parse(text) {
    var parts = en(text || "").replace(/-/g, "/").split("/").filter(Boolean);
    if (parts.length !== 3) return null;
    var y = +parts[0], m = +parts[1], d = +parts[2];
    if (!y || m < 1 || m > 12 || d < 1 || d > 31) return null;
    return [y, m, d];
  }

  function format(y, m, d) {
    return fa(y) + "/" + fa(("0" + m).slice(-2)) + "/" + fa(("0" + d).slice(-2));
  }

  // ---- ساخت پنل تقویم
  var panel = null, current = null, view = null;

  function build() {
    panel = document.createElement("div");
    panel.className = "jdate-panel";
    panel.hidden = true;
    panel.addEventListener("mousedown", function (e) { e.preventDefault(); });
    document.body.appendChild(panel);
  }

  function render() {
    var jy = view[0], jm = view[1];
    var len = jMonthLength(jy, jm);
    var g = toGregorian(jy, jm, 1);
    // ۰=شنبه … ۶=جمعه
    var firstCol = (new Date(g[0], g[1] - 1, g[2]).getDay() + 1) % 7;
    var t = todayJalali();
    var sel = parse(current ? current.value : "");

    var html = '<div class="jdate-head">' +
      '<button type="button" data-nav="-1" aria-label="ماه قبل">‹</button>' +
      '<div class="jdate-title">' +
        '<select data-role="month">' + MONTHS.map(function (name, i) {
          return '<option value="' + (i + 1) + '"' + (i + 1 === jm ? " selected" : "") + '>' + name + "</option>";
        }).join("") + "</select>" +
        '<input data-role="year" value="' + fa(jy) + '" inputmode="numeric">' +
      "</div>" +
      '<button type="button" data-nav="1" aria-label="ماه بعد">›</button>' +
      "</div><div class=\"jdate-grid\">";

    WEEKDAYS.forEach(function (w) { html += '<span class="jdate-dow">' + w + "</span>"; });
    for (var i = 0; i < firstCol; i++) html += "<span></span>";
    for (var d = 1; d <= len; d++) {
      var cls = "jdate-day";
      if (sel && sel[0] === jy && sel[1] === jm && sel[2] === d) cls += " selected";
      if (t[0] === jy && t[1] === jm && t[2] === d) cls += " today";
      html += '<button type="button" class="' + cls + '" data-day="' + d + '">' + fa(d) + "</button>";
    }
    html += '</div><div class="jdate-foot">' +
      '<button type="button" data-today="1">امروز</button>' +
      '<button type="button" data-clear="1">پاک کردن</button></div>';
    panel.innerHTML = html;
  }

  function place(input) {
    var r = input.getBoundingClientRect();
    panel.hidden = false;
    var top = r.bottom + window.scrollY + 4;
    // اگر پایین صفحه جا نبود، بالای ورودی باز شود
    if (r.bottom + panel.offsetHeight + 8 > window.innerHeight) {
      top = r.top + window.scrollY - panel.offsetHeight - 4;
    }
    panel.style.top = Math.max(top, 8) + "px";
    panel.style.left = Math.max(r.left + window.scrollX, 8) + "px";
  }

  function open(input) {
    current = input;
    view = parse(input.value) || todayJalali();
    render();
    place(input);
  }

  function close() { if (panel) panel.hidden = true; current = null; }

  function pick(d) {
    current.value = format(view[0], view[1], d);
    current.dispatchEvent(new Event("change", { bubbles: true }));
    close();
  }

  document.addEventListener("focusin", function (e) {
    if (e.target.classList && e.target.classList.contains("jdate")) {
      if (!panel) build();
      open(e.target);
    }
  });

  document.addEventListener("click", function (e) {
    if (!panel || panel.hidden) return;
    if (panel.contains(e.target)) return;
    if (e.target.classList && e.target.classList.contains("jdate")) return;
    close();
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") close();
  });

  document.addEventListener("click", function (e) {
    if (!panel || panel.hidden || !panel.contains(e.target)) return;
    var el = e.target;
    if (el.dataset.day) return pick(+el.dataset.day);
    if (el.dataset.nav) {
      view[1] += +el.dataset.nav;
      if (view[1] < 1) { view[1] = 12; view[0]--; }
      if (view[1] > 12) { view[1] = 1; view[0]++; }
      return render();
    }
    if (el.dataset.today) {
      var t = todayJalali();
      view = t;
      return pick(t[2]);
    }
    if (el.dataset.clear) {
      current.value = "";
      current.dispatchEvent(new Event("change", { bubbles: true }));
      return close();
    }
  });

  document.addEventListener("change", function (e) {
    if (!panel || panel.hidden) return;
    if (e.target.dataset && e.target.dataset.role === "month") {
      view[1] = +e.target.value;
      render();
    }
  });

  document.addEventListener("input", function (e) {
    if (!panel || panel.hidden) return;
    if (e.target.dataset && e.target.dataset.role === "year") {
      var y = +en(e.target.value);
      if (y >= 1200 && y <= 1600) { view[0] = y; render(); }
    }
  });

  // ورودی دستی: ارقام لاتین به فارسی و افزودن خودکار «/»
  document.addEventListener("input", function (e) {
    var el = e.target;
    if (!el.classList || !el.classList.contains("jdate")) return;
    var digits = en(el.value).replace(/\D/g, "").slice(0, 8);
    var out = digits.slice(0, 4);
    if (digits.length > 4) out += "/" + digits.slice(4, 6);
    if (digits.length > 6) out += "/" + digits.slice(6, 8);
    el.value = fa(out);
  });
})();
