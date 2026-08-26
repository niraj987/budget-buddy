/* ==========================================================================
   Savings Goal Tracker Agent - Frontend JavaScript (ES6)
   ========================================================================== */

document.addEventListener("DOMContentLoaded", () => {
  // DOM Elements - Dashboard KPIs
  const kpiGoalAmount = document.getElementById("kpi-goal-amount");
  const kpiGoalPeriod = document.getElementById("kpi-goal-period");
  const kpiTotalSaved = document.getElementById("kpi-total-saved");
  const kpiSavedPct = document.getElementById("kpi-saved-pct");
  const kpiRemainingAmount = document.getElementById("kpi-remaining-amount");
  const kpiDeadlineDate = document.getElementById("kpi-deadline-date");

  // DOM Elements - Progress Gauge & Metrics
  const statusPill = document.getElementById("status-pill");
  const gaugeFill = document.getElementById("gauge-fill");
  const gaugePctText = document.getElementById("gauge-percentage");
  const metricMonthsElapsed = document.getElementById("metric-months-elapsed");
  const metricExpected = document.getElementById("metric-expected");
  const metricMonthlyGoingForward = document.getElementById("metric-monthly-going-forward");
  const linearFill = document.getElementById("linear-fill");

  // DOM Elements - Catch-Up Card
  const catchupCard = document.getElementById("catchup-card");
  const catchupStandardAmount = document.getElementById("catchup-standard-amount");
  const catchupSprintAmount = document.getElementById("catchup-sprint-amount");
  const catchupSprintLabel = document.getElementById("catchup-sprint-label");

  // DOM Elements - Deposit History
  const historyList = document.getElementById("history-list");
  const historyCount = document.getElementById("history-count");

  // DOM Elements - Chat UI
  const chatMessages = document.getElementById("chat-messages");
  const chatForm = document.getElementById("chat-form");
  const chatInput = document.getElementById("chat-input");
  const resetBtn = document.getElementById("reset-btn");
  const suggestionChips = document.querySelectorAll(".chip");

  // DOM Elements - Modals
  const goalModal = document.getElementById("goal-modal");
  const depositModal = document.getElementById("deposit-modal");
  const openGoalModalBtn = document.getElementById("open-goal-modal");
  const openDepositModalBtn = document.getElementById("open-deposit-modal");
  const closeModalBtns = document.querySelectorAll(".close-modal");
  const goalForm = document.getElementById("goal-form");
  const depositForm = document.getElementById("deposit-form");

  // Format INR Currency
  function formatINR(amount) {
    if (amount === undefined || amount === null || isNaN(amount)) return "₹0.00";
    return "₹" + Number(amount).toLocaleString("en-IN", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }

  // Fetch Current State & Update UI
  async function loadState() {
    try {
      const res = await fetch("/api/state");
      if (!res.ok) throw new Error("Failed to fetch state");
      const data = await res.json();
      updateDashboard(data);
    } catch (err) {
      console.error("Error loading state:", err);
    }
  }

  // Update Dashboard Components
  function updateDashboard(data) {
    const state = data.state || {};
    const progress = data.progress || {};
    const catchup = data.catchup || {};

    const goalAmount = state.goal_amount || 0;
    const savedTotal = state.saved_total || 0;
    const remainingAmount = goalAmount > 0 ? Math.max(goalAmount - savedTotal, 0) : 0;
    const history = state.history || [];

    // 1. Update KPI Cards
    kpiGoalAmount.textContent = goalAmount > 0 ? formatINR(goalAmount) : "₹0.00";
    kpiGoalPeriod.textContent = state.goal_months ? `Over ${state.goal_months} months` : "No goal set";

    kpiTotalSaved.textContent = formatINR(savedTotal);
    const pctAchieved = goalAmount > 0 ? Math.min(Math.round((savedTotal / goalAmount) * 100), 100) : 0;
    kpiSavedPct.textContent = `${pctAchieved}% of target`;

    kpiRemainingAmount.textContent = formatINR(remainingAmount);
    kpiDeadlineDate.textContent = state.deadline_date ? `Deadline: ${state.deadline_date}` : "Deadline: --";

    // 2. Update Gauge & Progress Bar
    const circumference = 314.15; // 2 * PI * 50
    const offset = circumference - (pctAchieved / 100) * circumference;
    gaugeFill.style.strokeDashoffset = offset;
    gaugePctText.textContent = `${pctAchieved}%`;
    linearFill.style.width = `${pctAchieved}%`;

    // 3. Update Status Pill
    if (!goalAmount) {
      statusPill.className = "status-pill status-gray";
      statusPill.textContent = "No Goal Set";
    } else if (progress.goal_reached) {
      statusPill.className = "status-pill status-emerald";
      statusPill.textContent = "🎉 Goal Reached!";
    } else if (progress.on_track) {
      statusPill.className = "status-pill status-emerald";
      statusPill.textContent = "On Track";
    } else {
      statusPill.className = "status-pill status-rose";
      statusPill.textContent = "Behind Pace";
    }

    // 4. Update Metrics Breakdown
    if (goalAmount > 0 && progress.status !== "error") {
      metricMonthsElapsed.textContent = `${progress.months_elapsed || 0} / ${state.goal_months || 0} months`;
      metricExpected.textContent = formatINR(progress.expected_saved_by_now || 0);
      metricMonthlyGoingForward.textContent = `${formatINR(progress.required_monthly_saving_going_forward || 0)} / mo`;
    } else {
      metricMonthsElapsed.textContent = "0 / 0 months";
      metricExpected.textContent = "₹0.00";
      metricMonthlyGoingForward.textContent = "₹0.00 / mo";
    }

    // 5. Update Catch-Up Card
    if (catchup && catchup.status === "catchup_plan") {
      catchupCard.classList.remove("hidden");
      catchupStandardAmount.textContent = formatINR(catchup.standard_catchup_monthly_saving);
      catchupSprintAmount.textContent = formatINR(catchup.accelerated_sprint_monthly_saving);
      catchupSprintLabel.textContent = `per month for ${catchup.accelerated_sprint_months} months`;
    } else {
      catchupCard.classList.add("hidden");
    }

    // 6. Update Deposit History Log
    historyCount.textContent = `${history.length} deposit${history.length === 1 ? "" : "s"}`;
    historyList.innerHTML = "";

    if (history.length === 0) {
      historyList.innerHTML = `<li class="empty-history"><i class="fa-solid fa-folder-open"></i> No savings logged yet. Start by typing in chat or using Quick Deposit!</li>`;
    } else {
      // Show newest first
      [...history].reverse().forEach((item) => {
        const li = document.createElement("li");
        li.className = "history-item";
        li.innerHTML = `
          <div class="history-date">
            <i class="fa-solid fa-calendar-day"></i> ${item.date}
          </div>
          <div class="history-amount">+${formatINR(item.amount)}</div>
        `;
        historyList.appendChild(li);
      });
    }
  }

  // Chat UI Functions
  function appendUserMessage(text) {
    const msgWrapper = document.createElement("div");
    msgWrapper.className = "message-wrapper message-user";
    msgWrapper.innerHTML = `
      <div class="msg-avatar"><i class="fa-solid fa-user"></i></div>
      <div class="msg-body">
        <div class="msg-author">You</div>
        <div class="msg-content">${escapeHTML(text)}</div>
      </div>
    `;
    chatMessages.appendChild(msgWrapper);
    scrollToBottom();
  }

  function appendAgentMessage(text, toolsCalled = []) {
    const msgWrapper = document.createElement("div");
    msgWrapper.className = "message-wrapper message-agent";

    let toolsHTML = "";
    if (toolsCalled && toolsCalled.length > 0) {
      const toolPills = toolsCalled.map(t => `<span class="tool-badge"><i class="fa-solid fa-bolt"></i> ${t}</span>`).join("");
      toolsHTML = `<div class="tool-badge-container">${toolPills}</div>`;
    }

    // Use marked if available, otherwise plain HTML
    const formattedContent = typeof marked !== "undefined" ? marked.parse(text) : escapeHTML(text);

    msgWrapper.innerHTML = `
      <div class="msg-avatar"><i class="fa-solid fa-robot"></i></div>
      <div class="msg-body">
        <div class="msg-author">Budget Buddy</div>
        ${toolsHTML}
        <div class="msg-content">${formattedContent}</div>
      </div>
    `;
    chatMessages.appendChild(msgWrapper);
    scrollToBottom();
  }

  function appendTypingIndicator() {
    const msgWrapper = document.createElement("div");
    msgWrapper.id = "typing-indicator";
    msgWrapper.className = "message-wrapper message-agent";
    msgWrapper.innerHTML = `
      <div class="msg-avatar"><i class="fa-solid fa-robot"></i></div>
      <div class="msg-body">
        <div class="msg-author">Budget Buddy</div>
        <div class="msg-content">
          <i class="fa-solid fa-spinner fa-spin"></i> Budget Buddy evaluating tools...
        </div>
      </div>
    `;
    chatMessages.appendChild(msgWrapper);
    scrollToBottom();
  }

  function removeTypingIndicator() {
    const el = document.getElementById("typing-indicator");
    if (el) el.remove();
  }

  function scrollToBottom() {
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function escapeHTML(str) {
    return str.replace(/[&<>'"]/g, 
      tag => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[tag] || tag)
    );
  }

  // Handle Send Chat
  async function handleSendChat(userText) {
    if (!userText.trim()) return;

    appendUserMessage(userText);
    chatInput.value = "";
    chatInput.style.height = "auto";
    appendTypingIndicator();

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: userText }),
      });

      removeTypingIndicator();

      if (!res.ok) {
        const errData = await res.json();
        appendAgentMessage(`❌ Error: ${errData.error || "Failed to communicate with agent"}`);
        return;
      }

      const data = await res.json();
      appendAgentMessage(data.response, data.tools_called);

      if (data.status) {
        updateDashboard(data.status);
      }
    } catch (err) {
      removeTypingIndicator();
      appendAgentMessage(`❌ Error connecting to agent server: ${err.message}`);
    }
  }

  // Event Listeners
  chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    handleSendChat(chatInput.value);
  });

  chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendChat(chatInput.value);
    }
  });

  // Reset Memory & Chat
  resetBtn.addEventListener("click", async () => {
    if (!confirm("Are you sure you want to reset your goal and savings history?")) return;

    try {
      const res = await fetch("/api/reset", { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        updateDashboard(data.status);
        chatMessages.innerHTML = `
          <div class="message-wrapper message-agent">
            <div class="msg-avatar"><i class="fa-solid fa-robot"></i></div>
            <div class="msg-body">
              <div class="msg-author">Savings Agent</div>
              <div class="msg-content">Memory and history cleared! What goal would you like to set today? 🎯</div>
            </div>
          </div>
        `;
      }
    } catch (err) {
      alert("Failed to reset memory: " + err.message);
    }
  });

  // Suggestion Chips
  suggestionChips.forEach((chip) => {
    chip.addEventListener("click", () => {
      const prompt = chip.dataset.prompt;
      handleSendChat(prompt);
    });
  });

  // Modals Handler
  openGoalModalBtn.addEventListener("click", () => goalModal.classList.remove("hidden"));
  openDepositModalBtn.addEventListener("click", () => depositModal.classList.remove("hidden"));

  closeModalBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      goalModal.classList.add("hidden");
      depositModal.classList.add("hidden");
    });
  });

  // Goal Form Submit
  goalForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const amount = parseFloat(document.getElementById("goal-amount-input").value);
    const months = parseInt(document.getElementById("goal-months-input").value);

    try {
      const res = await fetch("/api/goal", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ amount, months }),
      });
      if (res.ok) {
        const data = await res.json();
        updateDashboard(data.status);
        goalModal.classList.add("hidden");
        goalForm.reset();
        appendAgentMessage(`Goal updated directly via dashboard: Save ${formatINR(amount)} over ${months} months! 🎯`);
      } else {
        const err = await res.json();
        alert("Error: " + err.error);
      }
    } catch (err) {
      alert("Failed to set goal: " + err.message);
    }
  });

  // Deposit Form Submit
  depositForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const amount = parseFloat(document.getElementById("deposit-amount-input").value);

    try {
      const res = await fetch("/api/deposit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ amount }),
      });
      if (res.ok) {
        const data = await res.json();
        updateDashboard(data.status);
        depositModal.classList.add("hidden");
        depositForm.reset();
        appendAgentMessage(`Logged deposit of ${formatINR(amount)} via quick deposit button! 💰`);
      } else {
        const err = await res.json();
        alert("Error: " + err.error);
      }
    } catch (err) {
      alert("Failed to log deposit: " + err.message);
    }
  });

  // Initial Load
  loadState();
});
