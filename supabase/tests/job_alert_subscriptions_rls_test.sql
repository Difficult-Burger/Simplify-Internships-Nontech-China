begin;
select plan(12);

select ok(
    not has_table_privilege('anon', 'public.alert_subscriptions', 'select,insert,update,delete'),
    'signed-out visitors cannot access alert settings'
);
select ok(
    has_table_privilege('authenticated', 'public.alert_subscriptions', 'select,insert,update,delete'),
    'signed-in users can manage alert settings through RLS'
);
select ok(
    not has_table_privilege('authenticated', 'public.billing_entitlements', 'insert,update,delete'),
    'clients cannot grant themselves paid access'
);
select ok(
    has_table_privilege('authenticated', 'public.billing_entitlements', 'select'),
    'signed-in users can read their entitlement'
);

insert into auth.users (id, email)
values
    ('11111111-1111-1111-1111-111111111111', 'one@example.com'),
    ('22222222-2222-2222-2222-222222222222', 'two@example.com');

set local role authenticated;
select set_config('request.jwt.claims', '{"sub":"11111111-1111-1111-1111-111111111111"}', true);

select lives_ok(
    $$insert into public.alert_subscriptions (user_id, filters)
      values ('11111111-1111-1111-1111-111111111111', '{"categories":["产品"]}')$$,
    'a user can create their own alert settings'
);
select throws_ok(
    $$insert into public.alert_subscriptions (user_id)
      values ('22222222-2222-2222-2222-222222222222')$$,
    '42501',
    null,
    'a user cannot create settings for another user'
);
select results_eq(
    $$select user_id from public.alert_subscriptions$$,
    $$values ('11111111-1111-1111-1111-111111111111'::uuid)$$,
    'a user only reads their own settings'
);
select lives_ok(
    $$update public.alert_subscriptions set email_enabled = true
      where user_id = '11111111-1111-1111-1111-111111111111'$$,
    'a user can update their own settings'
);
select results_eq(
    $$select count(*)::bigint from public.billing_entitlements$$,
    array[0::bigint],
    'a user sees no entitlement until the server grants one'
);
select throws_ok(
    $$insert into public.billing_entitlements (user_id, status, provider)
      values ('11111111-1111-1111-1111-111111111111', 'active', 'mock')$$,
    '42501',
    null,
    'a client cannot create an entitlement'
);
select throws_ok(
    $$insert into public.notification_deliveries (user_id, status)
      values ('11111111-1111-1111-1111-111111111111', 'sent')$$,
    '42501',
    null,
    'a client cannot forge delivery history'
);
select lives_ok(
    $$delete from public.alert_subscriptions
      where user_id = '11111111-1111-1111-1111-111111111111'$$,
    'a user can delete their own settings'
);

select * from finish();
rollback;
