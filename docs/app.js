const state = { jobs: [], filtered: [], visible: 40 };
const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value) => String(value).replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);

function unique(values) {
  return [...new Set(values.filter(Boolean))].sort((a, b) => a.localeCompare(b, "zh-CN"));
}

function addOptions(select, values) {
  values.forEach((value) => select.insertAdjacentHTML("beforeend", `<option>${escapeHtml(value)}</option>`));
}

function render() {
  const list = $("#job-list");
  const jobs = state.filtered.slice(0, state.visible);
  $("#result-count").textContent = state.filtered.length.toLocaleString("zh-CN");
  if (!jobs.length) {
    list.innerHTML = '<p class="empty">没有命中。试着少选一个条件。</p>';
  } else {
    list.innerHTML = jobs.map((job, index) => {
      const seen = job.first_seen_at ? job.first_seen_at.slice(0, 10) : "日期未知";
      const cities = (job.locations || []).join(" / ");
      return `<article class="job" style="animation-delay:${Math.min(index, 12) * 25}ms">
        <div class="company">${escapeHtml(job.company)}</div>
        <div><h3 class="title">${escapeHtml(job.title)}</h3><span class="tag">${escapeHtml(job.category)}</span></div>
        <div class="meta">${escapeHtml(cities)}<br>${escapeHtml(job.stage)} · ${escapeHtml(job.source)}</div>
        <div class="freshness">首次发现<br>${escapeHtml(seen)}</div>
        <a class="apply" href="${escapeHtml(job.url)}" target="_blank" rel="noopener noreferrer">去官网申请 ↗</a>
      </article>`;
    }).join("");
  }
  $("#load-more").hidden = state.visible >= state.filtered.length;
}

function applyFilters() {
  const query = $("#search").value.trim().toLocaleLowerCase("zh-CN");
  const category = $("#category").value;
  const stage = $("#stage").value;
  const city = $("#city").value;
  const company = $("#company").value;
  state.filtered = state.jobs.filter((job) => {
    const haystack = [job.company, job.title, job.category, ...(job.locations || [])].join(" ").toLocaleLowerCase("zh-CN");
    return (!query || haystack.includes(query))
      && (!category || job.category === category)
      && (!stage || job.stage === stage)
      && (!city || (job.locations || []).includes(city))
      && (!company || job.company === company);
  });
  state.visible = 40;
  render();
}

async function boot() {
  try {
    const response = await fetch("jobs.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.jobs = await response.json();
    state.filtered = state.jobs;
    $("#total-count").textContent = state.jobs.length.toLocaleString("zh-CN");
    const newest = state.jobs.map((job) => job.last_seen_at).filter(Boolean).sort().at(-1);
    $("#updated-at").textContent = newest ? `更新 ${newest.slice(0, 10)}` : "等待首次更新";
    addOptions($("#category"), unique(state.jobs.map((job) => job.category)));
    addOptions($("#city"), unique(state.jobs.flatMap((job) => job.locations || [])));
    addOptions($("#company"), unique(state.jobs.map((job) => job.company)));
    render();
  } catch (error) {
    $("#job-list").innerHTML = `<p class="empty">数据读取失败：${escapeHtml(error.message)}</p>`;
    $("#updated-at").textContent = "读取失败";
  }
}

["#search", "#category", "#stage", "#city", "#company"].forEach((selector) => {
  $(selector).addEventListener(selector === "#search" ? "input" : "change", applyFilters);
});
$("#reset").addEventListener("click", () => {
  ["#search", "#category", "#stage", "#city", "#company"].forEach((selector) => { $(selector).value = ""; });
  applyFilters();
});
$("#load-more").addEventListener("click", () => { state.visible += 40; render(); });
boot();
