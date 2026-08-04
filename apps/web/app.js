const demos = {
  ambition: {
    question: "What would I learn about ambition and isolation?",
    answer: "Frankenstein treats ambition as a force that becomes dangerous when it outruns responsibility. Victor's desire to defeat death isolates him from family, community, and finally from the being he creates. The novel argues that knowledge is not inherently destructive—but pursuing it without care for its human consequences can be.",
    tags: ["ambition", "responsibility", "isolation"],
    citations: [
      ["Frankenstein", "Mary Shelley · Chapter 4", "Victor describes how a single scientific purpose consumes him, displacing every other relationship and ordinary pleasure."],
      ["Frankenstein", "Mary Shelley · Chapter 5", "After bringing the creature to life, Victor abandons it immediately—making the cost of creation and neglect visible in the same scene."],
      ["The Time Machine", "H. G. Wells · Chapter 4", "The Time Traveller's observations turn curiosity about progress into a warning about social isolation and unchecked assumptions."],
    ],
  },
  sea: {
    question: "Which book should I read for an adventure at sea?",
    answer: "Start with Moby-Dick if you want an expedition that is as much about obsession, labor, and the unknowable as it is about the ocean. Ishmael's voice makes room for practical shipboard detail, philosophical detours, and the mounting danger of Ahab's singular pursuit.",
    tags: ["adventure", "sea", "obsession"],
    citations: [
      ["Moby-Dick", "Herman Melville · Chapter 1", "Ishmael frames going to sea as both an escape from restlessness and a way to encounter the world's immensity."],
      ["Moby-Dick", "Herman Melville · Chapter 36", "Ahab turns a whaling voyage into a personal mission, establishing the tension that powers the book's adventure."],
      ["Moby-Dick", "Herman Melville · Chapter 94", "The work of the crew is described with unusual specificity, grounding the symbolic story in a material maritime world."],
    ],
  },
  chances: {
    question: "Find a story about second chances.",
    answer: "Persuasion is the clearest fit. Anne Elliot must revisit a choice she made under family pressure years earlier, then decide whether she can trust her own judgment when Frederick Wentworth returns. Its second chance is not a reset—it is earned through growth, patience, and clearer self-knowledge.",
    tags: ["love", "society", "second chances"],
    citations: [
      ["Persuasion", "Jane Austen · Chapter 4", "Anne's earlier engagement and the influence that ended it establish the novel's central lost opportunity."],
      ["Persuasion", "Jane Austen · Chapter 23", "Anne's conversation about constancy shows how deeply she has changed while still carrying the past forward."],
      ["Persuasion", "Jane Austen · Chapter 24", "Wentworth's letter converts a long period of restraint into a direct invitation to begin again."],
    ],
  },
};

const books = [
  { title:"Frankenstein", author:"Mary Shelley", color:"#d8e6c7", ink:"#193e32", topic:"Ambition & responsibility", prompt:"What would I learn about ambition and isolation?" },
  { title:"Moby-Dick", author:"Herman Melville", color:"#b8d6df", ink:"#123e4b", topic:"Adventure & obsession", prompt:"Which book should I read for an adventure at sea?" },
  { title:"Persuasion", author:"Jane Austen", color:"#f1cfbd", ink:"#713727", topic:"Love & second chances", prompt:"Find a story about second chances." },
  { title:"The Time Machine", author:"H. G. Wells", color:"#ded4ed", ink:"#453359", topic:"Society & progress", prompt:"What would I learn about ambition and isolation?" },
];

const form = document.querySelector("#question-form");
const input = document.querySelector("#question");
const questionLabel = document.querySelector("#question-label");
const answerText = document.querySelector("#answer-text");
const citations = document.querySelector("#citations");
const tags = document.querySelector("#answer-tags");

function pickDemo(query) {
  const value = query.toLowerCase();
  if (value.includes("sea") || value.includes("adventure") || value.includes("ocean")) return demos.sea;
  if (value.includes("chance") || value.includes("love") || value.includes("persuasion")) return demos.chances;
  return demos.ambition;
}

function render(demo) {
  questionLabel.textContent = demo.question;
  answerText.textContent = demo.answer;
  tags.replaceChildren(...demo.tags.map((tag) => Object.assign(document.createElement("span"), { textContent: tag })));
  document.querySelector("#result-count").textContent = `${demo.citations.length} supporting passages`;
  document.querySelector("#citation-count").textContent = `${demo.citations.length} citations`;
  citations.replaceChildren(...demo.citations.map(([title, subtitle, quote], index) => {
    const card = document.createElement("button");
    card.className = "citation";
    card.type = "button";
    card.innerHTML = `<span class="citation-summary"><span class="citation-number">${String(index + 1).padStart(2, "0")}</span><span><span class="citation-title">${title}</span><span class="citation-subtitle">${subtitle}</span></span><span class="citation-toggle">+</span></span><span class="citation-quote">“${quote}”</span>`;
    card.addEventListener("click", () => card.classList.toggle("open"));
    return card;
  }));
}

document.querySelectorAll("[data-prompt]").forEach((button) => button.addEventListener("click", () => {
  input.value = button.dataset.prompt;
  render(pickDemo(input.value));
  document.querySelector(".workspace").scrollIntoView({ behavior:"smooth", block:"start" });
}));

form.addEventListener("submit", (event) => { event.preventDefault(); render(pickDemo(input.value || demos.ambition.question)); });
document.querySelector("#clear-filters").addEventListener("click", () => document.querySelectorAll(".filters input").forEach((input, index) => { input.checked = index === 0; }));

const grid = document.querySelector("#book-grid");
books.forEach((book, index) => {
  const item = document.createElement("article");
  item.className = "book";
  item.style.setProperty("--book-color", book.color);
  item.style.setProperty("--book-ink", book.ink);
  item.innerHTML = `<div class="book-top"><span>0${index + 1}</span><span>Public domain</span></div><h3>${book.title}</h3><p>${book.author}<br />${book.topic}</p><button type="button">Ask about this book →</button>`;
  item.querySelector("button").addEventListener("click", () => { input.value = book.prompt; render(pickDemo(book.prompt)); document.querySelector("#explore").scrollIntoView({ behavior:"smooth" }); });
  grid.append(item);
});

render(demos.ambition);
