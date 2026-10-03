"""One id format for a mosque wherever it is stored: "osm:<type>/<id>" or "app:<id>".

  osm:node/123   a mosque from the nationwide OpenStreetMap file (services/mosque_index)
  app:42         a mosque added through the app (an approved mosque request, app_mosques)

Used by mosque_checkins.osm_id, prayer_log.mosque_id, user_roles.mosque_id and
app_mosques.osm_ref. The map and its JSON API use the bare OSM id ("node/123") and "app:42";
convert at the database boundary with from_api().
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


def to_app(mosque_id: str) -> int | None:
    """"app:42" -> 42; None for anything else."""
    if not mosque_id.startswith(APP_PREFIX):
        return None
    rest = mosque_id[len(APP_PREFIX):]
    return int(rest) if rest.isdigit() else None


def from_api(api_id: str) -> str:
    """Id as the map/API sends it -> stored form: "node/1" -> "osm:node/1", "app:3" stays."""
    return api_id if api_id.startswith(APP_PREFIX) else from_osm(api_id)
