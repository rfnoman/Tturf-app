import type { MetadataRoute } from "next";

/**
 * The web app manifest, which is what makes "add to home screen" an offer the browser
 * makes rather than something the user has to find in a menu.
 *
 * Bangladesh is a phone-first market with no app-store listing in sight, so an installed
 * icon is how the app gets opened a second time. `display: standalone` drops the browser
 * chrome, which matters most on the small screens this is actually used on.
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "TurfApp — book a ground, fill your match",
    short_name: "TurfApp",
    description: "Book sports turfs in Bangladesh, fill your match, build your profile.",
    start_url: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#ffffff",
    theme_color: "#16a34a",
    // Both languages, so an installed shortcut is labelled in whatever the phone reads.
    lang: "en",
    dir: "ltr",
    categories: ["sports", "lifestyle"],
    icons: [
      { src: "/icons/192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      // A maskable icon is the one Android actually puts on the launcher: without it the
      // icon is letterboxed inside a white circle on most devices.
      { src: "/icons/maskable.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
    shortcuts: [
      { name: "Find a match", url: "/play" },
      { name: "My bookings", url: "/bookings" },
      { name: "Store", url: "/store" },
    ],
  };
}
