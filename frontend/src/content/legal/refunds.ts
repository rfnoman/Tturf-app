import type { LegalDocument } from "./types";

/**
 * The cancellation and refund policy.
 *
 * Every rule here is the one the code actually applies — `refund_due()` in
 * `apps/payments/services.py` is the implementation of this document, and if the two
 * ever disagree the code is the bug. SSLCommerz asks for this URL during merchant
 * onboarding, which is the other reason it exists.
 */
export const refunds: LegalDocument = {
  slug: "refunds",
  title: "Cancellation and refund policy",
  summary: "What you get back when a booking or an order is cancelled, and when.",
  updated: "2026-11-04",
  bangla: {
    title: "বাতিল ও ফেরতের নিয়ম — সংক্ষেপে",
    points: [
      "টার্ফ বাতিল করলে আপনি পুরো টাকা ফেরত পাবেন — সবসময়।",
      "বিনামূল্যে বাতিলের সময়ের মধ্যে আপনি নিজে বাতিল করলেও পুরো টাকা ফেরত। প্রতিটি টার্ফ নিজের সময়সীমা ঠিক করে, আর বুক করার আগেই তা আপনাকে দেখানো হয়।",
      "দেরিতে বাতিল করলে অগ্রিম টাকাটা কেটে রাখা হয়, বাকিটা ফেরত আসে। অগ্রিমের কাজই হলো দেরিতে বাতিল করার একটা খরচ রাখা।",
      "অনলাইনে দেওয়া টাকা যেভাবে এসেছিল সেভাবেই ফেরত যায়, সাধারণত ৭–১০ কর্মদিবসে।",
      "স্টোরের অর্ডার টার্ফ বা গুদাম গ্রহণ করার আগপর্যন্ত বিনামূল্যে বাতিল করা যায়; পচনশীল পণ্য প্যাক হয়ে গেলে আর ফেরত নেওয়া যায় না।",
    ],
  },
  sections: [
    {
      heading: "Bookings cancelled by the turf",
      body: [
        "If a turf cancels your booking for any reason — weather, maintenance, double-booking, anything — you are refunded in full, including any advance. This is not discretionary and does not depend on how close to kick-off the cancellation happens.",
        "A turf that cancels does not count a cancellation against your reliability score.",
      ],
    },
    {
      heading: "Bookings you cancel inside the free window",
      body: [
        "Every turf sets a free-cancellation window, counted back from kick-off. The window that applies to your booking is shown on the booking page before you confirm, and again on the booking itself.",
        "Cancel at any point inside that window and you are refunded in full.",
      ],
    },
    {
      heading: "Bookings you cancel after the free window",
      body: [
        "The advance is forfeited and anything you paid beyond it is refunded.",
        "If you paid in full rather than paying a separate advance, the advance share of the price is treated as the deposit and the rest comes back. This is so that paying up front is never worse for you than paying the minimum.",
        "The advance exists to make a late cancellation cost something: the slot is held for you, and a turf that loses it an hour before kick-off cannot sell it again. Refunding the advance would make it decorative.",
      ],
      points: [
        "You can see exactly what a cancellation would be worth back, before you commit to it, on the booking page.",
        "Repeated late cancellations lower your reliability score, which affects whether future bookings are confirmed automatically.",
      ],
    },
    {
      heading: "No-shows",
      body: [
        "A booking nobody turns up to is not refunded. The slot was held, the turf was staffed, and nobody else could use it.",
      ],
    },
    {
      heading: "Store orders",
      body: [
        "An order can be cancelled for free at any time before the turf or the warehouse accepts it.",
        "Once accepted, perishable items that have been packed cannot be refunded. Everything else can be cancelled up until it leaves for delivery.",
        "If an item is out of stock when your order is picked, you are not charged for it. Nothing is substituted without asking you.",
      ],
    },
    {
      heading: "How refunds are paid",
      body: [
        "Money paid online is refunded to the same card or wallet it came from. We cannot send it anywhere else — that is a rule of the payment network, not ours.",
        "Refunds are requested the same day the cancellation is accepted. How long they take to appear is up to your bank or wallet provider; seven to ten working days is typical in Bangladesh.",
        "Money paid in cash at the turf is refunded in cash at the turf.",
      ],
    },
    {
      heading: "If something has gone wrong",
      body: [
        "Contact the turf first for anything about a specific booking — they can see it and can usually fix it immediately.",
        "For payment problems, disputed charges or a refund that has not arrived, contact us and include the booking or order reference. Every payment we take is recorded against a reference you can see on your payments page.",
      ],
    },
  ],
};
