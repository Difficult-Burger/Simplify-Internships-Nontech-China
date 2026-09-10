import { matchesJob, normalizePreferences, uniqueSorted } from "./domain.mjs";

const state = {
  jobs: [],
  email: "",
  preferences: normalizePreferences(),
  activated: false,
};

const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value) => String(value).replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);

function optionCounts(key) {
  const counts = new Map();
  for (const job of state.jobs) {
    const values = key === "cities" ? job.locations || [] : [key === "categories" ? job.category : job.company];
    values.forEach((value) => counts.set(value, (counts.get(value) || 0) + 1));
  }
  return counts;
}

function renderCategoryOptions() {
  const counts = optionCounts("categories");
  $("#category-options").innerHTML = [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([value, count]) => `<button type="button" class="choice-chip" data-filter="categories" data-value="${escapeHtml(value)}"><span>${escapeHtml(value)}</span><small>${count.toLocaleString("zh-CN")}</small></button>`)
    .join("");
}

function renderPicker(key, values) {
  $(`#${key}-options`).innerHTML = values.map((value) => `<label class="picker-option">
    <input type="checkbox" data-filter="${key}" value="${escapeHtml(value)}">
    <span>${escapeHtml(value)}</span>
  </label>`).join("");
}

function updateChoiceState() {
  document.querySelectorAll("[data-filter][data-value]").forEach((button) => {
    button.classList.toggle("is-selected", state.preferences[button.dataset.filter].includes(button.dataset.value));
  });
  document.querySelectorAll('input[type="checkbox"][data-filter]').forEach((input) => {
    input.checked = state.preferences[input.dataset.filter].includes(input.value);
  });
  ["cities", "companies"].forEach((key) => {
    const count = state.preferences[key].length;
    $(`#${key}-summary`).textContent = count ? `已选 ${count} 项` : key === "cities" ? "不限城市" : "不限公司";
  });
}

function renderPreview() {
  const matches = state.jobs.filter((job) => matchesJob(job, state.preferences));
  $("#match-count").textContent = matches.length.toLocaleString("zh-CN");
  $("#preview-list").innerHTML = matches.slice(0, 3).map((job) => `<li><strong>${escapeHtml(job.title)}</strong><span>${escapeHtml(job.company)} · ${escapeHtml((job.locations || []).slice(0, 2).join(" / "))}</span></li>`).join("") || "<li class=\"empty-preview\">选择岗位类别后查看匹配示例</li>";
  $("#activate").disabled = state.preferences.categories.length === 0;
}

function setSelection(key, value, selected) {
  const values = new Set(state.preferences[key]);
  if (selected) values.add(value);
  else values.delete(value);
  state.preferences = normalizePreferences({ ...state.preferences, [key]: [...values] });
  updateChoiceState();
  renderPreview();
}

function showBuilder() {
  $("#login-view").hidden = true;
  $("#builder-view").hidden = false;
  $("#account-email").textContent = state.email;
  renderPreview();
}

function activateDemo() {
  state.activated = true;
  $("#builder-view").hidden = true;
  $("#success-view").hidden = false;
  $("#success-email").textContent = state.email;
  $("#success-categories").textContent = state.preferences.categories.join("、");
}

async function boot() {
  const response = await fetch("../../docs/jobs.json", { cache: "no-store" });
  if (!response.ok) throw new Error(`岗位数据读取失败：HTTP ${response.status}`);
  state.jobs = await response.json();
  renderCategoryOptions();
  renderPicker("cities", uniqueSorted(state.jobs.flatMap((job) => job.locations || [])));
  renderPicker("companies", uniqueSorted(state.jobs.map((job) => job.company)));
  updateChoiceState();
  renderPreview();
}

$("#login-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const email = $("#email").value.trim();
  if (!email) return;
  state.email = email;
  showBuilder();
});

document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-filter][data-value]");
  if (!button) return;
  const key = button.dataset.filter;
  const value = button.dataset.value;
  setSelection(key, value, !state.preferences[key].includes(value));
});

document.addEventListener("change", (event) => {
  const input = event.target.closest('input[type="checkbox"][data-filter]');
  if (input) setSelection(input.dataset.filter, input.value, input.checked);
});

document.addEventListener("input", (event) => {
  const search = event.target.closest("[data-search]");
  if (!search) return;
  const query = search.value.trim().toLocaleLowerCase("zh-CN");
  $(`#${search.dataset.search}-options`).querySelectorAll(".picker-option").forEach((option) => {
    option.hidden = query && !option.textContent.toLocaleLowerCase("zh-CN").includes(query);
  });
});

$("#activate").addEventListener("click", activateDemo);
$("#restart").addEventListener("click", () => window.location.reload());

boot().catch((error) => {
  $("#prototype-error").hidden = false;
  $("#prototype-error").textContent = error.message;
});
