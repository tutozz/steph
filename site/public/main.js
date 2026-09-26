const L = window.STEPH_L10N;
const root = document.documentElement;
const live = document.getElementById("live");

function announce(msg) {
  // Vider puis réécrire : un lecteur d'écran n'annonce pas deux fois le même texte.
  live.textContent = "";
  requestAnimationFrame(() => { live.textContent = msg; });
}

// ---------- thème ----------

const themeButton = document.querySelector("[data-theme-toggle]");
const systemDark = window.matchMedia("(prefers-color-scheme: dark)");

function isDark() {
  return root.dataset.theme ? root.dataset.theme === "dark" : systemDark.matches;
}

function syncThemeButton() {
  themeButton.setAttribute("aria-pressed", String(isDark()));
}

themeButton.addEventListener("click", () => {
  const next = isDark() ? "light" : "dark";
  root.dataset.theme = next;
  try { localStorage.setItem("steph-theme", next); } catch {}
  syncThemeButton();
});
systemDark.addEventListener("change", syncThemeButton);
syncThemeButton();

// ---------- copie ----------

const commands = {
  hero: "curl -fsSL https://steph.lsmdx.com/install | sh",
  linux: "git clone https://github.com/tutozz/steph\ncd steph\n./scripts/install.sh\nsteph",
  mac: "brew install uv llama.cpp sox\ngit clone https://github.com/tutozz/steph\ncd steph\n./scripts/install.sh\nsteph",
};

document.querySelectorAll("[data-copy]").forEach((button) => {
  let timer;
  button.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(commands[button.dataset.copy]);
      button.textContent = L.copied;
      announce(L.copiedMsg);
    } catch {
      announce(L.copyFail);
    }
    clearTimeout(timer);
    timer = setTimeout(() => { button.textContent = L.copy; }, 2400);
  });
});

// ---------- extraits audio ----------

function fmt(t) {
  if (!t || !isFinite(t)) return "0:00";
  const s = Math.round(t);
  return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0");
}

const players = [...document.querySelectorAll("[data-clip]")].map((el) => {
  const audio = new Audio("/audio/" + el.dataset.clip + ".mp3");
  audio.preload = "metadata";
  const button = el.querySelector(".play");
  const label = el.querySelector(".lbl");
  const bar = el.querySelector(".bar i");
  const time = el.querySelector(".time");

  const render = () => {
    const on = !audio.paused;
    button.toggleAttribute("data-on", on);
    label.textContent = on ? L.pause : L.play;
    button.setAttribute("aria-label", (on ? L.pause : L.play) + ", " + el.dataset.name);
    bar.style.width = (audio.duration ? (audio.currentTime / audio.duration) * 100 : 0) + "%";
    time.textContent = fmt(audio.currentTime) + " / " + fmt(audio.duration);
  };

  ["loadedmetadata", "timeupdate", "play", "pause"].forEach((e) => audio.addEventListener(e, render));
  audio.addEventListener("ended", () => { audio.currentTime = 0; render(); });
  render();
  return { audio, button };
});

// Un seul extrait à la fois : deux voix superposées sont inaudibles.
players.forEach(({ audio, button }) => {
  button.addEventListener("click", () => {
    if (!audio.paused) { audio.pause(); return; }
    players.forEach((p) => p.audio.pause());
    stopDemo();
    audio.play().catch(() => {});
  });
});

// ---------- démo du hero ----------

const demo = document.querySelector(".demo");
const demoSteps = [...demo.querySelectorAll("[data-step]")].sort((a, b) => a.dataset.step - b.dataset.step);
const demoSays = demoSteps.filter((el) => el.dataset.say);
const demoButton = demo.querySelector(".demo-play");
const demoLabel = demoButton.querySelector(".lbl");
const demoAudio = {};
demo.querySelectorAll("[data-say]").forEach((el) => {
  demoAudio[el.dataset.say] = new Audio("/audio/" + el.dataset.say + ".mp3");
});
const demoScreen = demo.querySelector(".screen");
let demoRun = 0;

const demoDump = demo.querySelector(".dump");

// La dernière commande tapée reste en haut de l'écran ; une sortie trop longue défile
// sous elle en montrant ses dernières lignes, comme dans un terminal.
function followDemo() {
  const shown = demoSteps.filter((el) => !el.hidden && el.classList.contains("prompt") && !el.classList.contains("ask"));
  const last = shown.at(-1);
  if (!last) return;
  const pad = parseFloat(getComputedStyle(demoScreen).paddingTop);
  demoDump.style.maxHeight = demoScreen.clientHeight - 2 * pad - last.offsetHeight - 10 + "px";
  demoDump.scrollTop = demoDump.scrollHeight;
  demoScreen.scrollTop = last.offsetTop - pad;
}
window.addEventListener("resize", followDemo);
document.fonts.ready.then(followDemo);

const wait = (ms) => new Promise((r) => setTimeout(r, ms));

async function demoSpeak(el, withSound, run) {
  // Un seul sous-titre à la fois : celui de la phrase en cours.
  demoSays.forEach((say) => { say.hidden = say !== el; });
  followDemo();
  el.toggleAttribute("data-on", true);
  if (withSound) {
    const audio = demoAudio[el.dataset.say];
    audio.currentTime = 0;
    await new Promise((resolve) => {
      audio.onended = audio.onpause = audio.onerror = resolve;
      audio.play().catch(resolve);
    });
  } else {
    // Sans le son, laisser le temps de lire la phrase.
    await wait(1200 + el.textContent.length * 45);
  }
  if (run === demoRun) el.toggleAttribute("data-on", false);
}

async function playDemo(withSound) {
  const run = ++demoRun;
  const alive = () => run === demoRun;
  demoSteps.forEach((el) => { el.hidden = true; el.toggleAttribute("data-on", false); });
  for (const el of demoSteps) {
    if (!alive()) return;
    el.hidden = false;
    if (el.classList.contains("prompt")) {
      const text = el.dataset.text;
      for (let i = 1; i <= text.length && alive(); i++) {
        el.textContent = text.slice(0, i);
        followDemo();
        await wait(55);
      }
      await wait(400);
    } else if (el.classList.contains("dump")) {
      const lines = el.dataset.text.split("\n");
      for (let i = 1; i <= lines.length && alive(); i++) {
        el.textContent = lines.slice(0, i).join("\n");
        followDemo();
        await wait(30);
      }
      await wait(500);
    } else {
      await demoSpeak(el, withSound, run);
      await wait(500);
    }
  }
  if (alive()) stopDemo();
}

function stopDemo() {
  demoRun++;
  Object.values(demoAudio).forEach((a) => a.pause());
  demoSteps.forEach((el) => {
    el.hidden = el.dataset.say ? el !== demoSays.at(-1) : false;
    el.toggleAttribute("data-on", false);
    if (el.dataset.text) el.textContent = el.dataset.text;
  });
  followDemo();
  demoButton.toggleAttribute("data-on", false);
  demoLabel.textContent = L.demoPlay;
}

demoButton.addEventListener("click", () => {
  if (demoButton.hasAttribute("data-on")) { stopDemo(); return; }
  players.forEach((p) => p.audio.pause());
  demoButton.toggleAttribute("data-on", true);
  demoLabel.textContent = L.demoStop;
  playDemo(true);
});

// Une lecture muette au chargement montre le déroulé ; sans animation, le dernier état reste affiché.
followDemo();
if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) playDemo(false);
