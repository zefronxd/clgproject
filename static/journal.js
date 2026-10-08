const entryText = document.querySelector("#entry-text");
const characterCount = document.querySelector("#character-count");

if (entryText && characterCount) {
  const updateCount = () => {
    characterCount.textContent = `${entryText.value.length.toLocaleString()} / 3,000`;
  };
  entryText.addEventListener("input", updateCount);
  updateCount();
}
