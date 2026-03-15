"""Tests for wnsm utils."""
import os
import sys

# Add wnsm component dir so we can import utils/const without loading homeassistant
_wnsm_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "custom_components", "wnsm")
sys.path.insert(0, _wnsm_dir)
from wnsm.utils import translate_dict  # noqa: E402
from wnsm.const import ATTRS_BEWEGUNGSDATEN  # noqa: E402

CONSUMPTION_EMPTY_VALUES_PAYLOAD = {
    "descriptor": {
        "geschaeftspartnernummer": "***",
        "zaehlpunktnummer": "AT***",
        "rolle": "V001",
        "aggregat": "NONE",
        "granularitaet": "D",
        "einheit": None,
    },
    "values": [],
}


def test_translate_dict_consumption_call_empty_values():
    """translate_dict with consumption (ATTRS_BEWEGUNGSDATEN) payload with empty values."""
    result = translate_dict(CONSUMPTION_EMPTY_VALUES_PAYLOAD, ATTRS_BEWEGUNGSDATEN)
    from pprint import pprint
    pprint(result)
    assert result == {'aggregator': 'NONE',
                      'customerId': '***',
                      'granularity': 'D',
                      'role': 'V001',
                      'values': [],
                      'zaehlpunkt': 'AT***',
                      "unitOfMeasurement": None}
