'use strict';

/* ── Constants ───────────────────────────────────────────────────────────────── */
const POS_ORDER = ['Goalkeeper', 'Defender', 'Midfielder', 'Forward'];
const POS_SHORT = { Goalkeeper: 'GK', Defender: 'DEF', Midfielder: 'MID', Forward: 'FWD' };
const POS_CLASS = { Goalkeeper: 'pos-gk', Defender: 'pos-def', Midfielder: 'pos-mid', Forward: 'pos-fwd' };

/* ── Mutable season state ────────────────────────────────────────────────────── */
let currentSeason = null;
function dataBase() { return `data/${currentSeason}`; }

/* ── State ────────────────────────────────────────────────────────────────────── */
let store    = null;   // { challenges, predicted, actual }
let filter   = 'all';
let sortKey  = 'num-asc';

/* ── Data loading ─────────────────────────────────────────────────────────────── */
async function loadData() {
  const base = dataBase();
  const opts = { cache: 'no-cache' };
  const [challenges, predicted, actual, outcome] = await Promise.all([
    fetch(`${base}/challenges.json`, opts).then(r => r.json()),
    fetch(`${base}/predicted_optimal.json`, opts).then(r => r.json()).catch(() => ({})),
    fetch(`${base}/actual_optimal.json`, opts).then(r => r.json()).catch(() => ({})),
    fetch(`${base}/actual_outcome.json`, opts).then(r => r.json()).catch(() => null),
  ]);
  return { challenges, predicted, actual, outcome };
}

/* ── Utilities ────────────────────────────────────────────────────────────────── */
function fmt(n, dp = 1) {
  return typeof n === 'number' ? n.toFixed(dp) : '—';
}

function fmtNum(n) {
  return n.toLocaleString('en-GB');
}

function playersFlat(lineup) {
  const out = [];
  for (const pos of POS_ORDER) {
    for (const p of (lineup.Players[pos] || [])) {
      out.push({ ...p, Position: pos });
    }
  }
  return out;
}

function playerIds(lineup) {
  return new Set(playersFlat(lineup).map(p => p.ID));
}

function computeOverlap(pred, actual) {
  const pIds = playerIds(pred);
  const aIds = playerIds(actual);
  let shared = 0;
  for (const id of pIds) if (aIds.has(id)) shared++;
  const total = Math.max(pIds.size, aIds.size);
  return { shared, total, pct: total > 0 ? shared / total : 0 };
}

function statusOf(key, predicted, actual) {
  const hasPred = key in predicted;
  const hasAct  = key in actual;
  if (hasPred && hasAct) return 'complete';
  if (hasPred) return 'predicted';
  if (hasAct)  return 'actual';
  return 'pending';
}

function overlapColour(pct) {
  if (pct >= 0.5)  return 'var(--accent)';
  if (pct >= 0.25) return 'var(--gold)';
  return 'var(--red)';
}

function badgeHTML(status) {
  const map = {
    complete:  ['Complete',       'badge-complete'],
    predicted: ['Projected',      'badge-predicted'],
    actual:    ['Result only',    'badge-actual'],
    pending:   ['Pending',        'badge-pending'],
  };
  const [label, cls] = map[status] || map.pending;
  return `<span class="badge ${cls}">${label}</span>`;
}

/* ── Stats strip ──────────────────────────────────────────────────────────────── */
function renderStats() {
  const { challenges, predicted, actual } = store;
  const keys = Object.keys(challenges);

  let complete = 0, inProgress = 0, totalPtsCaptured = 0, ptsCapturedCount = 0;
  for (const key of keys) {
    const s = statusOf(key, predicted, actual);
    if (s === 'complete') {
      complete++;
      const oe  = store.outcome?.[key];
      const opt = actual[key]?.Total_Points;
      if (oe?.Total_Points != null && opt > 0) {
        totalPtsCaptured += oe.Total_Points / opt;
        ptsCapturedCount++;
      }
    } else if (s === 'predicted') {
      inProgress++;
    }
  }

  const avgCaptured = ptsCapturedCount > 0 ? `${(totalPtsCaptured / ptsCapturedCount * 100).toFixed(0)}%` : '—';

  const strip = document.getElementById('stats-strip');
  const cells = strip.querySelectorAll('.stat-cell');
  const values  = [keys.length, complete, inProgress, avgCaptured];
  const colours  = ['var(--text)', 'var(--accent)', 'var(--blue)', 'var(--text)'];

  cells.forEach((cell, i) => {
    const val = cell.querySelector('.stat-value');
    if (val) {
      val.textContent = values[i];
      val.style.color = colours[i];
    }
  });

}


/* ── Season standing ─────────────────────────────────────────────────────────── */
function renderStanding() {
  const outcome = store.outcome;
  const section = document.getElementById('standing-section');
  if (!outcome) { section.style.display = 'none'; return; }

  // Collect only numeric gameweek keys, exclude top-level metadata like total_players
  const gwKeys = Object.keys(outcome)
    .filter(k => !isNaN(Number(k)))
    .map(Number)
    .sort((a, b) => a - b);

  if (gwKeys.length === 0) { section.style.display = 'none'; return; }

  const lastGw = gwKeys[gwKeys.length - 1];
  const ranks  = outcome[String(lastGw)]?.Ranks;
  if (!ranks?.overall_rank) { section.style.display = 'none'; return; }

  const totalPlayers = typeof outcome.total_players === 'number' ? outcome.total_players : null;

  // Percentage position: rank / total * 100, rounded to one decimal place
  const pctText = (totalPlayers && ranks.overall_rank)
    ? `top ${(ranks.overall_rank / totalPlayers * 100).toFixed(1)}% of players`
    : null;

  document.getElementById('standing-rank').textContent =
    `#${fmtNum(ranks.overall_rank)}`;
  document.getElementById('standing-of').textContent =
    totalPlayers ? `/ ${fmtNum(totalPlayers)}` : '';
  document.getElementById('standing-pct').textContent = pctText ?? '';
  document.getElementById('standing-pct').style.display = pctText ? '' : 'none';
  document.getElementById('standing-gw').textContent =
    `after GW${lastGw}`;

  section.style.display = '';
}

/* ── Challenge grid ───────────────────────────────────────────────────────────── */
function sortedKeys() {
  const { challenges, predicted, actual } = store;
  let keys = Object.keys(challenges).map(Number);

  // Apply filter
  keys = keys.filter(n => {
    const s = statusOf(String(n), predicted, actual);
    if (filter === 'all') return true;
    return s === filter;
  });

  // Apply sort
  keys.sort((a, b) => {
    const ka = String(a), kb = String(b);
    switch (sortKey) {
      case 'num-desc':
        return b - a;
      case 'overlap-desc': {
        const sa = statusOf(ka, predicted, actual);
        const sb = statusOf(kb, predicted, actual);
        const pa = sa === 'complete' ? computeOverlap(predicted[ka], actual[ka]).pct : -1;
        const pb = sb === 'complete' ? computeOverlap(predicted[kb], actual[kb]).pct : -1;
        return pb - pa || a - b;
      }
      case 'pts-desc': {
        const pa = actual[ka] ? actual[ka].Total_Points : predicted[ka] ? predicted[ka].Total_Points : 0;
        const pb = actual[kb] ? actual[kb].Total_Points : predicted[kb] ? predicted[kb].Total_Points : 0;
        return pb - pa || a - b;
      }
      case 'ratio-desc':
      case 'ratio-asc': {
        const oe_a = store.outcome?.[ka];
        const oe_b = store.outcome?.[kb];
        const ra = (oe_a?.Total_Points != null && actual[ka]?.Total_Points > 0) ? oe_a.Total_Points / actual[ka].Total_Points : null;
        const rb = (oe_b?.Total_Points != null && actual[kb]?.Total_Points > 0) ? oe_b.Total_Points / actual[kb].Total_Points : null;
        // Push challenges without outcome data to the end
        if (ra === null && rb === null) return a - b;
        if (ra === null) return 1;
        if (rb === null) return -1;
        return sortKey === 'ratio-desc' ? rb - ra || a - b : ra - rb || a - b;
      }
      case 'scored-desc': {
        const pa = store.outcome?.[ka]?.Total_Points ?? -1;
        const pb = store.outcome?.[kb]?.Total_Points ?? -1;
        return pb - pa || a - b;
      }
      case 'gw-rank-asc': {
        const ra = store.outcome?.[ka]?.Ranks?.rank ?? Infinity;
        const rb = store.outcome?.[kb]?.Ranks?.rank ?? Infinity;
        return ra - rb || a - b;
      }
      default: // num-asc
        return a - b;
    }
  });

  return keys;
}

function renderGrid() {
  const { challenges, predicted, actual, outcome } = store;
  const grid = document.getElementById('challenge-grid');
  const keys = sortedKeys();

  if (keys.length === 0) {
    grid.innerHTML = `<div class="empty-state">No challenges match this filter.</div>`;
    return;
  }

  grid.innerHTML = keys.map(n => {
    const key    = String(n);
    const ch     = challenges[key];
    const status = statusOf(key, predicted, actual);
    const hasBoth = status === 'complete';
    const hasPred = status === 'complete' || status === 'predicted';
    const hasAct  = status === 'complete' || status === 'actual';
    const num     = String(n).padStart(2, '0');

    let footer = '';

    if (hasBoth) {
      const ov    = computeOverlap(predicted[key], actual[key]);
      const fillW = (ov.pct * 100).toFixed(1);
      const oe    = outcome?.[key];
      const opt   = actual[key].Total_Points;

      // ±delta: my score vs model's prediction
      const gap = (oe?.Total_Points != null)
        ? Math.round(oe.Total_Points - predicted[key].Total_Points)
        : null;
      const gapColour = gap !== null ? (gap >= 0 ? 'var(--accent)' : 'var(--red)') : null;

      // % of optimal ceiling captured
      const pctOpt = (oe?.Total_Points != null && opt > 0)
        ? Math.round(oe.Total_Points / opt * 100)
        : null;

      let outcomeRow = '';
      if (oe?.Total_Points != null) {
        const leftParts = [`Scored <span class="mono" style="color:var(--text-muted);">${oe.Total_Points} pts</span>`];
        if (pctOpt !== null) leftParts.push(`<span class="mono" style="color:var(--text-faint);">${pctOpt}% of optimal</span>`);
        const rightParts = [];
        if (gap !== null) rightParts.push(`<span class="mono" style="color:${gapColour};">${gap >= 0 ? '+' : ''}${gap} vs pred</span>`);
        if (oe.Ranks?.rank != null) rightParts.push(`GW #${fmtNum(oe.Ranks.rank)}`);
        outcomeRow = `<div class="outcome-row"><span>${leftParts.join(' · ')}</span><span style="color:var(--text-faint);">${rightParts.join(' · ')}</span></div>`;
      }

      footer = `
        <div class="card-footer">
          <div class="pts-row">
            <span>
              <span class="pts-pred">${fmt(predicted[key].Total_Points)}</span>
              <span class="pts-arrow">&rarr;</span>
              <span class="pts-actual">${fmt(actual[key].Total_Points)}</span>
              <span style="font-size:11px; color:var(--text-faint); margin-left:3px;">pts</span>
            </span>
            <span class="player-match">${ov.shared}/${ov.total} players</span>
          </div>
          <div class="acc-track">
            <div class="acc-fill" style="width:${fillW}%;"></div>
          </div>
          ${outcomeRow}
        </div>`;
    } else if (hasPred) {
      footer = `
        <div class="card-footer">
          <span style="font-size:12px; color:var(--text-muted);">
            Projected <span class="mono" style="color:var(--blue);">${fmt(predicted[key].Total_Points)} pts</span>
          </span>
        </div>`;
    } else if (hasAct) {
      const oe      = outcome?.[key];
      const outcomeRow = oe?.Ranks?.rank != null
        ? `<div class="outcome-row"><span>Scored <span class="mono" style="color:var(--text-muted);">${oe.Total_Points} pts</span></span><span>GW #${fmtNum(oe.Ranks.rank)}</span></div>`
        : '';
      footer = `
        <div class="card-footer">
          <span style="font-size:12px; color:var(--text-muted);">
            Actual optimal <span class="mono" style="color:var(--text);">${fmt(actual[key].Total_Points)} pts</span>
          </span>
          ${outcomeRow}
        </div>`;
    }

    return `
      <article
        class="challenge-card"
        data-id="${n}"
        data-status="${status}"
        ${status !== 'pending' ? 'role="button" tabindex="0"' : 'tabindex="-1"'}
        aria-label="${status !== 'pending' ? 'Open challenge ' + n + ': ' + ch.title : 'Challenge ' + n + ': ' + ch.title + ' \u2014 pending'}"
      >
        <div class="card-header">
          <span class="card-num">${num}</span>
          ${badgeHTML(status)}
        </div>
        <div class="card-body">
          <div class="card-title">${ch.title}</div>
          <div class="card-desc">${ch.description.trim()}</div>
        </div>
        ${footer}
      </article>`;
  }).join('');

  // Attach events — pending cards are not interactive
  grid.querySelectorAll('.challenge-card').forEach(card => {
    if (card.dataset.status === 'pending') return;
    card.addEventListener('click', () => openModal(Number(card.dataset.id)));
    card.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openModal(Number(card.dataset.id)); }
    });
  });
}

/* ── Filter / sort controls ───────────────────────────────────────────────────── */
document.querySelectorAll('.chip').forEach(chip => {
  chip.addEventListener('click', () => {
    document.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
    chip.classList.add('active');
    filter = chip.dataset.filter;
    if (store) renderGrid();
  });
});

document.getElementById('sort-select').addEventListener('change', e => {
  sortKey = e.target.value;
  if (store) renderGrid();
});

/* ── Modal ────────────────────────────────────────────────────────────────────── */
function positionSection(players, isActual, sharedIds, outcomeMap = null) {
  return players.map(p => {
    const isShared  = sharedIds.has(p.ID);
    const isCaptain = p.Captain;
    const rowCls    = isShared ? 'shared' : isCaptain ? 'is-captain' : '';
    const ptsValue  = isActual ? p.Points : p.Predicted_Points;
    const ptsColour = isActual ? 'color:var(--text);' : 'color:var(--text-muted);';
    const baseActualPts    = (!isActual && outcomeMap) ? (outcomeMap[p.ID] ?? null) : null;
    // Apply captain doubling relative to this column's captain, not the source lineup's
    const displayActualPts  = baseActualPts != null ? baseActualPts * (isCaptain ? 2 : 1) : null;
    const ptsLabel  = isActual
      ? 'pts'
      : displayActualPts != null
        ? `<span style="color:var(--text-faint);">${displayActualPts}pts &middot;</span> <span style="color:var(--text-muted);">xPts</span>`
        : '<span style="color:var(--text-muted);">xPts</span>';

    return `
      <div class="player-row ${rowCls}">
        <span class="pos-badge ${POS_CLASS[p.Position]}">${POS_SHORT[p.Position]}</span>
        <div style="flex:1; min-width:0;">
          <div style="display:flex; align-items:center; gap:5px;">
            <span class="player-name" style="font-weight:${isCaptain ? 600 : 400};">${p.Name}</span>
            ${isCaptain ? '<span class="captain-c">C</span>' : ''}
            ${isShared  ? '<span class="shared-tick">&#10003;</span>' : ''}
          </div>
          <div class="player-meta">${p.Team} &middot; &pound;${p.Cost.toFixed(1)}m</div>
        </div>
        <div class="player-pts-col">
          <div class="player-pts" style="${ptsColour}">${fmt(ptsValue)}</div>
          <div class="pts-kind">${ptsLabel}</div>
        </div>
      </div>`;
  }).join('');
}

function openModal(id) {
  const { challenges, predicted, actual } = store;
  const key         = String(id);
  const ch          = challenges[key];
  const pred        = predicted[key];
  const act         = actual[key];
  const outcomeData = store.outcome?.[key] ?? null;

  // Header
  document.getElementById('modal-challenge-num').textContent = `Challenge ${String(id).padStart(2, '0')}`;
  document.getElementById('modal-title').textContent = ch.title;
  document.getElementById('modal-desc').textContent  = ch.description.trim();

  // Compute shared IDs for row highlighting
  const sharedIds = new Set();
  if (pred && act) {
    const pIds = playerIds(pred);
    const aIds = playerIds(act);
    for (const id of pIds) if (aIds.has(id)) sharedIds.add(id);
  }

  // Build player ID → BASE points map (captain doubling stripped) so each column
  // can apply the multiplier relative to its own captain, not the source lineup's.
  const outcomeMap = {};
  if (act) playersFlat(act).forEach(p => { outcomeMap[p.ID] = p.Captain ? p.Points / 2 : p.Points; });
  if (outcomeData) playersFlat(outcomeData).forEach(p => {
    if (!(p.ID in outcomeMap)) outcomeMap[p.ID] = p.Captain ? p.Points / 2 : p.Points;
  });
  const predOutcomeMap = (pred && (act || outcomeData)) ? outcomeMap : null;

  // Totals row
  const totals = document.getElementById('modal-totals');
  totals.className = 'modal-split';
  if (pred && act && outcomeData) {
    totals.classList.add('modal-split--three-col');
    totals.innerHTML = `
      <div class="split-col">
        <div class="total-cell">
          <div class="eyebrow total-label">Predicted</div>
          <div class="total-val" style="color:var(--text-muted);">${fmt(pred.Total_Points)}</div>
          <div class="total-sub">xPts projection &middot; &pound;${fmt(pred.Total_Cost)}m budget used</div>
        </div>
      </div>
      <div class="split-divider"></div>
      <div class="split-col">
        <div class="total-cell">
          <div class="eyebrow total-label">My Result</div>
          <div class="total-val" style="color:var(--blue);">${outcomeData.Total_Points}</div>
          <div class="total-sub">points scored &middot; GW rank #${fmtNum(outcomeData.Ranks.rank)}</div>
        </div>
      </div>
      <div class="split-divider"></div>
      <div class="split-col">
        <div class="total-cell">
          <div class="eyebrow total-label">Actual Optimal</div>
          <div class="total-val" style="color:var(--text);">${fmt(act.Total_Points)}</div>
          <div class="total-sub">points scored &middot; &pound;${fmt(act.Total_Cost)}m budget used</div>
        </div>
      </div>`;
  } else if (pred && act) {
    totals.classList.add('modal-split--two-col');
    totals.innerHTML = `
      <div class="split-col">
        <div class="total-cell">
          <div class="eyebrow total-label">Predicted</div>
          <div class="total-val" style="color:var(--text-muted);">${fmt(pred.Total_Points)}</div>
          <div class="total-sub">projected pts &middot; &pound;${fmt(pred.Total_Cost)}m budget used</div>
        </div>
      </div>
      <div class="split-divider"></div>
      <div class="split-col">
        <div class="total-cell">
          <div class="eyebrow total-label">Actual Optimal</div>
          <div class="total-val" style="color:var(--text);">${fmt(act.Total_Points)}</div>
          <div class="total-sub">points scored &middot; &pound;${fmt(act.Total_Cost)}m budget used</div>
        </div>
      </div>`;
  } else if (pred) {
    totals.innerHTML = `
      <div class="total-cell">
        <div class="eyebrow total-label">Predicted Optimal</div>
        <div class="total-val" style="color:var(--blue);">${fmt(pred.Total_Points)}</div>
        <div class="total-sub">projected pts &middot; awaiting result</div>
      </div>`;
  } else if (act && outcomeData) {
    totals.classList.add('modal-split--two-col');
    totals.innerHTML = `
      <div class="split-col">
        <div class="total-cell">
          <div class="eyebrow total-label">My Result</div>
          <div class="total-val" style="color:var(--blue);">${outcomeData.Total_Points}</div>
          <div class="total-sub">points scored &middot; GW rank #${fmtNum(outcomeData.Ranks.rank)}</div>
        </div>
      </div>
      <div class="split-divider"></div>
      <div class="split-col">
        <div class="total-cell">
          <div class="eyebrow total-label">Actual Optimal</div>
          <div class="total-val" style="color:var(--text);">${fmt(act.Total_Points)}</div>
          <div class="total-sub">points scored &middot; no pre-gameweek prediction recorded</div>
        </div>
      </div>`;
  } else if (act) {
    totals.innerHTML = `
      <div class="total-cell">
        <div class="eyebrow total-label">Actual Optimal</div>
        <div class="total-val" style="color:var(--text);">${fmt(act.Total_Points)}</div>
        <div class="total-sub">points scored &middot; no pre-gameweek prediction recorded</div>
      </div>`;
  }

  // Lineups
  const lineups = document.getElementById('modal-lineups');
  lineups.className = 'modal-split';
  if (pred && act) {
    lineups.classList.add('modal-split--two-col');
    lineups.innerHTML = `
      <div class="split-col">
        <div class="col-header-row"><span class="eyebrow">Predicted selection</span></div>
        ${positionSection(playersFlat(pred), false, sharedIds, predOutcomeMap)}
      </div>
      <div class="split-divider"></div>
      <div class="split-col">
        <div class="col-header-row"><span class="eyebrow">Hindsight optimal</span></div>
        ${positionSection(playersFlat(act), true, sharedIds)}
      </div>`;
  } else if (pred) {
    lineups.innerHTML = `
      <div class="split-col">
        <div class="col-header-row"><span class="eyebrow">Predicted selection</span></div>
        ${positionSection(playersFlat(pred), false, sharedIds, predOutcomeMap)}
      </div>`;
  } else if (act) {
    lineups.innerHTML = `
      <div class="split-col">
        <div class="col-header-row"><span class="eyebrow">Actual optimal</span></div>
        ${positionSection(playersFlat(act), true, sharedIds)}
      </div>`;
  }

  // Footer — comparison stats
  const footer = document.getElementById('modal-footer');
  if (pred && act) {
    const ov       = computeOverlap(pred, act);
    const ptsDiff  = act.Total_Points - pred.Total_Points;

    let rankStats = '';
    if (outcomeData?.Ranks) {
      const totalPlayers = store.outcome?.total_players;
      const pctText      = totalPlayers
        ? `top ${(outcomeData.Ranks.overall_rank / totalPlayers * 100).toFixed(1)}% of players`
        : '';
      const gap          = outcomeData.Total_Points - act.Total_Points;
      const gapColor     = gap < 0 ? 'var(--red)' : 'var(--accent)';
      const gapPred      = outcomeData.Total_Points - pred.Total_Points;
      const gapPredColor = gapPred >= 0 ? 'var(--accent)' : 'var(--red)';
      rankStats = `
        <div class="comp-stat">
          <div class="eyebrow" style="margin-bottom:6px;">GW rank</div>
          <div class="comp-val">#${fmtNum(outcomeData.Ranks.rank)}</div>
          <div class="comp-sub">within this gameweek</div>
        </div>
        <div class="comp-stat">
          <div class="eyebrow" style="margin-bottom:6px;">Overall rank</div>
          <div class="comp-val">#${fmtNum(outcomeData.Ranks.overall_rank)}</div>
          <div class="comp-sub">${pctText}</div>
        </div>
        <div class="comp-stat">
          <div class="eyebrow" style="margin-bottom:6px;">Pts vs optimal</div>
          <div class="comp-val" style="color:${gapColor};">${gap >= 0 ? '+' : ''}${fmt(gap, 1)}</div>
          <div class="comp-sub">my score vs hindsight optimal</div>
        </div>
        <div class="comp-stat">
          <div class="eyebrow" style="margin-bottom:6px;">Pts vs predicted</div>
          <div class="comp-val" style="color:${gapPredColor};">${gapPred >= 0 ? '+' : ''}${fmt(gapPred, 1)}</div>
          <div class="comp-sub">my score vs model prediction</div>
        </div>`;
    }

    footer.innerHTML = `
      <div class="eyebrow" style="margin-bottom:12px;">Prediction analysis</div>
      <div class="comparison-grid">
        <div class="comp-stat">
          <div class="eyebrow" style="margin-bottom:6px;">Players matched</div>
          <div class="comp-val" style="color:var(--blue);">${ov.shared}/${ov.total}</div>
          <div class="comp-sub">${ov.shared} of ${ov.total} optimal players identified</div>
          <div class="acc-track" style="margin-top:8px; width:80px;">
            <div class="acc-fill" style="width:${(ov.pct*100).toFixed(1)}%;"></div>
          </div>
        </div>
        <div class="comp-stat">
          <div class="eyebrow" style="margin-bottom:6px;">Projected pts</div>
          <div class="comp-val" style="color:var(--blue);">${fmt(pred.Total_Points)}</div>
          <div class="comp-sub">model's pre-gameweek projection</div>
        </div>
        <div class="comp-stat">
          <div class="eyebrow" style="margin-bottom:6px;">Optimal ceiling</div>
          <div class="comp-val" style="color:var(--gold);">+${fmt(ptsDiff)}</div>
          <div class="comp-sub">hindsight optimal above projection</div>
        </div>
      </div>
      ${rankStats ? `
      <div style="height:1px; background:var(--border); margin:16px 0;"></div>
      <div class="eyebrow" style="margin-bottom:12px;">My result</div>
      <div class="comparison-grid">${rankStats}</div>` : ''}
      <p class="note-text">
        Green-ticked rows appear in both the predicted and hindsight-optimal lineups.
        The captain (C) is the model&rsquo;s highest-projected or highest-scoring player.
      </p>`;
  } else {
    footer.innerHTML = '';
  }

  // Open overlay
  const overlay = document.getElementById('modal-overlay');
  document.body.style.overflow = 'hidden';
  overlay.classList.add('open');
  document.getElementById('modal-close').focus({ preventScroll: true });
}

function closeModal() {
  document.getElementById('modal-overlay').classList.remove('open');
  document.body.style.overflow = '';
}

document.getElementById('modal-close').addEventListener('click', closeModal);

document.getElementById('modal-overlay').addEventListener('click', e => {
  if (e.target === document.getElementById('modal-overlay')) closeModal();
});

/* ── Season switcher ──────────────────────────────────────────────────────────── */
async function initSeasons() {
  let seasons;
  try {
    seasons = await fetch('data/seasons.json', { cache: 'no-cache' }).then(r => r.json());
  } catch {
    seasons = ['2025-26'];
  }

  // Default to the most recent season — last entry when sorted alphabetically
  currentSeason = [...seasons].sort().at(-1);

  const sel = document.getElementById('season-select');
  sel.innerHTML = seasons.map(s =>
    `<option value="${s}"${s === currentSeason ? ' selected' : ''}>${s}</option>`
  ).join('');

  sel.addEventListener('change', async () => {
    currentSeason = sel.value;
    await loadSeason();
  });
}

async function loadSeason() {
  document.getElementById('standing-section').style.display = 'none';
  sortKey = 'num-asc';
  document.getElementById('sort-select').value = 'num-asc';
  try {
    store = await loadData();
    renderStats();
    renderStanding();
    renderGrid();
  } catch (err) {
    console.error('Failed to load data:', err);
    document.getElementById('challenge-grid').innerHTML =
      `<div class="empty-state" style="color:var(--red);">Failed to load challenge data. Check the console for details.</div>`;
  }
}

/* ── Season standing chart ────────────────────────────────────────────────────── */
let standingChartInstance = null;

function openStandingChart() {
  const outcome = store?.outcome;
  if (!outcome) return;

  const gwKeys = Object.keys(outcome)
    .filter(k => !isNaN(Number(k)))
    .map(Number)
    .sort((a, b) => a - b);

  if (gwKeys.length === 0) return;

  const totalPlayers = typeof outcome.total_players === 'number' ? outcome.total_players : null;
  const ranks        = gwKeys.map(k => outcome[String(k)]?.Ranks?.overall_rank ?? null);
  const validRanks   = ranks.filter(r => r !== null);

  if (validRanks.length === 0) return;

  const currentRank = validRanks[validRanks.length - 1];
  const bestRank    = Math.min(...validRanks);
  const worstRank   = Math.max(...validRanks);
  // Positive = improved (rank number dropped), negative = declined
  const rankChange  = validRanks.length >= 2 ? validRanks[0] - currentRank : null;

  // ── Stats panel ────────────────────────────────────────────────────────────────
  const pctText = (totalPlayers && currentRank)
    ? `top ${(currentRank / totalPlayers * 100).toFixed(1)}%`
    : '';
  const changeColour = rankChange === null || rankChange === 0
    ? 'var(--text-muted)'
    : rankChange > 0 ? 'var(--accent)' : 'var(--red)';
  const changeDisplay = rankChange === null || rankChange === 0
    ? '—'
    : rankChange > 0 ? `+${fmtNum(rankChange)}` : fmtNum(rankChange);
  const changeSub = rankChange === null || rankChange === 0
    ? 'no change'
    : rankChange > 0 ? 'places improved' : 'places declined';

  document.getElementById('standing-chart-stats').innerHTML = `
    <div class="chart-stat-cell">
      <div class="eyebrow">Current rank</div>
      <div class="chart-stat-val" style="color:var(--accent);">#${fmtNum(currentRank)}</div>
      <div style="font-size:11px; color:var(--text-faint); margin-top:5px;">${pctText}</div>
    </div>
    <div class="chart-stat-cell">
      <div class="eyebrow">Best rank</div>
      <div class="chart-stat-val" style="color:var(--text);">#${fmtNum(bestRank)}</div>
      <div style="font-size:11px; color:var(--text-faint); margin-top:5px;">season high</div>
    </div>
    <div class="chart-stat-cell">
      <div class="eyebrow">Since GW${gwKeys[0]}</div>
      <div class="chart-stat-val" style="color:${changeColour};">${changeDisplay}</div>
      <div style="font-size:11px; color:var(--text-faint); margin-top:5px;">${changeSub}</div>
    </div>
    <div class="chart-stat-cell">
      <div class="eyebrow">GWs tracked</div>
      <div class="chart-stat-val" style="color:var(--text-muted);">${validRanks.length}</div>
      <div style="font-size:11px; color:var(--text-faint); margin-top:5px;">of ${gwKeys.length} total</div>
    </div>`;

  // Open overlay before rendering so the canvas has dimensions
  const overlay = document.getElementById('standing-chart-overlay');
  document.body.style.overflow = 'hidden';
  overlay.classList.add('open');
  document.getElementById('standing-chart-close').focus({ preventScroll: true });

  // Destroy stale instance before re-creating
  if (standingChartInstance) {
    standingChartInstance.destroy();
    standingChartInstance = null;
  }

  // ── Chart ──────────────────────────────────────────────────────────────────────
  const rankPad = (worstRank - bestRank) * 0.12 || worstRank * 0.05;
  const ctx     = document.getElementById('standing-chart-canvas').getContext('2d');

  standingChartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels: gwKeys.map(k => `GW${k}`),
      datasets: [{
        label: 'Overall rank',
        data: ranks,
        borderColor: '#3fb950',
        borderWidth: 2,
        backgroundColor: 'rgba(63, 185, 80, 0.07)',
        fill: 'end',
        tension: 0.35,
        pointRadius: gwKeys.length > 25 ? 3 : 4,
        pointHoverRadius: 6,
        pointBackgroundColor: '#3fb950',
        pointBorderColor: '#0d1117',
        pointBorderWidth: 2,
        spanGaps: false,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 500, easing: 'easeOutQuart' },
      interaction: { mode: 'index', intersect: false },
      scales: {
        y: {
          reverse: true,
          min: Math.max(1, Math.floor(bestRank - rankPad)),
          max: Math.ceil(worstRank + rankPad),
          title: {
            display: true,
            text: 'Overall rank',
            color: '#7d8590',
            font: { family: "'JetBrains Mono', monospace", size: 10 },
          },
          ticks: {
            color: '#7d8590',
            font: { family: "'JetBrains Mono', monospace", size: 10 },
            callback: v => `#${fmtNum(Math.round(v))}`,
            maxTicksLimit: 6,
          },
          grid: { color: '#21262d' },
          border: { color: '#21262d' },
        },
        x: {
          ticks: {
            color: '#7d8590',
            font: { family: "'JetBrains Mono', monospace", size: 10 },
            maxRotation: 0,
          },
          grid: { color: 'rgba(33, 38, 45, 0.6)' },
          border: { color: '#21262d' },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#161b22',
          borderColor: '#30363d',
          borderWidth: 1,
          titleColor: '#e6edf3',
          titleFont: { family: "'JetBrains Mono', monospace", size: 12, weight: '500' },
          bodyColor: '#7d8590',
          bodyFont: { family: "'Inter', sans-serif", size: 12 },
          padding: 12,
          displayColors: false,
          callbacks: {
            title: items => items[0].label,
            label: item => {
              if (item.raw === null) return 'No data';
              const rank = item.raw;
              const pct  = totalPlayers ? ` · top ${(rank / totalPlayers * 100).toFixed(1)}%` : '';
              return `Rank #${fmtNum(rank)}${pct}`;
            },
            afterLabel: item => {
              const gw  = gwKeys[item.dataIndex];
              const pts = outcome[String(gw)]?.Total_Points;
              return pts != null ? `${pts} pts this GW` : '';
            },
          },
        },
      },
    },
  });
}

function closeStandingChart() {
  document.getElementById('standing-chart-overlay').classList.remove('open');
  document.body.style.overflow = '';
}

document.getElementById('standing-section').addEventListener('click', () => {
  if (store?.outcome) openStandingChart();
});
document.getElementById('standing-section').addEventListener('keydown', e => {
  if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); if (store?.outcome) openStandingChart(); }
});
document.getElementById('standing-chart-close').addEventListener('click', closeStandingChart);
document.getElementById('standing-chart-overlay').addEventListener('click', e => {
  if (e.target === document.getElementById('standing-chart-overlay')) closeStandingChart();
});

/* ── About modal ─────────────────────────────────────────────────────────────── */
function openAbout() {
  document.getElementById('about-overlay').classList.add('open');
  document.body.style.overflow = 'hidden';
  document.getElementById('about-close').focus();
}

function closeAbout() {
  document.getElementById('about-overlay').classList.remove('open');
  document.body.style.overflow = '';
}

document.getElementById('hero-summary').addEventListener('click', openAbout);
document.getElementById('about-close').addEventListener('click', closeAbout);

document.getElementById('about-overlay').addEventListener('click', e => {
  if (e.target === document.getElementById('about-overlay')) closeAbout();
});

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') { closeModal(); closeAbout(); closeStandingChart(); }
});

/* ── Bootstrap ────────────────────────────────────────────────────────────────── */
initSeasons().then(() => loadSeason());
