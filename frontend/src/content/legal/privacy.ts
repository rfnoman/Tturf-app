import type { LegalDocument } from "./types";

/**
 * The privacy policy.
 *
 * Written from what the code actually stores and sends, not from a template. Every
 * claim here is checkable against the models and the Phase 11 step 4 and 5 work — in
 * particular the parts about what error reports exclude and what a player's name falls
 * back to.
 */
export const privacy: LegalDocument = {
  slug: "privacy",
  title: "Privacy policy",
  summary: "What we hold about you, why, who else sees it, and how to get rid of it.",
  updated: "2026-11-04",
  bangla: {
    title: "গোপনীয়তা — সংক্ষেপে",
    points: [
      "আপনার নাম, ইমেইল আর (দিলে) ফোন নম্বর রাখি — অ্যাকাউন্ট চালাতে আর বুকিং নিয়ে যোগাযোগ করতে।",
      "আপনার ফোন নম্বর অন্য খেলোয়াড়দের দেখানো হয় না। টার্ফ শুধু তাদের নিজেদের বুকিংয়ের তথ্য দেখে।",
      "আপনার ইমেইল কখনো আপনার নাম হিসেবে দেখানো হয় না — নাম না দিলে শুধু 'Player' লেখা থাকে।",
      "আমরা কার্ডের তথ্য রাখি না। অনলাইনে টাকা দিলে তা সরাসরি পেমেন্ট গেটওয়েতে যায়।",
      "কোনো বিজ্ঞাপন বা ট্র্যাকিং কুকি নেই। যে কুকিগুলো আছে সেগুলো অ্যাপ চালানোর জন্যই দরকার।",
      "অ্যাকাউন্ট মুছতে চাইলে বলুন — আমরা মুছে দেব, তবে হিসাবের রেকর্ড আইন অনুযায়ী রাখতে হয়।",
    ],
  },
  sections: [
    {
      heading: "What we hold",
      body: ["Only what the app needs to work. In practice that is:"],
      points: [
        "Your name, email address and — if you give one — your phone number. Sign-in itself is handled by Clerk; we never see your password.",
        "Your player profile: display name, area, the sports you play, your self-assessed skills, and optionally your date of birth, height and weight. The weight is used for one thing: estimating calories burned.",
        "Your bookings, matches, scorecards, ratings and orders — the record of what you did on the app.",
        "Delivery addresses you save, and the phone number attached to them.",
        "Payment records: the amount, the method, the gateway's transaction reference and whether it succeeded. Never card numbers.",
      ],
    },
    {
      heading: "What other people can see",
      body: [
        "Your display name, area, sport cards, ratings and match history are visible to other players. That is the point of the app — somebody deciding whether to invite you to a match needs to see them.",
        "Your phone number is not shown to other players. Turf staff see the contact details attached to bookings at their own turf, because they have to be able to reach you about them.",
        "Your email address is never used as your name. If you have not set a name, you appear as “Player”.",
        "You can turn off `Appear in player search` in settings. A direct link to your profile still works — that is what makes a shared profile link useful — but you stop appearing in search results.",
        "Peer ratings are anonymous. The player you rated sees the number, never who gave it.",
      ],
    },
    {
      heading: "What we never hold",
      body: [
        "Card numbers, CVVs and wallet PINs. Online payments happen on the payment gateway's own page; what comes back to us is a transaction reference and a result.",
        "Your password. Clerk holds that, and we could not read it if we wanted to.",
      ],
    },
    {
      heading: "Who we share it with",
      body: ["Four companies, each for one job, and none of them for advertising:"],
      points: [
        "Clerk — sign-in and account management.",
        "SSLCommerz — online card and wallet payments.",
        "Sentry — error reports, so we find out when something breaks. Request bodies are never sent, and credentials are stripped before anything leaves our servers.",
        "Our hosting and email providers, which necessarily handle data in transit.",
      ],
    },
    {
      heading: "Cookies",
      body: [
        "There are no advertising cookies and no analytics cookies on this site. We do not track you across other websites, and we do not sell anything about you.",
        "The cookies that exist are the ones the app needs to function: your sign-in session (set by Clerk) and your language choice. There is no consent banner because there is nothing to consent to — a banner for strictly necessary cookies is theatre, and we would rather tell you plainly what is set and why.",
      ],
    },
    {
      heading: "How long we keep it",
      body: [
        "Your account and profile for as long as you have an account.",
        "Bookings, orders and payment records for as long as we are required to keep financial records, which is longer than your account may last. Those records are kept against the transaction, not against your profile.",
        "Error reports for 90 days.",
      ],
    },
    {
      heading: "Your choices",
      body: [
        "You can edit or delete your profile details at any time in settings, and turn off discoverability there too.",
        "You control every notification individually, including quiet hours, and push notifications are off until you turn them on.",
        "Ask us to delete your account and we will. Financial records attached to completed transactions have to stay, and they are kept with your personal details removed.",
        "Ask us for a copy of what we hold about you and we will send it.",
      ],
    },
    {
      heading: "Security",
      body: [
        "All traffic is encrypted in transit. Administrative access to the system requires a second factor.",
        "If we ever discover a breach affecting your data, we will tell you what happened and what was affected rather than wait to be asked.",
      ],
    },
  ],
};
