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
  hero: "git clone https://github.com/tutozz/steph\ncd steph\n./scripts/install.sh",
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
    audio.play().catch(() => {});
  });
});
