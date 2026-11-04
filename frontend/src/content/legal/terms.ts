import type { LegalDocument } from "./types";

/** The terms players agree to by using the app. */
export const terms: LegalDocument = {
  slug: "terms",
  title: "Terms of use",
  summary: "What you can expect from us, and what we expect from you.",
  updated: "2026-11-04",
  bangla: {
    title: "ব্যবহারের শর্ত — সংক্ষেপে",
    points: [
      "টার্ফ বুক করতে, ম্যাচে যোগ দিতে আর স্কোরকার্ড রাখতে এই অ্যাপ ব্যবহার করুন।",
      "আপনি যে মাঠ বুক করেন সেটি আমাদের নয় — টার্ফ মালিকের। মাঠের অবস্থা আর নিরাপত্তা তাদের দায়িত্ব।",
      "খেলার সময় যা ঘটে তার ঝুঁকি আপনার নিজের। খেলার আগে নিজের শারীরিক অবস্থা বুঝে নিন।",
      "একটি অ্যাকাউন্ট, আসল নাম। অন্যের নামে অ্যাকাউন্ট চালাবেন না।",
      "গালিগালাজ, বারবার না-আসা বা বিপজ্জনক খেলার জন্য অ্যাকাউন্ট বন্ধ হতে পারে।",
      "স্কোরকার্ড আর রেটিং খেলোয়াড়েরাই দেন। আমরা মাঝে থেকে বিবাদ মেটাই, ফল বানাই না।",
    ],
  },
  sections: [
    {
      heading: "What this app is",
      body: [
        "TurfApp lets you find and book sports turfs in Bangladesh, fill matches with other players, record what happened, and buy things to use while you play.",
        "We are the platform. We are not the turf. The ground you book belongs to its owner, who is responsible for its condition, its safety and what happens on it.",
      ],
    },
    {
      heading: "Your account",
      body: [
        "One account per person, in your own name. Do not create an account for somebody else or let somebody else use yours — bookings, ratings and conduct records are attached to accounts, and they are worthless if an account is not one person.",
        "You must be old enough to enter into a contract in Bangladesh, or have a parent or guardian do it for you.",
        "Keep your sign-in details to yourself. Tell us if you think somebody else has them.",
      ],
    },
    {
      heading: "Playing is at your own risk",
      body: [
        "Sport carries a risk of injury. You take that risk on yourself. Make sure you are fit to play before you play, and stop if you are not.",
        "We do not provide insurance, medical cover or supervision, and we do not inspect turfs for safety. A turf is responsible for its own ground.",
      ],
    },
    {
      heading: "Bookings",
      body: [
        "A booking is an agreement between you and the turf. We take the payment and keep the record.",
        "A new player's booking is held until the turf confirms it, and is released if they do not confirm in time. Once you have a track record at a turf, bookings there confirm automatically.",
        "Cancellation and refunds are covered by their own policy, which forms part of these terms.",
      ],
    },
    {
      heading: "Matches and other players",
      body: [
        "When you put a match on the board, anyone can ask to join and you decide. When you ask to join somebody else's, they decide.",
        "Turn up to what you commit to. Repeated no-shows and late cancellations lower your reliability score, which is visible to other players and affects whether your bookings confirm automatically.",
        "Treat other players decently. Abuse, unsafe play, and persistently not turning up can get an account suspended.",
      ],
    },
    {
      heading: "Scorecards and ratings",
      body: [
        "Results are entered by players and confirmed by the other side's captain. Turf staff can settle a dispute. We do not invent results and we do not change them to suit anybody.",
        "Ratings are computed from matches that have been locked. The formula is the same for everybody and does not change retroactively: a rating you earned is not recalculated because the weights changed later.",
        "Peer ratings are anonymous, and are meant to describe how somebody was to play with. Using them to punish somebody for a result is a misuse, and persistent misuse is treated as conduct.",
      ],
    },
    {
      heading: "The store",
      body: [
        "Items are sold by the turf or by us, depending on what you are buying — the order says which.",
        "Prices and availability can change until you place the order. If something sells out while you are deciding, we will tell you rather than substitute it.",
      ],
    },
    {
      heading: "Suspension",
      body: [
        "We can suspend or close an account that abuses other players, repeatedly fails to turn up, tries to defraud a turf or us, or uses the app to do something illegal.",
        "Where we can, we will tell you why and give you a chance to respond. Where money is owed in either direction, suspension does not cancel it.",
      ],
    },
    {
      heading: "What we are responsible for",
      body: [
        "We will run the app with reasonable care, keep your data as described in the privacy policy, and pass on your money to the right place.",
        "We are not responsible for injuries, for the condition of a turf, for what another player does, or for a turf cancelling on you — though in that last case you are refunded in full.",
        "If we get something wrong with a payment, we will put it right.",
      ],
    },
    {
      heading: "Changes",
      body: [
        "These terms will change as the app does. The date at the top says when they last did, and we will tell you about anything that materially affects you rather than quietly editing the page.",
      ],
    },
  ],
};
