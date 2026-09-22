create table public.alert_subscriptions (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null unique references auth.users(id) on delete cascade,
    email_enabled boolean not null default false,
    frequency text not null default 'daily' check (frequency in ('daily')),
    filters jsonb not null default '{}'::jsonb check (jsonb_typeof(filters) = 'object'),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table public.billing_entitlements (
    user_id uuid primary key references auth.users(id) on delete cascade,
    status text not null check (status in ('inactive', 'trialing', 'active', 'past_due', 'cancelled')),
    provider text not null,
    provider_customer_id text,
    provider_subscription_id text,
    current_period_end timestamptz,
    updated_at timestamptz not null default now()
);

create table public.notification_deliveries (
    id bigint generated always as identity primary key,
    user_id uuid not null references auth.users(id) on delete cascade,
    sent_at timestamptz not null default now(),
    matched_job_ids text[] not null default '{}',
    provider_message_id text,
    status text not null check (status in ('sent', 'failed', 'suppressed'))
);

alter table public.alert_subscriptions enable row level security;
alter table public.billing_entitlements enable row level security;
alter table public.notification_deliveries enable row level security;

revoke all on table public.alert_subscriptions from anon, authenticated;
revoke all on table public.billing_entitlements from anon, authenticated;
revoke all on table public.notification_deliveries from anon, authenticated;

grant select, insert, update, delete on table public.alert_subscriptions to authenticated;
grant select on table public.billing_entitlements to authenticated;
grant select on table public.notification_deliveries to authenticated;

create policy "Users can read their own alert settings"
on public.alert_subscriptions for select
to authenticated
using ((select auth.uid()) = user_id);

create policy "Users can create their own alert settings"
on public.alert_subscriptions for insert
to authenticated
with check ((select auth.uid()) = user_id);

create policy "Users can update their own alert settings"
on public.alert_subscriptions for update
to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

create policy "Users can delete their own alert settings"
on public.alert_subscriptions for delete
to authenticated
using ((select auth.uid()) = user_id);

create policy "Users can read their own entitlement"
on public.billing_entitlements for select
to authenticated
using ((select auth.uid()) = user_id);

create policy "Users can read their own delivery history"
on public.notification_deliveries for select
to authenticated
using ((select auth.uid()) = user_id);
