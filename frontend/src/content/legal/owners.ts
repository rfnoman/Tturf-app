import type { LegalDocument } from "./types";

/** The agreement a turf owner is accepting when they list a venue. */
export const owners: LegalDocument = {
  slug: "owners",
  title: "Turf owner agreement",
  summary: "The terms a venue lists under: commission, payouts, and who is responsible for what.",
  updated: "2026-11-04",
  bangla: {
    title: "টার্ফ মালিকের চুক্তি — সংক্ষেপে",
    points: [
      "আপনি নিজের মাঠ, দাম আর খোলা সময় নিজেই ঠিক করেন।",
      "প্রতিটি বুকিং আর বিক্রি থেকে প্ল্যাটফর্ম একটা কমিশন নেয়; আপনার হারটি আপনার হিসাব পাতায় লেখা থাকে।",
      "টাকা পরিশোধ হয় সময় ধরে ধরে — প্রতিটি পরিশোধের আগে আপনি পুরো বিবরণী দেখতে পাবেন।",
      "মাঠের অবস্থা, নিরাপত্তা আর সেখানকার কর্মীরা আপনার দায়িত্ব।",
      "আপনি বাতিল করলে খেলোয়াড় পুরো টাকা ফেরত পান — সেটি আপনার হিসাব থেকেই যায়।",
      "যে কোনো সময় তালিকা থেকে সরে যেতে পারেন; ইতিমধ্যে নেওয়া বুকিংগুলো সম্মান করতে হবে।",
    ],
  },
  sections: [
    {
      heading: "What you control",
      body: [
        "Your grounds, your opening hours, your prices and your price rules. We do not set them and we do not change them.",
        "Whether a booking confirms automatically, and how long before kick-off cancellation is free.",
        "Whether you ask for an advance, and what percentage.",
        "Your own inventory, its prices, and who on your staff can do what.",
      ],
    },
    {
      heading: "What we do",
      body: [
        "List your turf to players, take bookings, collect payment, and hold the record of both.",
        "Pass players' money to you, less commission, on the payout schedule below.",
        "Give you the tools to run the venue: a day calendar, a confirmation queue, a counter till, stock, rentals and a finance page.",
      ],
    },
    {
      heading: "Commission and payouts",
      body: [
        "We take a percentage of each booking and each sale made through the platform. Your rate is shown on your finance page, and it is the same for every booking unless we have agreed otherwise with you in writing.",
        "Earnings are paid out per period by bank transfer or bKash. Before each payout you can see the full statement it was calculated from, line by line, and download it.",
        "Cash taken at your own counter is already yours; commission on it is settled against your payouts rather than collected separately.",
        "If you cancel a booking, the player is refunded in full and that refund comes out of your earnings. That is the cost of cancelling on somebody.",
      ],
    },
    {
      heading: "What you are responsible for",
      body: [
        "The condition and safety of your grounds, facilities and equipment, and compliance with whatever local rules apply to your venue.",
        "The people who work for you, including anybody you give staff access to in the app.",
        "Honouring bookings the platform has confirmed. A slot you have sold twice is your problem to resolve, and the player is entitled to a full refund.",
        "The accuracy of what you list: if the floodlights do not work, the listing should not say they do.",
      ],
    },
    {
      heading: "Review and listing",
      body: [
        "A new turf is reviewed before it becomes visible to players. We can decline a listing, and we will say why.",
        "We can suspend a listing that repeatedly cancels on players, misrepresents the venue, or is unsafe. Suspension does not cancel money owed in either direction.",
      ],
    },
    {
      heading: "Leaving",
      body: [
        "You can take your turf off the platform at any time. Bookings already taken must be honoured, and your final payout is settled on the normal schedule.",
        "Your historical records — bookings, payments, statements — stay in the system because they are financial records, and you keep access to your own.",
      ],
    },
  ],
};
