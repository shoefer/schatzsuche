const els = {
  step: document.getElementById("step"),
  title: document.getElementById("title"),
  prompt: document.getElementById("prompt"),
  hintWrap: document.getElementById("hintWrap"),
  hintText: document.getElementById("hintText"),
  media: document.getElementById("media"),
  form: document.getElementById("form"),
  answer: document.getElementById("answer"),
  msg: document.getElementById("msg"),
  resetBtn: document.getElementById("resetBtn"),
};

let countdownTimer = null;
let currentQuestionIndex = null;

const ATTEMPT_KEY = "attemptsByQuestion"; // localStorage key

function getAttemptsMap() {
  try {
    return JSON.parse(localStorage.getItem(ATTEMPT_KEY) || "{}");
  } catch {
    return {};
  }
}

function getAttempts(qid) {
  const m = getAttemptsMap();
  return Number(m[qid] || 0);
}

function setAttempts(qid, n) {
  const m = getAttemptsMap();
  m[qid] = n;
  localStorage.setItem(ATTEMPT_KEY, JSON.stringify(m));
}

function resetAttempts(qid) {
  const m = getAttemptsMap();
  delete m[qid];
  localStorage.setItem(ATTEMPT_KEY, JSON.stringify(m));
}

function maybeRevealHint(data) {
  // data = /api/current payload (hat hint + id)
  if (!data || !data.hint || !data.id) return;
  const tries = getAttempts(data.id);
  if (tries >= 3) {
    els.hintWrap.hidden = false;
    els.hintWrap.open = true; // automatisch aufklappen
  }
}

function setMsg(html, kind = "") {
  setRich(els.msg, html);
  els.msg.className = `msg ${kind}`.trim();
}

function setRich(el, html) {
  // \n -> <br> damit deine JSON-Strings mit \n weiterhin hübsch umbrechen
  el.innerHTML = (html ?? "").toString().replace(/\n/g, "<br>");
}

function setFormEnabled(enabled) {
  els.answer.disabled = !enabled;
  const btn = els.form.querySelector('button[type="submit"]');
  if (btn) btn.disabled = !enabled;
}

function clearCountdown() {
  if (countdownTimer) {
    clearInterval(countdownTimer);
    countdownTimer = null;
  }
}

function renderMedia(url) {
  els.media.innerHTML = "";
  if (!url) {
    els.media.hidden = true;
    return;
  }
  els.media.hidden = false;

  const lower = url.toLowerCase();
  if (lower.match(/\.(jpg|jpeg|png|webp|gif)$/)) {
    const img = document.createElement("img");
    img.src = url;
    img.alt = "Hinweis-Medium";
    img.loading = "lazy";
    els.media.appendChild(img);
  } else if (lower.match(/\.(mp4|webm)$/)) {
    const v = document.createElement("video");
    v.src = url;
    v.controls = true;
    v.playsInline = true;
    v.preload = "metadata";
    els.media.appendChild(v);
  } else if (lower.match(/\.(mp3|wav|ogg)$/)) {
    const a = document.createElement("audio");
    a.src = url;
    a.controls = true;
    a.preload = "metadata";
    els.media.appendChild(a);
  } else {
    const link = document.createElement("a");
    link.href = url;
    link.textContent = "Medium öffnen";
    link.target = "_blank";
    link.rel = "noreferrer";
    els.media.appendChild(link);
  }
}

async function loadCurrent() {
  clearCountdown();
  setFormEnabled(true);
  setMsg("");

  const r = await fetch("/api/current", { credentials: "same-origin" });
  const data = await r.json();

  currentQuestionIndex = data.progress;

  if (data.done) {
    els.step.textContent = `Fertig 🎉`;
    els.title.textContent = `Alle Aufgaben gelöst!`;
    els.prompt.textContent = `Super! Du hast alle ${data.total} Stationen geschafft. Der Schatz befindet sich im Ofen bei Höfers/Bolls!`;
    els.form.hidden = true;
    renderMedia(null);
    els.hintWrap.hidden = true;
    els.hintWrap.open = false;
    return;
  }

  els.form.hidden = false;
  els.step.textContent = `Aufgabe ${data.progress + 1} / ${data.total}`;
  setRich(els.title, data.title || `Aufgabe ${data.progress + 1}`);
  setRich(els.prompt, data.prompt || "");
  renderMedia(data.media);

  if (data.hint) {
    // standardmäßig versteckt
    setRich(els.hintText, data.hint);
    els.hintWrap.hidden = true;
    els.hintWrap.open = false;

    // ab 3 Fehlversuchen automatisch zeigen
    maybeRevealHint(data);
  } else {
    els.hintWrap.hidden = true;
    els.hintWrap.open = false;
    els.hintText.textContent = "";
  }

  els.answer.value = "";
  els.answer.focus();
}

async function submitAnswer(answer) {
  clearCountdown();
  setMsg("Prüfe…");
  setFormEnabled(false);

  let data;
  try {
    const r = await fetch("/api/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ answer }),
    });
    data = await r.json();
  } catch (err) {
    setMsg("Netzwerkfehler beim Prüfen.", "bad");
    setFormEnabled(true);
    return;
  }

  if (!data || !data.ok) {
    setMsg("Fehler beim Prüfen.", "bad");
    setFormEnabled(true);
    return;
  }

  const reaction =
    data.reaction && String(data.reaction).trim()
      ? String(data.reaction).trim()
      : data.correct
      ? "Richtig ✅"
      : "Leider falsch.";

  if (data.correct) {
    // Attempts für diese Frage zurücksetzen
    if (currentQuestionIndex !== null) {
      resetAttempts(currentQuestionIndex);
    }

    let remaining = 5;
    setMsg(`${reaction} <span>(weiter in ${remaining}s)</span>`, "good");
    setFormEnabled(false);

    countdownTimer = setInterval(() => {
      remaining -= 1;
      if (remaining <= 0) {
        clearCountdown();
        loadCurrent();
      } else {
        setMsg(`${reaction} (weiter in ${remaining}s)`, "good");
      }
    }, 1000);

    return;
  }

  // falsch: Attempts hochzählen, ggf. Hint zeigen
  if (currentQuestionIndex !== null) {
    const tries = getAttempts(currentQuestionIndex) + 1;
    setAttempts(currentQuestionIndex, tries);

    if (tries >= 3) {
      els.hintWrap.hidden = false;
      els.hintWrap.open = true;
    }
  }

  setMsg(reaction, "bad");
  setFormEnabled(true);
  els.answer.select();
}

els.form.addEventListener("submit", (e) => {
  e.preventDefault();
  const answer = els.answer.value;
  if (!answer.trim()) {
    setMsg("Bitte gib eine Antwort ein.", "bad");
    return;
  }
  submitAnswer(answer);
});

els.resetBtn.addEventListener("click", async () => {
  if (!confirm("Fortschritt wirklich zurücksetzen?")) return;

  clearCountdown();
  localStorage.removeItem(ATTEMPT_KEY);

  await fetch("/api/reset", { method: "POST", credentials: "same-origin" });
  await loadCurrent();
});

// Start
loadCurrent();
