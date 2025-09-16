-- Step 1: Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- Step 2: Tables
-- Users table to hold profile information, decoupled from auth.users for chatbot interaction
CREATE TABLE IF NOT EXISTS public.users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    phone_number TEXT UNIQUE,
    full_name TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Landlords table, linked to a user profile
CREATE TABLE IF NOT EXISTS public.landlords (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID UNIQUE REFERENCES public.users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    contact_number TEXT NOT NULL,
    email TEXT,
    is_verified BOOLEAN DEFAULT FALSE
);

-- Complexes table, owned by a landlord
CREATE TABLE IF NOT EXISTS public.complexes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    location TEXT,
    landlord_id UUID REFERENCES public.landlords(id) ON DELETE CASCADE
);

-- Enriched Listings table
CREATE TABLE IF NOT EXISTS public.listings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title TEXT NOT NULL,
    description TEXT,
    property_type TEXT,
    location TEXT,
    price FLOAT,
    is_bargainable BOOLEAN DEFAULT FALSE,
    size_sqm FLOAT,
    floor_number INT,
    year_built INT,
    furnishing TEXT,
    amenities TEXT[],
    utilities TEXT,
    internet_speed TEXT,
    minimum_lease_duration TEXT,
    availability_date DATE,
    photos TEXT[],
    video_tour_url TEXT,
    floor_plan_url TEXT,
    neighborhood_rating FLOAT,
    renovations TEXT,
    landlord_id UUID REFERENCES public.landlords(id) ON DELETE CASCADE,
    complex_id UUID REFERENCES public.complexes(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Embeddings table for vector search
CREATE TABLE IF NOT EXISTS public.listings_embeddings (
    listing_id UUID PRIMARY KEY REFERENCES public.listings(id) ON DELETE CASCADE,
    embedding VECTOR(1536),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Reviews table
CREATE TABLE IF NOT EXISTS public.reviews (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    listing_id UUID REFERENCES public.listings(id) ON DELETE CASCADE,
    user_id UUID REFERENCES public.users(id) ON DELETE CASCADE,
    rating INT CHECK (rating >= 1 AND rating <= 5),
    comment TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Chats table for conversation history
CREATE TABLE IF NOT EXISTS public.chats (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES public.users(id) ON DELETE CASCADE,
    user_message TEXT NOT NULL,
    bot_response TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Step 3: RLS (Row Level Security) Policies
-- Enable RLS on all tables
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.landlords ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.complexes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.listings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.listings_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.chats ENABLE ROW LEVEL SECURITY;

-- Policies for USERS table
DROP POLICY IF EXISTS "Enable read access for all users" ON public.users;
CREATE POLICY "Enable read access for all users" ON public.users FOR SELECT USING (true);

-- Policies for LANDLORDS table
DROP POLICY IF EXISTS "Anyone can view landlords." ON public.landlords;
CREATE POLICY "Anyone can view landlords." ON public.landlords FOR SELECT USING (true);

-- Policies for COMPLEXES table
DROP POLICY IF EXISTS "Enable all access for service_role on complexes" ON public.complexes;
CREATE POLICY "Enable all access for service_role on complexes" ON public.complexes FOR ALL USING (true);

-- Policies for LISTINGS table
DROP POLICY IF EXISTS "Anyone can view listings." ON public.listings;
CREATE POLICY "Anyone can view listings." ON public.listings FOR SELECT USING (true);

DROP POLICY IF EXISTS "Enable all access for service_role on listings" ON public.listings;
CREATE POLICY "Enable all access for service_role on listings" ON public.listings FOR ALL USING (true);

-- Policies for REVIEWS table
DROP POLICY IF EXISTS "Anyone can view reviews." ON public.reviews;
CREATE POLICY "Anyone can view reviews." ON public.reviews FOR SELECT USING (true);

DROP POLICY IF EXISTS "Enable all access for service_role on reviews" ON public.reviews;
CREATE POLICY "Enable all access for service_role on reviews" ON public.reviews FOR ALL USING (true);

-- Policies for CHATS table
DROP POLICY IF EXISTS "Enable all access for service_role on chats" ON public.chats;
CREATE POLICY "Enable all access for service_role on chats" ON public.chats FOR ALL USING (true);

-- Policies for EMBEDDINGS (should be managed by backend)
DROP POLICY IF EXISTS "Deny all access to embeddings table." ON public.listings_embeddings;
CREATE POLICY "Deny all access to embeddings table." ON public.listings_embeddings FOR ALL USING (false);

-- Step 4: RPC Functions for Vector Search
DROP FUNCTION IF EXISTS match_listings(vector, float, int);
CREATE OR REPLACE FUNCTION match_listings (
  query_embedding vector(1536),
  match_threshold float,
  match_count int
)
RETURNS TABLE (
  id uuid,
  title text,
  description text,
  property_type text,
  location text,
  price float,
  is_bargainable boolean,
  size_sqm float,
  floor_number int,
  year_built int,
  furnishing text,
  amenities text[],
  utilities text,
  internet_speed text,
  minimum_lease_duration text,
  availability_date date,
  photos text[],
  video_tour_url text,
  floor_plan_url text,
  neighborhood_rating float,
  renovations text,
  landlord_id uuid,
  complex_id uuid,
  created_at timestamptz,
  similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    l.id,
    l.title,
    l.description,
    l.property_type,
    l.location,
    l.price,
    l.is_bargainable,
    l.size_sqm,
    l.floor_number,
    l.year_built,
    l.furnishing,
    l.amenities,
    l.utilities,
    l.internet_speed,
    l.minimum_lease_duration,
    l.availability_date,
    l.photos,
    l.video_tour_url,
    l.floor_plan_url,
    l.neighborhood_rating,
    l.renovations,
    l.landlord_id,
    l.complex_id,
    l.created_at,
    1 - (le.embedding <=> query_embedding) as similarity
  FROM
    listings_embeddings le
  JOIN
    listings l ON le.listing_id = l.id
  WHERE
    1 - (le.embedding <=> query_embedding) > match_threshold
  ORDER BY
    similarity DESC
  LIMIT
    match_count;
END;
$$;