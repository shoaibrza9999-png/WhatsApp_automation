CREATE TABLE IF NOT EXISTS houses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    house_no VARCHAR(255) UNIQUE NOT NULL,
    address TEXT
);

CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    house_id UUID REFERENCES houses(id),
    room_no VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    phone_number VARCHAR(50) UNIQUE NOT NULL,
    rent_amount NUMERIC NOT NULL,
    rent_balance NUMERIC DEFAULT 0,
    electricity_balance NUMERIC DEFAULT 0,
    last_meter_reading NUMERIC DEFAULT 0,
    billing_cycle_date INTEGER CHECK (billing_cycle_date >= 1 AND billing_cycle_date <= 28),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

DO $$ BEGIN
    CREATE TYPE transaction_type_enum AS ENUM ('RENT_CHARGE', 'RENT_PAYMENT', 'ELEC_CHARGE', 'ELEC_PAYMENT');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

CREATE TABLE IF NOT EXISTS transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    transaction_type transaction_type_enum NOT NULL,
    amount NUMERIC NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
