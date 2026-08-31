const filterKeys = ["category", "subcategory", "program", "tag", "stage", "freshness", "city", "company"];
const majorCities = ["北京", "上海", "深圳", "广州", "杭州", "成都", "南京", "武汉", "西安", "苏州"];
const filterNames = {
  category: "岗位类别",
  subcategory: "细分方向",
  program: "招聘项目",
  tag: "岗位标签",
  stage: "招聘类型",
  freshness: "新鲜度",
  city: "城市",
  company: "公司",
};
const state = {
  jobs: [],
  companies: [],
  grouped: [],
  filtered: [],
  page: 1,
  pageSize: 20,
  selections: Object.fromEntries(filterKeys.map((key) => [key, new Set()])),
  optionValues: {},
};
const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value) => String(value).replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);
const number = (value) => value.toLocaleString("zh-CN");

function unique(values) {
  return [...new Set(values.filter(Boolean))].sort((a, b) => a.localeCompare(b, "zh-CN"));
}

function matchesQuery(haystack, query) {
  if (/^[a-z0-9]{1,3}$/.test(query)) {
    return new RegExp(`(^|[^a-z0-9])${query}([^a-z0-9]|$)`).test(haystack);
  }
  return haystack.includes(query);
}

function freshnessTimestamp(job) {
  if (job.freshness_basis === "baseline") return 0;
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
      if (freshnessTimestamp(job) > freshnessTimestamp(current)) {
        groups.set(key, { ...job, duplicate_count: current.duplicate_count });
      }
    }
  }
  return [...groups.values()].sort((a, b) => freshnessTimestamp(b) - freshnessTimestamp(a));
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

function relativeAge(timestamp) {
  const hours = Math.max(0, (Date.now() - timestamp) / 3600000);
  if (hours < 1) return "<1h";
  if (hours < 24) return `${Math.floor(hours)}h`;
  const days = Math.floor(hours / 24);
  return days > 14 ? ">14d" : `${days}d`;
}

function freshnessLabel(job) {
  if (job.freshness_basis === "baseline") return "未知";
  const timestamp = freshnessTimestamp(job);
  if (!timestamp) return "未知";
  return relativeAge(timestamp);
}

function freshnessEvidence(job) {
  if (job.freshness_basis === "baseline") return "项目首次上线时批量导入，官网未提供发布时间";
  const value = job.freshness_basis === "official" ? job.published_at : job.first_seen_at;
  const prefix = job.freshness_basis === "official" ? "企业官方接口发布时间" : "本项目首次收录时间";
  const merged = job.duplicate_count > 1 ? "；合并岗位采用最新一条时间" : "";
  return `${prefix}：${chinaDate(value)}${merged}`;
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
    const selectedCompanies = [...state.selections.company];
    const company = selectedCompanies.length === 1
      ? state.companies.find((item) => item.company === selectedCompanies[0])
      : null;
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
      const freshness = freshnessLabel(job);
      const evidence = freshnessEvidence(job);
      const tags = (job.tags || []).length ? ` · ${(job.tags || []).join(" / ")}` : "";
      const duplicate = job.duplicate_count > 1 ? `<span class="duplicate-note">合并 ${job.duplicate_count} 条发布</span>` : "";
      return `<article class="job">
        <div class="company">${escapeHtml(job.company)}</div>
        <div><h3 class="title">${escapeHtml(job.title)}</h3>${duplicate}<div class="compact-meta">${escapeHtml(job.category)} · ${escapeHtml(job.subcategory || job.category)} · ${escapeHtml(cities)}</div><div class="compact-labels"><span class="stage">${escapeHtml(job.stage)}</span><span class="time-label" title="${escapeHtml(evidence)}">${escapeHtml(freshness)}</span></div></div>
        <div class="category-cell"><span class="tag">${escapeHtml(job.category)}</span><span class="direction">${escapeHtml(job.subcategory || job.category)}${escapeHtml(tags)}</span></div>
        <div class="location">${escapeHtml(cities)}</div>
        <div class="stage-cell"><span class="stage">${escapeHtml(job.stage)}</span></div>
        <div class="freshness-cell"><span class="time-label" title="${escapeHtml(evidence)}">${escapeHtml(freshness)}</span></div>
        <a class="apply" href="${escapeHtml(job.url)}" target="_blank" rel="noopener noreferrer">投递 ↗</a>
      </article>`;
    }).join("");
  }
  renderPagination();
}

const filterDefaults = {
  category: "全部类别",
  subcategory: "全部细分方向",
  program: "全部项目",
  tag: "全部标签",
  stage: "全部类型",
  freshness: "全部时间",
  city: "全部城市",
  company: "全部公司",
};

function updateFilterSummary(key) {
  const selected = [...state.selections[key]];
  $(`#${key}-summary`).textContent = selected.length === 0
    ? filterDefaults[key]
    : selected.length === 1 ? selected[0] : `已选 ${selected.length} 项`;
}

function optionChoices(key, values) {
  return values.map((value) => `<label class="option-choice">
    <input type="checkbox" data-filter="${key}" value="${escapeHtml(value)}" ${state.selections[key].has(value) ? "checked" : ""}>
    <span>${escapeHtml(value)}</span>
  </label>`).join("");
}

function optionGroup(key, label, values) {
  if (!values.length) return "";
  return `<section class="option-group" data-option-group>
    ${label ? `<h4>${escapeHtml(label)}</h4>` : ""}
    <div class="option-grid">${optionChoices(key, values)}</div>
  </section>`;
}

function optionPanel(key, values) {
  const search = `<input class="option-search" type="search" data-option-search="${key}" aria-label="搜索${filterNames[key]}选项" placeholder="搜索${filterNames[key]}" autocomplete="off">`;
  if (key !== "city") return search + optionGroup(key, "", values);
  const available = new Set(values);
  const popular = majorCities.filter((city) => available.has(city));
  const other = values.filter((city) => !majorCities.includes(city));
  return search + optionGroup(key, "热门城市", popular) + optionGroup(key, "其他城市", other);
}

function renderMultiFilter(key, values, disabledLabel = "") {
  const details = $(`#${key}-filter`);
  const options = $(`#${key}-options`);
  const valid = new Set(values);
  state.selections[key] = new Set([...state.selections[key]].filter((value) => valid.has(value)));
  if (disabledLabel) {
    state.selections[key].clear();
    details.open = false;
    details.classList.add("is-disabled");
    $(`#${key}-summary`).textContent = disabledLabel;
    options.innerHTML = "";
    return;
  }
  details.classList.remove("is-disabled");
  options.innerHTML = optionPanel(key, values);
  updateFilterSummary(key);
}

function updateSubcategoryOptions() {
  const categories = state.selections.category;
  if (!categories.size) {
    renderMultiFilter("subcategory", [], "先选岗位类别");
    return;
  }
  const values = unique(state.grouped
    .filter((job) => categories.has(job.category))
    .map((job) => job.subcategory));
  renderMultiFilter("subcategory", values, values.length <= 1 ? "无需细分" : "");
}

function renderAllFilters() {
  renderMultiFilter("category", state.optionValues.category);
  updateSubcategoryOptions();
  ["program", "tag", "stage", "freshness", "city", "company"].forEach((key) => {
    renderMultiFilter(key, state.optionValues[key]);
  });
}

function selectedMatches(key, values) {
  const selected = state.selections[key];
  return selected.size === 0 || values.some((value) => selected.has(value));
}

function freshnessMatches(job) {
  const selected = state.selections.freshness;
  if (!selected.size) return true;
  if (job.freshness_basis === "baseline") return selected.has("未知");
  const timestamp = freshnessTimestamp(job);
  if (!timestamp) return selected.has("未知");
  const hours = Math.max(0, (Date.now() - timestamp) / 3600000);
  return (selected.has("最近24小时") && hours <= 24)
    || (selected.has("最近7天") && hours <= 24 * 7)
    || (selected.has("最近14天") && hours <= 24 * 14);
}

function applyFilters() {
  const query = $("#search").value.trim().toLocaleLowerCase("zh-CN");
  state.filtered = state.grouped.filter((job) => {
    const haystack = [job.company, job.title, job.category, job.subcategory, job.raw_category, job.program, ...(job.tags || []), ...(job.locations || [])].join(" ").toLocaleLowerCase("zh-CN");
    return (!query || matchesQuery(haystack, query))
      && selectedMatches("category", [job.category])
      && selectedMatches("subcategory", [job.subcategory])
      && selectedMatches("program", [job.program])
      && selectedMatches("tag", job.tags || [])
      && selectedMatches("stage", [job.stage])
      && freshnessMatches(job)
      && selectedMatches("city", job.locations || [])
      && selectedMatches("company", [job.company]);
  });
  updateSourceStatus();
  state.page = 1;
  updatePageUrl();
  render();
}

function updateSourceStatus() {
  const element = $("#source-status");
  const companyNames = [...state.selections.company];
  const company = companyNames.length === 1
    ? state.companies.find((item) => item.company === companyNames[0])
    : null;
  const messages = {
    "抓取失败": "本轮官方源抓取失败，当前结果来自上次成功更新。",
    "暂无匹配岗位": "最近一次检查未发现符合本项目范围的实习或校招岗位。",
    "待接入": "该公司的官方招聘源正在接入，暂未展示岗位。",
  };
  const message = company ? messages[company.status] : "";
  element.hidden = !message;
  element.textContent = message ? `${company.company}：${message}` : "";
}

function searchFilterOptions(input) {
  const query = input.value.trim().toLocaleLowerCase("zh-CN");
  const panel = input.closest(".option-panel");
  panel.querySelectorAll("[data-option-group]").forEach((group) => {
    let visible = 0;
    group.querySelectorAll(".option-choice").forEach((choice) => {
      const matches = !query || choice.textContent.toLocaleLowerCase("zh-CN").includes(query);
      choice.hidden = !matches;
      if (matches) visible += 1;
    });
    group.hidden = visible === 0;
  });
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
    state.optionValues = {
      category: unique(state.grouped.map((job) => job.category)),
      program: unique(state.grouped.map((job) => job.program)),
      tag: unique(state.grouped.flatMap((job) => job.tags || [])),
      stage: unique(state.grouped.map((job) => job.stage)),
      freshness: ["最近24小时", "最近7天", "最近14天", "未知"],
      city: unique(state.grouped.flatMap((job) => job.locations || [])),
      company: unique(state.companies.map((company) => company.company)),
    };
    renderAllFilters();
    render();
  } catch (error) {
    $("#job-list").innerHTML = `<p class="empty">数据读取失败：${escapeHtml(error.message)}</p>`;
    $("#updated-at").textContent = "数据读取失败";
  }
}

$("#search").addEventListener("input", applyFilters);
$("#filter-panel").addEventListener("input", (event) => {
  const input = event.target.closest("input[data-option-search]");
  if (input) searchFilterOptions(input);
});
$("#filter-panel").addEventListener("change", (event) => {
  const input = event.target.closest("input[data-filter]");
  if (!input) return;
  const key = input.dataset.filter;
  if (input.checked) state.selections[key].add(input.value);
  else state.selections[key].delete(input.value);
  updateFilterSummary(key);
  if (key === "category") updateSubcategoryOptions();
  applyFilters();
});
$("#filter-panel").addEventListener("click", (event) => {
  const summary = event.target.closest(".multi-filter.is-disabled summary");
  if (summary) event.preventDefault();
});
$("#reset").addEventListener("click", () => {
  $("#search").value = "";
  filterKeys.forEach((key) => state.selections[key].clear());
  document.querySelectorAll(".multi-filter").forEach((details) => { details.open = false; });
  renderAllFilters();
  applyFilters();
});
document.querySelectorAll(".multi-filter").forEach((details) => {
  details.addEventListener("toggle", () => {
    if (!details.open) return;
    document.querySelectorAll(".multi-filter").forEach((other) => {
      if (other !== details) other.open = false;
    });
  });
});
document.addEventListener("click", (event) => {
  if (event.target.closest(".multi-filter")) return;
  document.querySelectorAll(".multi-filter").forEach((details) => { details.open = false; });
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
setInterval(() => {
  if (state.jobs.length) render();
}, 60000);
