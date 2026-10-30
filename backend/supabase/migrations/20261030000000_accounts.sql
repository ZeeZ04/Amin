-- Amin's cloud holds accounts and subscriptions only (decision 2026-10-30).
-- Questions, documents, memory and conversations never reach this database:
-- they stay on each person's own devices (ADR-014).

create table public.profiles (
  id          uuid primary key references auth.users (id) on delete cascade,
  display_name text check (char_length(display_name) <= 64),
  locale      text not null default 'en' check (locale in ('en', 'ar', 'ml')),
  created_at  timestamptz not null default now()
);

-- One row per person, written only by the RevenueCat webhook (service role).
create table public.entitlements (
  user_id     uuid primary key references auth.users (id) on delete cascade,
  plan        text not null default 'free' check (plan in ('free', 'pro')),
  product_id  text,
  store       text,                       -- APP_STORE | PLAY_STORE | STRIPE | PROMOTIONAL
  expires_at  timestamptz,                -- null = no expiry (lifetime or free)
  updated_at  timestamptz not null default now()
);

alter table public.profiles enable row level security;
alter table public.entitlements enable row level security;

create policy "read own profile"   on public.profiles for select using (auth.uid() = id);
create policy "update own profile" on public.profiles for update using (auth.uid() = id) with check (auth.uid() = id);
create policy "read own plan"      on public.entitlements for select using (auth.uid() = user_id);
-- No insert/update/delete policies on entitlements: only the service role writes plans.

-- A profile and a free plan for every new account.
create function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  insert into public.profiles (id, display_name, locale)
  values (new.id, new.raw_user_meta_data ->> 'display_name', coalesce(new.raw_user_meta_data ->> 'locale', 'en'));
  insert into public.entitlements (user_id) values (new.id);
  return new;
end $$;

create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.handle_new_user();

-- Is this person Pro right now? Used by the app after sign-in.
create function public.is_pro() returns boolean
language sql stable security invoker set search_path = '' as $$
  select exists (
    select 1 from public.entitlements
    where user_id = auth.uid() and plan = 'pro' and (expires_at is null or expires_at > now())
  );
$$;
