const search = document.getElementById("part-query");
const count = document.getElementById("match-count");
const parts = [...document.querySelectorAll("#part-list > details")];
let previouslyOpen = null;

function normalize(text) {
  return text.normalize("NFKC").toLowerCase();
}

function filterParts() {
  const query = normalize(search.value.trim());
  if (query && previouslyOpen === null) {
    previouslyOpen = new Set(parts.filter(part => part.open));
  }
  for (const part of parts) {
    part.hidden = Boolean(query) && !normalize(part.textContent).includes(query);
    if (query) part.open = !part.hidden;
    else if (previouslyOpen !== null) part.open = previouslyOpen.has(part);
  }
  if (!query) previouslyOpen = null;
  const visible = parts.filter(part => !part.hidden).length;
  count.textContent = !query ? "" : visible
    ? `${parts.length}分類のうち ${visible}分類を表示`
    : "該当する分類がありません。キーワードを変えるか、検索を解除してください。";
}

function openTarget(hash) {
  const target = document.getElementById(hash.slice(1));
  if (!(target instanceof HTMLDetailsElement)) return;
  if (target.hidden) {
    search.value = "";
    filterParts();
  }
  target.open = true;
}

search.addEventListener("input", filterParts);
document.getElementById("clear-query").addEventListener("click", () => {
  search.value = "";
  filterParts();
  search.focus();
});
document.addEventListener("click", event => {
  const link = event.target.closest('a[href^="#"]');
  if (link) openTarget(link.hash);
});
window.addEventListener("hashchange", () => openTarget(location.hash));
document.getElementById("part-search").hidden = false;
openTarget(location.hash);
