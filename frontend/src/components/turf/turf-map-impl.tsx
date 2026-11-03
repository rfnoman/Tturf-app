"use client";

import { useEffect, useMemo, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

export type MapMarker = {
  id: string;
  latitude: number;
  longitude: number;
  label: string;
  sublabel?: string;
  href?: string;
};

/** Dhaka, used when there is nothing to centre on. */
const DHAKA: [number, number] = [23.8103, 90.4125];

/**
 * Leaflet's default marker is a PNG it resolves relative to its own CSS, which no
 * bundler rewrites correctly — the stock setup renders a broken-image icon with the alt
 * text "Marker". An inline SVG `divIcon` avoids the asset-path problem entirely and
 * picks up the app's own colours.
 */
function pinIcon(): L.DivIcon {
  return L.divIcon({
    className: "",
    html: `<svg width="26" height="34" viewBox="0 0 26 34" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <path d="M13 0C5.8 0 0 5.8 0 13c0 9.6 11.6 20 12.1 20.4a1.4 1.4 0 0 0 1.8 0C14.4 33 26 22.6 26 13 26 5.8 20.2 0 13 0z" fill="#16a34a"/>
      <circle cx="13" cy="13" r="5" fill="#fff"/>
    </svg>`,
    iconSize: [26, 34],
    // Anchored at the tip of the pin, so it points at the actual coordinate.
    iconAnchor: [13, 34],
    popupAnchor: [0, -30],
  });
}

/**
 * A Leaflet map over OpenStreetMap tiles (DECISIONS D24).
 *
 * Never imported directly — `./turf-map` wraps it in a browser-only dynamic import.
 * Leaflet reads `window` at module scope, and `"use client"` does not stop Next from
 * *evaluating* the module on the server to render the initial HTML, so importing this
 * file from a page is a 500.
 *
 * Driven through the imperative Leaflet API rather than react-leaflet components, so the
 * whole thing is one client boundary and nothing but this file ships Leaflet to the
 * browser. `draggableMarker` turns it into the registration form's location picker — the
 * same map, one extra prop, instead of a second component that drifts out of sync.
 */
export function TurfMapImpl({
  markers = [],
  center,
  zoom = 12,
  className = "h-80 w-full rounded-xl border",
  draggableMarker = false,
  onMove,
}: {
  markers?: MapMarker[];
  center?: [number, number];
  zoom?: number;
  className?: string;
  draggableMarker?: boolean;
  onMove?: (latitude: number, longitude: number) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const layer = useRef<L.LayerGroup | null>(null);
  // Held in a ref so a changing callback never tears down and rebuilds the map.
  // Written in an effect, not during render: a ref write during render is not a
  // render-safe operation and React flags it.
  const moveHandler = useRef(onMove);
  useEffect(() => {
    moveHandler.current = onMove;
  }, [onMove]);

  const initialCenter = useMemo<[number, number]>(() => {
    if (center) return center;
    if (markers.length > 0) return [markers[0].latitude, markers[0].longitude];
    return DHAKA;
  }, [center, markers]);

  useEffect(() => {
    if (!container.current || map.current) return;

    const instance = L.map(container.current, { scrollWheelZoom: false }).setView(
      initialCenter,
      zoom,
    );
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 19,
    }).addTo(instance);

    map.current = instance;
    layer.current = L.layerGroup().addTo(instance);

    if (draggableMarker) {
      instance.on("click", (event: L.LeafletMouseEvent) => {
        moveHandler.current?.(event.latlng.lat, event.latlng.lng);
      });
    }

    return () => {
      instance.remove();
      map.current = null;
      layer.current = null;
    };
    // Built once; later prop changes are applied by the effects below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Markers.
  useEffect(() => {
    const group = layer.current;
    const instance = map.current;
    if (!group || !instance) return;

    group.clearLayers();
    for (const marker of markers) {
      const pin = L.marker([marker.latitude, marker.longitude], {
        draggable: draggableMarker,
        title: marker.label,
        icon: pinIcon(),
        alt: marker.label,
      });
      if (draggableMarker) {
        pin.on("dragend", () => {
          const { lat, lng } = pin.getLatLng();
          moveHandler.current?.(lat, lng);
        });
      } else {
        const link = marker.href
          ? `<a href="${marker.href}" class="font-medium underline">${marker.label}</a>`
          : `<strong>${marker.label}</strong>`;
        pin.bindPopup(`${link}${marker.sublabel ? `<br>${marker.sublabel}` : ""}`);
      }
      pin.addTo(group);
    }

    if (markers.length > 1) {
      instance.fitBounds(
        L.latLngBounds(markers.map((m) => [m.latitude, m.longitude] as [number, number])),
        { padding: [32, 32], maxZoom: 15 },
      );
    }
  }, [markers, draggableMarker]);

  // Recentre when the caller moves the view (geolocation, or a picked address).
  useEffect(() => {
    if (map.current && center) {
      map.current.setView(center, map.current.getZoom());
    }
  }, [center]);

  return <div ref={container} className={className} role="application" aria-label="Map" />;
}
