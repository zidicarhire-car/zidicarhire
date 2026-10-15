/*
 * Date-range calendar for the booking popup. Vanilla JS, no library.
 * Two months side by side when there's room, one on phones. Swipe or use the arrow buttons to
 * change month. Keyboard: arrow keys move a day/week, Home/End jump to the week's start/end,
 * Page Up/Down change month, Enter or Space picks the day.
 *
 * A booking holds the car from pick-up day up to (not including) return day, so a fully booked
 * day can still be chosen as the return day, but never as the pick-up day or in between.
 */
(function () {
  const DAY_MS = 86400000;
  const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  const LONG_DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
  const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September',
    'October', 'November', 'December'];

  const parse = (iso) => { const [y, m, d] = iso.split('-').map(Number); return new Date(y, m - 1, d, 12); };
  const iso = (dt) => `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}`;
  const addDays = (s, n) => { const dt = parse(s); dt.setDate(dt.getDate() + n); return iso(dt); };
  const diffDays = (a, b) => Math.round((parse(b) - parse(a)) / DAY_MS);
  const monthStart = (s) => { const dt = parse(s); return iso(new Date(dt.getFullYear(), dt.getMonth(), 1, 12)); };
  const addMonths = (s, n) => { const dt = parse(s); return iso(new Date(dt.getFullYear(), dt.getMonth() + n, 1, 12)); };

  class RangeCalendar {
    constructor(el, opts) {
      this.el = el;
      this.min = opts.min;                      // first selectable day (ISO)
      this.max = opts.max || addDays(opts.min, 365);
      this.maxDays = opts.maxDays || 60;
      this.onChange = opts.onChange || (() => {});
      this.onMessage = opts.onMessage || (() => {});
      this.onPick = opts.onPick || null;
      this.unavailable = new Set();
      this.start = null;
      this.end = null;
      this.view = monthStart(this.min);
      this.focused = this.min;
      // One month, or two side by side when the calendar itself is wide enough (e.g. the popup on a desktop).
      this.months = 1;
      if (window.ResizeObserver) {
        new ResizeObserver(() => {
          const n = this.el.clientWidth >= 560 ? 2 : 1;
          if (n !== this.months) { this.months = n; this.render(); }
        }).observe(this.el);
      }
      this.uid = `rc${Math.random().toString(36).slice(2, 7)}`;
      this.bind();
      this.render();
    }

    /* ---------- rules ---------- */
    isBlocked(day) { return this.unavailable.has(day); }
    outOfRange(day) { return day < this.min || day > this.max; }

    /* Days in [from, to) that are fully booked. */
    firstBlockedBetween(from, to) {
      for (let d = from; d < to; d = addDays(d, 1)) if (this.isBlocked(d)) return d;
      return null;
    }

    canStart(day) { return !this.outOfRange(day) && !this.isBlocked(day); }

    canEnd(day) {
      if (!this.start || day <= this.start || this.outOfRange(day)) return false;
      if (diffDays(this.start, day) > this.maxDays) return false;
      return !this.firstBlockedBetween(this.start, day);
    }

    /* ---------- public ---------- */
    setUnavailable(days) {
      this.unavailable = new Set(days);
      if (this.start && this.isBlocked(this.start)) { this.start = null; this.end = null; this.onChange(null, null); }
      else if (this.end && !this.canEnd(this.end)) { this.end = null; this.onChange(this.start, null); }
      this.render();
    }

    /* Returns '' on success, or a message explaining why the range can't be used. */
    setRange(start, end) {
      if (!this.canStart(start)) {
        if (!this.outOfRange(start)) { this.view = monthStart(start); this.focused = start; this.render(); }
        return this.isBlocked(start) ? 'The car is booked on that pick-up day.' : 'Choose a pick-up day from today onwards.';
      }
      this.start = start;
      this.end = null;
      if (end) {
        if (!this.canEnd(end)) {
          this.render();
          this.onChange(this.start, null);
          return this.explainEnd(end);
        }
        this.end = end;
      }
      this.focused = end || start;
      this.view = monthStart(start);
      this.render();
      this.onChange(this.start, this.end);
      return '';
    }

    clear() { this.start = null; this.end = null; this.render(); this.onChange(null, null); }

    explainEnd(day) {
      if (diffDays(this.start, day) > this.maxDays) return `Hires can be up to ${this.maxDays} days. Chat with us for longer.`;
      const blocked = this.firstBlockedBetween(this.start, day);
      if (blocked) {
        const dt = parse(blocked);
        return `The car is booked from ${LONG_DAYS[dt.getDay()]} ${dt.getDate()} ${MONTHS[dt.getMonth()]}. Choose a return day on or before then.`;
      }
      return 'Choose a return day after the pick-up day.';
    }

    pick(day) {
      if (this.outOfRange(day)) return;
      if (this.onPick) {   // preview mode: hand the day to the page instead of selecting it
        if (this.canStart(day)) this.onPick(day);
        else this.onMessage('The car is booked that day. Choose another day.');
        this.focused = day;
        this.render(true);
        return;
      }
      if (this.start && !this.end && day > this.start) {
        if (this.canEnd(day)) {
          this.end = day;
          this.onMessage('');
          this.onChange(this.start, this.end);
        } else if (this.canStart(day)) {
          this.onMessage(`${this.explainEnd(day)} Starting again from this day.`);
          this.start = day; this.end = null; this.onChange(this.start, null);
        } else {
          this.onMessage(this.explainEnd(day));
        }
      } else if (this.canStart(day)) {
        this.start = day; this.end = null;
        this.onMessage('');
        this.onChange(this.start, null);
      } else {
        this.onMessage('The car is booked that day. Choose another pick-up day.');
      }
      this.focused = day;
      this.render(true);
    }

    /* ---------- rendering ---------- */
    monthsShown() { return this.months; }

    render(keepFocus) {
      const months = this.monthsShown();
      const lastView = addMonths(monthStart(this.max), 1 - months);
      if (this.view > lastView) this.view = lastView;
      if (this.view < monthStart(this.min)) this.view = monthStart(this.min);
      const visibleEnd = addDays(addMonths(this.view, months), -1);
      if (this.focused < this.view || this.focused > visibleEnd) this.focused = this.view < this.min ? this.min : this.view;
      const hadFocus = keepFocus || this.el.contains(document.activeElement);

      let html = `<div class="rc-nav">
        <button type="button" class="icon-btn rc-prev" aria-label="Previous month"${this.view <= monthStart(this.min) ? ' disabled' : ''}>
          <i class="bi bi-chevron-left" aria-hidden="true"></i></button>
        <button type="button" class="icon-btn rc-next" aria-label="Next month"${this.view >= lastView ? ' disabled' : ''}>
          <i class="bi bi-chevron-right" aria-hidden="true"></i></button>
      </div><div class="rc-months">`;
      for (let m = 0; m < months; m += 1) html += this.monthHtml(addMonths(this.view, m), m);
      html += '</div><p class="rc-key"><span><span class="rc-key-swatch rc-key-booked" aria-hidden="true">8</span> Booked</span>'
        + '<span><span class="rc-key-swatch rc-key-picked" aria-hidden="true">8</span> Your dates</span></p>';
      this.el.innerHTML = html;
      if (hadFocus) this.el.querySelector(`[data-date="${this.focused}"]`)?.focus();
    }

    monthHtml(first, idx) {
      const dt = parse(first);
      const titleId = `${this.uid}-m${idx}`;
      const lead = (dt.getDay() + 6) % 7;     // Monday-first weeks
      const daysInMonth = new Date(dt.getFullYear(), dt.getMonth() + 1, 0).getDate();
      const today = this.min;
      let cells = '';
      for (let i = 0; i < lead; i += 1) cells += '<td role="gridcell"></td>';
      for (let d = 1; d <= daysInMonth; d += 1) {
        const day = iso(new Date(dt.getFullYear(), dt.getMonth(), d, 12));
        const cls = ['rc-day'];
        let state = '';
        const selectingEnd = this.start && !this.end;
        const disabled = selectingEnd ? !this.canEnd(day) && !this.canStart(day)
          : !this.canStart(day) && day !== this.end;
        if (this.outOfRange(day)) cls.push('is-out');
        if (this.isBlocked(day)) { cls.push('is-booked'); state = ', booked'; }
        if (day === today) cls.push('is-today');
        if (day === this.start) { cls.push('is-start'); state += ', pick-up day'; }
        if (day === this.end) { cls.push('is-end'); state += ', return day'; }
        if (this.start && this.end && day > this.start && day < this.end) cls.push('in-range');
        if (selectingEnd && this.canEnd(day)) cls.push('can-end');
        const wd = parse(day);
        const label = `${LONG_DAYS[wd.getDay()]} ${d} ${MONTHS[wd.getMonth()]} ${wd.getFullYear()}${state}`;
        const selected = day === this.start || day === this.end || cls.includes('in-range');
        cells += `<td role="gridcell" aria-selected="${selected}"><button type="button" class="${cls.join(' ')}" data-date="${day}"
          tabindex="${day === this.focused ? 0 : -1}" aria-label="${label}"${disabled ? ' aria-disabled="true"' : ''}>${d}</button></td>`;
        if ((lead + d) % 7 === 0 && d !== daysInMonth) cells += '</tr><tr>';
      }
      const head = WEEKDAYS.map((w) => `<th scope="col" abbr="${w}">${w.slice(0, 2)}</th>`).join('');
      return `<div class="rc-month"><h4 class="rc-title" id="${titleId}">${MONTHS[dt.getMonth()]} ${dt.getFullYear()}</h4>
        <table class="rc-grid" role="grid" aria-labelledby="${titleId}"><thead><tr>${head}</tr></thead><tbody><tr>${cells}</tr></tbody></table></div>`;
    }

    /* ---------- interaction ---------- */
    shift(months) {
      this.view = addMonths(this.view, months);
      this.focused = this.view < this.min ? this.min : this.view;
      this.render(true);
    }

    moveFocus(day) {
      if (day < this.min) day = this.min;
      if (day > this.max) day = this.max;
      this.focused = day;
      const visibleEnd = addDays(addMonths(this.view, this.monthsShown()), -1);
      if (day < this.view || day > visibleEnd) this.view = monthStart(day < this.view ? day : addMonths(monthStart(day), 1 - this.monthsShown()));
      this.render(true);
    }

    bind() {
      this.el.addEventListener('click', (e) => {
        if (e.target.closest('.rc-prev')) { this.shift(-1); return; }
        if (e.target.closest('.rc-next')) { this.shift(1); return; }
        // Unavailable days still respond, so pick() can explain why they can't be chosen.
        const btn = e.target.closest('.rc-day');
        if (btn) this.pick(btn.dataset.date);
      });
      this.el.addEventListener('keydown', (e) => {
        const btn = e.target.closest('.rc-day');
        if (!btn) return;
        const day = btn.dataset.date;
        const wd = (parse(day).getDay() + 6) % 7;
        const moves = {
          ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7, Home: -wd, End: 6 - wd,
        };
        if (e.key in moves) { e.preventDefault(); this.moveFocus(addDays(day, moves[e.key])); }
        else if (e.key === 'PageUp' || e.key === 'PageDown') {
          e.preventDefault();
          const dt = parse(day);
          const target = new Date(dt.getFullYear(), dt.getMonth() + (e.key === 'PageUp' ? -1 : 1), 1, 12);
          const last = new Date(target.getFullYear(), target.getMonth() + 1, 0).getDate();
          target.setDate(Math.min(dt.getDate(), last));
          this.moveFocus(iso(target));
        } else if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          this.pick(day);
        }
      });
      let touchX = null;
      let touchY = null;
      this.el.addEventListener('touchstart', (e) => { touchX = e.touches[0].clientX; touchY = e.touches[0].clientY; }, { passive: true });
      this.el.addEventListener('touchend', (e) => {
        if (touchX === null) return;
        const dx = e.changedTouches[0].clientX - touchX;
        const dy = e.changedTouches[0].clientY - touchY;
        touchX = null;
        if (Math.abs(dx) > 45 && Math.abs(dx) > Math.abs(dy) * 1.5) {
          const next = dx < 0;
          const btn = this.el.querySelector(next ? '.rc-next' : '.rc-prev');
          if (btn && !btn.disabled) this.shift(next ? 1 : -1);
        }
      }, { passive: true });
    }
  }

  RangeCalendar.addDays = addDays;
  RangeCalendar.diffDays = diffDays;
  RangeCalendar.parse = parse;
  RangeCalendar.iso = iso;
  window.RangeCalendar = RangeCalendar;
})();
