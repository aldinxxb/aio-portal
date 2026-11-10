// Layout only: natural-language search is not built yet, so the field and button are disabled.
export default function SearchBar() {
  return (
    <div className="search" title="Natural-language search: coming later">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
        <circle cx="11" cy="11" r="7" />
        <path d="M20 20l-3.5-3.5" />
      </svg>
      <input disabled placeholder="What model and open data do I need for flood risk mapping in a basin?" />
      <button className="search-btn" disabled>
        Search
      </button>
    </div>
  );
}