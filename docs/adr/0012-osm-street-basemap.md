# ADR 0012: OSM Carto street basemap in the Ask map

Status: accepted
Date: 2026-08-15

## Context

V1.5.2 shipped a tile-free Leaflet map: a bundled BC boundary and official
geometries on a CSS hatch, with evaluation gates requiring zero browser
requests to `tile.openstreetmap.org`. Owner preview feedback asked for a
street map so place and fire locations are readable.

A same-origin tile proxy is not implemented. Satellite imagery needs a
licensed host that is not in this repository.

## Decision

The production web map may load **OSM Carto** raster tiles directly in the
browser from `*.tile.openstreetmap.org`. Required OSM attribution is shown
on the map. The CSP `img-src` directive allowlists those tile hosts.

This revises the V1.5.2 tile-free claim in
`data/evaluation/frontend_surface.v1.yaml` and the matching e2e / security
assertions. `direct_third_party_tile_requests_max` is the allowlisted OSM
tile budget, not zero.

Satellite, Google, and Mapbox tiles are out of scope.

Community labels and coordinates remain coarse (two decimals). The map does
not persist Ask content or precise addresses.

## Consequences

Anonymous Ask sessions disclose tile requests to OSM. Privacy copy must say
so. Qualification and CSP tests must allow the allowlisted hosts instead of
asserting a tile-free map.
