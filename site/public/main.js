const L = window.STEPH_L10N;
const live = document.getElementById("live");

function announce(msg) {
  // Vider puis réécrire : un lecteur d'écran n'annonce pas deux fois le même texte.
  live.textContent = "";
  requestAnimationFrame(() => { live.textContent = msg; });
}

// ---------- frange décorative, graine fixe ----------

function fringe(n, seed) {
  let s = seed >>> 0;
  const rnd = () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  return Array.from({ length: n }, (_, i) => i !== 0 && i !== n - 1 && rnd() < 0.62);
}

document.querySelectorAll("[data-fringe]").forEach((el) => {
  const [n, seed] = el.dataset.fringe.split(",").map(Number);
  el.replaceChildren(...fringe(n, seed).map((on) => {
    const cell = document.createElement("span");
    cell.toggleAttribute("data-on", on);
    return cell;
  }));
});

// ---------- copie ----------

const commands = {
  hero: "curl -fsSL https://steph.lsmdx.com/install | sh",
  install: "curl -fsSL https://steph.lsmdx.com/install | sh\nsteph",
};

document.querySelectorAll("[data-copy]").forEach((button) => {
  const label = button.querySelector(".lbl");
  const box = button.parentElement;
  let timer;
  button.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(commands[button.dataset.copy]);
      label.textContent = L.copied;
      box.toggleAttribute("data-copied", true);
      announce(L.copiedMsg);
    } catch {
      announce(L.copyFail);
    }
    clearTimeout(timer);
    timer = setTimeout(() => {
      label.textContent = L.copy;
      box.toggleAttribute("data-copied", false);
    }, 2000);
  });
});

// ---------- sortie lspci dépliable ----------

document.querySelectorAll("[data-expand]").forEach((button) => {
  const target = document.getElementById(button.dataset.expand);
  button.addEventListener("click", () => {
    const open = !target.hasAttribute("data-expanded");
    target.toggleAttribute("data-expanded", open);
    button.setAttribute("aria-expanded", String(open));
    button.textContent = open ? L.expanded : L.expand;
  });
});
