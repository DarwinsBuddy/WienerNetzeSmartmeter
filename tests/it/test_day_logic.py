import asyncio

from wnsm.day_logic import async_get_latest_day_payload


class _FakeSmartmeter:
    async def get_historic_data(self, zaehlpunkt, start, end, granularity):
        return {
            "unitOfMeasurement": "KWH",
            "values": [
                {"zeitBis": "2024-02-01T00:00:00+00:00", "messwert": 3.0},
                {"zeitBis": "2024-02-02T00:00:00+00:00", "messwert": 4.0},
            ],
        }


def test_day_payload_sets_reading_dates_from_latest_points():
    latest, latest_two, attributes = asyncio.run(
        async_get_latest_day_payload(
            _FakeSmartmeter(),
            "AT001",
            {"active": True, "smartMeterReady": True},
        )
    )

    assert latest is not None
    assert [point.reading_date for point in latest_two] == attributes["reading_dates"]
    assert attributes["reading_date"] == latest.reading_date
