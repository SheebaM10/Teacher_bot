document.addEventListener("DOMContentLoaded", () => {
  const hamburgerBtn = document.getElementById("hamburgerBtn");
  if (hamburgerBtn) {
    hamburgerBtn.addEventListener("click", () => {
      const menu = document.getElementById("dropdownMenu");
      if (menu) {
        menu.style.display = menu.style.display === "flex" ? "none" : "flex";
      }
    });
  }
 
  const path = window.location.pathname;
 
  if (path.includes("question_bot.html")) {
    initQuestionBot();
  } else if (path.includes("teacher_bot.html")) {
    initTeacherBot();
  }

  // ✅ Stop any ongoing voice immediately when the page loads
if ('speechSynthesis' in window) {
  window.speechSynthesis.cancel();
}
 
  // Login form
  const loginForm = document.getElementById("loginForm");
  if (loginForm) {
    loginForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const username = document.getElementById("username").value.trim();
      const password = document.getElementById("password").value.trim();
      const loginError = document.getElementById("loginError");
 
      try {
        const res = await fetch("http://localhost:8000/login", {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body: new URLSearchParams({ username, password }),
        });
        const data = await res.json();
 
        if (data.success) {
          window.location.href = "home.html";
        } else {
          loginError.textContent = data.message || "Login failed";
        }
      } catch {
        loginError.textContent = "Error connecting to server.";
      }
    });
  }
 
  // Upload PDF
  const uploadButton = document.getElementById("uploadBtn");
  if (uploadButton) {
    uploadButton.addEventListener("click", uploadFile);
  }
 
  // Teacher Bot manual send button
  const sendBtn = document.getElementById("sendBtn");
  if (sendBtn) {
    sendBtn.addEventListener("click", askTeacherBot);
  }
});
 
// Global variable for current question
let currentQuestion = "";
 
// ========== Question Bot ==========

let chatHistory = [];

chatHistory.push({ role: "bot", message: currentQuestion });
chatHistory.push({ role: "user", message: userAnswer });
chatHistory.push({ role: "bot", message: evaluation });


function initQuestionBot() {
  const micBtn = document.getElementById("micBtn");
  if (!micBtn || !window.webkitSpeechRecognition) return;
 
  const recognition = new webkitSpeechRecognition();
  recognition.lang = 'en-US';
  recognition.continuous = false;
  recognition.interimResults = false;
 
  micBtn.addEventListener("click", () => {
    recognition.start();
    micBtn.innerText = "🎙️";
  });
 
  recognition.onresult = async (event) => {
    const userAnswer = event.results[0][0].transcript;
    appendMessage(userAnswer, "user");
    micBtn.innerText = "🎤";
 
    // Evaluate user's answer
    try {
      const res = await fetch("http://localhost:8000/evaluate_answer/", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({
          question: currentQuestion,
          answer: userAnswer
        })
      });
 
      const data = await res.json();
      const evaluation = data.evaluation || "Evaluation not available.";
      appendMessage(evaluation, "bot");
    } catch (err) {
      appendMessage("Error evaluating answer.", "bot");
    }
 
    setTimeout(() => askBotQuestion(), 3000); // Ask next after feedback
  };
 
  recognition.onerror = () => { micBtn.innerText = "🎤"; };
  recognition.onend = () => { micBtn.innerText = "🎤"; };
 
  askBotQuestion();
}
 
async function askBotQuestion() {
  try {
    const res = await fetch("http://localhost:8000/generate_question/", {
      method: "POST"
    });
    const data = await res.json();
    currentQuestion = data.question || "No question generated.";
    appendMessage(currentQuestion, "bot"); // speakText already handled inside appendMessage
  } catch {
    appendMessage("Error generating question.", "bot");
  }
}

function cleanBotResponse(response) {
  return response
    .replace(/^(The student's response:\s*)+/i, "")  // removes repeated prefix
    .replace(/^Answer:\s*/i, "")
    .trim();
}

 
// ========== Teacher Bot ==========
function initTeacherBot() {
  const micBtn = document.getElementById("micBtn");
  const input = document.getElementById("questionInput");
 
  if (micBtn && input && 'webkitSpeechRecognition' in window) {
    const recognition = new webkitSpeechRecognition();
    recognition.lang = 'en-US';
    recognition.continuous = false;
    recognition.interimResults = false;
 
    micBtn.addEventListener("click", () => {
      recognition.start();
      micBtn.innerText = "🎙️";
    });
 
    recognition.onresult = (event) => {
      input.value = event.results[0][0].transcript;
      askTeacherBot();
      micBtn.innerText = "🎤";
    };
 
    recognition.onerror = () => { micBtn.innerText = "🎤"; };
    recognition.onend = () => { micBtn.innerText = "🎤"; };
  }
}
 
async function askTeacherBot() {
  const input = document.getElementById("questionInput");
  const question = input.value.trim();
  if (!question) return;
 
  appendMessage(question, "user");
  input.value = "";
 
  try {
    const res = await fetch("http://localhost:8000/ask", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ question }),
    });
    const data = await res.json();
    const rawAnswer = data.answer || "No answer found.";
    const cleaned = cleanBotResponse(rawAnswer);
    appendMessage(cleaned, "bot");
  } catch {
    appendMessage("Error communicating with server.", "bot");
  }
}
 
// ========== Upload ==========
async function uploadFile() {
  const input = document.getElementById("fileInput");
  if (!input || input.files.length === 0) {
    alert("Please select a file first.");
    return;
  }
 
  const formData = new FormData();
  formData.append("file", input.files[0]);
 
  try {
    const res = await fetch("http://localhost:8000/upload_pdf", {
      method: "POST",
      body: formData,
    });
    const result = await res.json();
    alert(result.message || "Uploaded successfully!");
  } catch (err) {
    console.error("Upload failed:", err);
    alert("Upload failed.");
  }
}
 
// ========== Utilities ==========
function appendMessage(msg, sender) {
  const chatBox = document.getElementById("chatBox");
  if (!chatBox) return;
 
  const msgElem = document.createElement("div");
  msgElem.className = "chat-msg " + sender;
  msgElem.textContent = msg;
  chatBox.appendChild(msgElem);
  chatBox.scrollTop = chatBox.scrollHeight;
 
  if (sender === "bot") speakText(msg);
}
 
function speakText(text) {
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = 'en-US';
  speechSynthesis.speak(utterance);
}
 
function cleanBotResponse(response) {
  return response
    .replace(/^Question:\s*.*?\n?/i, "")
    .replace(/^Answer based on knowledge base:\s*/i, "")
    .replace(/^Answer:\s*/i, "")
    .trim();
}
 