// LoanLedger AI Chatbot Interface
document.addEventListener("DOMContentLoaded", () => {
  const launcher = document.getElementById("chatbotLauncher");
  const windowEl = document.getElementById("chatbotWindow");
  const closeBtn = document.getElementById("chatbotClose");
  const msgsContainer = document.getElementById("chatbotMessages");
  const form = document.getElementById("chatbotForm");
  const input = document.getElementById("chatbotInput");

  if (!launcher || !windowEl || !closeBtn || !msgsContainer || !form || !input) {
    return;
  }

  // Load chat history from sessionStorage
  let chatHistory = [];
  try {
    const stored = sessionStorage.getItem("loanledger_chat_history");
    if (stored) {
      chatHistory = JSON.parse(stored);
    }
  } catch (e) {
    console.error("Failed to parse chat history", e);
  }

  // Toggle Chatbot
  const badgeEl = document.getElementById("chatbotBadge");
  const startersEl = document.getElementById("chatbotStarters");
  
  launcher.addEventListener("click", () => {
    launcher.classList.toggle("active");
    windowEl.classList.toggle("open");
    if (windowEl.classList.contains("open")) {
      input.focus();
      scrollToBottom();
      if (badgeEl) badgeEl.style.display = "none";
    }
  });

  closeBtn.addEventListener("click", () => {
    launcher.classList.remove("active");
    windowEl.classList.remove("open");
  });

  // Toggle Help Popover
  const helpBtn = document.getElementById("chatbotHelpBtn");
  const helpPopover = document.getElementById("chatbotHelpPopover");

  if (helpBtn && helpPopover) {
    helpBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      helpPopover.classList.toggle("open");
    });

    document.addEventListener("click", (e) => {
      if (!helpPopover.contains(e.target) && e.target !== helpBtn) {
        helpPopover.classList.remove("open");
      }
    });
  }

  // Render initial greeting if history is empty
  if (chatHistory.length === 0) {
    appendMessage("assistant", "Hi! I'm your LoanLedger Assistant. I can help you manage your loans using natural language.\n\nYou can ask me to:\n* **Create a loan** (e.g., *'Create an auto loan named Car Loan, amount 20000, interest 5.5%, tenure 36 months, starting 2026-07-01'*\n* **List loans** (*'Show all my active loans'*)\n* **Get loan details** (*'Give me details of loan car-123'*)\n* **Change interest rates** (*'Change interest rate of auto-123 to 4.5%'*)\n* **Change tenure** (*'Change tenure of auto-123 to 24 months'*)\n* **Modify name/bank/notes** (*'Update bank for auto-123 to Wells Fargo'*)\n\nWhat can I do for you today?");
  } else {
    // Render existing history
    chatHistory.forEach(msg => {
      const text = msg.parts && msg.parts[0] ? msg.parts[0].text : "";
      if (text) {
        appendMessage(msg.role === "user" ? "user" : "assistant", text, false);
      }
    });
  }

  // Send message
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const userMsg = input.value.trim();
    if (!userMsg) return;

    // Append user message to UI and history
    appendMessage("user", userMsg);
    input.value = "";
    
    // Add turn to history
    chatHistory.push({
      role: "user",
      parts: [{ text: userMsg }]
    });
    saveHistory();

    // Render typing indicator
    const typingIndicator = appendTypingIndicator();
    scrollToBottom();

    // Prepare API call
    try {
      const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") || "";
      const res = await fetch("/chatbot/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken
        },
        body: JSON.stringify({
          message: userMsg,
          history: chatHistory
        })
      });

      const data = await res.json();
      removeTypingIndicator(typingIndicator);

      if (data.reply) {
        appendMessage("assistant", data.reply);
        
        // Update history from server
        if (data.history) {
          chatHistory = data.history;
        } else {
          chatHistory.push({
            role: "model",
            parts: [{ text: data.reply }]
          });
        }
        saveHistory();

        // If a loan action was successful, refresh the dashboard charts and active loan list
        if (data.reply.toLowerCase().includes("successfully") || data.reply.toLowerCase().includes("updated") || data.reply.toLowerCase().includes("created")) {
          if (window.refreshDashboard) {
            window.refreshDashboard();
          }
          // Optionally trigger local page refresh or dynamic reload after some delay if on loan detail pages
          if (window.location.pathname.includes("/loans/") || window.location.pathname.includes("/recalculate")) {
            setTimeout(() => window.location.reload(), 2000);
          }
        }
      } else if (data.error === "api_key_missing") {
        appendMessage("assistant", data.reply);
      } else {
        appendMessage("assistant", "Sorry, I encountered an issue. Please try again.");
      }
    } catch (err) {
      removeTypingIndicator(typingIndicator);
      appendMessage("assistant", "Network error. Failed to reach the chatbot server.");
      console.error(err);
    }
    scrollToBottom();
  });

  // Helper: Append Message Bubble
  function appendMessage(role, text, shouldScroll = true) {
    const bubble = document.createElement("div");
    bubble.className = `chat-msg ${role}`;
    bubble.innerHTML = formatMarkdown(text);
    msgsContainer.appendChild(bubble);
    if (shouldScroll) {
      scrollToBottom();
    }
  }

  // Helper: Append Typing Indicator
  function appendTypingIndicator() {
    const indicator = document.createElement("div");
    indicator.className = "typing-indicator";
    indicator.innerHTML = `
      <span class="typing-dot"></span>
      <span class="typing-dot"></span>
      <span class="typing-dot"></span>
    `;
    msgsContainer.appendChild(indicator);
    return indicator;
  }

  // Helper: Remove Typing Indicator
  function removeTypingIndicator(el) {
    if (el && el.parentNode) {
      el.parentNode.removeChild(el);
    }
  }

  // Helper: Scroll container to bottom
  function scrollToBottom() {
    msgsContainer.scrollTop = msgsContainer.scrollHeight;
  }

  // Helper: Save conversation history
  function saveHistory() {
    // Keep last 30 turns to avoid hitting storage or payload limits
    if (chatHistory.length > 60) {
      chatHistory = chatHistory.slice(chatHistory.length - 60);
    }
    sessionStorage.setItem("loanledger_chat_history", JSON.stringify(chatHistory));
  }

  // Helper: Format Markdown markup into HTML safe tags
  function formatMarkdown(text) {
    if (!text) return "";
    
    // HTML Escape
    let html = text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");

    // Bold text: **text**
    html = html.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");

    // Code: `code`
    html = html.replace(/`(.*?)`/g, "<code>$1</code>");

    // Lists and linebreaks
    const lines = html.split("\n");
    let inList = false;
    let result = [];

    for (let line of lines) {
      const trimmed = line.trim();
      if (trimmed.startsWith("* ") || trimmed.startsWith("- ")) {
        if (!inList) {
          result.push('<ul style="margin-left: 16px; margin-top: 4px; margin-bottom: 4px; list-style-type: disc;">');
          inList = true;
        }
        result.push(`<li style="margin-bottom: 2px;">${trimmed.substring(2)}</li>`);
      } else {
        if (inList) {
          result.push("</ul>");
          inList = false;
        }
        if (trimmed) {
          result.push(`<p style="margin-bottom: 6px;">${line}</p>`);
        } else {
          result.push('<div style="height: 6px;"></div>');
        }
      }
    }
    if (inList) {
      result.push("</ul>");
    }

    return result.join("");
  }

  // Render starter chips dynamically
  function renderStarters(starters) {
    if (!startersEl) return;
    startersEl.innerHTML = "";
    startersEl.style.display = "flex";
    
    starters.forEach(text => {
      const chip = document.createElement("div");
      chip.className = "chatbot-starter-chip";
      chip.textContent = text;
      chip.addEventListener("click", () => {
        input.value = text;
        form.dispatchEvent(new Event("submit"));
        startersEl.style.display = "none";
      });
      startersEl.appendChild(chip);
    });
  }

  // Fetch proactive alerts and suggestion chips
  async function runProactiveCheck() {
    try {
      const res = await fetch("/chatbot/proactive-check");
      const data = await res.json();
      
      if (data.notification) {
        if (badgeEl) badgeEl.style.display = "block";
        
        if (chatHistory.length === 0) {
          msgsContainer.innerHTML = ""; // Clear initial instructions to prioritize notification alert
          appendMessage("assistant", data.notification);
          chatHistory.push({
            role: "model",
            parts: [{ text: data.notification }]
          });
          saveHistory();
        }
      }
      
      if (data.starters && data.starters.length > 0) {
        renderStarters(data.starters);
      }
    } catch (e) {
      console.error("Proactive check failed", e);
    }
  }

  // Web Speech API Microphone Integration
  const micBtn = document.getElementById("chatbotMicBtn");
  if (micBtn) {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
      const recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.lang = "en-US";
      recognition.interimResults = false;
      
      let isListening = false;
      
      micBtn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (!isListening) {
          recognition.start();
        } else {
          recognition.stop();
        }
      });
      
      recognition.onstart = () => {
        isListening = true;
        micBtn.classList.add("listening");
        input.placeholder = "Listening...";
      };
      
      recognition.onend = () => {
        isListening = false;
        micBtn.classList.remove("listening");
        input.placeholder = "Ask about your loans...";
      };
      
      recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        input.value = transcript;
        input.focus();
      };
      
      recognition.onerror = (event) => {
        console.error("Speech recognition error", event.error);
        input.placeholder = "Speech error. Try again...";
        setTimeout(() => {
          input.placeholder = "Ask about your loans...";
        }, 2000);
      };
    } else {
      micBtn.style.display = "none";
    }
  }

  // Trigger Proactive dashboard warning checks
  runProactiveCheck();
});
