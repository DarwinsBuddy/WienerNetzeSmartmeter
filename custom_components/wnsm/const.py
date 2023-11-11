"""
    component constants
"""
DOMAIN = "wnsm"

CONF_ZAEHLPUNKTE = "zaehlpunkte"

ATTRS_ZAEHLPUNKT_CALL = [
    ("zaehlpunktnummer", "zaehlpunktnummer"),
    ("customLabel", "label"),
    ("equipmentNumber", "equipmentNumber"),
    ("dailyConsumption", "dailyConsumption"),
    ("geraetNumber", "deviceId"),
    ("customerId", "geschaeftspartner"),
    ("verbrauchsstelle.strasse", "street"),
    ("verbrauchsstelle.hausnummer", "streetNumber"),
    ("verbrauchsstelle.postleitzahl", "zip"),
    ("verbrauchsstelle.ort", "city"),
    ("verbrauchsstelle.laengengrad", "longitude"),
    ("verbrauchsstelle.breitengrad", "latitude"),
    ("anlage.typ", "type"),
]

ATTRS_ZAEHLPUNKTE_CALL = [
    ("geschaeftspartner", "customerId"),
    ("zaehlpunktnummer", "zaehlpunktnummer"),
    ("customLabel", "label"),
    ("equipmentNumber", "equipmentNumber"),
    ("geraetNumber", "deviceId"),
    ("verbrauchsstelle.strasse", "street"),
    ("verbrauchsstelle.anlageHausnummer", "streetNumber"),
    ("verbrauchsstelle.postleitzahl", "zip"),
    ("verbrauchsstelle.ort", "city"),
    ("verbrauchsstelle.laengengrad", "longitude"),
    ("verbrauchsstelle.breitengrad", "latitude"),
    ("anlage.typ", "type"),
    ("isDefault", "default"),
    ("isActive", "active"),
    ("isSmartMeterMarketReady", "smartMeterReady"),
    ("idexStatus.granularity.status", "granularity")
]

ATTRS_CONSUMPTIONS_CALL = [
    ("consumptionYesterday.value", "consumptionYesterdayValue"),
    ("consumptionYesterday.validated", "consumptionYesterdayValidated"),
    ("consumptionYesterday.date", "consumptionYesterdayTimestamp"),
    ("consumptionDayBeforeYesterday.value", "consumptionDayBeforeYesterdayValue"),
    ("consumptionDayBeforeYesterday.validated", "consumptionDayBeforeYesterdayValidated"),
    ("consumptionDayBeforeYesterday.date", "consumptionDayBeforeYesterdayTimestamp"),
]

ATTRS_BASEINFORMATION_CALL = [
    ("hasSmartMeter", "hasSmartMeter"),
    ("isDataDeleted", "isDataDeleted"),
    ("dataDeletionTimestampUTC", "dataDeletionAt"),
    ("zaehlpunkt.zaehlpunktName", "name"),
    ("zaehlpunkt.zaehlpunktnummer", "zaehlpunkt"),
    ("zaehlpunkt.zaehlpunktAnlagentyp", "type"),
    ("zaehlpunkt.adresse", "address"),
    ("zaehlpunkt.postleitzahl", "zip"),
]

ATTRS_METERREADINGS_CALL = [
    ("meterReadings.0.value", "lastValue"),
    ("meterReadings.0.date", "lastReading"),
    ("meterReadings.0.validated", "lastValidated"),
    ("meterReadings.0.type", "lastType")
]

ATTRS_VERBRAUCH_CALL = [
    ("quarter-hour-opt-in", "optIn"),
    ("statistics.average", "consumptionAverage"),
    ("statistics.minimum", "consumptionMinimum"),
    ("statistics.maximum", "consumptionMaximum"),
    ("values", "values"),
]

ATTRS_HISTORIC_DATA = [
    ('obisCode', 'obisCode'),
    ('einheit', 'unitOfMeasurement'),
    ('messwerte', 'values'),
]
ATTRS_HISTORIC_MEASUREMENT = [
]
