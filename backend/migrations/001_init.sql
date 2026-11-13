-- BE-02: schema, RLS and private storage buckets (API-CONTRACT §6).
-- Idempotent: safe to run more than once in the Supabase SQL editor.

create table if not exists recipes (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  chef_name text,
  video_path text,                 -- Storage path, bucket "videos"
  transcript text,
  step_marks_s numeric[] not null default '{}',  -- chef's pinch marks while recording (step-boundary hints)
  status text not null,            -- 'uploading' | 'processing' | 'review' | 'published' | 'failed'
  error text,                      -- human-readable reason when status = 'failed'
  consent_at timestamptz,          -- when the uploader confirmed consent
  created_at timestamptz not null default now()
);

create table if not exists steps (
  id uuid primary key default gen_random_uuid(),
  recipe_id uuid not null references recipes on delete cascade,
  idx int not null,                -- 1-based
  title text not null,
  key_line text not null,
  instruction text not null,
  chef_quote text,
  timestamp_s numeric not null,
  clip_start_s numeric,
  clip_end_s numeric,
  success_criteria text[] not null default '{}',
  watch_fors jsonb not null default '[]',   -- [{id, mistake, headline, fix, spoken}]
  ref_image_path text,             -- Storage path, bucket "media"
  clip_path text,                  -- Storage path, bucket "media"
  timer_s int,
  unique (recipe_id, idx)
);

create table if not exists sessions (
  id uuid primary key default gen_random_uuid(),
  recipe_id uuid not null references recipes on delete cascade,
  client text not null,            -- 'ios' | 'web-sim'
  device_label text,
  started_at timestamptz not null default now(),
  finished_at timestamptz
);

create table if not exists session_events (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references sessions on delete cascade,
  step_id uuid references steps on delete set null,
  kind text not null,
  request_id uuid,
  payload jsonb not null default '{}',
  created_at timestamptz not null default now()
);

create index if not exists steps_recipe_id_idx_idx on steps (recipe_id, idx);
create index if not exists sessions_recipe_id_idx on sessions (recipe_id);
create index if not exists sessions_started_at_idx on sessions (started_at desc);
create index if not exists session_events_session_id_created_at_idx
  on session_events (session_id, created_at);
-- Foreign key used by "on delete set null" when steps are replaced.
create index if not exists session_events_step_id_idx on session_events (step_id);

-- RLS on, no policies: anon and authenticated can do nothing. The service role bypasses RLS.
alter table recipes enable row level security;
alter table steps enable row level security;
alter table sessions enable row level security;
alter table session_events enable row level security;

-- Private buckets. Clients upload videos straight to Storage, so Storage itself enforces
-- the 500 MB / video/mp4 limits on "videos".
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('videos', 'videos', false, 524288000, '{video/mp4}')
on conflict (id) do nothing;

insert into storage.buckets (id, name, public)
values ('media', 'media', false), ('frames', 'frames', false)
on conflict (id) do nothing;
