"""Seed local development data for routes, pricing, and schedules."""

from __future__ import annotations

import asyncio
from decimal import Decimal

from sqlalchemy import select

from app.config.database import async_session_factory, engine
from app.models.database import Route, RoutePricing, RouteSchedule


TEST_ROUTES = [
    {
        "name": "Classic Thailand Explorer",
        "supplier": "Skyline Travel",
        "tags": ["thailand", "family", "beach"],
        "summary": "7-day Bangkok and Phuket journey with city and island highlights.",
        "highlights": "Grand Palace, Phi Phi Islands, Thai cultural performance.",
        "base_info": "6 nights, 4-star hotels, shared group transfer.",
        "itinerary_json": {
            "days": [
                {"day": 1, "title": "Arrival Bangkok"},
                {"day": 2, "title": "Bangkok city tour"},
                {"day": 3, "title": "Transfer to Phuket"},
            ]
        },
        "notice": "Passport validity must exceed 6 months.",
        "included": "Hotel, breakfast, airport transfer, local guide.",
        "doc_url": "https://example.com/routes/classic-thailand",
        "is_hot": True,
        "sort_weight": 100,
        "pricing": {"price_min": Decimal("2999.00"), "price_max": Decimal("4599.00")},
        "schedule": {
            "schedules_json": [
                {"date": "2026-04-10", "seats_left": 12},
                {"date": "2026-04-24", "seats_left": 18},
            ]
        },
    },
    {
        "name": "Japan Sakura Discovery",
        "supplier": "North Star Tours",
        "tags": ["japan", "sakura", "culture"],
        "summary": "Tokyo, Kyoto, and Osaka cherry blossom route.",
        "highlights": "Ueno Park, Fushimi Inari, Arashiyama bamboo forest.",
        "base_info": "7 nights, mixed city hotels, rail pass included.",
        "itinerary_json": {
            "days": [
                {"day": 1, "title": "Arrival Tokyo"},
                {"day": 2, "title": "Tokyo free exploration"},
                {"day": 3, "title": "Bullet train to Kyoto"},
            ]
        },
        "notice": "Visa may be required depending on passport.",
        "included": "Hotels, transport pass, daily breakfast.",
        "doc_url": "https://example.com/routes/japan-sakura",
        "is_hot": True,
        "sort_weight": 95,
        "pricing": {"price_min": Decimal("6999.00"), "price_max": Decimal("9999.00")},
        "schedule": {
            "schedules_json": [
                {"date": "2026-03-20", "seats_left": 8},
                {"date": "2026-03-28", "seats_left": 6},
            ]
        },
    },
    {
        "name": "Bali Relax Retreat",
        "supplier": "Oceanic Holidays",
        "tags": ["bali", "honeymoon", "resort"],
        "summary": "5-day Bali resort retreat with spa and coastline activities.",
        "highlights": "Uluwatu sunset, Nusa Dua beach, Balinese spa package.",
        "base_info": "4 nights, beachfront resort, private transfer.",
        "itinerary_json": {
            "days": [
                {"day": 1, "title": "Arrival Denpasar"},
                {"day": 2, "title": "Resort and spa day"},
                {"day": 3, "title": "South Bali coastline tour"},
            ]
        },
        "notice": "Peak season surcharge may apply.",
        "included": "Resort, breakfast, one spa package, airport transfer.",
        "doc_url": "https://example.com/routes/bali-retreat",
        "is_hot": False,
        "sort_weight": 70,
        "pricing": {"price_min": Decimal("3899.00"), "price_max": Decimal("5699.00")},
        "schedule": {
            "schedules_json": [
                {"date": "2026-05-08", "seats_left": 15},
                {"date": "2026-05-22", "seats_left": 10},
            ]
        },
    },
    {
        "name": "Swiss Alps Panorama",
        "supplier": "EuroVista Travel",
        "tags": ["switzerland", "mountain", "scenic"],
        "summary": "8-day scenic rail and alpine landscape route in Switzerland.",
        "highlights": "Jungfraujoch, Lucerne lake, Glacier Express segment.",
        "base_info": "7 nights, alpine hotels, rail connections included.",
        "itinerary_json": {
            "days": [
                {"day": 1, "title": "Arrival Zurich"},
                {"day": 2, "title": "Lucerne and lake area"},
                {"day": 3, "title": "Interlaken alpine excursion"},
            ]
        },
        "notice": "Suitable cold-weather gear is recommended.",
        "included": "Hotels, breakfast, scenic train tickets.",
        "doc_url": "https://example.com/routes/swiss-panorama",
        "is_hot": False,
        "sort_weight": 85,
        "pricing": {"price_min": Decimal("11999.00"), "price_max": Decimal("15999.00")},
        "schedule": {
            "schedules_json": [
                {"date": "2026-06-12", "seats_left": 9},
                {"date": "2026-06-26", "seats_left": 14},
            ]
        },
    },
    {
        "name": "Xinjiang Silk Road Adventure",
        "supplier": "Westland Journeys",
        "tags": ["xinjiang", "culture", "landscape"],
        "summary": "10-day Xinjiang route covering Urumqi, Turpan, and Kashgar.",
        "highlights": "Tianshan views, Karez wells, old city market exploration.",
        "base_info": "9 nights, mixed hotels, domestic transport included.",
        "itinerary_json": {
            "days": [
                {"day": 1, "title": "Arrival Urumqi"},
                {"day": 2, "title": "Heavenly Lake excursion"},
                {"day": 3, "title": "Turpan culture route"},
            ]
        },
        "notice": "Weather and road conditions can affect schedule.",
        "included": "Hotels, selected meals, guide service, transfers.",
        "doc_url": "https://example.com/routes/xinjiang-silk-road",
        "is_hot": True,
        "sort_weight": 90,
        "pricing": {"price_min": Decimal("5299.00"), "price_max": Decimal("7999.00")},
        "schedule": {
            "schedules_json": [
                {"date": "2026-04-18", "seats_left": 20},
                {"date": "2026-05-16", "seats_left": 16},
            ]
        },
    },
]


async def seed_routes() -> None:
    """Insert seed routes with pricing and schedule records."""

    route_names = [item["name"] for item in TEST_ROUTES]

    try:
        async with async_session_factory() as session:
            existing_result = await session.execute(select(Route.name).where(Route.name.in_(route_names)))
            existing_names = set(existing_result.scalars().all())

            inserted_count = 0
            for item in TEST_ROUTES:
                if item["name"] in existing_names:
                    continue

                route = Route(
                    name=item["name"],
                    supplier=item["supplier"],
                    tags=item["tags"],
                    summary=item["summary"],
                    highlights=item["highlights"],
                    base_info=item["base_info"],
                    itinerary_json=item["itinerary_json"],
                    notice=item["notice"],
                    included=item["included"],
                    doc_url=item["doc_url"],
                    is_hot=item["is_hot"],
                    sort_weight=item["sort_weight"],
                )
                session.add(route)
                await session.flush()

                pricing = item["pricing"]
                schedule = item["schedule"]

                session.add(
                    RoutePricing(
                        route_id=route.id,
                        price_min=pricing["price_min"],
                        price_max=pricing["price_max"],
                        currency="CNY",
                    )
                )
                session.add(
                    RouteSchedule(
                        route_id=route.id,
                        schedules_json=schedule["schedules_json"],
                    )
                )
                inserted_count += 1

            await session.commit()
    finally:
        await engine.dispose()

    print(f"Seed completed. Inserted {inserted_count} new routes.")


if __name__ == "__main__":
    asyncio.run(seed_routes())
