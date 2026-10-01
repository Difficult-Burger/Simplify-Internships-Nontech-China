export const FILTER_KEYS = ["categories", "stages", "cities", "companies"];

export function uniqueSorted(values) {
  return [...new Set(values.filter(Boolean))].sort((a, b) => a.localeCompare(b, "zh-CN"));
}

export function normalizePreferences(input = {}) {
  return Object.fromEntries(FILTER_KEYS.map((key) => [key, uniqueSorted(Array.isArray(input[key]) ? input[key] : [])]));
}

function selectedMatches(selected, values) {
  return selected.length === 0 || values.some((value) => selected.includes(value));
}

export function matchesJob(job, input = {}) {
  const preferences = normalizePreferences(input);
  return selectedMatches(preferences.categories, [job.category])
    && selectedMatches(preferences.stages, [job.stage])
    && selectedMatches(preferences.cities, job.locations || [])
    && selectedMatches(preferences.companies, [job.company]);
}

export function freshnessTimestamp(job) {
  if (job.freshness_basis === "baseline") return 0;
  return Date.parse(job.published_at || job.first_seen_at || 0) || 0;
}

export function matchingJobs(jobs, preferences, since = 0) {
  return jobs
    .filter((job) => freshnessTimestamp(job) > since && matchesJob(job, preferences))
    .sort((a, b) => freshnessTimestamp(b) - freshnessTimestamp(a));
}

export function estimateMonthlyEmailVolume(subscribers, runsPerDay = 1, days = 30) {
  if (![subscribers, runsPerDay, days].every((value) => Number.isInteger(value) && value >= 0)) {
    throw new TypeError("email volume inputs must be non-negative integers");
  }
  return subscribers * runsPerDay * days;
}
