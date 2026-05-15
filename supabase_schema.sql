create table if not exists public.incassi (
  id uuid primary key default gen_random_uuid(),
  data date not null unique,
  os numeric(12,2) not null default 0,
  contanti numeric(12,2) not null default 0,
  bonifici numeric(12,2) not null default 0,
  paypal numeric(12,2) not null default 0,
  altri numeric(12,2) not null default 0,
  totale numeric(12,2) not null default 0,
  note text not null default '',
  created_at timestamptz not null default now()
);
