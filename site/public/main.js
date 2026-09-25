const status = document.getElementById("status");

document.querySelectorAll("[data-copy]").forEach((button) => {
  const label = button.textContent;
  button.addEventListener("click", async () => {
    const text = document.getElementById(button.dataset.copy).textContent;
    try {
      await navigator.clipboard.writeText(text);
      status.textContent = "";
      requestAnimationFrame(() => { status.textContent = button.dataset.done; });
      button.textContent = button.dataset.label;
    } catch {
      status.textContent = button.dataset.fail;
    }
    setTimeout(() => { button.textContent = label; }, 2000);
  });
});

// Un seul extrait audio à la fois : deux voix superposées sont inaudibles.
const players = [...document.querySelectorAll("audio")];
players.forEach((a) => a.addEventListener("play", () => {
  players.forEach((b) => b !== a && b.pause());
}));

const reveals = document.querySelectorAll(".reveal");
if ("IntersectionObserver" in window) {
  const io = new IntersectionObserver((entries) => {
    entries.forEach((e) => {
      if (e.isIntersecting) {
        e.target.classList.add("in");
        io.unobserve(e.target);
      }
    });
  }, { rootMargin: "0px 0px -8% 0px" });
  reveals.forEach((el) => io.observe(el));
} else {
  reveals.forEach((el) => el.classList.add("in"));
}

// Traits de repère entre chaque note et l'objet qu'elle désigne, recalculés à chaque redimensionnement.
const hero = document.querySelector(".hero");
const svg = hero && hero.querySelector(".leaders");

function drawLeaders() {
  if (!svg || getComputedStyle(svg).display === "none") return;
  const box = hero.getBoundingClientRect();
  svg.setAttribute("width", box.width);
  svg.setAttribute("height", box.height);
  svg.replaceChildren();
  hero.querySelectorAll(".note[data-target]").forEach((note) => {
    const target = hero.querySelector(note.dataset.target);
    if (!target) return;
    const n = note.getBoundingClientRect();
    const t = target.getBoundingClientRect();
    const x1 = n.left - box.left;
    const y1 = n.top - box.top + n.height / 2;
    const x2 = t.left - box.left + t.width * 0.55;
    const y2 = t.top - box.top + t.height * 0.5;
    const bend = x1 - 36;
    const path = document.createElementNS(svg.namespaceURI, "path");
    path.setAttribute("d", `M${x1} ${y1} H${bend} L${x2 + 10} ${y2} H${x2}`);
    const node = document.createElementNS(svg.namespaceURI, "rect");
    node.setAttribute("x", x2 - 4);
    node.setAttribute("y", y2 - 4);
    node.setAttribute("width", 8);
    node.setAttribute("height", 8);
    svg.append(path, node);
  });
}

if (svg) {
  new ResizeObserver(drawLeaders).observe(hero);
  window.addEventListener("load", drawLeaders);
}
