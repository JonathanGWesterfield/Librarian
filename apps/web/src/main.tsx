import { useState, type CSSProperties, type FormEvent } from "react";
import { createRoot } from "react-dom/client";
import "../styles.css";

type Citation = [title: string, subtitle: string, quote: string];

type Demo = {
  question: string;
  answer: string;
  tags: string[];
  citations: Citation[];
};

const demos: Record<"ambition" | "sea" | "chances", Demo> = {
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
  { title: "Frankenstein", author: "Mary Shelley", color: "#d8e6c7", ink: "#193e32", topic: "Ambition & responsibility", prompt: demos.ambition.question },
  { title: "Moby-Dick", author: "Herman Melville", color: "#b8d6df", ink: "#123e4b", topic: "Adventure & obsession", prompt: demos.sea.question },
  { title: "Persuasion", author: "Jane Austen", color: "#f1cfbd", ink: "#713727", topic: "Love & second chances", prompt: demos.chances.question },
  { title: "The Time Machine", author: "H. G. Wells", color: "#ded4ed", ink: "#453359", topic: "Society & progress", prompt: demos.ambition.question },
];

function pickDemo(query: string): Demo {
  const value = query.toLowerCase();
  if (value.includes("sea") || value.includes("adventure") || value.includes("ocean")) return demos.sea;
  if (value.includes("chance") || value.includes("love") || value.includes("persuasion")) return demos.chances;
  return demos.ambition;
}

export function App() {
  const [query, setQuery] = useState("");
  const [demo, setDemo] = useState<Demo>(demos.ambition);
  const [openCitation, setOpenCitation] = useState<number | null>(null);
  const [collection, setCollection] = useState("all");
  const [topics, setTopics] = useState<string[]>([]);

  const showDemo = (prompt: string, target: "workspace" | "explore") => {
    setQuery(prompt);
    setDemo(pickDemo(prompt));
    setOpenCitation(null);
    document.getElementById(target)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setDemo(pickDemo(query || demos.ambition.question));
    setOpenCitation(null);
  };

  return <main className="app-shell">
    <nav className="topbar" aria-label="Primary navigation">
      <a className="brand" href="#explore" aria-label="Librarian home"><span className="brand-mark" aria-hidden="true">L</span><span>Librarian</span></a>
      <div className="nav-links"><a className="active" href="#explore">Explore</a><a href="#library">Library</a><a href="#how-it-works">How it works</a></div>
      <a className="github-link" href="https://github.com/JonathanGWesterfield/Librarian" target="_blank" rel="noreferrer">View source <span aria-hidden="true">↗</span></a>
    </nav>

    <section id="explore" className="hero">
      <p className="eyebrow">A public demonstration of local-first RAG</p>
      <h1>Ask the library.<br /><em>See the evidence.</em></h1>
      <p className="hero-copy">Librarian helps readers discover and understand books with grounded answers that link directly back to the passages that support them.</p>
      <form className="question-form" onSubmit={submit}>
        <label className="sr-only" htmlFor="question">Ask a question about the sample library</label>
        <input id="question" autoComplete="off" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={demos.ambition.question} />
        <button type="submit">Ask <span aria-hidden="true">→</span></button>
      </form>
      <div className="starter-row" aria-label="Suggested questions"><span>Try a question</span>
        <button type="button" onClick={() => showDemo(demos.ambition.question, "workspace")}>Ambition &amp; isolation</button>
        <button type="button" onClick={() => showDemo(demos.sea.question, "workspace")}>A sea adventure</button>
        <button type="button" onClick={() => showDemo(demos.chances.question, "workspace")}>Second chances</button>
      </div>
    </section>

    <section id="workspace" className="workspace" aria-labelledby="answer-heading">
      <aside className="filters">
        <div className="filter-heading"><span>Refine this search</span><button type="button" onClick={() => { setCollection("all"); setTopics([]); }}>Clear</button></div>
        <fieldset><legend>Collection</legend>
          {[["all", "All books"], ["fiction", "Fiction"]].map(([value, label]) => <label key={value}><input type="radio" name="collection" value={value} checked={collection === value} onChange={() => setCollection(value)} /> {label} <span>4</span></label>)}
        </fieldset>
        <fieldset><legend>Topics</legend>
          {["identity", "adventure", "society", "ambition"].map((topic) => <label key={topic}><input type="checkbox" value={topic} checked={topics.includes(topic)} onChange={() => setTopics((current) => current.includes(topic) ? current.filter((value) => value !== topic) : [...current, topic])} /> {topic[0].toUpperCase() + topic.slice(1)}</label>)}
        </fieldset>
        <div className="demo-note"><span className="note-icon">i</span><p>This is a rights-safe sample corpus. Personal libraries stay local.</p></div>
      </aside>
      <div className="answer-area">
        <div className="answer-meta"><p id="answer-heading" className="eyebrow">Grounded answer</p><span>{demo.citations.length} supporting passages</span></div>
        <article className="answer-card" aria-live="polite"><div className="answer-number">01</div><div><p className="asked-question">{demo.question}</p><p className="answer-text">{demo.answer}</p><div className="tag-row">{demo.tags.map((tag) => <span key={tag}>{tag}</span>)}</div></div></article>
        <div className="citations-header"><div><p className="eyebrow">Traceable sources</p><h2>Read the passages</h2></div><span>{demo.citations.length} citations</span></div>
        <div className="citations">{demo.citations.map(([title, subtitle, quote], index) => <button key={`${title}-${subtitle}`} className={`citation${openCitation === index ? " open" : ""}`} type="button" onClick={() => setOpenCitation((current) => current === index ? null : index)}><span className="citation-summary"><span className="citation-number">{String(index + 1).padStart(2, "0")}</span><span><span className="citation-title">{title}</span><span className="citation-subtitle">{subtitle}</span></span><span className="citation-toggle">+</span></span><span className="citation-quote">“{quote}”</span></button>)}</div>
      </div>
    </section>

    <section id="library" className="library-section"><div className="section-heading"><div><p className="eyebrow">Sample collection</p><h2>A small library, made explorable.</h2></div><p>Four public-domain books. One evidence-first interface.</p></div><div className="book-grid">{books.map((book, index) => <article className="book" key={book.title} style={{ "--book-color": book.color, "--book-ink": book.ink } as CSSProperties}><div className="book-top"><span>0{index + 1}</span><span>Public domain</span></div><h3>{book.title}</h3><p>{book.author}<br />{book.topic}</p><button type="button" onClick={() => showDemo(book.prompt, "explore")}>Ask about this book →</button></article>)}</div></section>

    <section id="how-it-works" className="how-section"><div><p className="eyebrow">Under the hood</p><h2>Designed for answers you can inspect.</h2></div><ol className="pipeline">{[["Ingest", "Parse EPUBs into structured, source-aware chunks."], ["Retrieve", "Combine semantic and keyword search with useful filters."], ["Ground", "Build answers only from the passages the system found."], ["Evaluate", "Measure retrieval and answer quality with a golden corpus."]].map(([title, description], index) => <li key={title}><span>0{index + 1}</span><strong>{title}</strong><p>{description}</p></li>)}</ol></section>
    <footer><p>Built as an AI engineering portfolio project.</p><p>© 2026 Librarian <span aria-hidden="true">·</span> <a href="https://github.com/JonathanGWesterfield/Librarian" target="_blank" rel="noreferrer">GitHub ↗</a></p></footer>
  </main>;
}

const root = document.getElementById("root");
if (root) {
  createRoot(root).render(<App />);
}
