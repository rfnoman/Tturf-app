"""Demo turfs for local development (phase 02 brief: five Dhaka areas, realistic BDT).

Coordinates are real neighbourhood centroids so "near me" ordering is meaningful when
you drag the map around Dhaka, and prices follow the local market: a 5-a-side evening
slot runs roughly ৳1,500–3,000, with peak Thursday/Friday nights at the top of that.

Idempotent, like every other seed: matched on slug and updated in place.
"""

from __future__ import annotations

from datetime import time
from decimal import Decimal
from typing import Any

#: Dhaka's weekend is Friday and Saturday, so those carry the peak prices — not Sat/Sun.
FRIDAY, SATURDAY = 4, 5
WEEKEND = [FRIDAY, SATURDAY]
WEEKDAYS = [0, 1, 2, 3, 6]

DEMO_TURFS: list[dict[str, Any]] = [
    {
        "slug": "dhanmondi-arena",
        "name": "Dhanmondi Arena",
        "area": "Dhanmondi",
        "address": "Road 27, Dhanmondi, Dhaka 1209",
        "description": "Rooftop five-a-side with floodlights, two minutes from Road 27.",
        "latitude": 23.7465,
        "longitude": 90.3760,
        "phone": "+8801711000001",
        "amenities": ["floodlights", "parking", "changing_room", "washroom", "cafe"],
        "hours": [(day, time(6, 0), time(0, 0)) for day in range(7)],
        "grounds": [
            {
                "name": "Main Pitch",
                "surface": "artificial_turf",
                "max_players": 14,
                "slot_minutes": 60,
                "formats": [("football", "5v5"), ("football", "7v7")],
                "prices": [
                    (WEEKDAYS, time(6, 0), time(16, 0), "1500.00", "Off-peak"),
                    (WEEKDAYS, time(16, 0), time(22, 0), "2500.00", "Peak"),
                    (WEEKDAYS, time(22, 0), time(0, 0), "1800.00", "Night"),
                    (WEEKEND, time(6, 0), time(16, 0), "2000.00", "Off-peak"),
                    (WEEKEND, time(16, 0), time(22, 0), "3000.00", "Peak"),
                    (WEEKEND, time(22, 0), time(0, 0), "2200.00", "Night"),
                ],
            },
            {
                "name": "Court B",
                "surface": "synthetic",
                "max_players": 4,
                "slot_minutes": 60,
                "formats": [("badminton", "singles"), ("badminton", "doubles")],
                "prices": [
                    ([], time(6, 0), time(16, 0), "600.00", "Off-peak"),
                    ([], time(16, 0), time(0, 0), "900.00", "Peak"),
                ],
            },
        ],
    },
    {
        "slug": "mirpur-turf-club",
        "name": "Mirpur Turf Club",
        "area": "Mirpur",
        "address": "Section 11, Mirpur, Dhaka 1216",
        "description": "Two full-size seven-a-side pitches and a box-cricket net.",
        "latitude": 23.8223,
        "longitude": 90.3654,
        "phone": "+8801711000002",
        "amenities": ["floodlights", "parking", "washroom", "drinking_water", "seating"],
        # Closes at 02:00, so availability has to carry the window past midnight.
        "hours": [(day, time(7, 0), time(2, 0)) for day in range(7)],
        "grounds": [
            {
                "name": "Pitch 1",
                "surface": "artificial_turf",
                "max_players": 14,
                "slot_minutes": 90,
                "formats": [("football", "7v7"), ("football", "5v5")],
                "prices": [
                    (WEEKDAYS, time(7, 0), time(17, 0), "2000.00", "Off-peak"),
                    (WEEKDAYS, time(17, 0), time(2, 0), "3200.00", "Peak"),
                    (WEEKEND, time(7, 0), time(17, 0), "2400.00", "Off-peak"),
                    (WEEKEND, time(17, 0), time(2, 0), "3800.00", "Peak"),
                ],
            },
            {
                "name": "Cricket Net",
                "surface": "concrete",
                "max_players": 16,
                "slot_minutes": 60,
                "formats": [("cricket", "nets"), ("cricket", "box")],
                "prices": [
                    ([], time(7, 0), time(17, 0), "800.00", "Off-peak"),
                    ([], time(17, 0), time(2, 0), "1400.00", "Peak"),
                ],
            },
        ],
    },
    {
        "slug": "banani-sports-hub",
        "name": "Banani Sports Hub",
        "area": "Banani",
        "address": "Road 11, Banani, Dhaka 1213",
        "description": "Indoor futsal court with a cafe overlooking the pitch.",
        "latitude": 23.7937,
        "longitude": 90.4066,
        "phone": "+8801711000003",
        "amenities": ["floodlights", "changing_room", "washroom", "cafe", "first_aid", "cctv"],
        "hours": [(day, time(8, 0), time(23, 0)) for day in range(7)],
        "grounds": [
            {
                "name": "Indoor Court",
                "surface": "wooden",
                "max_players": 10,
                "slot_minutes": 60,
                "formats": [("futsal", "5v5"), ("futsal", "4v4")],
                "prices": [
                    (WEEKDAYS, time(8, 0), time(17, 0), "1800.00", "Off-peak"),
                    (WEEKDAYS, time(17, 0), time(23, 0), "2800.00", "Peak"),
                    (WEEKEND, time(8, 0), time(17, 0), "2200.00", "Off-peak"),
                    (WEEKEND, time(17, 0), time(23, 0), "3400.00", "Peak"),
                ],
            }
        ],
    },
    {
        "slug": "uttara-green-ground",
        "name": "Uttara Green Ground",
        "area": "Uttara",
        "address": "Sector 7, Uttara, Dhaka 1230",
        "description": "Natural grass, the only one left this side of the airport road.",
        "latitude": 23.8759,
        "longitude": 90.3795,
        "phone": "+8801711000004",
        "amenities": ["parking", "washroom", "drinking_water", "equipment_rental"],
        "hours": [(day, time(6, 0), time(21, 0)) for day in range(7)],
        "grounds": [
            {
                "name": "Grass Pitch",
                "surface": "natural_grass",
                "max_players": 22,
                "slot_minutes": 120,
                "formats": [("football", "9v9"), ("football", "11v11")],
                "prices": [
                    (WEEKDAYS, time(6, 0), time(16, 0), "3000.00", "Off-peak"),
                    (WEEKDAYS, time(16, 0), time(21, 0), "4500.00", "Peak"),
                    (WEEKEND, time(6, 0), time(16, 0), "3600.00", "Off-peak"),
                    (WEEKEND, time(16, 0), time(21, 0), "5200.00", "Peak"),
                ],
            }
        ],
    },
    {
        "slug": "bashundhara-play-zone",
        "name": "Bashundhara Play Zone",
        "area": "Bashundhara",
        "address": "Block C, Bashundhara R/A, Dhaka 1229",
        "description": "Three courts under one roof: futsal, badminton and box cricket.",
        "latitude": 23.8213,
        "longitude": 90.4254,
        "phone": "+8801711000005",
        "amenities": [
            "floodlights",
            "parking",
            "changing_room",
            "washroom",
            "cafe",
            "equipment_rental",
            "seating",
        ],
        "hours": [(day, time(7, 0), time(1, 0)) for day in range(7)],
        "grounds": [
            {
                "name": "Court 1",
                "surface": "synthetic",
                "max_players": 10,
                "slot_minutes": 60,
                "formats": [("futsal", "5v5")],
                "prices": [
                    ([], time(7, 0), time(17, 0), "1600.00", "Off-peak"),
                    ([], time(17, 0), time(1, 0), "2600.00", "Peak"),
                ],
            },
            {
                "name": "Court 2",
                "surface": "synthetic",
                "max_players": 4,
                "slot_minutes": 60,
                "formats": [("badminton", "doubles"), ("badminton", "singles")],
                "prices": [
                    ([], time(7, 0), time(17, 0), "700.00", "Off-peak"),
                    ([], time(17, 0), time(1, 0), "1100.00", "Peak"),
                ],
            },
            {
                "name": "Box Cricket",
                "surface": "artificial_turf",
                "max_players": 16,
                "slot_minutes": 90,
                "formats": [("cricket", "box")],
                "prices": [
                    ([], time(7, 0), time(17, 0), "1200.00", "Off-peak"),
                    ([], time(17, 0), time(1, 0), "2000.00", "Peak"),
                ],
            },
        ],
    },
]


def price_decimal(raw: str) -> Decimal:
    return Decimal(raw)
