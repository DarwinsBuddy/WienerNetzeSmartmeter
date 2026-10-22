"""WNSMSensor helper tests"""
from wnsm.api.constants import AnlagenType
from wnsm.wnsm_sensor import eeg_splits


def test_eeg_splits_consumption():
    assert eeg_splits(AnlagenType.CONSUMING.value) == (
        ("_grid", "G001", None),
        ("_eeg", "G003", None),
    )


def test_eeg_splits_feeding():
    assert eeg_splits(AnlagenType.FEEDING.value) == (
        ("_grid", "U001", None),
        ("_eeg", "E002", "U001"),
    )


def test_eeg_splits_unknown_type_falls_back_to_consumption():
    assert eeg_splits(None)[1] == ("_eeg", "G003", None)
