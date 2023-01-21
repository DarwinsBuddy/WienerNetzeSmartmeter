'''
    component constants
'''
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
]

ATTRS_WELCOME_CALL = [
    ("zaehlpunkt.zaehlpunktName", "name"),
    ("zaehlpunkt.zaehlpunktnummer", "zaehlpunkt"),
    ("zaehlpunkt.zaehlpunktAnlagentyp", "type"),
    ("zaehlpunkt.adresse", "address"),
    ("zaehlpunkt.postleitzahl", "zip"),
    ("zaehlpunkt.meterReadings.0.value", "lastValue"),
    ("zaehlpunkt.meterReadings.0.date", "lastReading"),
    ("zaehlpunkt.consumptionYesterday.value", "consumptionYesterday"),
    ("zaehlpunkt.consumptionDayBeforeYesterday.value", "consumptionDayBeforeYesterday"),
]

ATTRS_VERBRAUCH_CALL = [
    ("quarter-hour-opt-in", "optIn"),
    ("statistics.average", "consumptionAverage"),
    ("statistics.minimum", "consumptionMinimum"),
    ("statistics.maximum", "consumptionMaximum"),
    ("values", "values"),
]
