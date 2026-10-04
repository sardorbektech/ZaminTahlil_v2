/**
 * AI hisobotini Markdown formatida ko'rsatish va .md fayl sifatida yuklab olish.
 */

export function renderMarkdownReport(containerId, markdownText) {
  const container = document.getElementById(containerId);
  if (!container) return;

  if (window.marked && window.DOMPurify) {
    const rawHtml = window.marked.parse(markdownText);
    const cleanHtml = window.DOMPurify.sanitize(rawHtml);
    container.innerHTML = cleanHtml;
  } else {
    // Agar kutubxona yuklanmagan bo'lsa
    container.textContent = markdownText;
  }
}

export function downloadReportAsFile(filename, markdownText) {
  const blob = new Blob([markdownText], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename || "rekognossirovka_hisoboti.md";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
