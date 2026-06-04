/**
 * Qualix Sandbox — sandbox.js
 *
 * All LLM output inserted into the DOM is passed through escapeHtml() first.
 * innerHTML is only used with pre-escaped strings — no raw LLM text is ever
 * set directly via innerHTML.
 */

// ── Expense-approval PRD ──────────────────────────────────────────────────────
const EXPENSE_APPROVAL_PRD = [
  '# Expense Approval PRD',
  '',
  '## Goal',
  '',
  'Let employees submit expense requests and route them to the right approvers before payment.',
  '',
  '## Business Rules',
  '',
  '- A requester can create an expense request with `amount`, `currency`, `category`, `reason`, and one receipt attachment.',
  '- `amount` must be greater than zero.',
  '- `currency` must be one of `USD`, `EUR`, or `CNY`.',
  '- A request below 500 USD equivalent can be approved by the requester\'s direct manager.',
  '- A request at or above 500 USD equivalent requires manager approval and finance approval.',
  '- A manager cannot approve their own request.',
  '- A rejected request must include a rejection reason visible to the requester.',
  '- The requester must be notified whenever the request status changes.',
  '',
  '## Status Model',
  '',
  '```',
  'DRAFT -> SUBMITTED -> MANAGER_APPROVED -> FINANCE_APPROVED -> PAID',
  'SUBMITTED -> REJECTED',
  'MANAGER_APPROVED -> REJECTED',
  '```',
  '',
  'For requests below 500 USD equivalent, `MANAGER_APPROVED` is the final approval state before payment.',
  '',
  '## Non-Functional Requirements',
  '',
  '- Status transitions must be idempotent. Repeating the same approval request must not create a second audit entry or send a second notification.',
  '- Each approval decision must be audit logged with `actor_id`, `timestamp`, `previous_status`, `next_status`, and `comment`.',
  '- Amount comparison must use decimal arithmetic, not floating point.',
  '',
  '## Open Questions',
  '',
  '- Which exchange-rate source should be used for non-USD threshold conversion?',
  '- Should a requester be allowed to edit and resubmit a rejected request?',
].join('\n');

// ── Baked-in demo result (zero API calls) ────────────────────────────────────
// Pre-computed Q01 output for the expense-approval PRD above, so the first-time
// visitor sees a concrete result instantly — no API key, no button click.
// Values mirror examples/expense-approval/expected/q01-structured.json.
const EXPENSE_APPROVAL_RESULT = {
  semantic_expectations: [
    {
      se_id: 'SE-001',
      description: 'Every status change sends exactly one requester notification.',
      why_it_matters: 'A test that asserts "a notification was sent" passes even when two are sent. The "exactly one" semantic is the part that breaks on a non-idempotent retry.'
    },
    {
      se_id: 'SE-002',
      description: 'Approval transitions are idempotent: repeating the same approval must not create a second audit entry or send a second notification.',
      why_it_matters: 'Shallow tests check the happy-path approval once. They rarely replay the same approval, so a duplicate audit row or double notification escapes undetected.'
    },
    {
      se_id: 'SE-003',
      description: 'A request at exactly 500 USD requires manager AND finance approval — the threshold is inclusive, not exclusive.',
      why_it_matters: 'Tests at 120 USD and 600 USD exercise both branches and turn coverage green, but the exact 500 boundary is never asserted. An implementation using > 500 instead of >= 500 silently routes 500 to the wrong path.'
    },
    {
      se_id: 'SE-004',
      description: 'Approval decisions are audit logged with actor_id, timestamp, previous_status, next_status, and comment.',
      why_it_matters: 'A test that checks "an audit row exists" passes even when a required field like timestamp is missing. Schema completeness is the semantic, not row existence.'
    },
    {
      se_id: 'SE-005',
      description: 'Amount comparison uses decimal arithmetic, not floating point.',
      why_it_matters: 'Float comparison can make 499.99 + 0.01 fail an == 500 check. A test using float literals may pass while production data crosses the boundary incorrectly.'
    }
  ],
  shallow_misses: [
    'A test that only checks amounts 120 and 600 — both approval branches are hit, coverage is green, but the exact 500 boundary is never asserted.',
    'A test that only checks that an audit entry was created, not that a second identical approval fails to create a duplicate one.',
    'A test that only asserts a notification was sent, not that exactly one was sent per status change.'
  ],
  gaps: [
    {
      gap_id: 'GAP-001',
      description: 'Non-USD exchange-rate source is not specified in the PRD.',
      risk_level: 'P1'
    }
  ],
  open_items: [
    {
      open_id: 'OPEN-001',
      question: 'Should a rejected request be editable and resubmittable by the requester?'
    }
  ],
  conclusion: 'PRD is clear on the core approval flow. SE-003 (inclusive 500 USD boundary) and SE-002 (idempotency) are the two semantics most at risk of being missed by a standard test suite.'
};

// ── System prompt ─────────────────────────────────────────────────────────────
function buildSystemPrompt() {
  return [
    'You are performing Q01 Requirements Structuring for the Qualix quality-gate pipeline.',
    '',
    'Your task: extract Semantic Expectations (SE) from the PRD text.',
    '',
    'WHAT IS A SEMANTIC EXPECTATION?',
    'A semantic expectation is a testable business rule that a shallow test suite is likely to miss.',
    'Focus on:',
    '- Boundary values (exact thresholds, inclusive vs exclusive)',
    '- Idempotency constraints (repeating an action must not have side effects)',
    '- State transition rules (valid/invalid paths through a state machine)',
    '- Data integrity rules (decimal vs float, required audit fields)',
    '- Authorization constraints (who can or cannot perform an action)',
    '',
    'DO NOT list every feature as an SE. Only extract behaviors where a developer might',
    'write a passing test that still misses the real business semantics.',
    '',
    'OUTPUT FORMAT:',
    'Return only a JSON object with this exact shape — no markdown fences, no explanation:',
    '{',
    '  "semantic_expectations": [',
    '    {',
    '      "se_id": "SE-001",',
    '      "description": "Concise statement of the semantic expectation",',
    '      "why_it_matters": "Why a shallow test suite would miss this, and what goes wrong if it does"',
    '    }',
    '  ],',
    '  "shallow_misses": [',
    '    "A specific example of what a naive test suite would write that misses an SE"',
    '  ],',
    '  "gaps": [',
    '    {',
    '      "gap_id": "GAP-001",',
    '      "description": "Something the PRD leaves underspecified",',
    '      "risk_level": "P1"',
    '    }',
    '  ],',
    '  "open_items": [',
    '    {',
    '      "open_id": "OPEN-001",',
    '      "question": "Unresolved question from the PRD"',
    '    }',
    '  ],',
    '  "conclusion": "One or two sentences summarizing which SEs are most at risk of being missed."',
    '}',
    '',
    'Rules:',
    '- se_id sequential: SE-001, SE-002, …',
    '- gap_id sequential: GAP-001, GAP-002, …',
    '- open_id sequential: OPEN-001, OPEN-002, …',
    '- risk_level must be "P1" or "P2"',
    '- shallow_misses: 2-4 concrete examples, each starting with "A test that only checks..."',
    '- Output only valid JSON. No extra keys. No markdown.',
  ].join('\n');
}

// ── LLM calls ─────────────────────────────────────────────────────────────────
async function callAnthropic(apiKey, prdText) {
  const body = {
    model: 'claude-haiku-4-5-20251001',
    max_tokens: 2000,
    system: buildSystemPrompt(),
    messages: [
      { role: 'user', content: 'Here is the PRD to analyze:\n\n' + prdText + '\n\nReturn only the JSON object.' }
    ]
  };

  const response = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'x-api-key': apiKey,
      'anthropic-version': '2023-06-01',
      'content-type': 'application/json',
      'anthropic-dangerous-direct-browser-access': 'true'
    },
    body: JSON.stringify(body)
  });

  if (!response.ok) {
    const err = await response.json().catch(function() { return { error: { message: response.statusText } }; });
    throw new Error('Anthropic API error ' + response.status + ': ' + (err.error && err.error.message ? err.error.message : response.statusText));
  }

  const data = await response.json();
  return (data.content && data.content[0] && data.content[0].text) ? data.content[0].text : '';
}

async function callOpenAI(apiKey, prdText) {
  const body = {
    model: 'gpt-4o-mini',
    max_tokens: 2000,
    response_format: { type: 'json_object' },
    messages: [
      { role: 'system', content: buildSystemPrompt() },
      { role: 'user', content: 'Here is the PRD to analyze:\n\n' + prdText + '\n\nReturn only the JSON object.' }
    ]
  };

  const response = await fetch('https://api.openai.com/v1/chat/completions', {
    method: 'POST',
    headers: {
      'Authorization': 'Bearer ' + apiKey,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(body)
  });

  if (!response.ok) {
    const err = await response.json().catch(function() { return { error: { message: response.statusText } }; });
    throw new Error('OpenAI API error ' + response.status + ': ' + (err.error && err.error.message ? err.error.message : response.statusText));
  }

  const data = await response.json();
  return (data.choices && data.choices[0] && data.choices[0].message && data.choices[0].message.content) ? data.choices[0].message.content : '';
}

// ── Parse LLM response ────────────────────────────────────────────────────────
function parseResponse(text) {
  var cleaned = text
    .replace(/^```(?:json)?\n?/i, '')
    .replace(/\n?```$/i, '')
    .trim();
  return JSON.parse(cleaned);
}

// ── DOM / HTML helpers ────────────────────────────────────────────────────────
function escapeHtml(str) {
  return String(str == null ? '' : str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/**
 * Safe DOM builder — every string value is escaped via escapeHtml before
 * being assembled into an HTML string. No raw user or LLM content is
 * ever interpolated without escaping.
 */
function h(tag, attrs, children) {
  var attrStr = '';
  if (attrs) {
    Object.keys(attrs).forEach(function(k) {
      attrStr += ' ' + k + '="' + escapeHtml(attrs[k]) + '"';
    });
  }
  var inner = Array.isArray(children) ? children.join('') : (children || '');
  return '<' + tag + attrStr + '>' + inner + '</' + tag + '>';
}

function setOutput(html) {
  document.getElementById('output-panel').innerHTML = html;
}

// ── Render helpers ────────────────────────────────────────────────────────────
function renderEmpty() {
  return (
    '<div class="output-empty">' +
      '<div class="output-empty-icon">&#9672;</div>' +
      '<div class="output-empty-title">No analysis yet</div>' +
      '<div class="output-empty-desc">' +
        'Paste a PRD on the left, add your API key, and click ' +
        '<strong>Extract Semantic Expectations</strong> to see what ' +
        'a shallow test suite might miss.' +
      '</div>' +
    '</div>'
  );
}

function renderLoading() {
  return (
    '<div class="loading-state">' +
      '<div class="spinner"></div>' +
      '<div class="loading-text">Extracting semantic expectations…</div>' +
    '</div>'
  );
}

function renderError(message) {
  return (
    '<div class="error-box">' +
      '<div class="error-title">Extraction failed</div>' +
      '<div>' + escapeHtml(message) + '</div>' +
    '</div>'
  );
}

function renderResults(data) {
  var ses = Array.isArray(data.semantic_expectations) ? data.semantic_expectations : [];
  var gaps = Array.isArray(data.gaps) ? data.gaps : [];
  var opens = Array.isArray(data.open_items) ? data.open_items : [];
  var misses = Array.isArray(data.shallow_misses) ? data.shallow_misses : [];
  var conclusion = data.conclusion || '';

  var parts = [];

  // SE table
  var seRows;
  if (ses.length === 0) {
    seRows = '<tr><td colspan="3" style="padding:16px;text-align:center;color:#6b7280;">No semantic expectations extracted.</td></tr>';
  } else {
    seRows = ses.map(function(se) {
      return (
        '<tr>' +
          '<td><span class="se-id-badge">' + escapeHtml(se.se_id) + '</span></td>' +
          '<td class="se-description">' + escapeHtml(se.description) + '</td>' +
          '<td class="se-why">' + escapeHtml(se.why_it_matters) + '</td>' +
        '</tr>'
      );
    }).join('');
  }

  parts.push(
    '<div>' +
      '<div class="section-header">' +
        'Semantic Expectations' +
        '<span class="section-badge">' + ses.length + ' extracted</span>' +
      '</div>' +
      '<div class="se-table-wrapper">' +
        '<table class="se-table">' +
          '<thead><tr>' +
            '<th>ID</th>' +
            '<th>Description</th>' +
            '<th>Why it matters</th>' +
          '</tr></thead>' +
          '<tbody>' + seRows + '</tbody>' +
        '</table>' +
      '</div>' +
    '</div>'
  );

  // Shallow misses
  if (misses.length > 0) {
    var missItems = misses.map(function(miss, i) {
      return (
        '<div class="miss-item">' +
          '<div class="miss-bullet">' + (i + 1) + '</div>' +
          '<div class="miss-text">' + escapeHtml(miss) + '</div>' +
        '</div>'
      );
    }).join('');
    parts.push(
      '<details class="shallow-miss-box" open>' +
        '<summary>' +
          '<span class="shallow-miss-icon">&#9888;</span>' +
          ' What a shallow test suite might miss' +
        '</summary>' +
        '<div class="shallow-miss-body">' + missItems + '</div>' +
      '</details>'
    );
  }

  // GAPs
  if (gaps.length > 0) {
    var gapItems = gaps.map(function(g) {
      var riskCls = (g.risk_level === 'P1') ? 'risk-p1' : 'risk-p2';
      return (
        '<div class="tag-item">' +
          '<span class="tag-badge tag-badge-gap">' + escapeHtml(g.gap_id) + '</span>' +
          '<span class="tag-content">' +
            escapeHtml(g.description) +
            '<span class="risk-badge ' + riskCls + '">' + escapeHtml(g.risk_level) + '</span>' +
          '</span>' +
        '</div>'
      );
    }).join('');
    parts.push(
      '<div>' +
        '<div class="section-header">' +
          'Specification Gaps' +
          '<span class="section-badge" style="background:#fef3c7;color:#92400e;">' + gaps.length + '</span>' +
        '</div>' +
        '<div class="tag-list">' + gapItems + '</div>' +
      '</div>'
    );
  }

  // Open items
  if (opens.length > 0) {
    var openItems = opens.map(function(o) {
      return (
        '<div class="tag-item">' +
          '<span class="tag-badge tag-badge-open">' + escapeHtml(o.open_id) + '</span>' +
          '<span class="tag-content">' + escapeHtml(o.question) + '</span>' +
        '</div>'
      );
    }).join('');
    parts.push(
      '<div>' +
        '<div class="section-header">' +
          'Open Questions' +
          '<span class="section-badge" style="background:#f3f4f6;color:#374151;">' + opens.length + '</span>' +
        '</div>' +
        '<div class="tag-list">' + openItems + '</div>' +
      '</div>'
    );
  }

  // Conclusion
  if (conclusion) {
    parts.push(
      '<div class="conclusion-box">' +
        '<div class="conclusion-label">Analysis Summary</div>' +
        escapeHtml(conclusion) +
      '</div>'
    );
  }

  return '<div class="results-container">' + parts.join('') + '</div>';
}

// ── Main handler ──────────────────────────────────────────────────────────────
async function handleExtract() {
  var providerEl = document.querySelector('input[name="provider"]:checked');
  var provider = providerEl ? providerEl.value : 'anthropic';
  var apiKey = document.getElementById('api-key').value.trim();
  var prdText = document.getElementById('prd-input').value.trim();
  var btn = document.getElementById('extract-btn');

  if (!apiKey) {
    setOutput(
      '<div class="error-box">' +
        '<div class="error-title">API key required</div>' +
        'Enter your ' + escapeHtml(provider === 'anthropic' ? 'Anthropic' : 'OpenAI') + ' API key to continue.' +
      '</div>'
    );
    return;
  }

  if (prdText.length < 50) {
    setOutput(
      '<div class="error-box">' +
        '<div class="error-title">PRD too short</div>' +
        'Paste a more complete PRD (at least 50 characters). Try the "Load example" button.' +
      '</div>'
    );
    return;
  }

  btn.disabled = true;
  setOutput(renderLoading());

  try {
    var raw;
    if (provider === 'anthropic') {
      raw = await callAnthropic(apiKey, prdText);
    } else {
      raw = await callOpenAI(apiKey, prdText);
    }
    var data = parseResponse(raw);
    setOutput(renderResults(data));
  } catch (err) {
    console.error('Extraction error:', err);
    setOutput(renderError(err.message));
  } finally {
    btn.disabled = false;
  }
}

// ── Init ──────────────────────────────────────────────────────────────────────
function init() {
  // First-time visitor sees a concrete result instantly: the expense PRD is
  // pre-loaded and its Q01 output is rendered from a baked-in result with zero
  // API calls. "Extract" re-runs it live against the user's own API key.
  document.getElementById('prd-input').value = EXPENSE_APPROVAL_PRD;
  setOutput(
    '<div class="demo-banner">' +
      '⚡ Example result below — 0 API calls. ' +
      'Edit the PRD or paste your own, add an API key, and click ' +
      '<strong>Extract Semantic Expectations</strong> to run it live.' +
    '</div>' +
    renderResults(EXPENSE_APPROVAL_RESULT)
  );

  document.getElementById('load-example-btn').addEventListener('click', function() {
    document.getElementById('prd-input').value = EXPENSE_APPROVAL_PRD;
  });

  document.getElementById('extract-btn').addEventListener('click', handleExtract);

  document.getElementById('api-key').addEventListener('keydown', function(e) {
    if (e.key === 'Enter') { handleExtract(); }
  });
}

document.addEventListener('DOMContentLoaded', init);
