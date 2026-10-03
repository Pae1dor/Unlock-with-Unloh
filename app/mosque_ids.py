"""One id format for a mosque wherever it is stored: "osm:<type>/<id>" or "app:<id>".

  osm:node/123   a mosque from the nationwide OpenStreetMap file (services/mosque_index)
  app:42         a mosque added through the app (approved mosque request; later round)

Used by mosque_checkins.osm_id, prayer_log.mosque_id and user_roles.mosque_id. The map and
its JSON API keep using the bare OSM id ("node/123"); convert at the database boundary.
(The old `mosques` table and its integer ids are not part of this scheme.)
"""
OSM_PREFIX = "osm:"
APP_PREFIX = "app:"


def from_osm(osm_id: str) -> str:
    """"node/123" -> "osm:node/123" (already-prefixed ids pass through)."""
    return osm_id if osm_id.startswith(OSM_PREFIX) else OSM_PREFIX + osm_id


def to_osm(mosque_id: str) -> str | None:
    """"osm:node/123" -> "node/123"; None for an app mosque."""
    return mosque_id[len(OSM_PREFIX):] if mosque_id.startswith(OSM_PREFIX) else None


def from_app(app_mosque_id: int) -> str:
    return f"{APP_PREFIX}{app_mosque_id}"
