-- 2026-05-17 — sites 6 seed (fixture data/mock_sites.json → PG)
-- 5 mock + 1 real (m15x-ph3-ibl PoC). is_mock 으로 구분.
-- Spec: docs/superpowers/specs/2026-05-17-cpia-db-migration-api-contract-design.md §7.3
-- fixture 와 1:1 정합: id/name/location/status/plan_progress/actual_progress/headcount/hours_saved/fte_saved

INSERT INTO sites (site_id, name, location, status, plan_progress, actual_progress, headcount, hours_saved, fte_saved, is_mock)
VALUES
  ('m15x-ph3-ibl',   'M15X Ph-3 IBL',   '청주', 'risk',    38.5, 34.2,  65, 221, 1.6, FALSE),
  ('y1-ph1-obl',     'Y-1 Ph-1 OBL',    '평택', 'normal',  62.1, 62.5, 130, 832, 5.9, TRUE),
  ('indiana-hac',    'Indiana Fab HAC', '미국', 'normal',  48.7, 48.6,  60, 353, 2.5, TRUE),
  ('pt3-extension',  'P&T 3 증축',       '이천', 'normal',  71.4, 72.6,  50, 255, 1.8, TRUE),
  ('m15x-obl-pt7',   'M15X OBL & PT7',  '청주', 'normal',  22.8, 22.5,  50, 246, 1.7, TRUE),
  ('y1-ph1-ibl',     'Y-1 Ph-1 IBL',    '평택', 'normal',  55.6, 55.8,  90, 248, 1.8, TRUE)
ON CONFLICT (site_id) DO UPDATE SET
  name = EXCLUDED.name,
  location = EXCLUDED.location,
  status = EXCLUDED.status,
  plan_progress = EXCLUDED.plan_progress,
  actual_progress = EXCLUDED.actual_progress,
  headcount = EXCLUDED.headcount,
  hours_saved = EXCLUDED.hours_saved,
  fte_saved = EXCLUDED.fte_saved,
  is_mock = EXCLUDED.is_mock,
  updated_at = NOW();
