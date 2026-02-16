import { z } from "zod";

export const RunSchema = z.object({
  id: z.string(),
  entity_type: z.string(),
  source_type: z.string(),
  created_at: z.string(),
  params_json: z.string().nullable(),
  status: z.string(),
});
export type Run = z.infer<typeof RunSchema>;

export const RunDetailSchema = RunSchema.extend({
  total_entities: z.number(),
  total_matches: z.number(),
  matches_high: z.number(),
  matches_medium: z.number(),
  matches_low: z.number(),
  total_clusters: z.number(),
});
export type RunDetail = z.infer<typeof RunDetailSchema>;

export const EntitySchema = z.object({
  id: z.string(),
  run_id: z.string(),
  entity_type: z.string(),
  external_id: z.string(),
  raw_json: z.record(z.unknown()).nullable(),
});
export type Entity = z.infer<typeof EntitySchema>;

export const ReasonItemSchema = z.object({
  feature: z.string(),
  weight: z.number(),
  detail: z.string(),
});

export const MatchSchema = z.object({
  id: z.string(),
  run_id: z.string(),
  entity_type: z.string(),
  a_entity_id: z.string(),
  b_entity_id: z.string(),
  score: z.number(),
  reasons_json: z.array(ReasonItemSchema).nullable(),
  recommended_survivor_entity_id: z.string().nullable(),
  status: z.string(),
  updated_at: z.string(),
  entity_a: EntitySchema.nullable().optional(),
  entity_b: EntitySchema.nullable().optional(),
});
export type Match = z.infer<typeof MatchSchema>;

export const MatchesListSchema = z.object({
  items: z.array(MatchSchema),
  total: z.number(),
  limit: z.number(),
  offset: z.number(),
});
export type MatchesList = z.infer<typeof MatchesListSchema>;

export const ClusterSummarySchema = z.object({
  id: z.string(),
  run_id: z.string(),
  entity_type: z.string(),
  member_count: z.number(),
  member_entity_ids: z.array(z.string()),
  recommended_survivor_entity_id: z.string().nullable(),
  recommended_survivor_name: z.string().nullable().optional(),
});
export type ClusterSummary = z.infer<typeof ClusterSummarySchema>;

export const ClusterDetailSchema = z.object({
  id: z.string(),
  run_id: z.string(),
  entity_type: z.string(),
  member_entity_ids: z.array(z.string()),
  recommended_survivor_entity_id: z.string().nullable(),
  members: z.array(EntitySchema),
  pairwise_matches: z.array(MatchSchema),
});
export type ClusterDetail = z.infer<typeof ClusterDetailSchema>;
