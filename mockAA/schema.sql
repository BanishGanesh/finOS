-- Run this once to set up your local PostgreSQL
-- psql -U postgres -d clinicos -f schema.sql

create extension if not exists "pgcrypto";

-- Master clinics table
create table if not exists clinics (
    id          uuid primary key default gen_random_uuid(),
    name        text not null,
    owner_name  text not null,
    specialty   text,
    city        text default 'Bengaluru',
    mobile      text,
    gstin       text,
    plan        text default 'starter',
    created_at  timestamptz default now()
);

-- AA consent records
create table if not exists aa_consents (
    id              uuid primary key default gen_random_uuid(),
    clinic_id       uuid not null references clinics(id),
    consent_handle  text unique not null,
    bank_id         text,
    bank_name       text,
    aa_handle       text,
    status          text default 'PENDING',
    last_synced_at  timestamptz,
    created_at      timestamptz default now(),
    updated_at      timestamptz default now()
);

-- Raw AA payloads — source of truth
create table if not exists raw_aa_payloads (
    id                  uuid primary key default gen_random_uuid(),
    clinic_id           uuid not null references clinics(id),
    consent_handle      text not null,
    raw_json            jsonb not null,
    transaction_count   integer,
    date_from           text,
    date_to             text,
    is_processed        boolean default false,
    processed_at        timestamptz,
    received_at         timestamptz default now()
);

create index if not exists idx_raw_clinic on raw_aa_payloads(clinic_id);
create index if not exists idx_raw_processed on raw_aa_payloads(is_processed);

-- Transactions — extracted and categorised
create table if not exists transactions (
    txn_id          text primary key,
    clinic_id       uuid not null references clinics(id),
    account_number  text,
    txn_date        date,
    txn_type        text,
    mode            text,
    amount          numeric(12,2),
    balance_after   numeric(12,2),
    narration       text,
    reference       text,
    category        text,
    gst_eligible    boolean default false,
    source          text default 'aa_framework',
    created_at      timestamptz default now()
);

create index if not exists idx_txn_clinic on transactions(clinic_id);
create index if not exists idx_txn_date on transactions(txn_date);
create index if not exists idx_txn_category on transactions(category);
create index if not exists idx_txn_clinic_date on transactions(clinic_id, txn_date);

-- Insert a test clinic so foreign key works
insert into clinics (id, name, owner_name, specialty, mobile)
values
    ('11111111-1111-1111-1111-111111111111',
     'Dr. Sharma Dental Clinic', 'Dr. Sharma', 'dental', '9876543210'),
    ('22222222-2222-2222-2222-222222222222',
     'Bengaluru Skin Clinic', 'Dr. Mehta', 'derma', '9876543211'),
    ('33333333-3333-3333-3333-333333333333',
     'City Family Practice', 'Dr. Rao', 'gp', '9876543212')
on conflict do nothing;