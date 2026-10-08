/**
 * Py2SafeRust-X Web Frontend Application
 *
 * Provides a reactive, clean, and interactive single-page interface for:
 * - Python-to-Rust transpilation
 * - Adaptive repair tracking
 * - Dual execution semantic verification
 * - Explainable compilation reports
 * - Transparent confidence assessment
 */

document.addEventListener('DOMContentLoaded', () => {
  // DOM Elements - Input Side
  const pythonCodeInput = document.getElementById('python-code-input');
  const fileInput = document.getElementById('file-input');
  const btnLoadFile = document.getElementById('btn-load-file');
  const btnClear = document.getElementById('btn-clear');
  const btnTranspile = document.getElementById('btn-transpile');
  const asyncModeToggle = document.getElementById('async-mode-toggle');
  const testInputsInput = document.getElementById('test-inputs-input');
  const inputValidationAlert = document.getElementById('input-validation-alert');
  const inputValidationMsg = document.getElementById('input-validation-msg');

  // DOM Elements - Health Status
  const healthPill = document.getElementById('health-pill');
  const healthDot = document.getElementById('health-dot');
  const healthLabel = document.getElementById('health-label');
  const healthDropdown = document.getElementById('health-dropdown');
  const btnRefreshHealth = document.getElementById('btn-refresh-health');
  const detailApi = document.getElementById('detail-api');
  const detailRustc = document.getElementById('detail-rustc');
  const detailPython = document.getElementById('detail-python');
  const detailLlm = document.getElementById('detail-llm');

  // DOM Elements - Output Side States
  const emptyState = document.getElementById('empty-state');
  const loadingState = document.getElementById('loading-state');
  const loadingTitle = document.getElementById('loading-title');
  const loadingDesc = document.getElementById('loading-desc');
  const errorBanner = document.getElementById('error-banner');
  const errorTitle = document.getElementById('error-title');
  const errorMessageText = document.getElementById('error-message-text');
  const btnCloseError = document.getElementById('btn-close-error');
  const resultsContainer = document.getElementById('results-container');

  // DOM Elements - Summary Strip
  const badgeCompilation = document.getElementById('badge-compilation');
  const badgeVerification = document.getElementById('badge-verification');
  const confidenceNumber = document.getElementById('confidence-number');
  const gaugeBar = document.getElementById('gauge-bar');
  const breakdownItemsList = document.getElementById('breakdown-items-list');

  // DOM Elements - Warnings
  const warningsWrapper = document.getElementById('warnings-wrapper');
  const warningsList = document.getElementById('warnings-list');
  const btnDismissWarnings = document.getElementById('btn-dismiss-warnings');

  // DOM Elements - Tabs & Content Panes
  const tabButtons = document.querySelectorAll('.tab-btn');
  const tabPanes = document.querySelectorAll('.tab-pane');
  const repairCountBadge = document.getElementById('repair-count-badge');
  const rustLinesMeta = document.getElementById('rust-lines-meta');
  const rustCodeOutput = document.getElementById('rust-code-output');
  const btnCopyRust = document.getElementById('btn-copy-rust');
  const copyBtnText = document.getElementById('copy-btn-text');
  const explanationRenderedView = document.getElementById('explanation-rendered-view');
  const repairTimelineContainer = document.getElementById('repair-timeline-container');
  const verificationSummaryBox = document.getElementById('verification-summary-box');
  const verificationTableBody = document.getElementById('verification-table-body');
  const verificationTableWrapper = document.getElementById('verification-table-wrapper');
  const verificationSessionsWrapper = document.getElementById('verification-sessions-wrapper');
  const verificationSessionsContainer = document.getElementById('verification-sessions-container');
  const btnViewTable = document.getElementById('btn-view-table');
  const btnViewSessions = document.getElementById('btn-view-sessions');
  const mismatchFeedbackContainer = document.getElementById('mismatch-feedback-container');
  const mismatchFeedbackPre = document.getElementById('mismatch-feedback-pre');

  if (btnViewTable && btnViewSessions) {
    btnViewTable.addEventListener('click', () => {
      btnViewTable.classList.add('active');
      btnViewSessions.classList.remove('active');
      if (verificationTableWrapper) verificationTableWrapper.style.display = 'block';
      if (verificationSessionsWrapper) verificationSessionsWrapper.style.display = 'none';
    });
    btnViewSessions.addEventListener('click', () => {
      btnViewSessions.classList.add('active');
      btnViewTable.classList.remove('active');
      if (verificationTableWrapper) verificationTableWrapper.style.display = 'none';
      if (verificationSessionsWrapper) verificationSessionsWrapper.style.display = 'block';
    });
  }

  // State
  let currentJobId = null;
  let pollIntervalId = null;
  let latestRustCode = '';

  // ---------------------------------------------------------------------------
  // 1. Health Status Checking
  // ---------------------------------------------------------------------------

  async function checkBackendHealth() {
    healthDot.className = 'health-dot';
    healthLabel.textContent = 'Connecting...';

    try {
      const response = await fetch('/api/v1/health');
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data = await response.json();

      detailApi.textContent = 'Connected (v1)';
      detailApi.style.color = '#10b981';

      if (data.rustc_available) {
        detailRustc.textContent = data.rustc_path ? 'Available' : 'Found on PATH';
        detailRustc.title = data.rustc_path || '';
        detailRustc.style.color = '#10b981';
      } else {
        detailRustc.textContent = 'Missing / Not Found';
        detailRustc.style.color = '#f87171';
      }

      detailPython.textContent = data.python_version || 'Unknown';
      detailLlm.textContent = data.llm_backend ? data.llm_backend.toUpperCase() : 'Ollama';

      if (data.rustc_available) {
        healthDot.className = 'health-dot healthy';
        healthLabel.textContent = 'System Healthy';
      } else {
        healthDot.className = 'health-dot degraded';
        healthLabel.textContent = 'Degraded (Rustc Missing)';
      }
    } catch (err) {
      healthDot.className = 'health-dot unreachable';
      healthLabel.textContent = 'Backend Offline';
      detailApi.textContent = 'Unreachable';
      detailApi.style.color = '#f87171';
      detailRustc.textContent = 'Unknown';
      detailPython.textContent = 'Unknown';
      detailLlm.textContent = 'Unknown';
    }
  }

  // Toggle health dropdown
  healthPill.addEventListener('click', (e) => {
    e.stopPropagation();
    healthDropdown.classList.toggle('show');
  });

  document.addEventListener('click', (e) => {
    if (!healthDropdown.contains(e.target) && !healthPill.contains(e.target)) {
      healthDropdown.classList.remove('show');
    }
  });

  btnRefreshHealth.addEventListener('click', (e) => {
    e.stopPropagation();
    checkBackendHealth();
  });

  // Initial health check
  checkBackendHealth();

  // ---------------------------------------------------------------------------
  // 2. Editor Interaction & Helpers
  // ---------------------------------------------------------------------------

  // Handle Tab key in editor to insert 4 spaces
  pythonCodeInput.addEventListener('keydown', (e) => {
    if (e.key === 'Tab') {
      e.preventDefault();
      const start = pythonCodeInput.selectionStart;
      const end = pythonCodeInput.selectionEnd;
      const val = pythonCodeInput.value;

      pythonCodeInput.value = val.substring(0, start) + '    ' + val.substring(end);
      pythonCodeInput.selectionStart = pythonCodeInput.selectionEnd = start + 4;
    }
  });

  // Load from .py file via FileReader
  btnLoadFile.addEventListener('click', () => {
    fileInput.click();
  });

  fileInput.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      pythonCodeInput.value = event.target.result;
      hideInputAlert();
    };
    reader.onerror = () => {
      showInputAlert('Failed to read the selected file.');
    };
    reader.readAsText(file);
    // Reset file input so same file can be reloaded if desired
    fileInput.value = '';
  });

  // Clear button
  btnClear.addEventListener('click', () => {
    pythonCodeInput.value = '';
    testInputsInput.value = '';
    hideInputAlert();
    hideErrorBanner();
    if (pollIntervalId) {
      clearInterval(pollIntervalId);
      pollIntervalId = null;
    }
    // Reset view to empty state
    loadingState.style.display = 'none';
    resultsContainer.style.display = 'none';
    emptyState.style.display = 'flex';
    btnTranspile.disabled = false;
  });

  // Input validation alert helpers
  function showInputAlert(msg) {
    inputValidationMsg.textContent = msg;
    inputValidationAlert.style.display = 'flex';
  }

  function hideInputAlert() {
    inputValidationAlert.style.display = 'none';
  }

  pythonCodeInput.addEventListener('input', () => {
    if (pythonCodeInput.value.trim().length > 0) {
      hideInputAlert();
    }
  });

  // Error Banner helpers
  function showErrorBanner(title, msg) {
    errorTitle.textContent = title;
    errorMessageText.textContent = msg;
    errorBanner.style.display = 'block';
  }

  function hideErrorBanner() {
    errorBanner.style.display = 'none';
  }

  btnCloseError.addEventListener('click', hideErrorBanner);

  // Warnings Dismiss
  btnDismissWarnings.addEventListener('click', () => {
    warningsWrapper.style.display = 'none';
  });

  // Tab switching
  tabButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      const targetTabId = btn.getAttribute('data-tab');

      tabButtons.forEach(b => {
        b.classList.remove('active');
        b.setAttribute('aria-selected', 'false');
      });
      tabPanes.forEach(p => p.classList.remove('active'));

      btn.classList.add('active');
      btn.setAttribute('aria-selected', 'true');
      const targetPane = document.getElementById(targetTabId);
      if (targetPane) targetPane.classList.add('active');
    });
  });

  function cleanRustCode(code) {
    if (!code) return '';
    // Use a textarea for reliable browser-native HTML entity decoding.
    // Loops until stable to handle double-encoded entities (&amp;#039; -> &#039; -> ').
    const ta = document.createElement('textarea');
    let current = String(code);
    let prev;
    do {
      prev = current;
      ta.innerHTML = prev;
      current = ta.value;
    } while (current !== prev);
    return current;
  }

  // Copy Rust code button
  btnCopyRust.addEventListener('click', async () => {
    let code = latestRustCode || rustCodeOutput.textContent || '';
    code = cleanRustCode(code);
    if (!code) return;

    try {
      await navigator.clipboard.writeText(code);
      copyBtnText.textContent = 'Copied!';
      setTimeout(() => {
        copyBtnText.textContent = 'Copy Code';
      }, 2000);
    } catch (err) {
      // Fallback
      const ta = document.createElement('textarea');
      ta.value = code;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      copyBtnText.textContent = 'Copied!';
      setTimeout(() => {
        copyBtnText.textContent = 'Copy Code';
      }, 2000);
    }
  });

  // ---------------------------------------------------------------------------
  // 3. Pipeline Execution: Synchronous & Asynchronous Flow
  // ---------------------------------------------------------------------------

  btnTranspile.addEventListener('click', async () => {
    const rawCode = pythonCodeInput.value;

    // Strict validation: do not proceed if input is empty or whitespace-only
    if (!rawCode || rawCode.trim().length === 0) {
      showInputAlert('Please enter some Python code first.');
      pythonCodeInput.focus();
      return;
    }

    hideInputAlert();
    hideErrorBanner();

    // Parse optional test inputs if present
    let testInputs = undefined;
    const rawTestInputs = testInputsInput.value.trim();
    if (rawTestInputs.length > 0) {
      try {
        testInputs = JSON.parse(rawTestInputs);
      } catch (err) {
        showInputAlert('Invalid JSON in Test Inputs: ' + err.message);
        testInputsInput.focus();
        return;
      }
    }

    // Set UI to loading state
    btnTranspile.disabled = true;
    emptyState.style.display = 'none';
    resultsContainer.style.display = 'none';
    loadingState.style.display = 'flex';
    loadingTitle.textContent = 'Transpiling & Verifying...';
    loadingDesc.textContent = 'Running 5-stage pipeline (AST -> IR -> Type Inference -> Ownership -> Verifier)...';

    const payload = {
      python_code: rawCode,
    };
    if (testInputs !== undefined) {
      payload.test_inputs = testInputs;
    }

    const useAsync = asyncModeToggle.checked;

    if (useAsync) {
      runAsyncJob(payload);
    } else {
      runSynchronous(payload);
    }
  });

  // Synchronous Execution
  async function runSynchronous(payload) {
    try {
      const response = await fetch('/api/v1/transpile', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `Server returned HTTP ${response.status}`);
      }

      const result = await response.json();
      renderPipelineResult(result);
    } catch (err) {
      loadingState.style.display = 'none';
      showErrorBanner('Transpilation Failed', err.message);
    } finally {
      btnTranspile.disabled = false;
    }
  }

  // Asynchronous Execution with Polling
  async function runAsyncJob(payload) {
    loadingTitle.textContent = 'Submitting Async Job...';
    loadingDesc.textContent = 'Registering job in task queue...';

    try {
      const submitResp = await fetch('/api/v1/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!submitResp.ok) {
        const errData = await submitResp.json().catch(() => ({}));
        throw new Error(errData.detail || `Failed to submit job: HTTP ${submitResp.status}`);
      }

      const submitData = await submitResp.json();
      currentJobId = submitData.job_id;

      loadingTitle.textContent = `Processing Job [${currentJobId.substring(0, 8)}...]`;
      loadingDesc.textContent = 'Orchestrating adaptive repair and semantic verification...';

      // Start polling every 1.5 seconds
      pollIntervalId = setInterval(async () => {
        try {
          const statusResp = await fetch(`/api/v1/jobs/${currentJobId}`);
          if (!statusResp.ok) {
            throw new Error(`Failed to poll status: HTTP ${statusResp.status}`);
          }
          const statusData = await statusResp.json();

          if (statusData.status === 'done') {
            clearInterval(pollIntervalId);
            pollIntervalId = null;
            // Fetch final result
            const resultResp = await fetch(`/api/v1/jobs/${currentJobId}/result`);
            if (!resultResp.ok) {
              const resErr = await resultResp.json().catch(() => ({}));
              throw new Error(resErr.detail || 'Failed to fetch completed job result');
            }
            const finalResult = await resultResp.json();
            renderPipelineResult(finalResult);
            btnTranspile.disabled = false;

          } else if (statusData.status === 'failed') {
            clearInterval(pollIntervalId);
            pollIntervalId = null;
            loadingState.style.display = 'none';
            showErrorBanner('Async Job Failed', statusData.error || 'Job failed during execution');
            btnTranspile.disabled = false;
          } else {
            loadingDesc.textContent = `Current status: ${statusData.status}...`;
          }
        } catch (pollErr) {
          clearInterval(pollIntervalId);
          pollIntervalId = null;
          loadingState.style.display = 'none';
          showErrorBanner('Polling Error', pollErr.message);
          btnTranspile.disabled = false;
        }
      }, 1500);

    } catch (err) {
      loadingState.style.display = 'none';
      showErrorBanner('Async Submission Error', err.message);
      btnTranspile.disabled = false;
    }
  }

  // ---------------------------------------------------------------------------
  // 4. Render Results Payload
  // ---------------------------------------------------------------------------

  function renderPipelineResult(data) {
    loadingState.style.display = 'none';
    resultsContainer.style.display = 'flex';

    // 1. Compilation Status Badge
    if (data.compiled) {
      badgeCompilation.className = 'status-badge badge-success';
      badgeCompilation.textContent = '✅ Compiled';
    } else {
      badgeCompilation.className = 'status-badge badge-failed';
      badgeCompilation.textContent = '❌ Not Compiled';
    }

    // 2. Semantic Verification Badge
    if (!data.compiled) {
      badgeVerification.className = 'status-badge badge-skipped';
      badgeVerification.textContent = '⏸️ Skipped (Not Compiled)';
    } else if (data.semantic_match) {
      badgeVerification.className = 'status-badge badge-success';
      badgeVerification.textContent = '✅ Verified';
    } else {
      badgeVerification.className = 'status-badge badge-failed';
      badgeVerification.textContent = '⚠️ Mismatch';
    }

    // 3. Confidence Score & Breakdown Gauge
    const score = Math.max(0, Math.min(100, data.confidence_score || 0));
    confidenceNumber.textContent = `${score} / 100`;

    gaugeBar.style.width = `${score}%`;
    gaugeBar.className = 'gauge-bar ' + (score >= 70 ? 'gauge-high' : score >= 40 ? 'gauge-medium' : 'gauge-low');
    confidenceNumber.style.color = (score >= 70 ? '#10b981' : score >= 40 ? '#f59e0b' : '#ef4444');

    // Populate breakdown dropdown
    breakdownItemsList.innerHTML = '';
    if (data.confidence_breakdown && data.confidence_breakdown.length > 0) {
      data.confidence_breakdown.forEach(item => {
        const el = document.createElement('div');
        el.className = 'breakdown-item';
        el.innerHTML = `
          <span class="breakdown-reason">${escapeHtml(item.reason || item.category)}</span>
          <span class="breakdown-amt">-${item.deduction}</span>
        `;
        breakdownItemsList.appendChild(el);
      });
    } else {
      breakdownItemsList.innerHTML = '<div class="breakdown-item"><span class="breakdown-reason" style="color: #10b981;">No deductions — perfect score!</span></div>';
    }

    // 4. Warnings List
    if (data.warnings && data.warnings.length > 0) {
      warningsList.innerHTML = '';
      data.warnings.forEach(w => {
        const li = document.createElement('li');
        li.textContent = w;
        warningsList.appendChild(li);
      });
      warningsWrapper.style.display = 'block';
    } else {
      warningsWrapper.style.display = 'none';
    }

    // 5. Tab 1: Rust Code
    const rustCode = cleanRustCode(data.rust_code || '// No Rust code emitted');
    latestRustCode = rustCode;
    const linesCount = rustCode.split('\n').length;
    rustLinesMeta.textContent = `${linesCount} line${linesCount !== 1 ? 's' : ''}`;
    rustCodeOutput.innerHTML = highlightRustSyntax(rustCode);

    // 6. Tab 2: Explanation Report
    const reportMd = data.explanation_report_markdown || 'No explanation report available.';
    explanationRenderedView.innerHTML = renderMarkdown(reportMd);

    // 7. Tab 3: Repair Log Timeline
    repairTimelineContainer.innerHTML = '';
    const logs = data.repair_log || [];
    if (logs.length > 0) {
      repairCountBadge.textContent = logs.length;
      repairCountBadge.style.display = 'inline-block';

      logs.forEach(entry => {
        const entryEl = document.createElement('div');
        entryEl.className = 'timeline-entry';

        const sourceClass = entry.rule_type === 'learned' ? 'source-learned'
                          : entry.fix_source === 'kb' ? 'source-kb'
                          : 'source-llm';
        const sourceLabel = entry.rule_type === 'learned' ? 'Learned Rule'
                          : entry.fix_source === 'kb' ? 'Knowledge Base'
                          : 'LLM Repair';

        entryEl.innerHTML = `
          <div class="timeline-header">
            <span class="timeline-iter">Iteration ${entry.iteration || 1}</span>
            <span class="source-badge ${sourceClass}">${sourceLabel}</span>
            ${entry.error_code ? `<span class="timeline-error-code">${escapeHtml(entry.error_code)}</span>` : ''}
          </div>
          ${entry.error_message ? `<div class="timeline-error-msg">${escapeHtml(entry.error_message)}</div>` : ''}
          <div class="timeline-rationale">${escapeHtml(entry.explanation || 'Rule applied successfully.')}</div>
        `;
        repairTimelineContainer.appendChild(entryEl);
      });
    } else {
      if (data.compiled) {
        repairCountBadge.style.display = 'none';
        repairTimelineContainer.innerHTML = `
          <div style="padding: 20px; text-align: center; color: var(--text-muted);">
            <p>✅ Clean compilation on first attempt.</p>
            <p style="font-size: 12px; margin-top: 4px;">Zero borrow-checker errors encountered; no secondary repair passes were necessary.</p>
          </div>
        `;
      } else {
        repairCountBadge.textContent = 'Failed';
        repairCountBadge.style.display = 'inline-block';
        repairTimelineContainer.innerHTML = `
          <div style="padding: 20px; text-align: center; color: var(--text-muted);">
            <p style="color: #ef4444; font-weight: 600;">❌ Not Compiled</p>
            <p style="font-size: 12px; margin-top: 4px;">Rust compiler rejected the generated source; no executable binary could be produced.</p>
          </div>
        `;
      }
    }

    // 8. Tab 4: Verification Pane
    if (!data.compiled) {
      verificationSummaryBox.innerHTML = `
        <div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">
          <strong>Verification Outcome:</strong> <span style="color: var(--text-muted); font-weight: 600;">Skipped — Rust Compilation Failed</span>
        </div>
        <div class="verif-divergence-notice" style="background: rgba(239, 68, 68, 0.08); border-color: rgba(239, 68, 68, 0.25); color: #fca5a5;">
          <span>❌ Rust code failed compilation. Semantic verification requires executable binaries from both Python and Rust and was skipped. Please inspect the Adaptive Repair tab for compiler error diagnostics.</span>
        </div>
      `;
      verificationTableBody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 32px;">Semantic verification skipped because Rust compilation failed.</td></tr>`;
      if (verificationSessionsContainer) {
        verificationSessionsContainer.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 32px;">Semantic verification skipped because Rust compilation failed.</div>`;
      }
      return;
    }

    const verif = data.verification_details || {};
    const passRate = verif.pass_rate !== undefined ? `${(verif.pass_rate * 100).toFixed(1)}%` : '--';
    verificationSummaryBox.innerHTML = `
      <div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">
        <strong>Verification Outcome:</strong> ${verif.semantic_match ? '<span style="color:#10b981; font-weight: 600;">Semantic Equivalence Verified (Pass Rate: ' + passRate + ')</span>' : '<span style="color:#ef4444; font-weight: 600;">Semantic Divergence Detected (Pass Rate: ' + passRate + ')</span>'}
      </div>
      ${!verif.semantic_match ? `
        <div class="verif-divergence-notice">
          <span>⚠️ Rust runtime output diverged from Python. Detailed line-by-line differences are highlighted below.</span>
        </div>
      ` : ''}
    `;

    // Reset view toggle to Table View
    if (btnViewTable && btnViewSessions) {
      btnViewTable.classList.add('active');
      btnViewSessions.classList.remove('active');
      if (verificationTableWrapper) verificationTableWrapper.style.display = 'block';
      if (verificationSessionsWrapper) verificationSessionsWrapper.style.display = 'none';
    }

    verificationTableBody.innerHTML = '';
    if (verificationSessionsContainer) verificationSessionsContainer.innerHTML = '';

    const cases = verif.cases || [];
    if (cases.length > 0) {
      cases.forEach((tc, idx) => {
        const statusBadge = tc.passed
          ? '<span class="status-badge badge-success">Pass</span>'
          : `<span class="status-badge badge-failed" title="${escapeHtml(tc.error || '')}">Fail</span>`;

        const inputVal = tc.formatted_input || tc.input || 'default';
        const pyOutVal = tc.formatted_output || tc.python_output || '';
        
        let rsOutVal = '';
        if (tc.rust_formatted_output && tc.rust_formatted_output.trim() !== '') {
          rsOutVal = tc.rust_formatted_output;
        } else if (tc.rust_output && tc.rust_output.trim() !== '') {
          rsOutVal = tc.rust_output;
        } else if (tc.error) {
          rsOutVal = tc.error;
        } else if (!tc.passed) {
          rsOutVal = '(execution failed / no output)';
        } else {
          rsOutVal = '(no output)';
        }

        const inputHtml = formatInputHtml(inputVal);
        const pyOutputHtml = formatOutputHtml(pyOutVal);
        const rsOutputHtml = formatOutputHtml(rsOutVal);

        // Difference display block for failed cases
        let diffBannerHtml = '';
        if (!tc.passed) {
          diffBannerHtml = `
            <div class="tc-diff-banner">
              <div class="tc-diff-header">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                <span>Output Divergence / Difference:</span>
              </div>
              <div class="tc-diff-body">
                <div class="diff-line diff-expected"><span class="diff-badge">- Python:</span> <span class="diff-val">${escapeHtml(pyOutVal)}</span></div>
                <div class="diff-line diff-actual"><span class="diff-badge">+ Rust:</span> <span class="diff-val">${escapeHtml(rsOutVal)}</span></div>
                ${tc.diff ? `<pre class="diff-details-pre">${escapeHtml(tc.diff)}</pre>` : ''}
              </div>
            </div>
          `;
        }

        // 1. Table Row
        const tr = document.createElement('tr');
        if (!tc.passed) tr.classList.add('row-mismatch');
        tr.innerHTML = `
          <td>
            <div style="font-weight: 600; color: var(--text-primary); margin-bottom: 4px;">Case #${idx + 1}</div>
            <button type="button" class="btn-toggle-drawer" data-drawer-target="drawer-tc-${idx}">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
              <span>Session View</span>
            </button>
          </td>
          <td>
            <div class="tc-block tc-input-block">${inputHtml}</div>
          </td>
          <td>
            <div class="tc-block tc-output-block">${pyOutputHtml}</div>
          </td>
          <td>
            <div class="tc-block tc-output-block ${tc.passed ? '' : 'mismatch'}">
              ${rsOutputHtml}
              ${diffBannerHtml}
            </div>
          </td>
          <td>${statusBadge}</td>
        `;
        verificationTableBody.appendChild(tr);

        // 2. Expandable Drawer Row for Session Transcript
        const drawerTr = document.createElement('tr');
        drawerTr.className = 'tc-drawer-row';
        drawerTr.id = `drawer-tc-${idx}`;
        drawerTr.style.display = 'none';
        drawerTr.innerHTML = `
          <td colspan="5">
            <div class="terminal-window">
              <div class="terminal-header">
                <div class="terminal-dots">
                  <span class="terminal-dot dot-red"></span>
                  <span class="terminal-dot dot-yellow"></span>
                  <span class="terminal-dot dot-green"></span>
                </div>
                <span class="terminal-title">Dual Execution Transcript &mdash; Case #${idx + 1}</span>
                ${statusBadge}
              </div>
              <div class="terminal-body">
                <div class="session-dual-grid">
                  <div class="session-box">
                    <div class="session-box-title">🐍 Python Execution (Expected)</div>
                    <div class="session-box-content">${formatSessionTranscriptHtml(tc.session_transcript || (inputVal + '\n' + pyOutVal))}</div>
                  </div>
                  <div class="session-box ${tc.passed ? '' : 'session-box-mismatch'}">
                    <div class="session-box-title">🦀 Rust Execution (Actual)</div>
                    <div class="session-box-content">${formatSessionTranscriptHtml(tc.rust_session_transcript || (inputVal + '\n' + rsOutVal))}</div>
                  </div>
                </div>
                ${!tc.passed ? `
                  <div class="session-diff-alert">
                    <div class="session-diff-alert-title">⚖️ Divergence Analysis &amp; Difference:</div>
                    <pre class="session-diff-code">${escapeHtml(tc.diff || tc.error || `Expected '${pyOutVal}', got '${rsOutVal}'`)}</pre>
                  </div>
                ` : ''}
              </div>
            </div>
          </td>
        `;
        verificationTableBody.appendChild(drawerTr);

        // 3. Terminal Session Card for Grid View
        if (verificationSessionsContainer) {
          const termCard = document.createElement('div');
          termCard.className = 'terminal-window';
          termCard.innerHTML = `
            <div class="terminal-header">
              <div class="terminal-dots">
                <span class="terminal-dot dot-red"></span>
                <span class="terminal-dot dot-yellow"></span>
                <span class="terminal-dot dot-green"></span>
              </div>
              <span class="terminal-title">Test Case #${idx + 1}</span>
              ${statusBadge}
            </div>
            <div class="terminal-body">
              <div class="session-dual-grid">
                <div class="session-box">
                  <div class="session-box-title">🐍 Python (Expected)</div>
                  <div class="session-box-content">${formatSessionTranscriptHtml(tc.session_transcript || (inputVal + '\n' + pyOutVal))}</div>
                </div>
                <div class="session-box ${tc.passed ? '' : 'session-box-mismatch'}">
                  <div class="session-box-title">🦀 Rust (Actual)</div>
                  <div class="session-box-content">${formatSessionTranscriptHtml(tc.rust_session_transcript || (inputVal + '\n' + rsOutVal))}</div>
                </div>
              </div>
              ${!tc.passed ? `
                <div class="session-diff-alert">
                  <div class="session-diff-alert-title">⚖️ Difference:</div>
                  <pre class="session-diff-code">${escapeHtml(tc.diff || tc.error || `Expected: ${pyOutVal}\nGot: ${rsOutVal}`)}</pre>
                </div>
              ` : ''}
            </div>
            <div class="terminal-footer">
              <span style="color: var(--text-muted); font-size: 11px;">Dual Python/Rust Semantic Equivalence</span>
              <span style="color: ${tc.passed ? '#10b981' : '#ef4444'}; font-size: 11px; font-weight: 500;">
                ${tc.passed ? '✓ Output Match' : '✗ Output Mismatch'}
              </span>
            </div>
          `;
          verificationSessionsContainer.appendChild(termCard);
        }
      });

      // Wire drawer toggle buttons
      document.querySelectorAll('.btn-toggle-drawer').forEach(btn => {
        btn.addEventListener('click', () => {
          const targetId = btn.getAttribute('data-drawer-target');
          const drawer = document.getElementById(targetId);
          if (drawer) {
            const isHidden = drawer.style.display === 'none';
            drawer.style.display = isHidden ? 'table-row' : 'none';
            const labelSpan = btn.querySelector('span');
            if (labelSpan) {
              labelSpan.textContent = isHidden ? 'Hide Session' : 'Session View';
            }
          }
        });
      });
    } else {
      verificationTableBody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">No explicit test case breakdown available</td></tr>';
      if (verificationSessionsContainer) {
        verificationSessionsContainer.innerHTML = '<div style="text-align: center; color: var(--text-muted); padding: 20px;">No explicit test case breakdown available</div>';
      }
    }

    // Mismatch Feedback
    if (!verif.semantic_match && verif.mismatch_feedback) {
      mismatchFeedbackPre.textContent = verif.mismatch_feedback;
      mismatchFeedbackContainer.style.display = 'block';
    } else {
      mismatchFeedbackContainer.style.display = 'none';
    }
  }

  // ---------------------------------------------------------------------------
  // 5. Verification Syntax Formatters
  // ---------------------------------------------------------------------------

  function formatInputHtml(rawInput) {
    if (!rawInput) return '<span style="color: var(--text-muted);">&lt;none&gt;</span>';
    const lines = String(rawInput).split('\n');
    return lines.map(line => {
      const colIdx = line.indexOf(':');
      if (colIdx !== -1) {
        const prompt = line.slice(0, colIdx + 1);
        const val = line.slice(colIdx + 1).trim();
        return `<div class="tc-line"><span class="tc-prompt">${escapeHtml(prompt)}</span> <span class="tc-val">${escapeHtml(val)}</span></div>`;
      }
      return `<div class="tc-line"><span class="tc-val">${escapeHtml(line)}</span></div>`;
    }).join('');
  }

  function formatOutputHtml(rawOutput) {
    if (!rawOutput) return '<span style="color: var(--text-muted);">&lt;empty&gt;</span>';
    const lines = String(rawOutput).split('\n');
    return lines.map(line => {
      const colIdx = line.indexOf(':');
      if (colIdx !== -1 && line.toLowerCase().startsWith('result')) {
        const lbl = line.slice(0, colIdx + 1);
        const val = line.slice(colIdx + 1).trim();
        return `<div class="tc-line"><span class="tc-res-label">${escapeHtml(lbl)}</span> <span class="tc-res-val">${escapeHtml(val)}</span></div>`;
      }
      return `<div class="tc-line">${escapeHtml(line)}</div>`;
    }).join('');
  }

  function formatSessionTranscriptHtml(transcript) {
    if (!transcript) return '<div class="terminal-line" style="color: var(--text-muted);">&gt; empty</div>';
    const lines = String(transcript).split('\n');
    return lines.map(line => {
      const colIdx = line.indexOf(':');
      if (colIdx !== -1) {
        const prefix = line.slice(0, colIdx + 1);
        const suffix = line.slice(colIdx + 1).trim();
        if (prefix.toLowerCase().startsWith('result')) {
          return `<div class="terminal-line"><span class="tc-res-label">${escapeHtml(prefix)}</span> <span class="tc-res-val">${escapeHtml(suffix)}</span></div>`;
        }
        return `<div class="terminal-line"><span class="tc-prompt">${escapeHtml(prefix)}</span> <span class="tc-val">${escapeHtml(suffix)}</span></div>`;
      }
      return `<div class="terminal-line">${escapeHtml(line)}</div>`;
    }).join('');
  }

  // ---------------------------------------------------------------------------
  // 5. Standalone Rust Syntax Highlighter
  // ---------------------------------------------------------------------------

  function highlightRustSyntax(rawCode) {
    const lines = rawCode.split('\n');
    const highlightedLines = lines.map(line => {
      // Escape HTML first
      let l = escapeHtml(line);

      // Comments
      if (l.includes('//')) {
        const idx = l.indexOf('//');
        const before = l.substring(0, idx);
        const comment = l.substring(idx);
        return highlightLineTokens(before) + `<span class="token-comment">${comment}</span>`;
      }
      return highlightLineTokens(l);
    });

    return highlightedLines.join('\n');
  }

  function highlightLineTokens(str) {
    // Double-quoted string literals (escapeHtml converts " to &quot;)
    str = str.replace(/(?:&quot;|")(.*?)(?:&quot;|")/g, '<span class="token-str">$&</span>');
    // Single-quoted char literals like '\r', '\n', 'a' — single quotes are NOT HTML-escaped
    str = str.replace(/'(?:\\.|[^'])'/g, '<span class="token-str">$&</span>');

    // Macros e.g. println!, vec!, format!
    str = str.replace(/\b(println!|print!|vec!|format!|panic!|assert!|assert_eq!)\b/g, '<span class="token-macro">$1</span>');

    // Keywords
    str = str.replace(/\b(fn|let|mut|if|else|while|for|in|return|struct|impl|pub|use|std|collections|derive|Debug|Clone|as)\b/g, '<span class="token-kw">$1</span>');

    // Types
    str = str.replace(/\b(i8|i16|i32|i64|u8|u16|u32|u64|f32|f64|bool|String|Vec|HashMap|Option|Result)\b/g, '<span class="token-type">$1</span>');

    // Numbers
    str = str.replace(/\b(\d+(\.\d+)?)\b/g, '<span class="token-num">$1</span>');

    // Method calls like .clone(), .push()
    str = str.replace(/\.(clone|push|insert|len|step_by|from)\(/g, '.<span class="token-fn">$1</span>(');

    return str;
  }

  // ---------------------------------------------------------------------------
  // 6. Robust Standalone Markdown Parser (Offline-safe)
  // ---------------------------------------------------------------------------

  function renderMarkdown(mdText) {
    const lines = mdText.split('\n');
    let html = '';
    let inTable = false;
    let inCodeBlock = false;
    let codeBlockContent = '';

    for (let i = 0; i < lines.length; i++) {
      let line = lines[i];

      // Fenced code blocks
      if (line.trim().startsWith('```')) {
        if (inCodeBlock) {
          html += `<pre><code>${escapeHtml(codeBlockContent.trim())}</code></pre>`;
          codeBlockContent = '';
          inCodeBlock = false;
        } else {
          inCodeBlock = true;
          codeBlockContent = '';
        }
        continue;
      }

      if (inCodeBlock) {
        codeBlockContent += line + '\n';
        continue;
      }

      // Tables
      if (line.trim().startsWith('|') && line.trim().endsWith('|')) {
        // Check if it's separator row
        if (line.includes('---')) {
          continue;
        }
        const cells = line.split('|').map(c => c.trim()).filter((_, idx, arr) => idx > 0 && idx < arr.length - 1);
        if (!inTable) {
          inTable = true;
          html += '<table><thead><tr>';
          cells.forEach(c => html += `<th>${formatInlineMarkdown(c)}</th>`);
          html += '</tr></thead><tbody>';
        } else {
          html += '<tr>';
          cells.forEach(c => html += `<td>${formatInlineMarkdown(c)}</td>`);
          html += '</tr>';
        }
        continue;
      } else {
        if (inTable) {
          html += '</tbody></table>';
          inTable = false;
        }
      }

      // Headers
      if (line.startsWith('### ')) {
        html += `<h3>${formatInlineMarkdown(line.substring(4))}</h3>`;
      } else if (line.startsWith('## ')) {
        html += `<h2>${formatInlineMarkdown(line.substring(3))}</h2>`;
      } else if (line.startsWith('# ')) {
        html += `<h1>${formatInlineMarkdown(line.substring(2))}</h1>`;
      } else if (line.startsWith('- ')) {
        html += `<ul><li>${formatInlineMarkdown(line.substring(2))}</li></ul>`;
      } else if (line.trim().length === 0) {
        // empty line
      } else {
        html += `<p>${formatInlineMarkdown(line)}</p>`;
      }
    }

    if (inTable) {
      html += '</tbody></table>';
    }
    if (inCodeBlock) {
      html += `<pre><code>${escapeHtml(codeBlockContent.trim())}</code></pre>`;
    }

    return html;
  }

  function formatInlineMarkdown(str) {
    let s = escapeHtml(str);
    // Bold
    s = s.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    // Inline code
    s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
    return s;
  }

  function escapeHtml(str) {
    if (!str) return '';
    // NOTE: Single quotes (') are intentionally NOT escaped here.
    // They are safe in HTML body content and must be preserved verbatim in
    // Rust code (e.g. char literals like '\r', '\n') so that copy-paste
    // into an external compiler works correctly.
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }
});
