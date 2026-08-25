const state = { jobs: [], companies: [], grouped: [], filtered: [], page: 1, pageSize: 20 };
const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value) => String(value).replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);
const number = (value) => value.toLocaleString("zh-CN");

function unique(values) {
  return [...new Set(values.filter(Boolean))].sort((a, b) => a.localeCompare(b, "zh-CN"));
}

function addOptions(select, values) {
  values.forEach((value) => select.insertAdjacentHTML("beforeend", `<option>${escapeHtml(value)}</option>`));
}

function replaceOptions(select, firstLabel, values) {
  select.innerHTML = `<option value="">${escapeHtml(firstLabel)}</option>`;
  addOptions(select, values);
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
  if (!value) return "未知";
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
  if (!job.published_at) return "未知";
  const days = Math.max(0, Math.floor((Date.now() - timestamp(job)) / 86400000));
  if (days === 0) return "今天";
  return days > 14 ? ">14 天前" : `${days} 天前`;
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
    const company = state.companies.find((item) => item.company === $("#company").value);
    const messages = {
      "抓取失败": "本轮官方源抓取失败，暂时没有可展示的已确认岗位。",
      "暂无匹配岗位": "最近一次检查未发现符合范围的实习或校招岗位。",
      "待接入": "官方招聘源正在接入，暂未展示岗位。",
    };
    const message = company && messages[company.status]
      ? messages[company.status]
      : "没有找到符合条件的岗位，请减少筛选条件后重试。";
    list.innerHTML = `<p class="empty">${escapeHtml(message)}</p>`;
  } else {
    list.innerHTML = jobs.map((job) => {
      const cities = (job.locations || []).join(" / ");
      const age = ageLabel(job);
      const tags = (job.tags || []).length ? ` · ${(job.tags || []).join(" / ")}` : "";
      const duplicate = job.duplicate_count > 1 ? `<span class="duplicate-note">合并 ${job.duplicate_count} 条发布</span>` : "";
      return `<article class="job">
        <div class="company">${escapeHtml(job.company)}</div>
        <div><h3 class="title">${escapeHtml(job.title)}</h3>${duplicate}<div class="compact-meta">${escapeHtml(job.category)} · ${escapeHtml(job.subcategory || job.category)} · ${escapeHtml(cities)} · ${escapeHtml(job.stage)} · ${escapeHtml(age)}</div></div>
        <div class="category-cell"><span class="tag">${escapeHtml(job.category)}</span><span class="direction">${escapeHtml(job.subcategory || job.category)}${escapeHtml(tags)}</span></div>
        <div class="location">${escapeHtml(cities)}</div>
        <div class="timing"><span class="stage">${escapeHtml(job.stage)}</span><span class="direction">${escapeHtml(job.program || "")}</span><span class="time-label">${escapeHtml(age)}</span></div>
        <a class="apply" href="${escapeHtml(job.url)}" target="_blank" rel="noopener noreferrer">投递 ↗</a>
      </article>`;
    }).join("");
  }
  renderPagination();
}

function applyFilters() {
  const query = $("#search").value.trim().toLocaleLowerCase("zh-CN");
  const category = $("#category").value;
  const subcategory = $("#subcategory").value;
  const program = $("#program").value;
  const tag = $("#tag").value;
  const stage = $("#stage").value;
  const city = $("#city").value;
  const company = $("#company").value;
  state.filtered = state.grouped.filter((job) => {
    const haystack = [job.company, job.title, job.category, job.subcategory, job.raw_category, job.program, ...(job.tags || []), ...(job.locations || [])].join(" ").toLocaleLowerCase("zh-CN");
    return (!query || matchesQuery(haystack, query))
      && (!category || job.category === category)
      && (!subcategory || job.subcategory === subcategory)
      && (!program || job.program === program)
      && (!tag || (job.tags || []).includes(tag))
      && (!stage || job.stage === stage)
      && (!city || (job.locations || []).includes(city))
      && (!company || job.company === company);
  });
  updateSourceStatus(company);
  state.page = 1;
  updatePageUrl();
  render();
}

function updateSubcategoryOptions() {
  const category = $("#category").value;
  const values = unique(state.grouped
    .filter((job) => !category || job.category === category)
    .map((job) => job.subcategory));
  replaceOptions($("#subcategory"), "全部方向", values);
}

function updateSourceStatus(companyName) {
  const element = $("#source-status");
  const company = state.companies.find((item) => item.company === companyName);
  const messages = {
    "抓取失败": "本轮官方源抓取失败，当前结果来自上次成功更新。",
    "暂无匹配岗位": "最近一次检查未发现符合本项目范围的实习或校招岗位。",
    "待接入": "该公司的官方招聘源正在接入，暂未展示岗位。",
  };
  const message = company ? messages[company.status] : "";
  element.hidden = !message;
  element.textContent = message ? `${companyName}：${message}` : "";
}

async function boot() {
  try {
    const [jobsResponse, companiesResponse] = await Promise.all([
      fetch("jobs.json", { cache: "no-store" }),
      fetch("companies.json", { cache: "no-store" }),
    ]);
    if (!jobsResponse.ok || !companiesResponse.ok) throw new Error(`HTTP ${jobsResponse.status}/${companiesResponse.status}`);
    state.jobs = await jobsResponse.json();
    state.companies = await companiesResponse.json();
    state.grouped = groupJobs(state.jobs);
    state.filtered = state.grouped;
    const requestedPage = Number(new URLSearchParams(window.location.search).get("page"));
    state.page = Number.isInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1;
    const latestSeen = state.jobs.map((job) => Date.parse(job.last_seen_at || 0)).filter(Boolean).sort((a, b) => b - a)[0];
    $("#updated-at").textContent = latestSeen ? `更新 ${chinaDate(latestSeen)}` : "等待更新";
    addOptions($("#category"), unique(state.grouped.map((job) => job.category)));
    updateSubcategoryOptions();
    addOptions($("#program"), unique(state.grouped.map((job) => job.program)));
    addOptions($("#tag"), unique(state.grouped.flatMap((job) => job.tags || [])));
    addOptions($("#city"), unique(state.grouped.flatMap((job) => job.locations || [])));
    addOptions($("#company"), unique(state.companies.map((company) => company.company)));
    render();
  } catch (error) {
    $("#job-list").innerHTML = `<p class="empty">数据读取失败：${escapeHtml(error.message)}</p>`;
    $("#updated-at").textContent = "数据读取失败";
  }
}

["#search", "#subcategory", "#program", "#tag", "#stage", "#city", "#company"].forEach((selector) => {
  $(selector).addEventListener(selector === "#search" ? "input" : "change", applyFilters);
});
$("#category").addEventListener("change", () => {
  updateSubcategoryOptions();
  applyFilters();
});
$("#reset").addEventListener("click", () => {
  ["#search", "#category", "#subcategory", "#program", "#tag", "#stage", "#city", "#company"].forEach((selector) => { $(selector).value = ""; });
  updateSubcategoryOptions();
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
