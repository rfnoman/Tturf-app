/**
 * What the service worker shows when a page load finds no network.
 *
 * Written in **both** languages, with no translator: it is cached once, at install
 * time, so a localised version would be frozen in whichever language was active that
 * day — and the one moment somebody reads this page is the moment the app cannot ask
 * the server, or the cookie, what language they wanted. Two short lines is cheaper than
 * being wrong.
 *
 * Static for the same reason: no session, no API call, nothing that will not be there.
 */
export const metadata = { title: "Offline · TurfApp" };

export default function OfflinePage() {
  return (
    <section className="mx-auto flex max-w-md flex-col gap-6 py-12 text-center">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">আপনি অফলাইনে আছেন</h1>
        <p className="text-muted-foreground">
          এই পেজটি দেখতে ইন্টারনেট দরকার। আপনার বুকিং বা অর্ডারের কিছুই হারায়নি।
        </p>
      </div>
      <div className="flex flex-col gap-2">
        <h2 className="text-lg font-semibold tracking-tight">You are offline</h2>
        <p className="text-muted-foreground text-sm">
          This page needs a connection. Nothing you booked or ordered has been lost.
        </p>
      </div>
    </section>
  );
}
