// Re-export de todas las funciones de lib/db/*
export { db } from "./client";
export { votesDb } from "./votes-client";
export {
  getUpcomingFixtures,
  getFixtureById,
  getRecentFixtures,
  getFixturesByJornada,
  getFixturesByJornadaExact,
  getUpcomingJornadas,
  getNextOpenJornada,
  getFixturesInRange,
  getRecentFinishedWithPredictions,
  type JornadaOption,
} from "./fixtures";
export { getAllTeams, getTeamById, getTeamRecentFixtures, getTeamUpcomingFixtures } from "./teams";
export {
  getLatestPredictionForFixture,
  getPredictionView,
  getPredictionHistory,
} from "./predictions";
export { getMatchdayOrdinal, getMatchdayOrdinalByDate, getMatchdayLabel } from "./matchday";
export { getFixtureCounts, getHistoryStats } from "./stats";
// Vote-related (read+write sobre la BD secundaria)
export {
  getCrowdSummary,
  getUserPick,
  getUserPicksBatch,
  getCrowdPick,
  recordVotesBatch,
  type CrowdSummary,
  type Pick,
  type BatchVoteResultItem,
} from "./votes";
// Tipos
export type * from "./types";
