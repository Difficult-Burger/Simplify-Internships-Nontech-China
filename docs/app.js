const state = { jobs: [], grouped: [], filtered: [], page: 1, pageSize: 50 };
const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value) => String(value).replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);
const number = (value) => value.toLocaleString("zh-CN");

function unique(values) {
  return [...new Set(values.filter(Boolean))].sort((a, b) => a.localeCompare(b, "zh-CN"));
}

function addOptions(select, values) {
  values.forEach((value) => select.insertAdjacentHTML("beforeend", `<option>${escapeHtml(value)}</option>`));
}

function matchesQuery(haystack, query) {
  if (/^[a-z0-9]{1,3}$/.test(query)) {
    return new RegExp(`(^|[^a-z0-9])${query}([^a-z0-9]|$)`).test(haystack);
  }
  return haystack.includes(query);
}

function timestamp(job) {
  return Date.parse(job.published_at || job.first_seen_at || 0) || 0;
}

function groupJobs(jobs) {
  const groups = new Map();
  for (const job of jobs) {
    const locations = [...(job.locations || [])].sort().join("|");
    const key = [job.company, job.title.trim(), locations, job.stage].join("::");
    const current = groups.get(key);
    if (!current) {
      groups.set(key, { ...job, duplicate_count: 1 });
    } else {
      current.duplicate_count += 1;
      if (timestamp(job) > timestamp(current)) groups.set(key, { ...job, duplicate_count: current.duplicate_count });
    }
  }
  return [...groups.values()].sort((a, b) => timestamp(b) - timestamp(a));
}

function chinaDate(value) {
  if (!value) return "时间未公开";
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

function ageLabel(job) {
  if (!job.published_at) return "时间未公开";
  const days = Math.max(0, Math.floor((Date.now() - timestamp(job)) / 86400000));
  return days === 0 ? "今天" : `${days} 天前`;
}

function pageNumbers(current, total) {
  const pages = new Set([1, total]);
  for (let page = current - 2; page <= current + 2; page += 1) {
    if (page > 1 && page < total) pages.add(page);
  }
  const sorted = [...pages].sort((a, b) => a - b);
  const items = [];
  sorted.forEach((page, index) => {
    if (index && page - sorted[index - 1] > 1) items.push("…");
    items.push(page);
  });
  return items;
}

function updatePageUrl() {
  const url = new URL(window.location.href);
  if (state.page === 1) url.searchParams.delete("page");
  else url.searchParams.set("page", state.page);
  window.history.replaceState({}, "", url);
}

function renderPagination() {
  const pagination = $("#pagination");
  const total = state.filtered.length;
  const totalPages = Math.max(1, Math.ceil(total / state.pageSize));
  state.page = Math.min(Math.max(1, state.page), totalPages);
  pagination.hidden = total === 0;
  if (!total) return;

  const start = (state.page - 1) * state.pageSize + 1;
  const end = Math.min(state.page * state.pageSize, total);
  $("#page-summary").textContent = `第 ${number(start)}–${number(end)} 条，共 ${number(total)} 条`;
  const pages = pageNumbers(state.page, totalPages)
    .map((page) => page === "…"
      ? '<span class="page-ellipsis">…</span>'
      : `<button class="page-number" type="button" data-page="${page}" ${page === state.page ? 'aria-current="page"' : ""}>${page}</button>`)
    .join("");
  $("#page-controls").innerHTML = `
    <button type="button" data-page="${state.page - 1}" ${state.page === 1 ? "disabled" : ""}>上一页</button>
    ${pages}
    <span class="pagination-status">第 ${state.page} / ${totalPages} 页</span>
    <button type="button" data-page="${state.page + 1}" ${state.page === totalPages ? "disabled" : ""}>下一页</button>`;
}

function setPage(page, scroll = true) {
  const totalPages = Math.max(1, Math.ceil(state.filtered.length / state.pageSize));
  state.page = Math.min(Math.max(1, page), totalPages);
  updatePageUrl();
  render();
  if (scroll) $(".results-head").scrollIntoView({ behavior: "smooth", block: "start" });
}

function render() {
  const list = $("#job-list");
  const start = (state.page - 1) * state.pageSize;
  const jobs = state.filtered.slice(start, start + state.pageSize);
  $("#result-count").textContent = number(state.filtered.length);
  if (!jobs.length) {
    list.innerHTML = '<p class="empty">没有找到符合条件的岗位，请减少筛选条件后重试。</p>';
  } else {
    list.innerHTML = jobs.map((job) => {
      const cities = (job.locations || []).join(" / ");
      const age = ageLabel(job);
      const duplicate = job.duplicate_count > 1 ? `<span class="duplicate-note">合并 ${job.duplicate_count} 条发布</span>` : "";
      return `<article class="job">
        <div class="company">${escapeHtml(job.company)}</div>
        <div><h3 class="title">${escapeHtml(job.title)}</h3>${duplicate}<div class="compact-meta">${escapeHtml(job.category)} · ${escapeHtml(cities)} · ${escapeHtml(job.stage)} · ${escapeHtml(age)}</div></div>
        <div class="category-cell"><span class="tag">${escapeHtml(job.category)}</span></div>
        <div class="location">${escapeHtml(cities)}</div>
        <div class="timing"><span class="stage">${escapeHtml(job.stage)}</span><span class="time-label">${escapeHtml(age)}</span></div>
        <a class="apply" href="${escapeHtml(job.url)}" target="_blank" rel="noopener noreferrer">投递 ↗</a>
      </article>`;
    }).join("");
  }
  renderPagination();
}

function applyFilters() {
  const query = $("#search").value.trim().toLocaleLowerCase("zh-CN");
  const category = $("#category").value;
  const stage = $("#stage").value;
  const city = $("#city").value;
  const company = $("#company").value;
  state.filtered = state.grouped.filter((job) => {
    const haystack = [job.company, job.title, job.category, job.raw_category, ...(job.locations || [])].join(" ").toLocaleLowerCase("zh-CN");
    return (!query || matchesQuery(haystack, query))
      && (!category || job.category === category)
      && (!stage || job.stage === stage)
      && (!city || (job.locations || []).includes(city))
      && (!company || job.company === company);
  });
  state.page = 1;
  updatePageUrl();
  render();
}

async function boot() {
  try {
    const response = await fetch("jobs.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.jobs = await response.json();
    state.grouped = groupJobs(state.jobs);
    state.filtered = state.grouped;
    const requestedPage = Number(new URLSearchParams(window.location.search).get("page"));
    state.page = Number.isInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1;
    const latestSeen = state.jobs.map((job) => Date.parse(job.last_seen_at || 0)).filter(Boolean).sort((a, b) => b - a)[0];
    $("#updated-at").textContent = latestSeen ? `更新 ${chinaDate(latestSeen)}` : "等待更新";
    addOptions($("#category"), unique(state.grouped.map((job) => job.category)));
    addOptions($("#city"), unique(state.grouped.flatMap((job) => job.locations || [])));
    addOptions($("#company"), unique(state.grouped.map((job) => job.company)));
    render();
  } catch (error) {
    $("#job-list").innerHTML = `<p class="empty">数据读取失败：${escapeHtml(error.message)}</p>`;
    $("#updated-at").textContent = "数据读取失败";
  }
}

["#search", "#category", "#stage", "#city", "#company"].forEach((selector) => {
  $(selector).addEventListener(selector === "#search" ? "input" : "change", applyFilters);
});
$("#reset").addEventListener("click", () => {
  ["#search", "#category", "#stage", "#city", "#company"].forEach((selector) => { $(selector).value = ""; });
  applyFilters();
});
$("#page-controls").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-page]");
  if (button && !button.disabled) setPage(Number(button.dataset.page));
});
window.addEventListener("popstate", () => {
  const page = Number(new URLSearchParams(window.location.search).get("page")) || 1;
  setPage(page, false);
});
boot();
