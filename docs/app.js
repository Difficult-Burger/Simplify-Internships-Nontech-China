const state = { jobs: [], grouped: [], filtered: [], visible: 50 };
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
      if (timestamp(job) > timestamp(current)) {
        groups.set(key, { ...job, duplicate_count: current.duplicate_count });
      }
    }
  }
  return [...groups.values()].sort((a, b) => timestamp(b) - timestamp(a));
}

function chinaDate(value, includeTime = false) {
  if (!value) return "时间未公开";
  const options = includeTime
    ? { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }
    : { timeZone: "Asia/Shanghai", month: "2-digit", day: "2-digit" };
  return new Intl.DateTimeFormat("zh-CN", options).format(new Date(value));
}

function renderMetrics() {
  const companies = unique(state.jobs.map((job) => job.company));
  const latestSeen = state.jobs.map((job) => Date.parse(job.last_seen_at || 0)).filter(Boolean).sort((a, b) => b - a)[0];
  const recentCutoff = latestSeen - 24 * 60 * 60 * 1000;
  const recent = state.grouped.filter((job) => Date.parse(job.first_seen_at || 0) >= recentCutoff).length;
  $("#unique-count").textContent = number(state.grouped.length);
  $("#total-count").textContent = number(state.jobs.length);
  $("#new-count").textContent = number(recent);
  $("#company-count").textContent = number(companies.length);
  $("#updated-at").textContent = latestSeen ? `最近确认：${chinaDate(latestSeen, true)}` : "等待首次更新";

  const sourceCounts = Object.entries(state.jobs.reduce((counts, job) => {
    counts[job.source] = (counts[job.source] || 0) + 1;
    return counts;
  }, {}));
  $("#source-list").innerHTML = sourceCounts
    .map(([source, count]) => `<span class="source-badge">${escapeHtml(source)} ${number(count)}</span>`)
    .join("");
}

function render() {
  const list = $("#job-list");
  const jobs = state.filtered.slice(0, state.visible);
  $("#result-count").textContent = number(state.filtered.length);
  if (!jobs.length) {
    list.innerHTML = '<p class="empty">没有找到符合条件的岗位，请减少筛选条件后重试。</p>';
  } else {
    list.innerHTML = jobs.map((job) => {
      const cities = (job.locations || []).join(" / ");
      const timeLabel = job.published_at ? `官方发布 ${chinaDate(job.published_at)}` : `首次收录 ${chinaDate(job.first_seen_at)}`;
      const duplicate = job.duplicate_count > 1 ? `<span class="duplicate-note">已合并 ${job.duplicate_count} 条同名官方发布，保留最新链接</span>` : "";
      return `<article class="job">
        <div class="company">${escapeHtml(job.company)}<span class="source-name">${escapeHtml(job.source)}</span></div>
        <div><h3 class="title">${escapeHtml(job.title)}</h3>${duplicate}</div>
        <div class="category-cell"><span class="tag">${escapeHtml(job.category)}</span></div>
        <div class="location">${escapeHtml(cities)}</div>
        <div class="timing"><span class="stage">${escapeHtml(job.stage)}</span><span class="time-label">${escapeHtml(timeLabel)}</span></div>
        <a class="apply" href="${escapeHtml(job.url)}" target="_blank" rel="noopener noreferrer">官网申请 ↗</a>
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
  state.filtered = state.grouped.filter((job) => {
    const haystack = [job.company, job.title, job.category, job.raw_category, ...(job.locations || [])].join(" ").toLocaleLowerCase("zh-CN");
    return (!query || matchesQuery(haystack, query))
      && (!category || job.category === category)
      && (!stage || job.stage === stage)
      && (!city || (job.locations || []).includes(city))
      && (!company || job.company === company);
  });
  state.visible = 50;
  render();
}

async function boot() {
  try {
    const response = await fetch("jobs.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.jobs = await response.json();
    state.grouped = groupJobs(state.jobs);
    state.filtered = state.grouped;
    renderMetrics();
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
$("#load-more").addEventListener("click", () => { state.visible += 50; render(); });
boot();
