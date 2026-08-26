-- Enable PostGIS extension (adds GIS support)
CREATE EXTENSION IF NOT EXISTS postgis;

-- Enable PostGIS Topology (optional, but useful)
CREATE EXTENSION IF NOT EXISTS postgis_topology;

-- Enable Trigram extension (adds support for fuzzy text/trigram matching)
CREATE EXTENSION IF NOT EXISTS pg_trgm;
