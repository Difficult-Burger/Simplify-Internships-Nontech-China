import assert from "node:assert/strict";
import test from "node:test";

import { estimateMonthlyEmailVolume, matchingJobs, matchesJob, normalizePreferences } from "../prototype/subscription/domain.mjs";

const jobs = [
  { id: "product", company: "字节跳动", title: "产品实习生", category: "产品", stage: "实习", locations: ["北京"], freshness_basis: "official", published_at: "2026-08-31T00:00:00Z" },
  { id: "ops", company: "腾讯", title: "运营培训生", category: "运营", stage: "校招", locations: ["深圳", "北京"], freshness_basis: "discovered", first_seen_at: "2026-08-30T00:00:00Z" },
  { id: "baseline", company: "腾讯", title: "市场实习生", category: "市场", stage: "实习", locations: ["深圳"], freshness_basis: "baseline", first_seen_at: "2026-08-24T00:00:00Z" },
];

test("normalizes duplicate and unordered preferences", () => {
  assert.deepEqual(normalizePreferences({ categories: ["运营", "产品", "运营"] }).categories, ["产品", "运营"]);
});

test("uses OR within a dimension and AND across dimensions", () => {
  assert.equal(matchesJob(jobs[0], { categories: ["产品", "运营"], stages: ["实习"], cities: ["北京"] }), true);
  assert.equal(matchesJob(jobs[1], { categories: ["产品", "运营"], stages: ["实习"], cities: ["北京"] }), false);
});

test("an empty optional dimension means no restriction", () => {
  assert.equal(matchesJob(jobs[1], { categories: ["运营"] }), true);
});

test("daily digest only includes matching jobs newer than the cursor", () => {
  const cursor = Date.parse("2026-08-29T00:00:00Z");
  assert.deepEqual(matchingJobs(jobs, { cities: ["北京"] }, cursor).map((job) => job.id), ["product", "ops"]);
});

test("baseline jobs are never reintroduced as new alerts", () => {
  assert.deepEqual(matchingJobs(jobs, { categories: ["市场"] }, 0), []);
});

test("email cost model returns the monthly upper bound", () => {
  assert.equal(estimateMonthlyEmailVolume(80), 2400);
  assert.throws(() => estimateMonthlyEmailVolume(-1), /non-negative integers/);
});
